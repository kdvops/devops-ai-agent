# DevOps AI Agent

Asistente web para consultar un clúster Kubernetes mediante la identidad del pod.
Las consultas usan `kubectl` con argumentos validados; la escritura de archivos y
la aplicación de manifiestos requieren confirmación explícita.

## Desarrollo local

```powershell
cd app
docker compose up --build
```

Abre `http://localhost:8080`. El usuario local se envía mediante el encabezado
`X-User` desde la interfaz; esto es identidad de desarrollo, no autenticación
empresarial. Define `OPENAI_API_KEY` antes de iniciar Compose. Kubernetes
permanece en modo de solo lectura por defecto.

## Despliegue Kubernetes

1. Construye y publica la imagen, y sustituye `image` en `app/k8s/deployment.yaml`.
2. Ajusta `ALLOWED_NAMESPACES` en `app/k8s/configmap.yaml`.
3. Crea el secreto del proveedor LLM sin guardarlo en Git:

```powershell
kubectl create secret generic devops-ai-agent-secrets -n devops-ai --from-literal=OPENAI_API_KEY=$env:OPENAI_API_KEY
kubectl create secret generic devops-ai-data -n devops-ai --from-literal=POSTGRES_PASSWORD="genera-un-secreto-fuerte"
```

4. Aplica los manifiestos:

```powershell
kubectl apply -f app/k8s/namespace.yaml
kubectl apply -f app/k8s/serviceaccount-rbac.yaml
kubectl apply -f app/k8s/configmap.yaml
kubectl apply -f app/k8s/deployment.yaml
kubectl apply -f app/k8s/networkpolicy.yaml
kubectl apply -f app/k8s/ingress.yaml
```

El RBAC incluido permite consultar pods, logs y workloads en `devops-ai`. Para
consultar otro namespace, crea un `Role` y `RoleBinding` equivalentes allí y
añádelo a `ALLOWED_NAMESPACES`. No habilites cambios Kubernetes sin una revisión
específica de RBAC y políticas.

## GitOps con Argo CD

La aplicación declarativa está en `app/argocd`. Antes del primer despliegue,
reemplaza `REPLACE_WITH_YOUR_ORG` en `app/argocd/project.yaml`,
`app/argocd/application-dev.yaml` y `app/k8s/deployment.yaml`. También ajusta
el host del Ingress en `app/k8s/ingress.yaml`.

Instala Argo CD en el clúster y registra la aplicación:

```powershell
kubectl apply -n argocd -f app/argocd/project.yaml
kubectl apply -n argocd -f app/argocd/application-dev.yaml
```

Argo CD sincronizará `main`, corregirá cambios manuales (`selfHeal`) y no
eliminará recursos automáticamente (`prune: false`). El workflow
`.github/workflows/app-image.yml` publica la imagen backend en GHCR solo cuando
el push a `main` contiene cambios en `app/**`. También puede ejecutarse
manualmente desde la pestaña Actions. Actualiza el tag de
`app/k8s/deployment.yaml` mediante un cambio revisado en Git antes de que Argo
CD despliegue una nueva versión.

El chat usa la Responses API de OpenAI con function calling: el modelo elige
entre las herramientas declaradas y el backend valida cada llamada antes de
ejecutarla. Configura otro modelo con `MODEL` si tu proyecto tiene acceso a él.

La estructura del MVP queda separada por responsabilidades: `app/agent.py`
contiene el agente y sus tools, `app/persistence.py` los modelos PostgreSQL,
`app/app_queue.py` la cola Redis, `app/integrations/` las integraciones de
Kubernetes, Jobs y Ansible, y `frontend/` la interfaz Next.js. La contraseña
`POSTGRES_PASSWORD` se crea como Secret en Kubernetes; no la guardes en Git.
