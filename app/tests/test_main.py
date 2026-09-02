from pathlib import Path

import pytest
from fastapi import HTTPException

import main


def test_rejects_workspace_traversal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.settings, "workspace_root", tmp_path)
    with pytest.raises(HTTPException) as error:
        main.safe_workspace_path("../secret")
    assert error.value.status_code == 403


def test_rejects_unapproved_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(main.settings, "allowed_namespaces", {"devops-ai"})
    with pytest.raises(HTTPException) as error:
        main.validate_namespace("production")
    assert error.value.status_code == 403


def test_write_action_requires_confirmation() -> None:
    assert main.requires_confirmation("write_file")
    assert not main.requires_confirmation("list_pods")


def test_git_state_changes_require_confirmation() -> None:
    assert main.requires_confirmation("git_clone")
    assert main.requires_confirmation("git_commit")
    assert main.requires_confirmation("git_push")
    assert not main.requires_confirmation("git_status")
    assert not main.requires_confirmation("git_diff")


def test_git_remote_rejects_embedded_credentials() -> None:
    from integrations.git_client import _validate_remote

    with pytest.raises(ValueError):
        _validate_remote("https://user:token@github.com/acme/app.git", {"github.com"})


def test_git_remote_requires_allowed_host() -> None:
    from integrations.git_client import _validate_remote

    with pytest.raises(ValueError):
        _validate_remote("https://evil.example/acme/app.git", {"github.com"})
