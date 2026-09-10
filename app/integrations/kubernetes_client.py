"""Controlled Kubernetes reads and namespace-scoped operational actions."""
from __future__ import annotations

from datetime import datetime, timezone
from kubernetes import client, config


def api_clients():
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api(), client.AppsV1Api()


def _serialized(value):
    return client.ApiClient().sanitize_for_serialization(value)


def read_tool(tool: str, arguments: dict, validate_namespace, validate_name) -> dict:
    """Execute allowlisted read-only Kubernetes operations."""
    core, apps = api_clients()
    if tool == "cluster_status":
        result = core.list_node()
    elif tool == "list_namespaces":
        result = core.list_namespace()
    elif tool == "list_pods":
        namespace = validate_namespace(arguments.get("namespace"))
        result = core.list_namespaced_pod(namespace)
    elif tool == "list_events":
        namespace = validate_namespace(arguments.get("namespace"))
        result = core.list_namespaced_event(namespace)
    elif tool == "list_services":
        namespace = validate_namespace(arguments.get("namespace"))
        result = core.list_namespaced_service(namespace)
    elif tool == "list_configmaps":
        namespace = validate_namespace(arguments.get("namespace"))
        result = core.list_namespaced_config_map(namespace)
        result = {
            "items": [
                {
                    "name": item.metadata.name,
                    "namespace": item.metadata.namespace,
                    "labels": item.metadata.labels or {},
                    "annotations": item.metadata.annotations or {},
                }
                for item in result.items
            ]
        }
    elif tool == "get_node":
        result = core.read_node(validate_name(arguments.get("name", ""), "El nodo"))
    elif tool == "get_pod":
        namespace = validate_namespace(arguments.get("namespace"))
        result = core.read_namespaced_pod(validate_name(arguments.get("pod", ""), "El pod"), namespace)
    elif tool == "get_workload":
        namespace = validate_namespace(arguments.get("namespace"))
        name = validate_name(arguments.get("name", ""), "El nombre")
        kind = arguments.get("kind", "deployment").lower()
        if kind == "deployment":
            result = apps.read_namespaced_deployment(name, namespace)
        elif kind == "statefulset":
            result = apps.read_namespaced_stateful_set(name, namespace)
        elif kind == "daemonset":
            result = apps.read_namespaced_daemon_set(name, namespace)
        else:
            raise ValueError("Tipo de workload no permitido.")
    elif tool == "get_pod_logs":
        namespace = validate_namespace(arguments.get("namespace"))
        tail_lines = min(max(int(arguments.get("tail_lines", 200)), 1), 500)
        result = {"data": core.read_namespaced_pod_log(name=validate_name(arguments.get("pod", ""), "El pod"), namespace=namespace, container=arguments.get("container"), tail_lines=tail_lines, previous=bool(arguments.get("previous", False)))}
    elif tool == "rollout_status":
        namespace = validate_namespace(arguments.get("namespace"))
        name = validate_name(arguments.get("name", ""), "El nombre")
        kind = arguments.get("kind", "deployment").lower()
        if kind == "deployment":
            result = apps.read_namespaced_deployment_status(name, namespace)
        elif kind == "statefulset":
            result = apps.read_namespaced_stateful_set_status(name, namespace)
        elif kind == "daemonset":
            result = apps.read_namespaced_daemon_set_status(name, namespace)
        else:
            raise ValueError("Tipo de workload no permitido.")
    else:
        raise ValueError("Herramienta Kubernetes de lectura no soportada.")
    return result if isinstance(result, dict) else {"data": _serialized(result)}


def write_tool(tool: str, arguments: dict, validate_namespace, validate_name) -> dict:
    """Execute confirmed, namespace-scoped operational changes."""
    core, apps = api_clients()
    namespace = validate_namespace(arguments.get("namespace"))
    name = validate_name(arguments.get("name") or arguments.get("pod", ""), "El nombre")
    kind = arguments.get("kind", "deployment").lower()
    if tool == "scale_workload":
        replicas = arguments.get("replicas")
        if kind not in {"deployment", "statefulset"} or not isinstance(replicas, int) or not 0 <= replicas <= 100:
            raise ValueError("Solo se permite escalar Deployments o StatefulSets entre 0 y 100 réplicas.")
        body = {"spec": {"replicas": replicas}}
        result = apps.patch_namespaced_deployment_scale(name, namespace, body) if kind == "deployment" else apps.patch_namespaced_stateful_set_scale(name, namespace, body)
    elif tool == "restart_workload":
        if kind not in {"deployment", "statefulset", "daemonset"}:
            raise ValueError("Tipo de workload no permitido.")
        patch = {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": datetime.now(timezone.utc).isoformat()}}}}}
        if kind == "deployment":
            result = apps.patch_namespaced_deployment(name, namespace, patch)
        elif kind == "statefulset":
            result = apps.patch_namespaced_stateful_set(name, namespace, patch)
        else:
            result = apps.patch_namespaced_daemon_set(name, namespace, patch)
    elif tool == "delete_pod":
        result = core.delete_namespaced_pod(name, namespace, grace_period_seconds=30)
    else:
        raise ValueError("Herramienta Kubernetes de escritura no soportada.")
    return {"data": _serialized(result)}
