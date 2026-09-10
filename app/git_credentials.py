"""Read-only Git repository credentials injected by a runtime Secret."""
from __future__ import annotations

import json
import os
from typing import Any


def _records() -> list[dict[str, Any]]:
    raw = os.getenv("GIT_REPOSITORIES_JSON", "[]")
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GIT_REPOSITORIES_JSON no contiene JSON válido.") from exc
    if not isinstance(records, list):
        raise RuntimeError("GIT_REPOSITORIES_JSON debe ser una lista.")
    for record in records:
        if not isinstance(record, dict) or not all(isinstance(record.get(key), str) and record[key] for key in ("id", "name", "url", "username", "secret")):
            raise RuntimeError("GIT_REPOSITORIES_JSON contiene una credencial incompleta.")
        if record.get("secret_type", "pat") not in {"pat", "password"}:
            raise RuntimeError("GIT_REPOSITORIES_JSON contiene un secret_type inválido.")
    return records


def list_public(user_id: str) -> list[dict[str, str]]:
    """Return metadata only; secrets never leave this module."""
    public_keys = ("id", "name", "url", "username", "secret_type")
    return [{key: record.get(key, "pat") if key == "secret_type" else record[key] for key in public_keys} for record in _records() if not record.get("user_id") or record["user_id"] == user_id]


def get(user_id: str, credential_id: str) -> dict[str, str]:
    for record in _records():
        if record["id"] == credential_id and (not record.get("user_id") or record["user_id"] == user_id):
            return {key: record[key] for key in ("id", "name", "url", "username", "secret", "secret_type")}
    raise KeyError("La credencial Git no existe o no pertenece al usuario.")
