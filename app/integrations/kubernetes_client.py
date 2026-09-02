"""Kubernetes Python client factory using the pod ServiceAccount."""
from kubernetes import client, config


def api_clients() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    return client.CoreV1Api(), client.AppsV1Api()


def read_tool(tool: str, arguments: dict, validate_namespace, validate_name) -> dict:
    """Execute read-only tools through the Kubernetes Python client."""
    core, apps = api_clients()
    if tool == "cluster_status":
        result = core.list_node()
    elif tool == "list_pods":
        result = core.list_namespaced_pod(validate_namespace(arguments.get("namespace")))
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
        result = {"data": core.read_namespaced_pod_log(name=validate_name(arguments.get("pod", ""), "El pod"), namespace=validate_namespace(arguments.get("namespace")), container=arguments.get("container"), tail_lines=200)}
    else:
        raise ValueError("Herramienta Kubernetes de lectura no soportada.")
    if isinstance(result, dict):
        return result
    return {"data": client.ApiClient().sanitize_for_serialization(result)}
