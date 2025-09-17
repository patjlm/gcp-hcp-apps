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

### Initial Bootstrap (via Terraform)

Deploy the root application that will manage all other applications:

```hcl
resource "kubernetes_manifest" "root_application" {
  manifest = yamldecode(templatefile("${path.module}/root-app.yaml", {
    environment = var.environment
    git_repo    = "https://github.com/patjlm/gcp-hcp-apps.git"
  }))
}
```

### Environment-Specific Deployments

The Helm chart automatically selects the appropriate values file based on the environment:

- **Dev**: Uses `values-dev.yaml` (latest versions, minimal resources)
- **Prod**: Uses `values-prod.yaml` (stable versions, HA configuration)

### Self-Management Flow

1. Make changes to application configurations in Git
2. Root application detects repository changes automatically
3. Root application updates itself and child applications
4. ArgoCD syncs all changes to the cluster

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