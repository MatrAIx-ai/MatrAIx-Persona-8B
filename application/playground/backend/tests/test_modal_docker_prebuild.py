"""Tests for Modal Docker image prebuild / Volume cache."""

from __future__ import annotations

from pathlib import Path

from backend.service.modal_docker_prebuild import (
    DockerCli,
    docker_context_digest,
    harbor_environment_type,
    harbor_main_image_name,
    job_task_dir,
    patch_task_toml_docker_image,
    prebuilt_image_tag,
    prepare_docker_environment_for_job,
    task_short_name,
)


class _FakeDocker(DockerCli):
    def __init__(self) -> None:
        self.images: set[str] = set()
        self.built: list[tuple[str, str]] = []
        self.loaded: list[str] = []
        self.saved: list[tuple[str, str]] = []

    def image_exists(self, tag: str) -> bool:
        return tag in self.images

    def build(self, context: Path, tag: str) -> None:
        self.built.append((str(context), tag))
        self.images.add(tag)

    def tag(self, source: str, dest: str) -> None:
        if source not in self.images:
            raise RuntimeError("missing {}".format(source))
        self.images.add(dest)

    def save(self, tag: str, dest: Path) -> None:
        dest.write_bytes(b"tar:" + tag.encode("utf-8"))
        self.saved.append((tag, str(dest)))

    def load(self, archive: Path) -> None:
        payload = archive.read_bytes().decode("utf-8")
        tag = payload.split("tar:", 1)[-1]
        self.images.add(tag)
        self.loaded.append(str(archive))


def _web_repo(tmp_path: Path) -> tuple[Path, Path]:
    env = tmp_path / "environment" / "task-environments" / "application" / "shared-web-playwright"
    env.mkdir(parents=True)
    (env / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    task = tmp_path / "application" / "tasks" / "example-web"
    task.mkdir(parents=True)
    (task / "task.toml").write_text(
        '[task]\nname = "application/playwright-quote-choice"\n'
        '[environment]\ndefinition = "application/shared-web-playwright"\n',
        encoding="utf-8",
    )
    return tmp_path, task


def test_digest_ignores_readme_when_dockerignore_allowlists_dockerfile(
    tmp_path: Path,
) -> None:
    env = tmp_path / "env"
    env.mkdir()
    (env / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (env / ".dockerignore").write_text("*\n!Dockerfile\n", encoding="utf-8")
    first = docker_context_digest(env)
    (env / "README.md").write_text("noise\n", encoding="utf-8")
    assert docker_context_digest(env) == first
    (env / "Dockerfile").write_text("FROM debian\n", encoding="utf-8")
    assert docker_context_digest(env) != first


def test_prepare_builds_once_then_loads_from_cache(tmp_path: Path) -> None:
    repo, task = _web_repo(tmp_path)
    yaml_text = (
        "environment:\n  type: docker\n"
        "tasks:\n  - path: application/tasks/example-web\n"
    )
    cache = tmp_path / "cache"
    docker = _FakeDocker()
    tag = prepare_docker_environment_for_job(
        yaml_text,
        repo_root=repo,
        cache_dir=cache,
        docker=docker,
        start_daemon=False,
    )
    assert tag == prebuilt_image_tag(
        docker_context_digest(
            repo / "environment" / "task-environments" / "application" / "shared-web-playwright"
        )
    )
    assert docker.built
    harbor = harbor_main_image_name(task_short_name(task))
    assert harbor in docker.images
    assert tag in docker.images
    toml = (task / "task.toml").read_text(encoding="utf-8")
    assert 'docker_image = "{}"'.format(tag) in toml

    docker.images.clear()
    docker.built.clear()
    again = prepare_docker_environment_for_job(
        yaml_text,
        repo_root=repo,
        cache_dir=cache,
        docker=docker,
        start_daemon=False,
    )
    assert again == tag
    assert not docker.built
    assert docker.loaded
    assert harbor in docker.images


def test_host_jobs_skip_prebuild(tmp_path: Path) -> None:
    assert harbor_environment_type("environment:\n  type: host\n") == "host"
    assert (
        prepare_docker_environment_for_job(
            "environment:\n  type: host\n",
            repo_root=tmp_path,
            start_daemon=False,
        )
        is None
    )


def test_docker_jobs_use_sandbox_not_function() -> None:
    from backend.service.modal_host_job import (
        modal_function_name_for_config,
        modal_uses_docker_sandbox,
    )

    assert modal_uses_docker_sandbox("environment:\n  type: docker\n")
    assert not modal_uses_docker_sandbox("environment:\n  type: host\n")
    assert (
        modal_function_name_for_config("environment:\n  type: host\n")
        == "harbor_host_job"
    )


def test_job_task_dir_and_patch(tmp_path: Path) -> None:
    repo, task = _web_repo(tmp_path)
    found = job_task_dir(
        "tasks:\n  - path: application/tasks/example-web\n",
        repo_root=repo,
    )
    assert found == task
    patch_task_toml_docker_image(task / "task.toml", "matraix-prebuilt:abc")
    assert 'docker_image = "matraix-prebuilt:abc"' in (task / "task.toml").read_text(
        encoding="utf-8"
    )
