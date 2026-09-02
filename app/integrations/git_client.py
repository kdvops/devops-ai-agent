"""Controlled Git operations for repositories inside the workspace."""
from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlparse


REPO_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,180}$")


def _validate_relative_path(workspace_root: Path, repo_path: str) -> Path:
    if not isinstance(repo_path, str) or not REPO_PATH.fullmatch(repo_path):
        raise ValueError("La ruta del repositorio no es válida.")
    root = workspace_root.resolve()
    candidate = (root / repo_path).resolve()
    if candidate == root or root not in candidate.parents:
        raise ValueError("El repositorio debe permanecer dentro del workspace.")
    return candidate


def _validate_branch(branch: str | None) -> str | None:
    if branch is not None and (not isinstance(branch, str) or not BRANCH.fullmatch(branch)):
        raise ValueError("El nombre de la rama no es válido.")
    return branch


def _validate_remote(url: str, allowed_hosts: set[str]) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or not parsed.hostname:
        raise ValueError("Solo se permiten URLs HTTPS sin credenciales embebidas.")
    host = parsed.hostname.lower().rstrip(".")
    if host not in allowed_hosts:
        raise ValueError("El host Git no está autorizado.")
    if not parsed.path or parsed.path == "/" or ".." in parsed.path.split("/"):
        raise ValueError("La ruta remota no es válida.")
    return url


def _run_git(arguments: list[str], cwd: Path | None, timeout: int, extra_env: dict[str, str] | None = None) -> str:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    if extra_env:
        env.update(extra_env)
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git no está disponible en el contenedor.") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("La operación Git excedió el tiempo permitido.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail[:2_000] or "Git rechazó la operación.")
    return (result.stdout or result.stderr).strip()[:50_000]


def clone(workspace_root: Path, url: str, repo_path: str, branch: str | None, allowed_hosts: set[str], timeout: int) -> dict:
    remote = _validate_remote(url, allowed_hosts)
    branch = _validate_branch(branch)
    destination = _validate_relative_path(workspace_root, repo_path)
    if destination.exists():
        raise ValueError("La ruta destino ya existe; usa otra ruta para evitar sobrescribir trabajo.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    args = ["clone", "--", remote, str(destination)] if branch is None else ["clone", "--branch", branch, "--", remote, str(destination)]
    extra_env, askpass = _askpass_environment()
    try:
        output = _run_git(args, None, timeout, extra_env)
    except Exception:
        destination.rmdir() if destination.exists() and not any(destination.iterdir()) else None
        raise
    finally:
        if askpass:
            askpass.unlink(missing_ok=True)
    return {"repo_path": repo_path, "branch": branch, "output": output or "Repositorio clonado."}


def _repo(workspace_root: Path, repo_path: str) -> Path:
    candidate = _validate_relative_path(workspace_root, repo_path)
    if not (candidate / ".git").exists():
        raise ValueError("La ruta no contiene un repositorio Git válido.")
    return candidate


def status(workspace_root: Path, repo_path: str, timeout: int) -> dict:
    repo = _repo(workspace_root, repo_path)
    return {"repo_path": repo_path, "branch": _run_git(["branch", "--show-current"], repo, timeout), "status": _run_git(["status", "--short"], repo, timeout)}


def diff(workspace_root: Path, repo_path: str, timeout: int) -> dict:
    repo = _repo(workspace_root, repo_path)
    return {"repo_path": repo_path, "diff": _run_git(["diff", "--no-ext-diff", "--", "."], repo, timeout)}


def _askpass_environment() -> tuple[dict[str, str], Path | None]:
    # PAT, API key, password and the legacy token are all Git HTTPS passwords.
    password = next((os.getenv(name) for name in ("GIT_PAT", "GIT_API_KEY", "GIT_PASSWORD", "GIT_TOKEN") if os.getenv(name)), None)
    if not password:
        return {}, None
    descriptor, filename = tempfile.mkstemp(prefix="git-askpass-", suffix=".sh")
    os.close(descriptor)
    askpass = Path(filename)
    askpass.write_text("#!/bin/sh\ncase \"$1\" in *Username*) printf '%s\\n' \"${GIT_USERNAME:-x-access-token}\" ;; *) printf '%s\\n' \"$GIT_TOKEN\" ;; esac\n", encoding="utf-8")
    askpass.chmod(0o700)
    return {"GIT_ASKPASS": str(askpass), "GIT_USERNAME": os.getenv("GIT_USERNAME", "x-access-token"), "GIT_TOKEN": password}, askpass


def commit(workspace_root: Path, repo_path: str, message: str, timeout: int) -> dict:
    if not isinstance(message, str) or not message.strip() or len(message) > 200 or "\n" in message or "\r" in message:
        raise ValueError("El mensaje de commit debe ser una sola línea de hasta 200 caracteres.")
    repo = _repo(workspace_root, repo_path)
    _run_git(["add", "--all", "--", "."], repo, timeout)
    identity = {
        "GIT_AUTHOR_NAME": os.getenv("GIT_COMMIT_NAME", "DevOps AI Agent"),
        "GIT_AUTHOR_EMAIL": os.getenv("GIT_COMMIT_EMAIL", "devops-ai-agent@local.invalid"),
        "GIT_COMMITTER_NAME": os.getenv("GIT_COMMIT_NAME", "DevOps AI Agent"),
        "GIT_COMMITTER_EMAIL": os.getenv("GIT_COMMIT_EMAIL", "devops-ai-agent@local.invalid"),
    }
    output = _run_git(["commit", "--no-verify", "-m", message.strip()], repo, timeout, identity)
    return {"repo_path": repo_path, "branch": _run_git(["branch", "--show-current"], repo, timeout), "output": output}


def push(workspace_root: Path, repo_path: str, branch: str | None, timeout: int) -> dict:
    repo = _repo(workspace_root, repo_path)
    branch = _validate_branch(branch) or _run_git(["branch", "--show-current"], repo, timeout)
    if not branch:
        raise ValueError("No hay una rama activa para hacer push.")
    extra_env, askpass = _askpass_environment()
    try:
        output = _run_git(["push", "origin", branch], repo, timeout, extra_env)
    finally:
        if askpass:
            askpass.unlink(missing_ok=True)
    return {"repo_path": repo_path, "branch": branch, "output": output or "Push completado."}
