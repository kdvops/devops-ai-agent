"""Controlled HTTP, SSH and browser integrations for the DevOps agent."""
from __future__ import annotations

import os
import re
import socket
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_RESPONSE_BYTES = 50_000
SAFE_SSH_COMMAND = re.compile(r"^[A-Za-z0-9_./:@%+=,\-\s]+$")


def _allowed_hosts(name: str) -> set[str]:
    return {item.strip().lower() for item in os.getenv(name, "").split(",") if item.strip()}


def _validate_url(url: str, setting: str) -> tuple[str, str]:
    if not isinstance(url, str) or len(url) > 2_048:
        raise ValueError("La URL no es válida.")
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValueError("Solo se permiten URLs HTTP(S) sin credenciales embebidas.")
    allowed = _allowed_hosts(setting)
    if "*" not in allowed and host not in allowed:
        raise ValueError(f"El host no está autorizado. Configura {setting}.")
    return url, host


def _bounded(text: bytes) -> str:
    return text[:MAX_RESPONSE_BYTES].decode("utf-8", errors="replace")


class _AllowlistedRedirects(HTTPRedirectHandler):
    def redirect_request(self, request: Request, fp: Any, code: int, msg: str, new_url: str) -> Request | None:
        _validate_url(new_url, "EXTERNAL_HTTP_ALLOWED_HOSTS")
        return super().redirect_request(request, fp, code, msg, new_url)


def http_request(arguments: dict[str, Any], timeout: int) -> dict[str, Any]:
    url, _ = _validate_url(arguments.get("url", ""), "EXTERNAL_HTTP_ALLOWED_HOSTS")
    method = arguments.get("method", "GET")
    if method not in {"GET", "HEAD"}:
        raise ValueError("http_request solo admite GET o HEAD; no modifica servicios remotos.")
    request = Request(url, method=method, headers={"User-Agent": "devops-ai-agent/0.3"})
    try:
        with build_opener(_AllowlistedRedirects()).open(request, timeout=timeout) as response:
            body = b"" if method == "HEAD" else response.read(MAX_RESPONSE_BYTES + 1)
            return {
                "url": response.geturl(),
                "status": response.status,
                "content_type": response.headers.get("content-type"),
                "truncated": len(body) > MAX_RESPONSE_BYTES,
                "body": _bounded(body),
            }
    except HTTPError as exc:
        return {"url": url, "status": exc.code, "body": _bounded(exc.read(MAX_RESPONSE_BYTES + 1)), "error": str(exc.reason)}
    except (URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"No se pudo consultar la URL: {exc}") from exc


def _validate_ssh_command(command: str) -> str:
    if not isinstance(command, str) or not command.strip() or len(command) > 500 or not SAFE_SSH_COMMAND.fullmatch(command):
        raise ValueError("El comando SSH contiene caracteres no permitidos o es demasiado largo.")
    normalized = command.strip()
    allowed = [item.strip() for item in os.getenv("SSH_ALLOWED_COMMANDS", "uname,uptime,hostname,whoami,df,free,systemctl status,docker ps,kubectl get,kubectl describe").split(",") if item.strip()]
    if not any(normalized == prefix or normalized.startswith(prefix + " ") for prefix in allowed):
        raise ValueError("El comando SSH no está autorizado por SSH_ALLOWED_COMMANDS.")
    return normalized


def ssh_command(arguments: dict[str, Any], timeout: int) -> dict[str, Any]:
    host = str(arguments.get("host", "")).lower().rstrip(".")
    allowed = _allowed_hosts("SSH_ALLOWED_HOSTS")
    if not host or ("*" not in allowed and host not in allowed):
        raise ValueError("El host SSH no está autorizado. Configura SSH_ALLOWED_HOSTS.")
    try:
        port = int(arguments.get("port", os.getenv("SSH_PORT", "22")))
    except (TypeError, ValueError) as exc:
        raise ValueError("El puerto SSH no es válido.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("El puerto SSH no es válido.")
    command = _validate_ssh_command(arguments.get("command", ""))
    username = str(arguments.get("username") or os.getenv("SSH_USERNAME", ""))
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", username):
        raise ValueError("El usuario SSH no es válido.")
    try:
        import paramiko
    except ImportError as exc:
        raise RuntimeError("La integración SSH no está instalada en el contenedor.") from exc

    client = paramiko.SSHClient()
    known_hosts = os.getenv("SSH_KNOWN_HOSTS", "")
    if known_hosts and Path(known_hosts).is_file():
        client.load_host_keys(known_hosts)
    if os.getenv("SSH_STRICT_HOST_KEY_CHECKING", "true").lower() == "true":
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
    else:
        client.set_missing_host_key_policy(paramiko.WarningPolicy())
    try:
        client.connect(
            hostname=host,
            port=port,
            username=username,
            key_filename=os.getenv("SSH_PRIVATE_KEY_PATH") or None,
            password=os.getenv("SSH_PASSWORD") or None,
            timeout=timeout,
            banner_timeout=timeout,
            auth_timeout=timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        _, stdout, stderr = client.exec_command(command, timeout=timeout)
        output, error = stdout.read(MAX_RESPONSE_BYTES + 1), stderr.read(MAX_RESPONSE_BYTES + 1)
        return {"host": host, "command": command, "exit_code": stdout.channel.recv_exit_status(), "stdout": _bounded(output), "stderr": _bounded(error)}
    except Exception as exc:
        raise RuntimeError(f"La conexión SSH no pudo completarse: {type(exc).__name__}.") from exc
    finally:
        client.close()


def browser_inspect(arguments: dict[str, Any], timeout: int) -> dict[str, Any]:
    url, _ = _validate_url(arguments.get("url", ""), "BROWSER_ALLOWED_HOSTS")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright no está instalado en el contenedor.") from exc
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
            try:
                page = browser.new_page()
                response = page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1_000)
                selector = arguments.get("selector")
                if selector and (not isinstance(selector, str) or len(selector) > 300):
                    raise ValueError("El selector no es válido.")
                content = page.locator(selector).inner_text() if selector else page.locator("body").inner_text()
                return {"url": page.url, "status": response.status if response else None, "title": page.title(), "text": content[:MAX_RESPONSE_BYTES], "selector": selector}
            finally:
                browser.close()
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError(f"La inspección Playwright no pudo completarse: {type(exc).__name__}.") from exc
