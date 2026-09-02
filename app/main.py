"""Controlled Kubernetes operations. User input is never passed to a shell."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Literal

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
import yaml

APP_DIR = Path(__file__).resolve().parent
RESOURCE_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
logger = logging.getLogger("devops_ai.audit")
logging.basicConfig(level=os.getenv("AUDIT_LOG_LEVEL", "INFO"), format="%(message)s")


class Settings(BaseModel):
    # Docker and Kubernetes set /workspace; a local clone stays self-contained.
    workspace_root: Path = Path(os.getenv("WORKSPACE_ROOT", str(APP_DIR / "workspace")))
    allowed_namespaces: set[str] = Field(default_factory=lambda: {x.strip() for x in os.getenv("ALLOWED_NAMESPACES", "default").split(",") if x.strip()})
    kubernetes_read_only: bool = os.getenv("KUBERNETES_READ_ONLY", "true").lower() == "true"
    max_tool_runtime_seconds: int = int(os.getenv("MAX_TOOL_RUNTIME_SECONDS", "15"))
    proposal_ttl_seconds: int = int(os.getenv("PROPOSAL_TTL_SECONDS", "300"))


settings = Settings()
settings.workspace_root.mkdir(parents=True, exist_ok=True)
proposals: dict[str, dict[str, Any]] = {}
proposal_lock = Lock()


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12_000)
    namespace: str | None = Field(default=None, max_length=63)


class ActionRequest(BaseModel):
    tool: Literal["cluster_status", "list_pods", "get_workload", "get_pod_logs", "list_files", "read_file", "write_file", "apply_kubernetes_manifest"]
    arguments: dict[str, Any] = Field(default_factory=dict)


class ConfirmationRequest(BaseModel):
    proposal_id: str = Field(min_length=1, max_length=64)
    approved: bool


app = FastAPI(title="DevOps AI Agent", version="0.2.0")


def audit(event: str, correlation_id: str, user: str, **data: Any) -> None:
    """Content is deliberately excluded because manifests can contain secrets."""
    logger.info(json.dumps({"event": event, "correlation_id": correlation_id, "user": user, **data}, default=str))


def current_user(x_user: str | None) -> str:
    if not x_user or not re.fullmatch(r"[A-Za-z0-9_.@-]{1,128}", x_user):
        raise HTTPException(401, "Se requiere un encabezado X-User válido.")
    return x_user


def validate_namespace(namespace: str | None) -> str:
    selected = namespace or "default"
    if not RESOURCE_NAME.fullmatch(selected) or selected not in settings.allowed_namespaces:
        raise HTTPException(403, "El namespace solicitado no está autorizado.")
    return selected


def validate_name(value: str, label: str) -> str:
    if not isinstance(value, str) or not RESOURCE_NAME.fullmatch(value):
        raise HTTPException(422, f"{label} no es un nombre Kubernetes válido.")
    return value


def safe_workspace_path(relative_path: str) -> Path:
    if not isinstance(relative_path, str) or not relative_path.strip():
        raise HTTPException(422, "La ruta es obligatoria.")
    root = settings.workspace_root.resolve()
    candidate = (root / relative_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(403, "La ruta debe permanecer dentro del workspace autorizado.")
    return candidate


def validate_manifest(manifest: str) -> None:
    """Only accept namespaced, low-risk resources in an allowed namespace."""
    try:
        documents = [doc for doc in yaml.safe_load_all(manifest) if doc]
    except yaml.YAMLError as exc:
        raise HTTPException(422, "El manifiesto YAML no es válido.") from exc
    if not documents:
        raise HTTPException(422, "El manifiesto no contiene recursos.")
    allowed_kinds = {"configmap", "service", "deployment", "statefulset", "daemonset"}
    for document in documents:
        if not isinstance(document, dict) or document.get("kind", "").lower() not in allowed_kinds:
            raise HTTPException(403, "El manifiesto contiene un tipo de recurso no permitido.")
        metadata = document.get("metadata", {})
        if not isinstance(metadata, dict):
            raise HTTPException(422, "Los metadatos del manifiesto no son válidos.")
        validate_namespace(metadata.get("namespace"))


def kubectl(arguments: list[str]) -> dict[str, Any]:
    command = ["kubectl", f"--request-timeout={settings.max_tool_runtime_seconds}s", *arguments]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=settings.max_tool_runtime_seconds + 2, check=False)
    except FileNotFoundError as exc:
        raise HTTPException(503, "kubectl no está disponible en el contenedor.") from exc
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(504, "La operación Kubernetes excedió el tiempo permitido.") from exc
    if result.returncode:
        raise HTTPException(502, "Kubernetes rechazó la operación o la identidad no tiene permisos.")
    output = result.stdout.strip()
    try:
        return {"data": json.loads(output)}
    except json.JSONDecodeError:
        return {"data": output[:50_000]}


def execute(tool: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if tool == "cluster_status":
        return kubectl(["get", "nodes", "-o", "json"])
    if tool == "list_pods":
        return kubectl(["get", "pods", "-n", validate_namespace(arguments.get("namespace")), "-o", "json"])
    if tool == "get_workload":
        kind = arguments.get("kind", "deployment").lower()
        if kind not in {"deployment", "statefulset", "daemonset"}:
            raise HTTPException(422, "Tipo de workload no permitido.")
        return kubectl(["get", kind, validate_name(arguments.get("name", ""), "El nombre"), "-n", validate_namespace(arguments.get("namespace")), "-o", "json"])
    if tool == "get_pod_logs":
        command = ["logs", validate_name(arguments.get("pod", ""), "El pod"), "-n", validate_namespace(arguments.get("namespace")), "--tail=200"]
        if arguments.get("container"):
            command.extend(["-c", validate_name(arguments["container"], "El contenedor")])
        return kubectl(command)
    if tool == "list_files":
        directory = safe_workspace_path(arguments.get("path", "."))
        if not directory.is_dir():
            raise HTTPException(404, "El directorio no existe.")
        return {"files": [str(p.relative_to(settings.workspace_root)) for p in directory.iterdir()][:500]}
    if tool == "read_file":
        target = safe_workspace_path(arguments.get("path", ""))
        if not target.is_file():
            raise HTTPException(404, "El archivo no existe.")
        if target.stat().st_size > 256_000:
            raise HTTPException(413, "El archivo supera el tamaño máximo permitido.")
        return {"path": str(target.relative_to(settings.workspace_root)), "content": target.read_text(encoding="utf-8")}
    if tool == "write_file":
        target, content = safe_workspace_path(arguments.get("path", "")), arguments.get("content")
        if not isinstance(content, str) or len(content) > 256_000:
            raise HTTPException(422, "El contenido no es válido o supera el tamaño máximo.")
        target.parent.mkdir(parents=True, exist_ok=True)
        previous = target.read_bytes() if target.exists() else b""
        target.write_text(content, encoding="utf-8")
        return {"path": str(target.relative_to(settings.workspace_root)), "previous_sha256": hashlib.sha256(previous).hexdigest(), "sha256": hashlib.sha256(content.encode()).hexdigest()}
    if tool == "apply_kubernetes_manifest":
        if settings.kubernetes_read_only:
            raise HTTPException(403, "Los cambios Kubernetes están desactivados: KUBERNETES_READ_ONLY=true.")
        manifest = arguments.get("manifest")
        if not isinstance(manifest, str) or not manifest.strip() or len(manifest) > 256_000:
            raise HTTPException(422, "El manifiesto no es válido o supera el tamaño máximo.")
        validate_manifest(manifest)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", encoding="utf-8", delete=False) as handle:
            handle.write(manifest)
            manifest_path = handle.name
        try:
            kubectl(["apply", "--dry-run=server", "-f", manifest_path])
            return kubectl(["apply", "-f", manifest_path])
        finally:
            Path(manifest_path).unlink(missing_ok=True)
    raise HTTPException(422, "Herramienta no soportada.")


def requires_confirmation(tool: str) -> bool:
    return tool in {"write_file", "apply_kubernetes_manifest"}


def create_proposal(tool: str, arguments: dict[str, Any], user: str, correlation_id: str) -> dict[str, Any]:
    proposal_id = str(uuid.uuid4())
    proposal = {"id": proposal_id, "tool": tool, "arguments": arguments, "user": user, "correlation_id": correlation_id, "expires_at": time.time() + settings.proposal_ttl_seconds}
    with proposal_lock:
        proposals[proposal_id] = proposal
    audit("proposal_created", correlation_id, user, tool=tool, proposal_id=proposal_id)
    return {"status": "WAITING_CONFIRMATION", "proposal_id": proposal_id, "tool": tool, "arguments": arguments, "message": "Esta acción modifica estado. Revísala y confírmala para ejecutarla."}


def run_action(request: ActionRequest, user: str, correlation_id: str) -> dict[str, Any]:
    if requires_confirmation(request.tool):
        return create_proposal(request.tool, request.arguments, user, correlation_id)
    audit("tool_started", correlation_id, user, tool=request.tool)
    result = execute(request.tool, request.arguments)
    audit("tool_succeeded", correlation_id, user, tool=request.tool)
    return {"status": "SUCCEEDED", "tool": request.tool, "result": result}


def infer_action(message: str, namespace: str | None) -> ActionRequest | None:
    text = message.lower()
    match = re.search(r"(?:namespace|ns)\s+([a-z0-9-]+)", text)
    selected = match.group(1) if match else namespace
    if "estado" in text and any(word in text for word in ("cluster", "nodo", "nodes")):
        return ActionRequest(tool="cluster_status")
    if any(word in text for word in ("listar pods", "lista pods", "ver pods")):
        return ActionRequest(tool="list_pods", arguments={"namespace": selected})
    if "listar archivo" in text or "listar archivos" in text:
        return ActionRequest(tool="list_files", arguments={"path": "."})
    return None


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/actions")
def action(request: ActionRequest, x_user: str | None = Header(default=None)) -> dict[str, Any]:
    user, correlation_id = current_user(x_user), str(uuid.uuid4())
    return {"correlation_id": correlation_id, **run_action(request, user, correlation_id)}


@app.post("/api/confirmations")
def confirmation(request: ConfirmationRequest, x_user: str | None = Header(default=None)) -> dict[str, Any]:
    user = current_user(x_user)
    with proposal_lock:
        proposal = proposals.pop(request.proposal_id, None)
    if not proposal or proposal["user"] != user or proposal["expires_at"] < time.time():
        raise HTTPException(404, "La propuesta no existe, expiró o no pertenece al usuario.")
    if not request.approved:
        audit("proposal_cancelled", proposal["correlation_id"], user, tool=proposal["tool"])
        return {"status": "CANCELLED", "correlation_id": proposal["correlation_id"]}
    audit("tool_started", proposal["correlation_id"], user, tool=proposal["tool"])
    result = execute(proposal["tool"], proposal["arguments"])
    audit("tool_succeeded", proposal["correlation_id"], user, tool=proposal["tool"])
    return {"status": "SUCCEEDED", "correlation_id": proposal["correlation_id"], "tool": proposal["tool"], "result": result}


@app.post("/api/chat")
def chat(request: ChatRequest, x_user: str | None = Header(default=None)) -> dict[str, Any]:
    user, correlation_id = current_user(x_user), str(uuid.uuid4())
    action_request = infer_action(request.message, request.namespace)
    audit("chat_received", correlation_id, user, has_action=bool(action_request))
    if not action_request:
        return {"correlation_id": correlation_id, "status": "RECEIVED", "reply": "Puedo consultar el estado del clúster, listar pods y listar archivos. Para acciones específicas usa /api/actions con una herramienta permitida.", "tools": []}
    try:
        outcome = run_action(action_request, user, correlation_id)
    except HTTPException as exc:
        audit("tool_failed", correlation_id, user, tool=action_request.tool, status=exc.status_code)
        return {"correlation_id": correlation_id, "status": "FAILED", "reply": exc.detail, "tools": [action_request.tool]}
    return {"correlation_id": correlation_id, "reply": f"Ejecuté {action_request.tool}.", "tools": [action_request.tool], **outcome}


@app.get("/")
def index() -> FileResponse:
    return FileResponse(APP_DIR / "index.html")
