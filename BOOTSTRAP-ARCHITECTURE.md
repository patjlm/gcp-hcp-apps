# ArgoCD Bootstrap Architecture

## Executive Summary

This document describes the ArgoCD App of Apps pattern implementation for bootstrapping workloads with minimal initial configuration. The goal is to deploy a single root application that can auto-update itself, manage ArgoCD components, and pull additional applications for multi-cluster environments.

## The Bootstrap Challenge

### Problem Statement

When deploying ArgoCD to manage a Kubernetes cluster, you face a classic "chicken and egg" problem:

- **Initial Bootstrap**: You need minimal ArgoCD configuration deployed via external tooling (Terraform, Helm, kubectl)
- **Self-Management**: Once running, ArgoCD should manage its own updates and configuration
- **Application Management**: ArgoCD should discover and deploy applications from Git repositories
- **Multi-Cluster Support**: The same pattern should work across dev/stage/prod environments with different configurations

### Key Requirements

1. **Minimal Bootstrap**: Deploy only essential ArgoCD components initially
2. **Self-Updating**: Root application updates itself from Git changes
3. **ArgoCD Management**: Manage ArgoCD operator, server, and controller updates
4. **Application Discovery**: Automatically deploy applications from repository structure
5. **Environment Flexibility**: Support different configurations per cluster
6. **Team Collaboration**: Enable multiple teams to manage their applications independently

## Architecture Analysis

### Option A: Pure ApplicationSet

**Architecture**:
```
ApplicationSet (List Generator)
├── prometheus: chart=kube-prometheus-stack, version=77.9.1
├── cert-manager: chart=cert-manager, version=v1.18.2
└── argocd: chart=argo-cd, version=5.46.0
```

**Pros**:
- Simple, direct approach
- No intermediate layers
- Clear Helm chart references

**Cons**:
- All apps defined in single ApplicationSet file
- Multi-team collaboration challenges
- Harder to manage per-environment differences

### Option B: Traditional App of Apps (CHOSEN)

**Architecture**:
```
Root Helm Chart
├── Chart.yaml
├── values.yaml (default)
├── values-dev.yaml
├── values-prod.yaml
└── templates/
    ├── argocd-app.yaml          → Application → Helm: argo-cd
    ├── prometheus-app.yaml      → Application → Helm: kube-prometheus-stack
    ├── cert-manager-app.yaml    → Application → Helm: cert-manager
    └── root-app.yaml            → Application → Self-reference (GitOps)
```

**Pros**:
- ✅ One file per application (team ownership)
- ✅ Helm chart enables multi-cluster with different parameters
- ✅ Progressive rollouts across environments
- ✅ Extensible to any workload type (Helm, Kustomize, plain manifests)
- ✅ Proven ArgoCD pattern

**Cons**:
- Slightly more complex initial setup
- Requires Helm knowledge for root app management

### Option C: Config-Based ApplicationSet

**Architecture**:
```
ApplicationSet + Git File Generator
├── configs/argocd.yaml         → Parameters → Generated Application
├── configs/prometheus.yaml     → Parameters → Generated Application
└── configs/cert-manager.yaml   → Parameters → Generated Application
```

**Pros**:
- Configuration-driven
- One file per app
- Flexible parameter handling

**Cons**:
- Primarily suited for Helm charts
- Less flexible for mixed workload types
- More complex templating logic

## Chosen Solution: Traditional App of Apps

### Why This Approach

1. **Team Collaboration**: Each team owns their application file
2. **Multi-Cluster Ready**: Helm chart with environment-specific values
3. **Progressive Rollouts**: Deploy changes across clusters incrementally
4. **Technology Agnostic**: Supports Helm, Kustomize, plain manifests
5. **GitOps Self-Management**: Root app can update itself and ArgoCD

### Multi-Cluster Bootstrap Flow

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Dev Cluster   │    │  Stage Cluster  │    │  Prod Cluster   │
├─────────────────┤    ├─────────────────┤    ├─────────────────┤
│ Terraform       │    │ Terraform       │    │ Terraform       │
│ Bootstrap       │    │ Bootstrap       │    │ Bootstrap       │
│     ↓           │    │     ↓           │    │     ↓           │
│ Root Helm App   │    │ Root Helm App   │    │ Root Helm App   │
│ (values-dev)    │    │ (values-stage)  │    │ (values-prod)   │
│     ↓           │    │     ↓           │    │     ↓           │
│ Applications:   │    │ Applications:   │    │ Applications:   │
│ • ArgoCD        │    │ • ArgoCD        │    │ • ArgoCD        │
│ • Prometheus    │    │ • Prometheus    │    │ • Prometheus    │
│ • cert-manager  │    │ • cert-manager  │    │ • cert-manager  │
│ • Monitoring    │    │ • Monitoring    │    │ • Security      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Self-Management Flow

```
┌─────────────────┐
│   Git Commit    │
│ (update app)    │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│  Root App       │
│  Detects Change │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│  Updates Self   │
│  & Child Apps   │
└─────┬───────────┘
      │
      ▼
┌─────────────────┐
│  Syncs Changes  │
│  to Cluster     │
└─────────────────┘
```

## Repository Structure

```
gcp-hcp-apps/
├── README.md
├── BOOTSTRAP-ARCHITECTURE.md
├── management-clusters/
│   ├── Chart.yaml                    # Root Helm chart
│   ├── values.yaml                   # Default values
│   ├── values-dev.yaml               # Dev cluster overrides
│   ├── values-stage.yaml             # Stage cluster overrides
│   ├── values-prod.yaml              # Prod cluster overrides
│   └── templates/
│       ├── argocd-app.yaml           # ArgoCD self-management
│       ├── prometheus-app.yaml       # Prometheus Application
│       ├── cert-manager-app.yaml     # cert-manager Application
│       ├── ingress-app.yaml          # Ingress controller Application
│       └── root-app.yaml             # Self-managing root Application
└── docs/
    └── application-templates/        # Templates for teams
```

## Implementation Guide

### 1. Root Helm Chart Configuration

**Chart.yaml**:
```yaml
apiVersion: v2
name: management-cluster-apps
description: Root application for bootstrapping and managing cluster applications
version: 1.0.0
```

**values.yaml** (defaults):
```yaml
global:
  destination:
    server: https://kubernetes.default.svc
  source:
    repoURL: https://github.com/your-org/gcp-hcp-apps.git
    targetRevision: main
  environment: dev

applications:
  argocd:
    enabled: true
    chart: argo-cd
    repoURL: https://argoproj.github.io/argo-helm
    version: "5.46.0"
    namespace: argocd
    values:
      server:
        service:
          type: ClusterIP

  prometheus:
    enabled: true
    chart: kube-prometheus-stack
    repoURL: https://prometheus-community.github.io/helm-charts
    version: "77.9.1"
    namespace: monitoring

  certManager:
    enabled: true
    chart: cert-manager
    repoURL: oci://quay.io/jetstack/charts
    version: "v1.18.2"
    namespace: cert-manager
```

**values-dev.yaml** (dev environment):
```yaml
global:
  environment: dev

applications:
  argocd:
    version: "5.46.0"  # Latest for dev
    values:
      controller:
        replicas: 1
      server:
        replicas: 1

  prometheus:
    version: "77.9.1"  # Latest for testing
    values:
      grafana:
        persistence:
          enabled: false
```

**values-prod.yaml** (production environment):
```yaml
global:
  environment: prod

applications:
  argocd:
    version: "5.45.0"  # Stable version
    values:
      controller:
        replicas: 2
      server:
        replicas: 2
        ingress:
          enabled: true

  prometheus:
    version: "77.8.0"  # Stable version
    values:
      grafana:
        persistence:
          enabled: true
          size: 50Gi
```

### 2. Application Templates

**templates/argocd-app.yaml** (ArgoCD self-management):
```yaml
{{- if .Values.applications.argocd.enabled }}
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: argocd
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    chart: {{ .Values.applications.argocd.chart }}
    repoURL: {{ .Values.applications.argocd.repoURL }}
    targetRevision: {{ .Values.applications.argocd.version }}
    helm:
      releaseName: argocd
      values: |
{{- .Values.applications.argocd.values | toYaml | nindent 8 }}
  destination:
    server: {{ .Values.global.destination.server }}
    namespace: {{ .Values.applications.argocd.namespace }}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
{{- end }}
```

**templates/root-app.yaml** (Self-management):
```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root-management-cluster-apps
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default
  source:
    repoURL: {{ .Values.global.source.repoURL }}
    targetRevision: {{ .Values.global.source.targetRevision }}
    path: management-clusters
    helm:
      valueFiles:
        - values-{{ .Values.global.environment }}.yaml
  destination:
    server: {{ .Values.global.destination.server }}
    namespace: argocd
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

### 3. Bootstrap Process

**Initial Deployment** (via Terraform):
```hcl
resource "kubernetes_manifest" "root_application" {
  manifest = yamldecode(templatefile("${path.module}/root-app.yaml", {
    environment = var.environment
    git_repo    = var.git_repository
  }))

  lifecycle {
    ignore_changes = ["all"]
    prevent_destroy = true
  }
}
```

**Subsequent Updates** (via GitOps):
1. Teams commit application changes to Git
2. Root application detects repository changes
3. Root application updates itself and child applications
4. ArgoCD syncs all changes to cluster

## Team Collaboration Workflow

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  Platform   │    │   Team A    │    │   Team B    │
│    Team     │    │ (Prometheus)│    │(cert-manager)│
├─────────────┤    ├─────────────┤    ├─────────────┤
│ Manages:    │    │ Manages:    │    │ Manages:    │
│ • Root app  │    │ • prometheus│    │ • cert-mgr  │
│ • ArgoCD    │    │   -app.yaml │    │   -app.yaml │
│ • Values    │    │ • Monitoring│    │ • Security  │
│   files     │    │   config    │    │   policies  │
└─────────────┘    └─────────────┘    └─────────────┘
        │                  │                  │
        └──────────────────┼──────────────────┘
                           │
                           ▼
                   ┌─────────────┐
                   │   Git Repo  │
                   │             │
                   │ Pull Request│
                   │   Review    │
                   │             │
                   │ Auto Deploy │
                   └─────────────┘
```

## Benefits

✅ **Minimal Bootstrap**: Single Terraform resource creates root application
✅ **Self-Updating**: Root app and ArgoCD update themselves from Git
✅ **Team Autonomy**: Each team manages their applications independently
✅ **Multi-Cluster**: Different configurations per environment
✅ **Progressive Rollouts**: Deploy changes incrementally across clusters
✅ **Technology Agnostic**: Supports Helm, Kustomize, plain manifests
✅ **Operational Safety**: Automated sync with human oversight via Git

This architecture provides a robust foundation for GitOps-based cluster management while maintaining simplicity in the bootstrap process and flexibility for ongoing operations.