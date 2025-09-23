# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the **gcp-hcp-apps** repository - A GitOps fleet management system for the GCP HCP (Google Cloud Platform Hypershift Container Platform) project. It implements a source-to-target generation pattern that manages deployment of applications across multi-dimensional hierarchies (environment/sector/region) to management clusters including ArgoCD, Prometheus, cert-manager, and the Hypershift operator.

## Repository Architecture

### Core Structure

- **config/**: Source configuration with dimensional hierarchy
  - `config.yaml`: Global fleet configuration defining environments/sectors/regions
  - `management-cluster/`: Cluster type organization
    - `application-defaults.yaml`: Default ArgoCD Application settings
    - `{app-name}/`: Individual application configuration
      - `metadata.yaml`: Application metadata and ownership
      - `values.yaml`: Base application configuration
      - `{environment}/values.yaml`: Environment-specific overrides
- **rendered/**: Generated ArgoCD Applications (auto-generated, committed)
  - `management-cluster/{environment}/{sector}/{region}/`: Target-specific manifests
    - `Chart.yaml`: Helm chart metadata
    - `values.yaml`: Aggregated configuration for target
    - `templates/{app-name}.yaml`: Individual ArgoCD Application manifests
- **templates/**: Base Helm templates for generation
  - `Chart.yaml`: Template chart definition
  - `application.yaml`: ArgoCD Application template
- **hack/**: Development tools and scripts
  - `generate.py`: Python fleet generator with uv dependencies
  - `test_generate.py`: Comprehensive test suite
- **Makefile**: Build targets (generate, test, check)

### Generation Flow

1. **Source Configuration**: Applications defined in `config/` with base values and environment overrides
2. **Target Discovery**: Generator discovers all dimensional combinations from `config.yaml`
3. **Value Merging**: Deep merge with precedence: defaults → base → environment overrides
4. **Helm Processing**: Templates processed via `helm template` to generate final ArgoCD Applications
5. **Output**: Individual application files created in `rendered/` hierarchy

### Deployment Flow

1. **ApplicationSets**: Consume generated manifests from `rendered/` directory
2. **Cluster Targeting**: ApplicationSets use cluster labels to match dimensional targets
3. **Value Injection**: Cluster metadata (name, region, projectId) injected at deployment time
4. **Progressive Rollouts**: Changes advance through dimensional hierarchy with validation gates

## Common Commands

### Fleet Generation

```bash
# Generate all ArgoCD applications
make generate

# Run comprehensive test suite
make test

# Check that generated files are current (CI/CD)
make check

# Manual generation
uv run hack/generate.py

# Manual testing
uv run hack/test_generate.py -v
```

### Development Workflow

```bash
# 1. Modify configuration
vim config/management-cluster/prometheus/values.yaml

# 2. Generate updated manifests
make generate

# 3. Validate changes
git diff rendered/

# 4. Run tests
make test

# 5. Commit both source and generated changes
git add config/ rendered/
git commit -m "Update prometheus configuration"
```

### Repository Validation

```bash
# Validate YAML syntax across repository
find . -name "*.yaml" -o -name "*.yml" | xargs -I {} yaml-lint {}

# Validate generated ArgoCD Applications
kubectl --dry-run=client apply -f rendered/management-cluster/production/prod-sector-1/us-east1/templates/
```

## Key Configuration Patterns

### Adding New Applications

1. **Create Application Directory**:

   ```bash
   mkdir -p config/management-cluster/my-app
   ```

2. **Add Metadata** (`config/management-cluster/my-app/metadata.yaml`):

   ```yaml
   name: my-app
   description: "Application description"
   owners:
     - team-platform@example.com
   ```

3. **Configure Base Values** (`config/management-cluster/my-app/values.yaml`):

   ```yaml
   applications:
     my-app:
       source:
         repoURL: https://charts.example.com
         targetRevision: "1.0.0"
         chart: my-app
       destination:
         namespace: my-namespace
       syncPolicy:
         syncOptions:
           - CreateNamespace=true
   ```

4. **Add to Fleet Configuration** (`config/config.yaml`):

   ```yaml
   cluster_types:
     - name: management-cluster
       applications:
         - argocd
         - prometheus
         - cert-manager
         - hypershift
         - my-app  # Add here
   ```

5. **Generate and Test**:

   ```bash
   make generate
   make test
   ```

### Environment Overrides

Create environment-specific configurations for production stability:

```bash
# Production overrides
mkdir -p config/management-cluster/my-app/production
cat > config/management-cluster/my-app/production/values.yaml << EOF
applications:
  my-app:
    source:
      targetRevision: "0.9.0"  # Stable version
      helm:
        valuesObject:
          replicas: 3
          resources:
            requests:
              memory: "1Gi"
              cpu: "500m"
EOF
```

### Dimensional Configuration

The fleet hierarchy supports any dimensional structure defined in `config.yaml`:

```yaml
sequence:
  environments:
    - name: integration
      sectors:
        - name: int-sector-1
          regions: [us-central1, europe-west1]
    - name: stage
      promotion: manual  # Validation gate
      sectors:
        - name: stage-sector-1
          regions: [us-east1, europe-west1]
    - name: production
      promotion: manual
      sectors:
        - name: prod-sector-1
          regions: [us-east1, europe-east1]
```

### Value Injection Patterns

Use template syntax for cluster-specific values:

```yaml
applications:
  my-app:
    destination:
      name: '{{ .Values.cluster.name }}'
      namespace: my-namespace
    source:
      helm:
        valuesObject:
          cluster:
            region: '{{ .Values.cluster.region }}'
            projectId: '{{ .Values.cluster.projectId }}'
            vpcId: '{{ .Values.cluster.vpcId }}'
```

### Promotion Flow

Changes progress through dimensions with validation gates:

1. **Integration**: `integration/int-sector-1/us-central1` (future auto-promotion)
2. **Staging**: `stage/stage-sector-1/us-east1` (manual gate)
3. **Production**: `production/prod-sector-1/us-east1` (manual gate)

External validation systems and automated promotion are planned but not yet implemented.

## Technical Implementation Details

### Generator Algorithm

1. **Discovery**: Scan `config/` to find all cluster-type/application combinations
2. **Dimensional Matrix**: Generate all environment/sector/region combinations from `config.yaml`
3. **Value Merging**: For each app/dimension combination:
   - Load cluster-type defaults (`application-defaults.yaml`)
   - Load base application values (`values.yaml`)
   - Apply environment/sector/region overrides (if exist)
4. **Template Processing**: Create temporary Helm charts and run `helm template`
5. **Validation**: Verify generated content and fail fast on errors

### CI/CD Integration

- **Pre-commit**: Ensure generation is current before PR submission
- **PR Validation**: Automated checks verify `make generate` produces no changes
- **Schema Validation**: YAML syntax validation across repository
- **Template Validation**: Ensure generated ArgoCD Applications are valid

### Conflict Resolution

- **Full Regeneration**: Remove everything, recreate eliminates drift
- **Idempotent Generation**: Re-running on unchanged sources produces no file changes
- **Audit Trail**: Git tracks exact deployment manifests per target

### Repository Evolution

This system handles both configuration changes and structural evolution:

- **Adding/removing applications**: Update `config.yaml` and regenerate
- **Changing resource structures**: Modify templates and regenerate all targets
- **Updating CRD schemas**: Templates adapt automatically via Helm processing
- **Modifying deployment patterns**: Generator ensures consistency across all dimensions

## Architecture Context

This repository implements a multi-tier architecture:

- **Regional Clusters**: Infrastructure management
- **Management Clusters**: Hypershift hosting (this repository manages these)
- **Customer Clusters**: Hypershift-managed hosted clusters

## Security Rules

### Global security rules for all projects 🛡️

### Security Principles

- **Complete Mediation:** Ensure every access request is validated and authorized. No bypasses allowed.
- **Compromise Recording:** Implement mechanisms to detect, record, and respond to security breaches.
- **Defense in Depth:** Use multiple, layered security controls to protect systems and data.
- **Economy of Mechanism:** Keep designs simple and easy to understand. Avoid unnecessary complexity.
- **Least Common Mechanism:** Minimize shared resources and isolate components to reduce risk.
- **Least Privilege:** Grant only the minimum permissions necessary for users and systems.
- **Open Design:** Favor transparency and well-understood mechanisms over security by obscurity.
- **Psychological Acceptability:** Make security controls user-friendly and aligned with user expectations.
- **Secure by Design, Default, Deployment (SD3):** Ship with secure defaults, deny by default, and avoid hardcoded credentials.

### Security Controls

- **Authentication:** Use strong, standard authentication methods. Require authentication for all non-public areas. Store credentials securely and enforce password policies. Use multi-factor authentication where possible.
- **Authorization:** Enforce least privilege and explicit permissions. Use a single, trusted component for authorization checks. Deny by default and audit permissions regularly.
- **Encryption:** Encrypt all network traffic and data at rest where applicable. Use approved certificates and protocols.
- **Logging:** Log security events centrally. Do not log sensitive data. Restrict log access and monitor for suspicious activity.
- **Networking:** Encrypt all communications. Do not expose unnecessary endpoints or ports. Restrict network access to only what is required.

Apply these rules to all code, infrastructure, and processes to maintain a strong security posture across your projects.

## Secure coding rules for Helm charts ⎈

- Check for vulnerable dependencies and validate chart provenance.
- Secure configuration and manage secrets outside of values.yaml.
- Use tools like checkov for security scanning.
