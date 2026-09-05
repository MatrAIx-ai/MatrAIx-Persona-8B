"""Schedule survey/chat host-agent Harbor jobs as GKE Jobs.

Harbor ``environment.type`` stays ``host``. Artifacts merge into the same
``jobs/<job_name>/`` tree as local / Modal Jobs runs.
"""

from __future__ import annotations

import base64
import json
import os
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from backend.service.modal_host_job import (
    HARBOR_MODULE_COMMAND,
    MODAL_REMOTE_REPO,
    ModalHostJobResult,
    apply_live_overlay,
    merge_job_artifacts,
    modal_pythonpath,
    prepare_modal_job_config,
    rewrite_job_artifact_paths,
)
from matraix.gke_settings import (
    GKE_HOST_IMAGE_ENV,
    GKE_JOBS_PVC_ENV,
    ensure_gke_kubeconfig,
    gke_host_image,
    gke_namespace,
)

GKE_REMOTE_REPO = MODAL_REMOTE_REPO
_EXIT_MARKER = "/tmp/matraix-exit"
_ARTIFACT_TAR = "/tmp/matraix-job.tgz"
_LIVE_STATUS_REMOTE = "/tmp/matraix-live.json"
_LIVE_PUSH_ENV = "MATRIX_GKE_LIVE_PUSH_SEC"

# Stdlib-only watcher so the mosaic can tick before Harbor finishes packing.
_GKE_LIVE_WATCH_PY = (
    "import json, os, time\n"
    "from pathlib import Path\n"
    "job = os.environ.get('MATRIX_GKE_LIVE_JOB') or ''\n"
    "root = Path(os.environ.get('MATRIX_REPO_ROOT') or '/matraix') / 'jobs' / job\n"
    "dest = Path({live_path!r})\n"
    "exit_marker = Path({exit_path!r})\n"
    "markers = ('config.json', 'trial.log', 'persona_meta.json')\n"
    "try:\n"
    "    interval = float(os.environ.get({push_env!r}) or '5')\n"
    "except ValueError:\n"
    "    interval = 5.0\n"
    "interval = 5.0 if interval <= 0 else max(interval, 0.5)\n"
    "while True:\n"
    "    status = {{}}\n"
    "    if job and root.is_dir():\n"
    "        for trial in sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith('_')):\n"
    "            result = trial / 'result.json'\n"
    "            if result.is_file():\n"
    "                try:\n"
    "                    payload = json.loads(result.read_text())\n"
    "                except Exception:\n"
    "                    payload = None\n"
    "                if isinstance(payload, dict) and (payload.get('exception_info') or payload.get('error')):\n"
    "                    status[trial.name] = 'error'\n"
    "                else:\n"
    "                    status[trial.name] = 'done'\n"
    "            elif any((trial / name).is_file() for name in markers) or (trial / 'agent').is_dir():\n"
    "                status[trial.name] = 'running'\n"
    "            else:\n"
    "                status[trial.name] = 'pending'\n"
    "    dest.write_text(json.dumps(status, sort_keys=True) + '\\n')\n"
    "    if exit_marker.is_file():\n"
    "        break\n"
    "    time.sleep(interval)\n"
).format(live_path=_LIVE_STATUS_REMOTE, exit_path=_EXIT_MARKER, push_env=_LIVE_PUSH_ENV)


class GkeHostJobError(RuntimeError):
    """GKE host workers could not be scheduled or completed."""


@dataclass(frozen=True)
class GkeHostJobRequest:
    job_name: str
    config_yaml: str
    env: dict[str, str]
    secret_env: dict[str, str] = field(default_factory=dict)
    shard_key: str = ""
    live_jobs_dir: str = ""


class GkeHostJobRunner(Protocol):
    def run(self, request: GkeHostJobRequest) -> ModalHostJobResult: ...


def gke_job_name(job_name: str, shard_key: str = "") -> str:
    slug = "".join(ch.lower() if ch.isalnum() else "-" for ch in job_name).strip("-")
    base = "matraix-host-{}".format(slug[:40]).strip("-") or "matraix-host-job"
    extra = "".join(ch.lower() if ch.isalnum() else "-" for ch in shard_key).strip("-")
    if not extra:
        return base[:63]
    return "{}-{}".format(base[:55], extra)[:63]


def gke_host_worker_script(job_name: str) -> str:
    """Run Harbor, pack ``jobs/<name>/``, then stay up so the API can pull the tar."""
    harbor = " ".join(shlex.quote(part) for part in HARBOR_MODULE_COMMAND)
    job_q = shlex.quote(job_name)
    repo_q = shlex.quote(GKE_REMOTE_REPO)
    watch = shlex.quote(_GKE_LIVE_WATCH_PY)
    return (
        "set +e\n"
        "export MATRIX_GKE_LIVE_JOB={job}\n"
        "python -c {watch} &\n"
        "LIVE_PID=$!\n"
        "{harbor} --yes -c /config/job.yaml\n"
        "echo $? > {marker}\n"
        "wait \"$LIVE_PID\" 2>/dev/null || true\n"
        "if [ -d {repo}/jobs/{job} ]; then\n"
        "  tar czf {artifact} -C {repo}/jobs {job}\n"
        "fi\n"
        "sleep 3600\n"
    ).format(
        harbor=harbor,
        marker=_EXIT_MARKER,
        repo=repo_q,
        job=job_q,
        artifact=_ARTIFACT_TAR,
        watch=watch,
    )


def apply_gke_live_status(dest: Path, raw: bytes | str) -> dict[str, str]:
    """Merge a worker ``live_status.json`` blob into the orchestrator overlay."""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    try:
        loaded = json.loads(text)
    except Exception:
        return {}
    if not isinstance(loaded, dict):
        return {}
    status = {str(key): str(value) for key, value in loaded.items() if str(key)}
    if status:
        apply_live_overlay(dest, status)
    return status


def gke_live_dest(request: GkeHostJobRequest) -> Path | None:
    root = (request.live_jobs_dir or "").strip()
    if not root:
        return None
    dest = Path(root) / request.job_name
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def build_gke_job_manifest(
    request: GkeHostJobRequest,
    *,
    image: str,
    namespace: str,
    pvc_name: str | None = None,
) -> dict[str, Any]:
    env_vars = [
        {"name": key, "value": value}
        for key, value in {**request.env, **request.secret_env}.items()
        if value
    ]
    env_vars.append({"name": "PYTHONPATH", "value": modal_pythonpath(Path(GKE_REMOTE_REPO))})
    env_vars.append({"name": "MATRIX_REPO_ROOT", "value": GKE_REMOTE_REPO})
    volumes = [
        {"name": "config", "configMap": {"name": gke_job_name(request.job_name, request.shard_key) + "-cfg"}}
    ]
    mounts = [
        {"name": "config", "mountPath": "/config", "readOnly": True},
        {"name": "jobs", "mountPath": "{}/jobs".format(GKE_REMOTE_REPO)},
    ]
    if pvc_name:
        volumes.append({"name": "jobs", "persistentVolumeClaim": {"claimName": pvc_name}})
    else:
        volumes.append({"name": "jobs", "emptyDir": {}})
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": gke_job_name(request.job_name, request.shard_key),
            "namespace": namespace,
            "labels": {"app": "matraix-host-job", "matraix-job": request.job_name},
        },
        "spec": {
            "backoffLimit": 0,
            "template": {
                "metadata": {"labels": {"app": "matraix-host-job"}},
                "spec": {
                    "restartPolicy": "Never",
                    "containers": [
                        {
                            "name": "harbor",
                            "image": image,
                            "workingDir": GKE_REMOTE_REPO,
                            "command": ["/bin/sh", "-c"],
                            "args": [gke_host_worker_script(request.job_name)],
                            "env": env_vars,
                            "volumeMounts": mounts,
                            "resources": {
                                "requests": {"cpu": "1", "memory": "4Gi"},
                                "limits": {"cpu": "2", "memory": "8Gi"},
                            },
                        }
                    ],
                    "volumes": volumes,
                },
            },
        },
    }


class SdkGkeHostJobRunner:
    """Create a Kubernetes Job, wait for Harbor to finish, and pull ``jobs/<name>/``."""

    poll_sec: float = 3.0
    timeout_sec: float = 60 * 60

    def spawn(self, request: GkeHostJobRequest) -> tuple[str, Any]:
        ctx = self._connect(request)
        yaml_text = prepare_modal_job_config(request.config_yaml, job_name=request.job_name)
        config_map = ctx["client"].V1ConfigMap(
            metadata=ctx["client"].V1ObjectMeta(name=ctx["cfg_name"], namespace=ctx["namespace"]),
            data={"job.yaml": yaml_text},
        )
        pvc = (os.environ.get(GKE_JOBS_PVC_ENV) or "").strip() or None
        manifest = build_gke_job_manifest(
            request,
            image=ctx["image"],
            namespace=ctx["namespace"],
            pvc_name=pvc,
        )
        try:
            self._replace_config_map(ctx["core"], ctx["cfg_name"], ctx["namespace"], config_map)
            self._replace_job(ctx["batch"], ctx["name"], ctx["namespace"], manifest)
        except Exception as exc:  # noqa: BLE001
            raise GkeHostJobError(str(exc)) from exc
        return ctx["name"], None

    def wait(
        self,
        request: GkeHostJobRequest,
        *,
        call: Any | None = None,
        call_id: str = "",
    ) -> ModalHostJobResult:
        del call
        ctx = self._connect(request)
        name = (call_id or "").strip() or ctx["name"]
        cfg_name = name + "-cfg" if name == ctx["name"] else name + "-cfg"
        if name != ctx["name"]:
            cfg_name = name + "-cfg"
        try:
            from kubernetes import stream
        except ImportError as exc:
            raise GkeHostJobError(
                "computeFamily=gcp requires the kubernetes extra (pip install 'matraix[gke]')"
            ) from exc
        try:
            dest = gke_live_dest(request)
            pod, exit_code = self._wait_for_exit_marker(
                stream, ctx["core"], name, ctx["namespace"], dest=dest
            )
            artifact = self._read_artifact_tar(stream, ctx["core"], pod, ctx["namespace"])
        except GkeHostJobError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise GkeHostJobError(str(exc)) from exc
        finally:
            self._delete_job(ctx["batch"], ctx["core"], name, cfg_name, ctx["namespace"])
        error = None if exit_code == 0 else "GKE host workers exited with code {}".format(exit_code)
        if exit_code == 0 and not artifact:
            raise GkeHostJobError(
                "GKE host workers finished without returning jobs/{}/ artifacts".format(
                    request.job_name
                )
            )
        return ModalHostJobResult(
            exit_code=exit_code,
            artifact_tar=artifact,
            error=error,
            volume_path=request.job_name,
        )

    def run(self, request: GkeHostJobRequest) -> ModalHostJobResult:
        call_id, _ = self.spawn(request)
        return self.wait(request, call_id=call_id)

    def _connect(self, request: GkeHostJobRequest) -> dict[str, Any]:
        image = gke_host_image()
        if not image:
            raise GkeHostJobError(
                "computeFamily=gcp for survey/chat requires {} "
                "(container image with MatrAIx + Harbor)".format(GKE_HOST_IMAGE_ENV)
            )
        try:
            from kubernetes import client, config
        except ImportError as exc:
            raise GkeHostJobError(
                "computeFamily=gcp requires the kubernetes extra (pip install 'matraix[gke]')"
            ) from exc
        self._load_kube_config(config)
        namespace = gke_namespace()
        name = gke_job_name(request.job_name, request.shard_key)
        return {
            "client": client,
            "batch": client.BatchV1Api(),
            "core": client.CoreV1Api(),
            "namespace": namespace,
            "name": name,
            "cfg_name": name + "-cfg",
            "image": image,
        }

    def _load_kube_config(self, config: Any) -> None:
        try:
            config.load_incluster_config()
            return
        except Exception:
            pass
        try:
            config.load_kube_config()
            return
        except Exception:
            pass
        ensure_gke_kubeconfig()
        try:
            config.load_kube_config()
        except Exception as exc:
            raise GkeHostJobError(
                "computeFamily=gcp (GKE host workers) requires a kubeconfig "
                "(KUBECONFIG or ~/.kube/config) or in-cluster credentials"
            ) from exc

    def _replace_config_map(self, core: Any, name: str, namespace: str, body: Any) -> None:
        try:
            core.delete_namespaced_config_map(name, namespace)
        except Exception:
            pass
        core.create_namespaced_config_map(namespace, body)

    def _replace_job(self, batch: Any, name: str, namespace: str, manifest: dict[str, Any]) -> None:
        try:
            batch.delete_namespaced_job(name, namespace, propagation_policy="Background")
        except Exception:
            pass
        batch.create_namespaced_job(namespace, manifest)

    def _delete_job(
        self,
        batch: Any,
        core: Any,
        job_name: str,
        cfg_name: str,
        namespace: str,
    ) -> None:
        try:
            batch.delete_namespaced_job(job_name, namespace, propagation_policy="Background")
        except Exception:
            pass
        try:
            core.delete_namespaced_config_map(cfg_name, namespace)
        except Exception:
            pass

    def _wait_for_exit_marker(
        self,
        stream: Any,
        core: Any,
        job_name: str,
        namespace: str,
        *,
        dest: Path | None = None,
    ) -> tuple[str, int]:
        deadline = time.time() + self.timeout_sec
        while time.time() < deadline:
            pod, phase = self._job_pod(core, job_name, namespace)
            if phase == "Failed":
                raise GkeHostJobError("GKE Job {} failed".format(job_name))
            if pod and phase == "Running":
                if dest is not None:
                    try:
                        self._pull_live_progress(stream, core, pod, namespace, dest)
                    except Exception:
                        pass
                try:
                    raw = self._exec(stream, core, pod, namespace, ["cat", _EXIT_MARKER])
                    text = raw.decode("utf-8", errors="replace").strip()
                    if text.isdigit():
                        return pod, int(text)
                except Exception:
                    pass
            time.sleep(self.poll_sec)
        raise GkeHostJobError("GKE Job {} timed out".format(job_name))

    def _pull_live_progress(
        self,
        stream: Any,
        core: Any,
        pod: str,
        namespace: str,
        dest: Path,
    ) -> None:
        raw = self._exec(stream, core, pod, namespace, ["cat", _LIVE_STATUS_REMOTE])
        apply_gke_live_status(dest, raw)

    def _job_pod(self, core: Any, job_name: str, namespace: str) -> tuple[str | None, str]:
        pods = core.list_namespaced_pod(
            namespace,
            label_selector="job-name={}".format(job_name),
        )
        items = list(getattr(pods, "items", []) or [])
        if not items:
            return None, ""
        pod = items[0]
        phase = str(getattr(getattr(pod, "status", None), "phase", "") or "")
        return pod.metadata.name, phase

    def _read_artifact_tar(
        self,
        stream: Any,
        core: Any,
        pod: str,
        namespace: str,
    ) -> bytes | None:
        try:
            encoded = self._exec(
                stream,
                core,
                pod,
                namespace,
                ["base64", _ARTIFACT_TAR],
            )
        except Exception:
            return None
        text = encoded.decode("ascii", errors="ignore").strip()
        if not text:
            return None
        try:
            return base64.b64decode(text)
        except Exception:
            return None

    def _exec(
        self,
        stream: Any,
        core: Any,
        pod: str,
        namespace: str,
        command: list[str],
    ) -> bytes:
        resp = stream.stream(
            core.connect_get_namespaced_pod_exec,
            pod,
            namespace,
            command=command,
            stderr=True,
            stdin=False,
            stdout=True,
            tty=False,
            _preload_content=False,
        )
        chunks: list[bytes] = []
        try:
            while resp.is_open():
                resp.update(timeout=60)
                if resp.peek_stdout():
                    data = resp.read_stdout()
                    if isinstance(data, bytes):
                        chunks.append(data)
                    else:
                        chunks.append(str(data).encode("latin1"))
        finally:
            resp.close()
        return b"".join(chunks)


def default_gke_host_job_runner() -> GkeHostJobRunner:
    return SdkGkeHostJobRunner()


def materialize_gke_artifacts(
    result: ModalHostJobResult,
    *,
    jobs_dir: Path,
    job_name: str,
) -> Path:
    dest = jobs_dir / job_name
    dest.mkdir(parents=True, exist_ok=True)
    if result.artifact_tar:
        merge_job_artifacts(
            result.artifact_tar,
            jobs_dir=jobs_dir,
            job_name=job_name,
            remote_repo=GKE_REMOTE_REPO,
        )
    else:
        rewrite_job_artifact_paths(
            dest,
            remote_repo=GKE_REMOTE_REPO,
            local_job_dir=dest,
            job_name=job_name,
        )
        if not any(path.name != "compute.json" for path in dest.iterdir()):
            raise GkeHostJobError(
                "GKE host workers finished without returning jobs/{}/ artifacts".format(
                    job_name
                )
            )
    return dest
