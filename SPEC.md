# DevOps AI Agent — Especificación del Proyecto

**Versión:** 0.1.0  
**Estado:** Propuesta inicial  
**Metodología:** Spec-Driven Development  
**Repositorio:** `kdvops/devops-ai-agent`

## 1. Objetivo

Construir un asistente DevOps accesible mediante una interfaz web de chat. El agente podrá consultar y operar de forma controlada sobre un servidor físico o virtual y sobre un clúster Kubernetes, siempre aplicando autenticación, autorización, confirmación de acciones sensibles y auditoría.

El sistema será desplegable sobre Kubernetes y estará orientado inicialmente a ambientes no productivos.

## 2. Alcance del MVP

### Incluido

- Interfaz web para enviar mensajes y visualizar respuestas.
- API backend para gestionar conversaciones.
- Agente con modelo de lenguaje configurable.
- Herramientas para consultar el estado del clúster Kubernetes.
- Herramientas para listar, crear y editar archivos dentro de un workspace autorizado.
- Confirmación explícita antes de modificar archivos o ejecutar acciones sensibles.
- Despliegue mediante Docker y manifiestos Kubernetes.
- ServiceAccount con RBAC limitado.
- Registro básico de solicitudes, herramientas invocadas, resultado y usuario.

### Fuera del alcance inicial

- Ejecución irrestricta de comandos shell.
- Acceso directo como root al servidor.
- Cambios automáticos en producción.
- Eliminación automática de recursos Kubernetes.
- Gestión de credenciales en texto plano.
- Soporte multiagente avanzado.
- Memoria empresarial persistente y base de conocimiento avanzada.

## 3. Usuarios y roles

### Operador DevOps

Puede consultar el clúster, revisar logs autorizados y solicitar cambios en archivos.

### Administrador

Puede administrar usuarios, políticas, herramientas permitidas, ambientes y permisos RBAC.

### Agente

Interpreta la solicitud, decide qué herramienta utilizar, solicita confirmación cuando corresponda y devuelve el resultado de forma comprensible.

## 4. Arquitectura lógica

```text
Usuario
  |
  v
Frontend Web
  |
  v
API Backend / Orquestador del agente
  |             |                 |
  v             v                 v
Modelo LLM   File Runner       Kubernetes Client
                              |
                              v
                         API Server K8s
```

### Componentes

#### Frontend

- Aplicación web de chat.
- Debe mostrar mensajes del usuario y del agente.
- Debe mostrar qué herramienta será utilizada.
- Debe solicitar confirmación para operaciones de escritura o cambios.
- No debe contener claves API ni tokens Kubernetes.

#### Backend

- API HTTP basada en FastAPI.
- Gestiona sesiones y mensajes.
- Orquesta el ciclo de razonamiento y uso de herramientas.
- Valida permisos antes de ejecutar cada herramienta.
- Devuelve respuestas estructuradas y errores controlados.

#### File Runner

- Opera únicamente dentro de `WORKSPACE_ROOT`.
- Debe impedir path traversal.
- No debe permitir acceso a `/etc`, `/var/lib`, `/root` ni rutas fuera del workspace.
- Las operaciones de escritura requieren confirmación.
- Debe registrar ruta, usuario, operación, hash anterior y hash posterior.

#### Kubernetes Client

- Usa configuración in-cluster cuando el agente corre en Kubernetes.
- Usa `KUBECONFIG` únicamente en desarrollo local.
- Debe comenzar en modo lectura.
- Debe limitarse mediante RBAC.
- No debe aceptar un token enviado desde el frontend.

## 5. Herramientas del agente

Cada herramienta debe tener un contrato definido, validación de entrada y registro de auditoría.

### `cluster_status`

Consulta la versión, estado general y disponibilidad de nodos.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `list_pods`

Lista pods por namespace, estado, nodo y reinicios.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `get_workload`

Obtiene Deployment, StatefulSet o DaemonSet y sus eventos asociados.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `get_pod_logs`

Consulta logs de un pod autorizado.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `list_files`

Lista archivos dentro del workspace autorizado.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `read_file`

Lee el contenido de un archivo permitido.

**Permiso inicial:** lectura.  
**Confirmación:** no requerida.

### `write_file`

Crea o modifica un archivo dentro del workspace.

**Permiso inicial:** escritura.  
**Confirmación:** obligatoria.

### `apply_kubernetes_manifest`

Valida y aplica un manifiesto permitido en un namespace autorizado.

**Permiso inicial:** deshabilitado.  
**Confirmación:** obligatoria y doble validación recomendada.

### `delete_kubernetes_resource`

Elimina un recurso Kubernetes.

**Permiso inicial:** deshabilitado.  
**Confirmación:** obligatoria; no disponible para producción.

## 6. Requisitos funcionales

### RF-001 — Chat

El sistema debe permitir que un usuario envíe una solicitud y reciba una respuesta del agente.

**Criterios de aceptación:**

- El usuario puede enviar texto desde el frontend.
- El backend responde mediante `/api/chat`.
- Los errores se muestran sin exponer secretos o trazas internas.

### RF-002 — Selección de herramientas

El agente debe seleccionar herramientas según la intención de la solicitud.

**Criterios de aceptación:**

- Una consulta de pods utiliza `list_pods`.
- Una consulta de archivos utiliza `list_files` o `read_file`.
- Una solicitud de escritura nunca se ejecuta sin confirmación.

### RF-003 — Confirmación

El sistema debe solicitar confirmación antes de ejecutar acciones con efectos de escritura, despliegue, reinicio o eliminación.

**Criterios de aceptación:**

- La interfaz muestra la acción, destino y parámetros.
- El usuario puede aprobar o cancelar.
- Una solicitud cancelada no modifica el estado.

### RF-004 — Acceso a Kubernetes

El agente debe consultar recursos Kubernetes utilizando la identidad asignada al pod.

**Criterios de aceptación:**

- El pod usa una ServiceAccount dedicada.
- La ServiceAccount tiene permisos explícitos y mínimos.
- Las operaciones no autorizadas devuelven `403` controlado.

### RF-005 — Gestión segura de archivos

El agente debe poder leer y modificar archivos únicamente dentro del workspace configurado.

**Criterios de aceptación:**

- `../` y rutas absolutas fuera del workspace son rechazadas.
- Se conserva el contenido anterior o un backup antes de sobrescribir.
- Se registra el resultado de cada escritura.

### RF-006 — Auditoría

El sistema debe registrar las acciones realizadas por el usuario y el agente.

**Criterios de aceptación:**

- Cada evento incluye fecha, usuario, solicitud, herramienta, destino y resultado.
- Los secretos nunca aparecen en los logs.
- Los registros pueden enviarse posteriormente a una plataforma centralizada.

## 7. Requisitos no funcionales

### Seguridad

- Autenticación obligatoria antes de usar el agente.
- Autorización por usuario, ambiente y herramienta.
- No ejecutar el proceso como root.
- `allowPrivilegeEscalation: false`.
- Filesystem de solo lectura cuando sea compatible.
- Secretos mediante Kubernetes Secret, Vault o equivalente.
- NetworkPolicy para limitar tráfico.
- Imagen proveniente de un registry autorizado.
- Escaneo de vulnerabilidades en CI/CD.

### Disponibilidad

- Health check en `/api/health`.
- Readiness y liveness probes en Kubernetes.
- Timeout para llamadas al modelo y herramientas.
- Manejo de reintentos sin duplicar operaciones de escritura.

### Rendimiento

- Tiempo de respuesta objetivo para consultas simples: menor de 10 segundos, excluyendo latencia del modelo.
- Límite de tamaño de mensajes y archivos.
- Límite de concurrencia configurable.

### Observabilidad

- Logs estructurados en JSON.
- Métricas HTTP, latencia, errores y uso de herramientas.
- Correlation ID por conversación y por ejecución.
- Integración futura con Prometheus, Grafana y Dynatrace.

## 8. Kubernetes y despliegue

El despliegue debe incluir:

- Namespace dedicado: `devops-ai`.
- Deployment del backend.
- Service interno tipo `ClusterIP`.
- Ingress o Gateway administrado por la plataforma.
- ServiceAccount dedicada.
- ClusterRole o Roles mínimos.
- Secret para la clave del modelo.
- ConfigMap para configuración no sensible.
- NetworkPolicy.
- Resource requests y limits.
- SecurityContext no privilegiado.

Para el entorno BSC, el acceso inicial recomendado es únicamente al clúster de desarrollo/QA. La promoción a producción debe seguir el proceso de Change Control y GitOps.

## 9. Variables de configuración

| Variable | Obligatoria | Descripción |
|---|---:|---|
| `OPENAI_API_KEY` | Sí | Credencial del proveedor LLM; debe venir de un Secret. |
| `MODEL` | Sí | Modelo utilizado por el agente. |
| `WORKSPACE_ROOT` | Sí | Directorio raíz autorizado para archivos. |
| `KUBERNETES_READ_ONLY` | Sí | Mantiene las operaciones K8s en modo lectura. |
| `ALLOWED_NAMESPACES` | Sí | Namespaces autorizados para consultas o cambios. |
| `AUDIT_LOG_LEVEL` | No | Nivel de detalle de auditoría. |
| `MAX_TOOL_RUNTIME_SECONDS` | No | Tiempo máximo de una herramienta. |

## 10. Flujo de una solicitud

1. El usuario inicia sesión.
2. Envía una solicitud desde el frontend.
3. El backend crea un `correlation_id`.
4. El agente clasifica la intención.
5. El agente propone una herramienta y sus parámetros.
6. El sistema valida autenticación, autorización y política.
7. Si existe riesgo de modificación, solicita confirmación.
8. Se ejecuta la herramienta con timeout.
9. Se registra la auditoría.
10. El agente presenta el resultado y las recomendaciones.

## 11. Estados de una ejecución

- `RECEIVED`: solicitud recibida.
- `PLANNED`: herramienta y parámetros propuestos.
- `WAITING_CONFIRMATION`: requiere aprobación.
- `AUTHORIZED`: política aprobada.
- `RUNNING`: herramienta en ejecución.
- `SUCCEEDED`: ejecución exitosa.
- `FAILED`: ejecución fallida.
- `CANCELLED`: cancelada por el usuario o política.
- `TIMEOUT`: excedió el tiempo permitido.

## 12. Pruebas requeridas

### Unitarias

- Validación de rutas.
- Validación de permisos.
- Clasificación de herramientas.
- Sanitización de logs.
- Manejo de errores del cliente Kubernetes.

### Integración

- Chat contra el backend.
- Consulta de pods en un clúster de prueba.
- Lectura y escritura dentro del workspace.
- Rechazo de rutas fuera del workspace.
- Rechazo de operaciones sin RBAC.

### Seguridad

- Path traversal.
- Inyección de comandos.
- Prompt injection en archivos y logs.
- Exposición de secretos.
- Acceso entre namespaces.
- Ejecución como root.
- Escalada de privilegios.

## 13. Fases de implementación

### Fase 1 — MVP conversacional

- Frontend de chat.
- API backend.
- Health check.
- Respuestas básicas.
- Docker Compose.

### Fase 2 — Herramientas de lectura

- `list_files`.
- `read_file`.
- `cluster_status`.
- `list_pods`.
- `get_workload`.
- `get_pod_logs`.

### Fase 3 — Escritura controlada

- `write_file`.
- Confirmaciones.
- Backups.
- Auditoría.
- Políticas por workspace.

### Fase 4 — Operaciones Kubernetes

- Aplicación de manifiestos.
- Dry-run obligatorio.
- Aprobación explícita.
- Restricción por namespace y ambiente.

### Fase 5 — Producción empresarial

- Entra ID/OIDC.
- RBAC por grupos.
- Secret manager.
- NetworkPolicy.
- Observabilidad.
- Escaneo de imágenes.
- Firma de imágenes.
- Integración GitOps y Change Control.

## 14. Definición de terminado del MVP

El MVP se considera terminado cuando:

- El frontend permite conversar con el backend.
- El backend se ejecuta mediante Docker.
- El health check responde correctamente.
- El proyecto se despliega en Kubernetes.
- El pod utiliza una ServiceAccount dedicada.
- El agente puede consultar recursos Kubernetes en modo lectura.
- El agente puede listar y leer archivos dentro del workspace.
- Las rutas fuera del workspace son rechazadas.
- Las pruebas automatizadas principales pasan.
- Existe documentación de instalación y configuración.
- No se almacenan secretos en el repositorio.
