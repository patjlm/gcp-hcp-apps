# Requirements

## Fleet Architecture

### Hierarchy Structure

- **Environment**: integration, stage, production
- **Sector**: Deployment stage within environment (int-1, int-2, stage-1, stage-2, prod-canary, prod-1, prod-2, prod-3)
- **Region**: One or multiple Google Cloud regions per environment/sector
- **Cluster Type**: Different cluster types per region (management clusters, others)

### Target Clusters

- **Management Clusters**: Host hypershift-operator, prometheus, cert-manager
- **Other Cluster Types**: Different application sets per type (future requirement)

## Repository Architecture

### Source vs Target Structure

- **Source Definitions**: Simple, maintainable application definitions with environment overrides
- **Target Deployment Folders**: Generated manifests per environment/sector/region combination
- **Rationale**: Handles source manifest evolution (not just parameterization) when:
  - Adding/removing applications
  - Changing resource structures
  - Updating CRD schemas
  - Modifying deployment patterns

### Generation Process

- **Developer Workflow**: Manual generation command must be run before PR submission
- **PR Verification**: Automated checks ensure generation is current (no file changes when re-run)
- **Conflict Resolution**: Full regeneration (remove everything, recreate) eliminates drift
- **Audit Trail**: Git history tracks exact deployment manifests per target

## GitOps Deployment

### ArgoCD Configuration

- One ApplicationSet per cluster-type
- ApplicationSet targets subfolder matching environment/sector/region in this repository
- Cluster generator provides dynamic values via `valueObject` for helm template:
  - cluster-name
  - region
  - vpc-id
  - project-id
  - Additional cluster metadata

### Deployment Scope

- ArgoCD cluster deployed per environment/sector/region
- Each ArgoCD manages clusters within same scope/dimension
- Single Helm chart manages all applications for each cluster type

## Change Management

### Progressive Rollout

- Changes must progress through environment/sector/region hierarchy
- Not all clusters run same version simultaneously
- Separate deployment folder required per environment/sector/region combination

### Upgrade Workflow

1. Developer creates pull request for upgrade (e.g., hypershift-operator v2.1)
2. Developer runs generation command to create deployment folders
3. Pull request includes both source changes and regenerated deployment folders
4. PR checks verify generation is current (command produces no changes)
5. After merge, corresponding clusters apply changes automatically
6. External validation component checks upgrade success
7. Promotion to next target (automated or manual based on configuration)

### Promotion Configuration

- **YAML Configuration**: Promotion rules defined in repository
- **Example**: "int/sector-2 comes after int/sector-1 and gets promoted automatically"
- **Manual Gates**: Human approval required for critical transitions (e.g., integration → stage)
- **Automatic Progression**: Validation-gated advancement within environments

### Generation Command

- **Developer Responsibility**: Run before submitting PR
- **Idempotent**: Re-running on unchanged sources produces no file changes
- **Comprehensive**: Regenerates all target folders from source definitions
- **CI Verification**: Automated checks ensure command was executed

## Deployment Artifacts

### Configurability

- Artifacts must be configurable for target cluster
- Helm templates receive values from caller
- Values include local cluster information:
  - cluster-name
  - region
  - vpc-id
  - project-id
  - Additional metadata

### Duplication Avoidance

- Minimize information duplication across configurations
- Single source of truth for application definitions
- Environment-specific overrides only where necessary

## External Validation Component

### Change Detection

- Monitors repository for deployment folder changes
- Triggers validation tests for affected environment/sector/region
- Reports validation status back to promotion system

### Validation Process

- Runs health checks on deployed applications
- Executes integration tests specific to cluster type
- Validates application functionality and performance
- Blocks promotion pipeline on failure

### Promotion Integration

- Success enables next promotion step
- Failure stops promotion pipeline and raises alerts
- Status reporting for visibility into promotion state

## Monitoring and Drift Detection

### ArgoCD Metrics

- Monitor sync status across all applications
- Alert on drift between Git and cluster state
- Track deployment success/failure rates

### Operational Monitoring

- Health checks for ArgoCD instances per environment/sector/region
- Application-specific monitoring (hypershift-operator, prometheus, cert-manager)
- Promotion pipeline status and validation results

## Validation Requirements

### Promotion Gates

- External validation required after each promotion step
- Automated checks before proceeding to next target
- Blocking capability if validation fails
- Process stops and alerts raised on mid-pipeline failures

### Change Verification

- Verify successful application of changes
- Health checks for deployed applications
- Rollback capability if issues detected
- Integration with external validation component
