# ArgoCD Apps Helm Chart

This Helm chart is a partial copy from the [official ArgoCD Helm chart](https://github.com/argoproj/argo-helm/tree/main/charts/argocd-apps), customized for the GCP HCP fleet management system.

## Overview

This chart enables deployment of highly configurable sets of ArgoCD `Applications` and `ApplicationSets` via Helm. It serves as the base template for the fleet generation system that creates ArgoCD resources across multiple environments, sectors, and regions.

## Usage

The chart accepts configuration through `values.yaml` files that define:

- **Applications**: Individual ArgoCD Applications with source, destination, and sync policies
- **ApplicationSets**: ArgoCD ApplicationSets for managing multiple applications with generators

### Configuration Structure

```yaml
applications:
  my-app:
    namespace: argocd
    project: default
    source:
      repoURL: https://github.com/example/repo.git
      targetRevision: HEAD
      path: manifests
    destination:
      server: https://kubernetes.default.svc
      namespace: my-namespace
    syncPolicy:
      automated:
        prune: true
        selfHeal: true

applicationsets:
  my-appset:
    namespace: argocd
    generators:
    - git:
        repoURL: https://github.com/example/repo.git
        revision: HEAD
        directories:
        - path: apps/*
    template:
      metadata:
        name: '{{path.basename}}'
      spec:
        project: default
        source:
          repoURL: https://github.com/example/repo.git
          targetRevision: HEAD
          path: '{{path}}'
        destination:
          server: https://kubernetes.default.svc
          namespace: '{{path.basename}}'
```

## Fleet Generation Integration

This chart is used by the fleet generation system (`hack/generate.py`) to create target-specific ArgoCD resources:

1. **Source Configuration**: Applications defined in `config/management-cluster/`
2. **Value Merging**: Base values merged with dimensional overrides (environment/sector/region)
3. **Template Processing**: This chart processes merged values via `helm template`
4. **Output**: Generated ArgoCD manifests placed in `rendered/` directory

See the [main project README](../README.md) for complete fleet management documentation.

## Example Values

For detailed configuration examples, see the [example values file](values-example.yaml) which demonstrates:

- Application source configurations (Git, Helm charts)
- Multi-source applications (ArgoCD v2.6+)
- Destination targeting and namespace creation
- Sync policies and automation settings
- ApplicationSet generators and templating
- Progressive sync strategies
