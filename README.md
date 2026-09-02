# DevOps AI Agent

Asistente DevOps conversacional para consultar Kubernetes y operar sobre un
workspace con controles de autorización, confirmación y auditoría. El MVP usa
OpenAI como cerebro, FastAPI como backend, Kubernetes Python Client para lecturas
y `kubectl` con argumentos controlados para aplicar manifiestos aprobados.

## Arquitectura

```text
Usuario
  -> Next.js frontend
  -> FastAPI backend
  -> OpenAI Agents SDK
       |-> Kubernetes Python Client (lecturas)
       |-> workspace seguro (lecturas/escrituras propuestas)
       |-> kubectl validado (manifiestos confirmados)
       |-> PostgreSQL / Redis
```

El stack de despliegue incluye backend, frontend, worker, PostgreSQL, Redis,
Ingress, RBAC, NetworkPolicy y almacenamiento persistente del workspace. El
frontend y backend tienen imágenes y workflows de publicación independientes.

## Requisitos

- Docker Desktop para desarrollo local.
- Python 3.12 y `pytest` para pruebas fuera de Docker.
- `kubectl` con un contexto válido si se quiere consultar un clúster desde Docker.
- Un API key de OpenAI con acceso al modelo configurado.
- Para Kubernetes: Argo CD, un registry GHCR accesible y un StorageClass para el PVC.

## Ejecución local

```powershell
cd app
Copy-Item .env.example .env
# Editar .env y definir OPENAI_API_KEY
docker compose up --build
```

Abrir [http://localhost:3000](http://localhost:3000) para usar el chat. La API
está en `http://localhost:8080`; el endpoint `/api/chat` requiere `POST` y el
encabezado `X-User`, por lo que no debe abrirse directamente como una página.

Configuración mínima de `app/.env`:

```env
OPENAI_API_KEY=tu_api_key
OPENAI_BASE_URL=https://api.openai.com/v1
MODEL=gpt-5.5
GIT_ALLOWED_HOSTS=github.com,gitlab.com,bitbucket.org
GIT_USERNAME=x-access-token
GIT_COMMIT_NAME=DevOps AI Agent
GIT_COMMIT_EMAIL=devops-ai-agent@local.invalid
# Opcional; preferir un Secret o helper de credenciales del entorno.
GIT_TOKEN=
GIT_PAT=
GIT_API_KEY=
GIT_PASSWORD=
```

En desarrollo local Compose monta el kubeconfig del usuario en modo lectura:

```text
$USERPROFILE/.kube/config -> /home/agent/.kube/config
```

El backend intenta primero configuración in-cluster y, si no está dentro de
Kubernetes, usa `KUBECONFIG`/kubeconfig local.

## Herramientas del agente

Herramientas de lectura disponibles:

- `cluster_status`: nodos del clúster.
- `list_pods`: pods de un namespace autorizado.
- `get_workload`: Deployments, StatefulSets y DaemonSets.
- `get_pod_logs`: logs recientes de un pod autorizado.
- `list_files` y `read_file`: workspace autorizado.

Herramientas con cambio de estado:

- `write_file`: propone escribir en el workspace.
- `apply_kubernetes_manifest`: valida YAML, tipo, namespace y ejecuta dry-run antes de aplicar; permanece bloqueada con `KUBERNETES_READ_ONLY=true`.
- `git_clone`: propone clonar un repositorio HTTPS de un host permitido en `/workspace`.
- `git_status` y `git_diff`: inspeccionan un repositorio clonado.
- `git_commit` y `git_push`: requieren confirmación humana antes de crear o publicar cambios.
- `http_request`: consulta URLs HTTP(S) autorizadas con `GET` o `HEAD`, equivalente a `curl` de solo lectura.
- `ssh_command`: ejecuta comandos de diagnóstico permitidos en hosts SSH autorizados y requiere confirmación.
- `browser_inspect`: abre una página autorizada con Playwright y devuelve estado, título y texto visible; requiere confirmación.

No existe ejecución de shell arbitrario ni un endpoint para enviar tokens
Kubernetes desde el frontend.
Las operaciones Git tampoco aceptan comandos o flags arbitrarios; el token Git
se inyecta como secreto de runtime y nunca se incluye en la URL.

Las herramientas externas están cerradas por allowlist. Configura
`EXTERNAL_HTTP_ALLOWED_HOSTS` y `BROWSER_ALLOWED_HOSTS` con hosts exactos. Para
SSH configura `SSH_ALLOWED_HOSTS`, `SSH_USERNAME` y una clave privada montada en
`SSH_PRIVATE_KEY_PATH` o `SSH_PASSWORD`; la verificación de host permanece activa
con `SSH_STRICT_HOST_KEY_CHECKING=true`. Los comandos se limitan mediante
`SSH_ALLOWED_COMMANDS` y no aceptan metacaracteres de shell.

## Kubernetes y Argo CD

La estructura GitOps es:

```text
app/k8s/base/              recursos comunes
app/k8s/overlays/dev/      configuración del entorno dev
app/argocd/project.yaml    AppProject
app/argocd/application-dev.yaml
```

Validar los manifiestos:

```powershell
kubectl kustomize app/k8s/overlays/dev
kubectl apply -k app/k8s/overlays/dev --dry-run=client
```

Crear primero los secretos fuera de Git:

```powershell
kubectl create namespace devops-ai
kubectl create secret generic devops-ai-agent-secrets -n devops-ai `
  --from-literal=OPENAI_API_KEY=$env:OPENAI_API_KEY `
  --from-literal=GIT_USERNAME="x-access-token" `
  --from-literal=GIT_PAT=$env:GIT_PAT
kubectl create secret generic devops-ai-data -n devops-ai `
  --from-literal=POSTGRES_PASSWORD="genera-un-secreto-fuerte"
```

El overlay `app/k8s/overlays/dev` incluye `secrets-dummy.yaml` para facilitar
pruebas de Argo CD. Esas credenciales son intencionalmente falsas y no deben
usarse fuera de desarrollo/QA; reemplázalas por Secrets gestionados fuera de Git
antes de desplegar en un entorno real.

Registrar la aplicación en Argo CD:

```powershell
kubectl apply -n argocd -f app/argocd/project.yaml
kubectl apply -n argocd -f app/argocd/application-dev.yaml
```

Argo CD sincroniza la rama `main`, aplica self-heal y mantiene `prune: false`.
Las imágenes son `ghcr.io/kdvops/devops-ai-agent` y
`ghcr.io/kdvops/devops-ai-agent-ui`. Los workflows publican `latest` y `sha-*`.
El overlay dev usa `latest` para el MVP; producción debe usar tags inmutables o
Argo CD Image Updater.

Si GHCR es privado, crea también un `imagePullSecret` y referencia ese secreto
en los deployments. El Ingress usa el host `devops-ai.example.com` por defecto;
ajústalo al dominio real.

## CI/CD

- `.github/workflows/app-image.yml`: construye y publica el backend cuando cambia `app/**`.
- `.github/workflows/container.yml`: construye y publica el frontend cuando cambia `frontend/**`.
- Ambos usan GitHub Container Registry y `GITHUB_TOKEN` con permiso `packages: write`.

## Configuración Kubernetes

- `OPENAI_API_KEY`: Secret obligatorio.
- `OPENAI_BASE_URL`: `https://api.openai.com/v1`.
- `MODEL`: `gpt-5.5`.
- `GIT_ALLOWED_HOSTS`: hosts HTTPS permitidos para clonar.
- `GIT_USERNAME`: usuario HTTPS opcional; por defecto `x-access-token`.
- `GIT_PAT`, `GIT_API_KEY`, `GIT_PASSWORD` o `GIT_TOKEN`: una credencial HTTPS opcional para repositorios privados; se usa la primera disponible en ese orden.
- `GIT_COMMIT_NAME` y `GIT_COMMIT_EMAIL`: identidad determinista usada al crear commits.
- `KUBERNETES_READ_ONLY`: `true` por defecto.
- `ALLOWED_NAMESPACES`: namespaces autorizados para herramientas; `*` habilita lectura en todos los namespaces.
- `WORKSPACE_ROOT`: `/workspace`.
- `DATABASE_URL`, `POSTGRES_PASSWORD` y `REDIS_URL`: persistencia/cola.

El `ServiceAccount` tiene lectura de nodos, pods, logs, eventos y workloads a
nivel de clúster. El MVP mantiene `KUBERNETES_READ_ONLY=true` y no concede
permisos de escritura Kubernetes.

## Pruebas

```powershell
pytest -q app/tests
git diff --check
kubectl kustomize app/k8s/overlays/dev
```

La prueba manual mínima es abrir el frontend, enviar un mensaje, consultar
`/api/health` y verificar que el backend registra un `correlation_id` sin
imprimir secretos.

## Estado del MVP

Implementado: chat web con adjuntos de imagen multimodales, OpenAI Agents SDK, herramientas Kubernetes de lectura,
workspace protegido, integración Git controlada para clonar/revisar/commit/push,
propuestas de cambio, Docker Compose, imágenes GHCR,
Kustomize, Argo CD, RBAC, NetworkPolicy, PostgreSQL/Redis y health checks.

Pendiente antes de producción: OIDC/SSO y autorización por usuario, persistencia
completa de conversaciones/ejecuciones/aprobaciones, tags inmutables, escaneo y
firma de imágenes, External Secrets/Vault, backups/HA de datos, métricas y
ejecución completa de Jobs/Ansible.
