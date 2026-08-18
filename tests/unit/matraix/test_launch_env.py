import os
from pathlib import Path

import pytest

from matraix.launch_env import (
    build_launch_env,
    find_repo_root,
    merge_pythonpath,
    normalize_persona_language,
    normalize_persona_language_source,
    required_pythonpath_entries,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("en", "en"),
        ("en-US", "en"),
        ("ko", "ko"),
        ("ko-KR", "ko"),
        ("zh", "zh-Hans"),
        ("zh-CN", "zh-Hans"),
        ("zh-Hans-CN", "zh-Hans"),
        ("zh-Hant", "zh-Hant"),
        ("zh-TW", "zh-Hant"),
        ("ja", "ja"),
        ("ja-JP", "ja"),
        ("pt", "pt-BR"),
        ("pt-BR", "pt-BR"),
        ("es", "es"),
        ("es-ES", "es"),
        ("es-419", "es"),
    ],
)
def test_normalize_persona_language_uses_canonical_tags(value: str, expected: str) -> None:
    assert normalize_persona_language(value) == expected


@pytest.mark.parametrize("source", ["ui", "env", "default", "cli"])
def test_normalize_persona_language_source_rejects_internal_or_legacy_sources(
    source: str,
) -> None:
    with pytest.raises(ValueError, match="follow_ui, explicit"):
        normalize_persona_language_source(source)


def test_required_entries_cover_all_monorepo_import_roots(tmp_path: Path) -> None:
    entries = required_pythonpath_entries(tmp_path)
    assert entries == [
        str(tmp_path),
        str(tmp_path / "src"),
        str(tmp_path / "environment" / "runtime"),
        str(tmp_path / "environment" / "agents"),
        str(tmp_path / "packages" / "playground" / "src"),
        str(tmp_path / "application" / "playground"),
    ]


def test_merge_pythonpath_prepends_and_dedupes(tmp_path: Path) -> None:
    existing = os.pathsep.join(["/custom/site", str(tmp_path / "src")])
    merged = merge_pythonpath(existing, tmp_path).split(os.pathsep)
    assert merged[0] == str(tmp_path)
    assert merged.count(str(tmp_path / "src")) == 1
    assert "/custom/site" in merged


def test_merge_pythonpath_handles_empty_existing(tmp_path: Path) -> None:
    merged = merge_pythonpath(None, tmp_path)
    assert merged.split(os.pathsep) == required_pythonpath_entries(tmp_path)


def test_build_launch_env_inherits_process_env(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("MATRAIX_TEST_MARKER", "yes")
    monkeypatch.setenv("PYTHONPATH", "/custom/site")
    env = build_launch_env(tmp_path)
    assert env["MATRAIX_TEST_MARKER"] == "yes"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path)
    assert "/custom/site" in env["PYTHONPATH"].split(os.pathsep)


def test_build_launch_env_isolated_base_for_remote(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SECRET_API_KEY", "do-not-leak")
    env = build_launch_env(tmp_path, base_env={})
    assert env == {"PYTHONPATH": os.pathsep.join(required_pythonpath_entries(tmp_path))}


def test_find_repo_root_walks_up_to_marker(tmp_path: Path) -> None:
    root = tmp_path / "checkout"
    (root / "environment" / "runtime" / "harbor").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
    nested = root / "configs" / "jobs" / "application-task-job-recipe"
    nested.mkdir(parents=True)
    assert find_repo_root(nested) == root


def test_find_repo_root_falls_back_to_package_checkout(tmp_path: Path) -> None:
    # No markers anywhere above tmp_path: fall back to the checkout that
    # provides matraix.launch_env itself (this repository).
    root = find_repo_root(tmp_path)
    assert (root / "environment" / "runtime" / "harbor").is_dir()
