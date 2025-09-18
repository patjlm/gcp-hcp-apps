# GCP HCP Apps

ArgoCD applications for the GCP HCP project using the Traditional App of Apps pattern.

## Architecture

This repository implements the Traditional App of Apps pattern with a root Helm chart that manages all cluster applications, including ArgoCD itself. This enables:

- **Self-updating**: Root app and ArgoCD update themselves from Git changes
- **Multi-environment support**: Different configurations per environment (dev/prod)
- **Team collaboration**: Each application is managed via individual templates
- **Progressive rollouts**: Deploy changes incrementally across environments

## Repository Structure

```
management-clusters/
├── Chart.yaml                    # Root Helm chart
├── values.yaml                   # Default values
├── values-dev.yaml               # Dev environment overrides
├── values-prod.yaml              # Production environment overrides
└── templates/
    ├── argocd-app.yaml           # ArgoCD self-management
    ├── prometheus-app.yaml       # Prometheus Application
    ├── cert-manager-app.yaml     # cert-manager Application
    └── root-app.yaml             # Self-managing root Application
```

## Usage

### Bootstrap Flow

**Two-stage bootstrap process for clean GitOps handoff:**

**Stage 1: Terraform Bootstrap**
- Creates ArgoCD namespace and operator
- Creates cluster metadata ConfigMap
- Deploys minimal root application (no valueFiles, no computed values)
- All applications start `enabled: false` by default

**Stage 2: ArgoCD Self-Configuration**
- Root app looks up cluster metadata from ConfigMap
- Dynamically includes environment-specific valueFiles (`values-dev.yaml`, etc.)
- Injects cluster metadata (project_id, region, vpc_network_id, etc.) to all apps
- Triggers deployment of all applications with correct configuration

### Environment Detection

The root application automatically determines the environment from the cluster metadata ConfigMap and loads the appropriate configuration:

- **Dev**: `values-dev.yaml` (latest versions, minimal resources)
- **Prod**: `values-prod.yaml` (stable versions, HA configuration)

### Self-Management Flow

1. Terraform creates infrastructure and minimal root app
2. ArgoCD syncs root app, which self-configures from cluster metadata
3. All applications deploy with dynamic cluster values
4. Future Git changes automatically sync via ArgoCD

## Adding New Applications

1. **Create template**: Add a new template file in `templates/` directory
2. **Configure values**: Add application configuration to `values.yaml`
3. **Environment overrides**: Add environment-specific settings in `values-dev.yaml` and `values-prod.yaml`
4. **Commit**: Changes are automatically deployed via GitOps

### Example Application Template

```yaml
{{- if .Values.applications.myapp.enabled }}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: myapp
  namespace: argocd
spec:
  source:
    chart: {{ .Values.applications.myapp.chart }}
    repoURL: {{ .Values.applications.myapp.repoURL }}
    targetRevision: {{ .Values.applications.myapp.version }}
  destination:
    server: {{ .Values.global.destination.server }}
    namespace: {{ .Values.applications.myapp.namespace }}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
{{- end }}
```
