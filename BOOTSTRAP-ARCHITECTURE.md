# GitOps Fleet Management Architecture

## Overview

This document describes the GitOps fleet management system for GCP HCP management clusters. The system uses a source-to-target generation pattern to manage deployment of applications across multi-dimensional hierarchies (environment/sector/region) to management clusters.

## Fleet Generation Architecture

### 1. Source Configuration
```
config/
├── config.yaml                      # Fleet dimensional hierarchy definition
└── management-cluster/               # Cluster type configuration
    ├── application-defaults.yaml     # Default ArgoCD Application settings
    └── {app-name}/                   # Individual application directories
        ├── metadata.yaml             # Application metadata
        ├── values.yaml               # Base application configuration
        ├── {environment}/override.yaml # Permanent dimensional overrides
        └── {environment}/patch-*.yaml  # Temporary rolling changes
```

### 2. Fleet Generation Process
```
hack/generate.py
├── Discovers targets from config.yaml dimensional matrix
├── Merges values with precedence: defaults → base → environment overrides
├── Processes templates via helm template
└── Generates ArgoCD Applications per target
```

### 3. Generated Target Structure
```
rendered/
└── management-cluster/
    └── {environment}/{sector}/{region}/
        ├── Chart.yaml                # Helm chart metadata
        ├── values.yaml               # Aggregated configuration
        └── templates/                # Individual ArgoCD Applications
            ├── argocd.yaml
            ├── prometheus.yaml
            ├── cert-manager.yaml
            └── hypershift.yaml
```

## Repository Structure

```
gcp-hcp-apps/
├── config/                           # Source configuration
│   ├── config.yaml                   # Fleet dimensional hierarchy
│   └── management-cluster/           # Cluster type organization
│       ├── application-defaults.yaml # Default ArgoCD settings
│       ├── argocd/                   # ArgoCD self-management
│       │   ├── metadata.yaml
│       │   ├── values.yaml
│       │   └── production/override.yaml
│       ├── prometheus/               # Monitoring stack
│       │   ├── metadata.yaml
│       │   ├── values.yaml
│       │   └── production/override.yaml
│       ├── cert-manager/             # Certificate management
│       │   ├── metadata.yaml
│       │   └── values.yaml
│       └── hypershift/               # Hypershift operator
│           ├── metadata.yaml
│           └── values.yaml
├── rendered/                         # Generated ArgoCD Applications
│   └── management-cluster/
│       ├── integration/int-sector-1/us-central1/
│       ├── integration/int-sector-2/us-central1/
│       ├── stage/stage-sector-1/us-east1/
│       └── production/prod-sector-1/us-east1/
├── templates/                        # Base Helm templates
│   ├── Chart.yaml                    # Template chart definition
│   ├── argocd-resources.yaml         # ArgoCD Application and ApplicationSet template
│   └── values-example.yaml           # Example values structure
├── hypershift/                       # Raw YAML manifests
│   ├── hypershift-dev.yaml           # Generated from hypershift binary
│   └── README.md                     # Generation instructions
├── hack/                             # Development tools
│   ├── generate.py                   # Fleet generator script
│   └── test_generate.py              # Comprehensive test suite
├── Makefile                          # Build targets (generate, test, check)
└── BOOTSTRAP-ARCHITECTURE.md         # This document
```

## Key Components

### Fleet Configuration (config/)
- **config.yaml**: Defines the dimensional hierarchy (environments, sectors, regions) and cluster types
- **application-defaults.yaml**: Common ArgoCD Application settings applied to all applications
- **{app}/values.yaml**: Base application configuration with Helm chart references
- **{app}/{env}/override.yaml**: Permanent dimensional overrides for production stability
- **{app}/{env}/patch-*.yaml**: Temporary rolling changes

### Fleet Generator (hack/generate.py)
- **Target Discovery**: Scans config.yaml to generate all dimensional combinations
- **Value Merging**: Deep merges configuration with precedence: defaults → base → environment
- **Template Processing**: Uses helm template to generate final ArgoCD Applications
- **Validation**: Ensures generated manifests are valid and consistent

### Generated Targets (rendered/)
- **Dimensional Structure**: Each environment/sector/region combination gets its own directory
- **Application Manifests**: Individual ArgoCD Application YAML files per application
- **Aggregated Values**: Combined configuration for the specific target
- **Helm Metadata**: Chart.yaml for potential direct helm deployment

### Application Templates (templates/)
- **argocd-resources.yaml**: Generic ArgoCD Application and ApplicationSet template supporting both Helm charts and raw manifests
- **Chart.yaml**: Template chart definition for helm processing
- **values-example.yaml**: Documentation of expected values structure

## Fleet Deployment Flow

### 1. Configuration Changes
```
Developer modifies config/management-cluster/prometheus/production/override.yaml or creates patch files
├── Updates production-specific Prometheus configuration
└── Environment-specific overrides for production clusters
```

### 2. Generation
```
make generate
├── Runs hack/generate.py
├── Discovers all targets from dimensional matrix
├── Merges values for each target with proper precedence
└── Generates updated ArgoCD Applications in rendered/
```

### 3. GitOps Deployment
```
ArgoCD ApplicationSets (external to this repo)
├── Watch rendered/ directory for changes
├── Match clusters using dimensional labels
├── Deploy applications with cluster-specific values injection
└── Progressive rollout through dimensional hierarchy
```

### 4. Value Injection at Deployment
```
Cluster metadata injected at deployment time:
├── {{ .Values.cluster.name }}       # Target cluster name
├── {{ .Values.cluster.region }}     # GCP region
├── {{ .Values.cluster.projectId }}  # GCP project ID
└── {{ .Values.cluster.vpcId }}      # VPC identifier
```

## Dimensional Hierarchy

The fleet supports multi-dimensional deployment patterns defined in config.yaml:

```yaml
sequence:
  environments:
    - name: integration        # Development/testing environment
      sectors:
        - name: int-sector-1   # Isolated failure domains
          regions: [us-central1, europe-west1]
    - name: stage
      promotion: manual        # Validation gate
      sectors:
        - name: stage-sector-1
          regions: [us-east1, europe-west1]
    - name: production
      promotion: manual        # Production gate
      sectors:
        - name: prod-canary    # Canary deployment
          regions: [us-east1]
        - name: prod-sector-1  # Full production
          regions: [us-east1, europe-east1]
```

## Promotion and Validation

- **Automated Progression**: Changes flow through integration automatically
- **Manual Gates**: Staging and production require explicit promotion
- **Environment Overrides**: Production uses stable versions and enhanced resources
- **Dimensional Isolation**: Failures contained within sectors/regions

## Benefits

✅ **Source-Driven**: All configuration in version-controlled source files
✅ **Multi-Dimensional**: Supports complex deployment hierarchies
✅ **Environment Consistency**: Same applications deployed across all targets
✅ **Production Safety**: Environment-specific overrides for stability
✅ **GitOps Native**: Generated manifests committed for full audit trail
✅ **Technology Agnostic**: Supports Helm charts and raw Kubernetes manifests
✅ **Validation Built-in**: Comprehensive test suite and make check for CI/CD
✅ **Progressive Rollouts**: Changes advance through dimensional hierarchy with gates