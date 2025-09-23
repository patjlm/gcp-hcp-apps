# GitOps Fleet Management System - Design Document

This document provides the complete technical specification for implementing a GitOps fleet management system that generates ArgoCD applications for multi-dimensional deployment hierarchies.

## Architecture Overview

### Repository Structure

The system uses a source-to-target generation pattern with clear separation between configuration and rendered output:

```
gcp-hcp-apps/
├── config/
│   ├── config.yaml                    # Global fleet configuration
│   ├── application-defaults.yaml      # Default Application values
│   ├── management-cluster/             # Cluster type organization
│   │   ├── hypershift-operator/
│   │   │   ├── OWNERS                  # Self-service ownership
│   │   │   ├── metadata.yaml           # Application metadata
│   │   │   ├── values.yaml             # Base values
│   │   │   ├── patches/                 # Version rollout patches
│   │   │   │   ├── patch-001.yaml
│   │   │   │   └── patch-002.yaml
│   │   │   ├── integration/             # Environment-based overrides
│   │   │   │   ├── values.yaml          # Environment-level override
│   │   │   │   ├── int-sector-1/
│   │   │   │   │   ├── values.yaml      # Sector-level override
│   │   │   │   │   ├── us-central1/
│   │   │   │   │   │   ├── values.yaml  # Region-level override
│   │   │   │   │   │   └── patches/
│   │   │   │   │   │       ├── patch-001.yaml
│   │   │   │   │   │       └── patch-002.yaml
│   │   │   │   │   └── europe-west1/
│   │   │   │   │       ├── values.yaml
│   │   │   │   │       └── patches/
│   │   │   │   │           └── patch-001.yaml
│   │   │   │   └── int-sector-2/
│   │   │   │       └── us-central1/
│   │   │   │           ├── values.yaml
│   │   │   │           └── patches/
│   │   │   │               └── patch-001.yaml
│   │   │   ├── stage/
│   │   │   │   ├── values.yaml
│   │   │   │   └── stage-sector-1/
│   │   │   │       ├── values.yaml
│   │   │   │       ├── us-east1/
│   │   │   │       │   ├── values.yaml
│   │   │   │       │   └── patches/
│   │   │   │       └── europe-west1/
│   │   │   │           ├── values.yaml
│   │   │   │           └── patches/
│   │   │   └── prod/
│   │   │       ├── values.yaml
│   │   │       ├── prod-canary/
│   │   │       │   ├── values.yaml
│   │   │       │   └── us-east1/
│   │   │       │       ├── values.yaml
│   │   │       │       └── patches/
│   │   │       ├── prod-sector-1/
│   │   │       │   ├── values.yaml
│   │   │       │   ├── us-east1/
│   │   │       │   │   ├── values.yaml
│   │   │       │   │   └── patches/
│   │   │       │   └── europe-east1/
│   │   │       │       ├── values.yaml
│   │   │       │       └── patches/
│   │   │       └── prod-sector-2/
│   │   │           └── europe-east1/
│   │   │               ├── values.yaml
│   │   │               └── patches/
│   │   ├── prometheus/
│   │   └── cert-manager/
│   └── regional-cluster/               # Different cluster type
│       ├── monitoring-agent/
│       └── log-collector/
├── rendered/                           # Generated output
│   ├── management-cluster/
│   │   ├── integration/int-sector-1/us-central1/
│   │   │   ├── Chart.yaml
│   │   │   ├── values.yaml             # Merged values
│   │   │   └── templates/
│   │   │       └── application.yaml    # ArgoCD Application template
│   │   ├── integration/int-sector-1/europe-west1/
│   │   └── stage/stage-sector-1/us-east1/
│   └── regional-cluster/
│       └── integration/int-sector-1/us-central1/
└── templates/                          # Base templates to copy
    ├── Chart.yaml
    ├── application.yaml                # Enhanced ArgoCD Application template
    └── values-example.yaml
```

### Data Flow

1. **Configuration Phase**: Teams maintain application configurations in `config/cluster-type/app-name/`
2. **Generation Phase**: Python generator merges values and copies templates to `rendered/`
3. **Deployment Phase**: ArgoCD ApplicationSets target appropriate `rendered/` subfolders
4. **Promotion Phase**: Patches advance through the dimensional hierarchy

### Component Relationships

```
ApplicationSet → Application → Helm Chart → Kubernetes Resources
     ↑              ↑              ↑
Cluster Generator  Generated    Application
     ↑            Templates      Repository
Fleet Config    ←  Generator  ←   (teams)
```

## Configuration Schema

### Global Configuration (`config/config.yaml`)

```yaml
# Fleet dimensional hierarchy
dimensions:
  - environments
  - sectors
  - regions

# Deployment sequence and promotion rules
sequence:
  environments:
    - name: integration
      sectors:
        - name: int-sector-1
          promotion: automated
          regions:
            - name: us-central1
            - name: europe-west1
        - name: int-sector-2
          promotion: automated
          regions:
            - name: us-central1
    - name: stage
      promotion: manual  # Gate between environments
      sectors:
        - name: stage-sector-1
          promotion: automated
          regions:
            - name: us-east1
            - name: europe-west1
    - name: prod
      promotion: manual
      sectors:
        - name: prod-canary
          promotion: automated
          regions:
            - name: us-east1
        - name: prod-sector-1
          promotion: manual
          regions:
            - name: us-east1
            - name: europe-east1

# Cluster type definitions
cluster_types:
  - name: management-cluster
    applications:
      - hypershift-operator
      - prometheus
      - cert-manager
  - name: regional-cluster
    applications:
      - monitoring-agent
      - log-collector
```

### Application Defaults

**Per Cluster Type**: `config/<cluster-type>/application-defaults.yaml`

**Management Cluster** (`config/management-cluster/application-defaults.yaml`):

```yaml
# Default values for management cluster applications
defaults:
  project: platform
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  syncPolicy:
    automated:
      prune: false  # Prevent accidental resource deletion
      selfHeal: true
    syncOptions:
      - CreateNamespace=true
  destination:
    name: "{{`{{name}}`}}"  # Target cluster from ApplicationSet
    namespace: argocd
  # No ignoreDifferences by default - applications must be explicit
```

**Regional Cluster** (`config/regional-cluster/application-defaults.yaml`):

```yaml
# Default values for regional cluster applications
defaults:
  project: workloads
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
  syncPolicy:
    automated:
      prune: false  # Prevent accidental resource deletion
      selfHeal: true   # Enforce GitOps - revert manual changes
    syncOptions:
      - CreateNamespace=true
  destination:
    name: "{{`{{name}}`}}"  # Target cluster from ApplicationSet
    namespace: argocd
  # No ignoreDifferences by default - applications must be explicit
```

### Application Metadata (`config/cluster-type/app-name/metadata.yaml`)

```yaml
name: hypershift-operator
description: "Hypershift operator for managing hosted clusters"
owners:
  - team-platform@example.com
```

### Application Values (`config/cluster-type/app-name/values.yaml`)

```yaml
# Base configuration for hypershift-operator
applications:
  hypershift-operator:
    # ArgoCD source configuration
    source:
      repoURL: https://github.com/openshift/hypershift.git
      targetRevision: "v4.17.0"
      path: install/charts/hypershift-operator
      helm:
        valuesObject:
          image:
            tag: "v4.17.0"
          resources:
            requests:
              cpu: 100m
              memory: 128Mi
          # Cluster values injected by ApplicationSet
          cluster:
            region: "{{`{{.Values.cluster.region}}`}}"
            projectId: "{{`{{.Values.cluster.projectId}}`}}"
            vpcId: "{{`{{.Values.cluster.vpcId}}`}}"

    # Deployment destination
    destination:
      namespace: hypershift

    # Application-specific configuration
    syncPolicy:
      syncOptions:
        - CreateNamespace=true
        - ServerSideApply=true

    ignoreDifferences:
      - group: hypershift.openshift.io
        kind: HostedCluster
        jsonPointers:
          - /status
```

### Override Values

Override files follow the same structure but only include changed values:

**Environment Override** (`config/cluster-type/app-name/production/values.yaml`):

```yaml
applications:
  hypershift-operator:
    source:
      helm:
        valuesObject:
          resources:
            requests:
              cpu: 500m
              memory: 512Mi
            limits:
              cpu: 1000m
              memory: 1Gi
```

**Region Override** (`config/cluster-type/app-name/europe-west1/values.yaml`):

```yaml
applications:
  hypershift-operator:
    source:
      helm:
        valuesObject:
          cluster:
            region: "europe-west1"
          backup:
            enabled: true
            schedule: "0 2 * * *"
```

### Strategic Merge Patches

Patches enable controlled version rollouts across dimensions:

**Version Patch** (`config/cluster-type/app-name/patches/patch-001.yaml`):

```yaml
metadata:
  id: "hypershift-v4.18-rollout"
  description: "Upgrade hypershift-operator to v4.18.0"
  dependencies:
    - /cert-manager/version: "v1.13.0"  # JSON path matching
    - /prometheus/ready: true
  merge_strategy:
    # Default is 'replace' for all fields
    # Override for specific paths that should append to lists
    "/hypershift-operator/syncPolicy/syncOptions": "append"
    "/hypershift-operator/ignoreDifferences": "append"

# Strategic merge patch content
patch:
  hypershift-operator:
    source:
      targetRevision: "v4.18.0"
      helm:
        valuesObject:
          image:
            tag: "v4.18.0"
    syncPolicy:
      syncOptions:
        - ServerSideApply=true  # Will append to existing options
    ignoreDifferences:
      - group: hypershift.openshift.io  # Will append to existing ignore rules
        kind: HostedClusterVersion
        jsonPointers:
          - /status
```

## Generation Process

### Python Generator Implementation

The generator is implemented as a self-contained Python script using `uv` for dependency management:

**Core Dependencies**:

- `pyyaml` - YAML parsing and generation
- `jsonpath-ng` - Dependency evaluation
- `click` - CLI interface

**Generation Algorithm**:

1. **Discovery**: Scan `config/` to find all cluster-type/application combinations
2. **Dimensional Matrix**: Generate all environment/sector/region combinations from global config
3. **Patch State Resolution**: For each application, determine which patches are active for each environment/sector/region based on promotion state
4. **Value Merging**: For each app/dimension combination:
   - Load cluster-type defaults (`config/cluster-type/application-defaults.yaml`)
   - Load base application values (`values.yaml`)
   - Apply environment override (if exists)
   - Apply sector override (if exists)
   - Apply region override (if exists)
   - Apply active patches for this dimension (from `patches/` folder)
5. **Template Rendering**: Copy templates and generate final `values.yaml`
6. **Validation**: Verify generated content against schema

**Patch Progression**: Patches defined in `config/cluster-type/app-name/patches/` are applied to specific environment/sector/region combinations based on the current promotion state. The same patch moves through the dimensional hierarchy as validation succeeds:

- `patch-001.yaml` starts in `integration/int-sector-1/us-central1/`
- After validation, progresses to `integration/int-sector-1/europe-west1/`
- Eventually reaches `prod/prod-sector-1/us-east1/`

### Value Merging Strategy

**Deep Merge Algorithm**:

```python
def deep_merge(base_dict, override_dict, merge_strategy=None, path=""):
    """Recursively merge override values into base dictionary."""
    for key, value in override_dict.items():
        current_path = f"{path}/{key}" if path else key

        if key in base_dict and isinstance(base_dict[key], dict) and isinstance(value, dict):
            deep_merge(base_dict[key], value, merge_strategy, current_path)
        elif key in base_dict and isinstance(base_dict[key], list) and isinstance(value, list):
            # Check merge strategy for this path
            strategy = merge_strategy.get(current_path, "replace") if merge_strategy else "replace"
            if strategy == "append":
                base_dict[key].extend(value)
            else:  # replace
                base_dict[key] = value
        else:
            base_dict[key] = value
    return base_dict
```

**Patch Lifecycle Management**:

```python
def validate_patch_completion(patch_id, applied_dimensions, all_dimensions):
    """Check if patch has rolled out to all target dimensions."""
    if set(applied_dimensions) == set(all_dimensions):
        raise ValidationError(
            f"Patch {patch_id} has been applied to all dimensions. "
            f"It should be promoted to base application values and removed from patches/. "
            f"This prevents configuration drift and simplifies maintenance."
        )
```

**Merge Precedence** (later values override earlier):

1. Application defaults (`config/application-defaults.yaml`)
2. Base application values (`values.yaml`)
3. Environment override
4. Sector override
5. Region override
6. Active patches (in dependency order)

### Dependency Resolution

Patches can declare dependencies on specific application states using JSON path matching:

```yaml
dependencies:
  - /cert-manager/version: "v1.13.0"
  - /prometheus/ready: true
  - /hypershift-operator/source/targetRevision: ">=v4.17.0"
```

The generator evaluates these dependencies against the current fleet state before applying patches.

## Template System

### Enhanced Application Template

The ArgoCD Application template is enhanced to support all required fields:

```yaml
{{- range $appName, $appData := .Values.applications }}
---
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  {{- with $appData.additionalAnnotations }}
  annotations:
    {{- range $key, $value := . }}
    {{ $key }}: {{ $value | quote }}
    {{- end }}
  {{- end }}
  {{- with $appData.additionalLabels }}
  labels:
    {{- toYaml . | nindent 4 }}
  {{- end }}
  name: {{ $appName }}
  {{- with $appData.namespace }}
  namespace: {{ . }}
  {{- end }}
  {{- with $appData.finalizers }}
  finalizers:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  project: {{ tpl $appData.project $ }}

  {{- with $appData.source }}
  source:
    {{- toYaml . | nindent 4 }}
  {{- end }}

  {{- with $appData.sources }}
  sources:
    {{- toYaml . | nindent 4 }}
  {{- end }}

  destination:
    {{- toYaml $appData.destination | nindent 4 }}

  {{- with $appData.syncPolicy }}
  syncPolicy:
    {{- toYaml . | nindent 4 }}
  {{- end }}

  {{- with $appData.revisionHistoryLimit }}
  revisionHistoryLimit: {{ . }}
  {{- end }}

  {{- with $appData.ignoreDifferences }}
  ignoreDifferences:
    {{- toYaml . | nindent 4 }}
  {{- end }}

  {{- with $appData.info }}
  info:
    {{- toYaml . | nindent 4 }}
  {{- end }}
{{- end }}
```

### Cluster Value Injection Challenge

**Problem**: ApplicationSets inject cluster metadata (region, projectId, vpcId, etc.) that applications need to reference in their helm values, but the templating mechanics are complex.

**Technical Challenge**:

1. ApplicationSet processes `{{cluster.region}}` → creates static Application with `cluster.region: "us-east1"`
2. ArgoCD processes this Application → targets our rendered Helm chart repository
3. **Our Helm chart** needs to process application values containing `"{{ .Values.cluster.region }}"` → resolve to `"us-east1"`
4. Final Application gets created with resolved values for target workload charts

**Current Implementation Gap**:
The ArgoCD Application template uses `{{- toYaml $appData.source.helm.valuesObject | nindent 8 }}` which outputs YAML structures as literal text. **Helm template expressions within YAML values are NOT processed** - they remain as literal strings like `"{{ .Values.cluster.region }}"`.

**Unresolved Design Decision**:
How can applications dynamically reference ApplicationSet-injected values without:

- Forcing standardized variable names (`cluster.region`) on all teams
- Requiring complex template preprocessing in the generator
- Breaking the clean separation between config and rendering

**Potential Approaches**:

1. **Escaped Templating** (Most Promising):
   Applications use escaped Helm templates in their values:

   ```yaml
   # In config/management-cluster/hypershift-operator/values.yaml
   hypershift-operator:
     source:
       helm:
         valuesObject:
           myregionvar: "{{`{{.Values.cluster.region}}`}}"
           myprojectvar: "{{`{{.Values.cluster.projectId}}`}}"
           version: "v4.18.0"
   ```

   **Flow**:
   - Generator preserves escaped templates (doesn't process Helm syntax)
   - Our chart template processes with `toYaml` → resolves escaping
   - Final Application contains `"{{.Values.cluster.region}}"` for target chart
   - ApplicationSet-injected cluster values become available as `.Values.cluster.*`

   **Benefits**: Applications control variable naming, no forced conventions
   **Critical Dependency**: ApplicationSet must properly inject cluster data into helm context

2. **Value File Separation**: ApplicationSet injects via separate valueFiles
3. **Generator Preprocessing**: Run `helm template` during generation with cluster placeholders
4. **Accept Limitation**: Applications use static values, no dynamic cluster injection

**Status**: Escaped templating (#1) appears most viable but **REQUIRES THOROUGH TESTING** to validate:

- ApplicationSet cluster value injection mechanics
- Helm template processing order and context
- End-to-end cluster value flow from ApplicationSet → target charts

This approach should be prototyped extensively before implementation to ensure the templating mechanics work as designed.

## Operational Workflows

### Developer Workflow

1. **Make Changes**: Modify application configuration in `config/cluster-type/app-name/`
2. **Generate**: Run `./generate.py` to update `rendered/` folders
3. **Validate**: Verify no unintended changes in generated output
4. **Submit PR**: Include both config changes and generated output
5. **CI Validation**: Automated checks ensure generation is current

### Version Rollout Process

1. **Create Patch**: Add new patch file with version updates and dependencies
2. **Generate**: Run generator to apply patch to appropriate dimensions
3. **Review**: Verify patch is applied only to expected targets
4. **Deploy**: Merge to trigger ArgoCD sync
5. **Validate**: External validation component checks deployment health
6. **Promote**: Manual or automated progression to next dimension

### ApplicationSet Configuration

Each cluster type requires an ApplicationSet that targets the appropriate rendered folders:

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
metadata:
  name: management-cluster-apps
  namespace: argocd
spec:
  generators:
    - clusters:
        selector:
          matchLabels:
            cluster-type: management-cluster
        values:
          environment: "{{metadata.labels.environment}}"
          sector: "{{metadata.labels.sector}}"
          region: "{{metadata.labels.region}}"

  template:
    metadata:
      name: "{{name}}-apps"
    spec:
      project: platform
      source:
        repoURL: https://github.com/your-org/gcp-hcp-apps.git
        targetRevision: HEAD
        path: "rendered/management-cluster/{{values.environment}}/{{values.sector}}/{{values.region}}"
        helm:
          valuesObject:
            cluster:
              name: "{{name}}"
              region: "{{metadata.labels.region}}"
              projectId: "{{metadata.labels.projectId}}"
              vpcId: "{{metadata.labels.vpcId}}"
      destination:
        server: "{{server}}"
        namespace: argocd
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
```

### CI/CD Integration

**Pre-commit Validation**:

```bash
# Ensure generation is current
./generate.py --dry-run --validate
if [ $? -ne 0 ]; then
  echo "Generated files are not current. Run ./generate.py"
  exit 1
fi
```

**PR Checks**:

- Schema validation for all YAML files
- OWNERS file validation for changed applications
- Dependency graph validation
- Template rendering verification

## Implementation Details

### File Structure Requirements

**Generated Helm Chart** (`rendered/cluster-type/env/sector/region/`):

```
Chart.yaml          # Standard Helm chart metadata
values.yaml         # Merged application values
templates/
  application.yaml  # ArgoCD Application template
```

**Chart.yaml Template**:

```yaml
apiVersion: v2
name: {{ cluster_type }}-apps
description: ArgoCD applications for {{ cluster_type }} in {{ environment }}/{{ sector }}/{{ region }}
version: 1.0.0
```

### Generator CLI Interface

```bash
# Generate all targets
./generate.py

# Generate specific cluster type
./generate.py --cluster-type management-cluster

# Generate specific dimension combination
./generate.py --environment prod --sector sector-1

# Dry run validation
./generate.py --dry-run --validate

# Apply specific patch
./generate.py --apply-patch patch-001
```

### Validation Requirements

1. **Config Validation**: JSON Schema validation for all configuration files
2. **Dependency Validation**: Ensure patch dependencies can be resolved
3. **Template Validation**: Verify generated templates render correctly
4. **Conflict Detection**: Check for overlapping patches or configuration conflicts
5. **Ownership Validation**: Ensure changes respect OWNERS file permissions

### Error Handling

- **Missing Dependencies**: Clear error messages when patch dependencies cannot be satisfied
- **Merge Conflicts**: Detailed reporting when value overrides conflict
- **Template Errors**: Validation of generated Helm templates before writing
- **Schema Violations**: Specific validation errors with file locations and fixes

This design provides the complete specification needed to implement the GitOps fleet management system with clear separation of concerns, robust value merging, and comprehensive operational workflows.
