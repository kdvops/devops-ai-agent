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
empresarial. Kubernetes permanece en modo de solo lectura por defecto.

## Despliegue Kubernetes

1. Construye y publica la imagen, y sustituye `image` en `app/k8s/deployment.yaml`.
2. Ajusta `ALLOWED_NAMESPACES` en `app/k8s/configmap.yaml`.
3. Aplica los manifiestos:

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
`.github/workflows/container.yml` publica la imagen en GHCR; actualiza el tag
de `app/k8s/deployment.yaml` mediante un cambio revisado en Git antes de que
Argo CD despliegue una nueva versión.
