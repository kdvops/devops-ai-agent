"""Build isolated Kubernetes Jobs for long-running tasks."""
from kubernetes import client


def build_job(name: str, image: str, command: list[str], namespace: str) -> client.V1Job:
    container = client.V1Container(
        name="task",
        image=image,
        command=command,
        security_context=client.V1SecurityContext(run_as_non_root=True, allow_privilege_escalation=False),
        resources=client.V1ResourceRequirements(requests={"cpu": "100m", "memory": "128Mi"}, limits={"cpu": "500m", "memory": "512Mi"}),
    )
    pod = client.V1PodSpec(restart_policy="Never", containers=[container], automount_service_account_token=False)
    template = client.V1PodTemplateSpec(metadata=client.V1ObjectMeta(labels={"app.kubernetes.io/part-of": "devops-ai-agent"}), spec=pod)
    return client.V1Job(metadata=client.V1ObjectMeta(name=name, namespace=namespace), spec=client.V1JobSpec(template=template, backoff_limit=0, ttl_seconds_after_finished=3600))
