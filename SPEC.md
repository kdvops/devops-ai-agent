# DevOps AI Agent - Especificacion del producto

**Version:** 0.2.0
**Estado:** MVP implementado; endurecimiento de produccion pendiente
**Metodologia:** Spec-Driven Development
**Repositorio:** `kdvops/devops-ai-agent`

## 1. Objetivo

Construir un asistente DevOps conversacional que permita a un operador consultar
un cluster Kubernetes y un workspace autorizado usando lenguaje natural. El
agente debe obtener datos reales, aplicar controles de autorizacion y solicitar
confirmacion humana antes de cualquier cambio de estado.

El sistema esta orientado primero a desarrollo y QA. No debe considerarse una
plataforma de produccion hasta completar autenticacion empresarial, persistencia
transaccional, gestion de secretos, observabilidad y una estrategia de imagenes
inmutables.

## 2. Decisiones de arquitectura

- **LLM:** OpenAI Agents SDK para Python con `OpenAIChatCompletionsModel`.
- **Proveedor:** OpenAI por defecto; `OPENAI_BASE_URL` permite proveedores compatibles.
- **API:** FastAPI y Uvicorn.
- **Kubernetes:** Kubernetes Python Client para lecturas; `kubectl` solo para aplicar manifiestos previamente validados.
- **Frontend:** Next.js 15, React 19 y Node.js 22.
- **Datos:** PostgreSQL para persistencia prevista y Redis para cola de trabajos.
- **Ejecucion aislada:** Kubernetes Jobs preparado para tareas largas.
- **Servidores externos:** Ansible Runner preparado como adaptador.
- **Contenedores:** Docker y Docker Compose para desarrollo.
- **Git:** binario Git con URLs HTTPS y hosts permitidos; credenciales solo mediante runtime Secret.
- **GitOps:** Kustomize con `base` y overlay `dev`, sincronizado por Argo CD.

## 3. Arquitectura vigente

```text
Operador
  |
  v
Next.js frontend :3000
  |
  v
FastAPI backend :8080
  |
  +--> OpenAI Agents SDK --> OpenAI API
  |
  +--> Kubernetes Python Client --> API Server Kubernetes
  |
  +--> kubectl validado --> API Server Kubernetes
  |
  +--> PostgreSQL
  +--> Redis --> worker
```

En Kubernetes, el backend usa la `ServiceAccount` del pod mediante configuración
in-cluster. En desarrollo local, Docker Compose monta el kubeconfig del usuario
como solo lectura y define `KUBECONFIG` dentro del contenedor.

## 4. Componentes del repositorio

- `app/main.py`: API, validacion de entradas, politicas, herramientas y auditoria.
- `app/agent.py`: agente, prompt operativo y tools del Agents SDK.
- `app/integrations/kubernetes_client.py`: lecturas Kubernetes.
- `app/integrations/job_runner.py`: constructor de Jobs Kubernetes.
- `app/integrations/ansible.py`: entrada de Ansible Runner.
- `app/persistence.py`: modelos PostgreSQL y auditoria persistente.
- `app/app_queue.py`, `app/worker.py`: cola Redis y worker inicial.
- `frontend/`: interfaz web del chat.
- `app/k8s/base/`: recursos Kubernetes comunes.
- `app/k8s/overlays/dev/`: overlay consumido por Argo CD.
- `app/argocd/`: `AppProject` y `Application`.
- `.github/workflows/`: pipelines de imagen backend y frontend.

## 5. Actores y confianza

### Operador local

El frontend envia actualmente `X-User: operator-local`. Este valor sirve para
identificar la sesion de desarrollo, pero no es autenticacion: un cliente puede
forjarlo. OIDC/SSO y autorizacion por grupos son requisitos de produccion.

### Agente LLM

El modelo selecciona tools, pero nunca debe considerarse una frontera de
seguridad. El backend valida cada argumento, namespace, ruta, tipo de recurso,
modo de operacion y confirmacion.

### Cluster Kubernetes

La identidad efectiva es la `ServiceAccount` del pod en Kubernetes o el
kubeconfig montado en desarrollo. El frontend nunca recibe tokens Kubernetes.

### Datos externos

Mensajes, logs, archivos y manifiestos son datos no confiables. El agente debe
ignorar instrucciones embebidas en esos datos y no convertirlas en acciones.

## 6. Herramientas y contratos

### Lectura

- `cluster_status`: lista nodos mediante Kubernetes Python Client.
- `list_pods(namespace)`: lista pods del namespace autorizado.
- `get_workload(kind, name, namespace)`: lee Deployment, StatefulSet o DaemonSet.
- `get_pod_logs(pod, namespace, container?)`: lee hasta 200 lineas de logs.
- `list_files(path)`: lista hasta 500 entradas bajo `WORKSPACE_ROOT`.
- `read_file(path)`: lee archivos de hasta 256 KiB bajo `WORKSPACE_ROOT`.

### Cambio de estado

- `write_file(path, content)`: crea una propuesta; la escritura requiere confirmacion.
- `apply_kubernetes_manifest(manifest)`: valida YAML, recursos permitidos y namespace; ejecuta dry-run de servidor y luego `kubectl apply` solo si el modo lectura esta desactivado y existe confirmacion.
- `git_clone(url, repo_path, branch)`: clona un remoto HTTPS permitido dentro del workspace y requiere confirmacion.
- `git_status(repo_path)` y `git_diff(repo_path)`: inspeccionan un repositorio local autorizado.
- `git_commit(repo_path, message)` y `git_push(repo_path, branch)`: requieren confirmacion humana.

No existe una tool de shell arbitrario, una tool de eliminacion de recursos ni una tool Git que permita pasar argumentos libres. Los repositorios se limitan al workspace y las URLs no pueden contener credenciales.

## 7. API HTTP

### `GET /api/health`

Devuelve `{"status":"ok"}` y se usa para readiness/liveness.

### `POST /api/chat`

Requiere `X-User` valido. Recibe `message`, `history` opcional y `namespace`
opcional. Devuelve `correlation_id`, `status`, `reply` y `model`. Una tool de
escritura devuelve tambien `proposal_id`, tool y argumentos.

### `POST /api/actions`

Permite ejecutar una tool explicita. Las tools de escritura siempre generan una
propuesta.

### `POST /api/confirmations`

Recibe `proposal_id` y `approved`. Verifica usuario, existencia y expiracion de
la propuesta antes de ejecutar o cancelar.

## 8. Seguridad y autorizacion

Requisitos implementados:

- Proceso y contenedores sin root.
- `allowPrivilegeEscalation: false` y capacidades Linux eliminadas.
- Filesystem de solo lectura en los deployments cuando aplica.
- Secretos por variables de entorno y Kubernetes Secret.
- Namespace y nombres Kubernetes validados.
- `ALLOWED_NAMESPACES` limita consultas y manifiestos; `*` habilita todos los namespaces.
- Path traversal bloqueado fuera de `WORKSPACE_ROOT`.
- Tipos de manifiesto restringidos a ConfigMap, Service, Deployment, StatefulSet y DaemonSet.
- `KUBERNETES_READ_ONLY=true` por defecto.
- Dry-run obligatorio antes de aplicar manifiestos.
- NetworkPolicy para API Kubernetes, DNS, PostgreSQL y Redis.
- Logs estructurados sin contenido de manifiestos o secretos.

Pendientes de seguridad:

- OIDC/SSO, sesiones y autorizacion por usuario real.
- Rate limiting y limites de concurrencia.
- Validacion mas estricta de campos de manifiestos y politicas por ambiente.
- Escaneo, firma y verificacion de imagenes.
- External Secrets, Vault o Secret Manager.
- RBAC por namespace y grupo para escenarios multiambiente.

## 9. Auditoria y persistencia

Cada solicitud obtiene `correlation_id` y genera eventos estructurados como
`chat_received`, `llm_tool_selected`, `tool_started`, `tool_succeeded` y
`proposal_created`. PostgreSQL contiene modelos para conversaciones,
ejecuciones, aprobaciones y auditoria.

El estado actual persiste auditoria cuando `PERSISTENCE_ENABLED=true`, pero el
flujo de chat todavia no persiste de forma completa cada conversacion,
ejecucion y aprobacion en sus tablas respectivas. Esto es una brecha conocida
del MVP y debe resolverse antes de depender de PostgreSQL como historial.

## 10. Despliegue local

```powershell
cd app
Copy-Item .env.example .env
# Definir OPENAI_API_KEY en .env sin versionarlo
docker compose up --build
```

El frontend se publica en `http://localhost:3000`. El backend se publica en
`http://localhost:8080` o en `8081` cuando el puerto local esta ocupado.

Variables principales:

| Variable | Requerida | Valor/uso |
|---|---:|---|
| `OPENAI_API_KEY` | Si | Secret del proveedor LLM. |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1`. |
| `MODEL` | No | `gpt-5.5`. |
| `GIT_ALLOWED_HOSTS` | No | `github.com,gitlab.com,bitbucket.org`. |
| `GIT_USERNAME` | No | Usuario runtime para autenticacion HTTPS. |
| `GIT_PAT` | No | PAT runtime para clone/push HTTPS privado. |
| `GIT_API_KEY` | No | API key runtime usada como password HTTPS. |
| `GIT_PASSWORD` | No | Password runtime para clone/push HTTPS privado. |
| `GIT_TOKEN` | No | Alias legado de credencial HTTPS; Secret, nunca Git. |
| `GIT_COMMIT_NAME` | No | Identidad del autor de commits automáticos. |
| `GIT_COMMIT_EMAIL` | No | Email del autor de commits automáticos. |
| `KUBECONFIG` | Local | `/home/agent/.kube/config`. |
| `KUBERNETES_READ_ONLY` | No | `true`. |
| `ALLOWED_NAMESPACES` | Si | Lista separada por comas; `*` habilita todos los namespaces. |
| `WORKSPACE_ROOT` | Si | `/workspace`. |
| `DATABASE_URL` | No | Conexion asyncpg a PostgreSQL. |
| `POSTGRES_PASSWORD` | Kubernetes | Secret usado para completar la URL. |
| `REDIS_URL` | No | Conexion Redis. |
| `PERSISTENCE_ENABLED` | No | `true` en Compose/Kubernetes. |

## 11. Despliegue Kubernetes y GitOps

Kustomize se organiza así:

```text
app/k8s/base/
app/k8s/overlays/dev/
```

El overlay dev incluye Namespace, ServiceAccount, RBAC, ConfigMap, backend,
frontend, worker, PostgreSQL, Redis, Ingress, NetworkPolicy y PVC del workspace.

Argo CD usa `app/argocd/application-dev.yaml`, apunta a la rama `main` y
sincroniza `app/k8s/overlays/dev`. El `AppProject` restringe el repositorio y el
namespace de destino. `selfHeal` esta activo y `prune` esta desactivado.

Antes de sincronizar deben existir fuera de Git:

- `devops-ai-agent-secrets/OPENAI_API_KEY`.
- `devops-ai-data/POSTGRES_PASSWORD`.
- `imagePullSecret` si los paquetes GHCR son privados.

Las imagenes publicadas son:

- `ghcr.io/kdvops/devops-ai-agent`.
- `ghcr.io/kdvops/devops-ai-agent-ui`.

CI publica tags `latest` y `sha-*`. El overlay dev usa `latest` para simplificar
el MVP; una promocion reproducible requiere tags inmutables y actualizacion
declarativa del overlay o Argo CD Image Updater.

## 12. CI/CD

- El workflow backend se dispara con cambios en `app/**` y publica la imagen API.
- El workflow frontend se dispara con cambios en `frontend/**` y publica la imagen UI.
- Ambos usan `GITHUB_TOKEN` con `packages: write`.
- El workflow backend no usa el backend de cache GHA de BuildKit porque produjo fallos de publish; el build se mantiene deliberadamente simple y estable.

## 13. Requisitos funcionales

### RF-001 Chat conversacional

El operador puede enviar texto desde Next.js y recibir una respuesta del agente.

**Aceptacion:** `/api/chat` responde con `SUCCEEDED` para una consulta valida y
el frontend muestra la respuesta.

### RF-002 Seleccion de tools

El agente puede seleccionar tools de lectura y el backend ejecuta solo tools
declaradas y validadas.

**Aceptacion:** una consulta de nodos usa `cluster_status`; una consulta de pods
usa `list_pods`; una consulta de archivos usa `list_files` o `read_file`.

### RF-003 Confirmacion

Toda escritura produce `WAITING_CONFIRMATION` y una propuesta asociada al usuario.

**Aceptacion:** cancelar no modifica estado; aprobar valida identidad y TTL antes
de ejecutar.

### RF-004 Kubernetes

El agente usa una identidad Kubernetes dedicada y comienza en modo lectura.

**Aceptacion:** el pod tiene `ServiceAccount`, RBAC limitado y las solicitudes a
namespaces no autorizados devuelven `403`.

### RF-005 Workspace

Las rutas absolutas y traversal fuera de `WORKSPACE_ROOT` son rechazadas.

**Aceptacion:** lectura y escritura nunca salen del workspace y los hashes de
contenido se calculan para las escrituras.

### RF-006 GitOps

Argo CD puede renderizar y sincronizar el overlay dev después de crear secretos
y resolver el acceso al registry.

**Aceptacion:** `kubectl kustomize app/k8s/overlays/dev` renderiza sin errores y
la Application apunta a la ruta correcta.

## 14. Requisitos no funcionales

- Timeout de tools configurable y limite de salida del modelo.
- Health, readiness y liveness checks.
- Logs JSON con correlation ID.
- Limites de mensaje, historial, archivos y manifiestos.
- Recursos CPU/memoria definidos en Kubernetes.
- NetworkPolicy y ejecución no privilegiada.
- No almacenar secretos en el repositorio.
- Git remoto solo por HTTPS con hosts allowlisted y credenciales fuera de las URLs.
- Respuesta de consultas simples objetivo menor a 10 segundos, excluyendo latencia externa del LLM.

## 15. Pruebas

Implementadas actualmente:

- Path traversal.
- Namespace no autorizado.
- Requisito de confirmacion para escritura.
- Build local de backend y frontend.
- Render de Kustomize y dry-run cliente.
- Health check y conversación real con OpenAI.
- Consulta real de nodos mediante kubeconfig local.
- Workflows GitHub Actions backend y frontend verificados.

Pendientes:

- Tests HTTP con `TestClient`.
- Tests del agente y tool calls simuladas.
- Tests de Kubernetes con mocks.
- Tests de confirmacion aprobada, cancelada y expirada.
- Tests de persistencia y Redis.
- Escaneo de dependencias e imagenes.
- Prueba de despliegue en un cluster efimero.

## 16. Roadmap

### Fase 1 - MVP conversacional: completada

Frontend, FastAPI, OpenAI Agents SDK, health check, Docker Compose y CI de imagenes.

### Fase 2 - Lecturas controladas: completada

Workspace seguro, cliente Kubernetes, lectura de nodos, pods, workloads y logs.

### Fase 3 - Cambios controlados: parcial

Propuestas y confirmaciones implementadas. Faltan persistencia completa, backups
de workspace y politicas de aprobación por usuario/ambiente.

### Fase 4 - GitOps Kubernetes: implementada para dev

Kustomize base/overlay, Argo CD, RBAC, NetworkPolicy, PVC y pipelines GHCR.
Faltan tags inmutables, secrets operator y promoción entre ambientes.

### Fase 5 - Producción empresarial: pendiente

OIDC/SSO, multiusuario, Change Control, métricas, trazas, backups, HA, firma de
imagenes, escaneo, External Secrets/Vault y operación completa de Jobs/Ansible.

## 17. Definición de terminado del MVP

El MVP se considera operativo cuando:

- Frontend y backend se comunican mediante Docker Compose.
- OpenAI devuelve respuestas a través del Agents SDK.
- El backend puede consultar un cluster real con kubeconfig local o ServiceAccount.
- Namespaces, rutas y manifiestos no autorizados son rechazados.
- Cambios requieren confirmación explicita.
- Argo CD renderiza el overlay dev.
- Los workflows publican ambas imagenes.
- Secrets permanecen fuera de Git.
- Las pruebas y validaciones documentadas pasan.

No se considera listo para producción hasta cerrar los pendientes de seguridad,
persistencia, promoción inmutable, observabilidad y alta disponibilidad.
