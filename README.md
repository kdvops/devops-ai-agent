# DevOps AI Agent

Asistente web para consultar un clúster Kubernetes mediante la identidad del pod.
Las consultas usan `kubectl` con argumentos validados; la escritura de archivos y
la aplicación de manifiestos requieren confirmación explícita.

## Desarrollo local

```powershell
cd app
docker compose up --build
```

Abre `http://localhost:8080`. Para usar DeepSeek, copia `app/.env.example` a
`app/.env`, configura tu key y ejecuta Compose. El usuario local se envía mediante el encabezado
`X-User` desde la interfaz; esto es identidad de desarrollo, no autenticación
empresarial. Kubernetes permanece en modo de solo lectura por defecto.

## Despliegue Kubernetes

1. Construye y publica las imágenes con los workflows de GitHub Actions.
2. Ajusta `ALLOWED_NAMESPACES` en `app/k8s/base/configmap.yaml`.
3. Crea el secreto del proveedor LLM sin guardarlo en Git:

```powershell
kubectl create secret generic devops-ai-agent-secrets -n devops-ai --from-literal=OPENAI_API_KEY=$env:OPENAI_API_KEY
kubectl create secret generic devops-ai-data -n devops-ai --from-literal=POSTGRES_PASSWORD="genera-un-secreto-fuerte"
```

4. Crea el namespace y aplica la base de recursos:

```powershell
kubectl apply -k app/k8s/overlays/dev
```

El RBAC incluido permite consultar pods, logs y workloads en `devops-ai`. Para
consultar otro namespace, crea un `Role` y `RoleBinding` equivalentes allí y
añádelo a `ALLOWED_NAMESPACES`. No habilites cambios Kubernetes sin una revisión
específica de RBAC y políticas.

## GitOps con Argo CD

La aplicación declarativa está en `app/argocd` y apunta al overlay
`app/k8s/overlays/dev`. Ajusta el host del Ingress en
`app/k8s/base/ingress.yaml`
antes de desplegar.

Instala Argo CD en el clúster y registra la aplicación:

```powershell
kubectl apply -n argocd -f app/argocd/project.yaml
kubectl apply -n argocd -f app/argocd/application-dev.yaml
```

Argo CD sincronizará `main`, corregirá cambios manuales (`selfHeal`) y no
eliminará recursos automáticamente (`prune: false`). Los workflows
`.github/workflows/app-image.yml` y `.github/workflows/container.yml` publican
las imágenes backend y frontend en GHCR con los tags `sha-*` y `latest`. El
overlay `dev` consume `latest` para el MVP.

El chat usa OpenAI Agents SDK con function calling: el modelo elige entre las
herramientas declaradas y el backend valida cada llamada antes de ejecutarla.
Configura otro modelo con `MODEL` si tu proyecto tiene acceso a él.

La estructura del MVP queda separada por responsabilidades: `app/agent.py`
contiene el agente y sus tools, `app/persistence.py` los modelos PostgreSQL,
`app/app_queue.py` la cola Redis, `app/integrations/` las integraciones de
Kubernetes, Jobs y Ansible, y `frontend/` la interfaz Next.js. La contraseña
`POSTGRES_PASSWORD` se crea como Secret en Kubernetes; no la guardes en Git.
