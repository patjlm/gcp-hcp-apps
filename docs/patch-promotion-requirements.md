# Requirements Document: Patch Promotion Tool (`hack/promote.py`)

## Overview

Create a simple, lean tool to automate the progressive promotion of patches through the multi-dimensional fleet hierarchy. The tool should enable safe, controlled rollouts by copying patches between dimensional levels and consolidating them when appropriate.

## Current System Analysis

### Dimensional Hierarchy (from `config/config.yaml`)
```
Environment (integration → stage → production)
├── Sector (int-sector-1, int-sector-2, stage-sector-1, prod-canary, prod-sector-1)
│   └── Region (us-central1, europe-west1, us-east1, europe-east1, ap-east1)
```

### Existing Patch Locations
- **Environment level**: `config/management-cluster/{app}/{environment}/patch-{NNN}.yaml`
- **Sector level**: `config/management-cluster/{app}/{environment}/{sector}/patch-{NNN}.yaml`
- **Region level**: `config/management-cluster/{app}/{environment}/{sector}/{region}/patch-{NNN}.yaml`

### Available Applications
- argocd, cert-manager, hypershift, prometheus

## Functional Requirements

### Core Promotion Logic

#### Command Interface
```bash
uv run hack/promote.py management-cluster hypershift patch-001
```

#### Promotion Rules
1. **Find Latest Patch**: Automatically finds the furthest patch in the sequence
2. **Gap Detection**: Fail if patches exist in later positions without earlier ones
3. **Default Level Promotion**: Promotes to sector level (configurable) when crossing environments
4. **Simple Copy**: Copies patch to next valid location in sequence

#### Complete Promotion Scenarios

**Scenario 1: Region-to-Region within Same Sector**
```
Current: env1/sector1/region1/patch.yaml
Next:    env1/sector1/region2/patch.yaml
```

**Scenario 2: Region-to-Sector (with future consolidation)**
```
Current: env1/sector1/region2/patch.yaml (last region in sector)
Next:    env1/sector2/patch.yaml (next sector at default level)
Future:  Consolidate env1/sector1/*/patch.yaml → env1/sector1/patch.yaml
```

**Scenario 3: Sector-to-Sector within Same Environment**
```
Current: env1/sector1/patch.yaml
Next:    env1/sector2/patch.yaml
```

**Scenario 4: Sector-to-Environment-to-Sector (with future consolidation)**
```
Current: env1/sector2/patch.yaml (last sector in environment)
Next:    env2/sector1/patch.yaml (first sector of next environment)
Future:  Consolidate env1/**/patch.yaml → env1/patch.yaml
```

**Scenario 5: Environment-to-Environment**
```
Current: env1/patch.yaml
Next:    env2/sector1/patch.yaml (first sector of next environment)
```

**Scenario 6: Final Integration (future)**
```
Current: env3/patch.yaml (last environment)
Future:  Consolidate to app/values.yaml (permanent integration)
```

#### Gap Detection Rules

**A gap exists when patches skip positions in the sequence:**

- `env1/sector1/region2/patch.yaml` exists but `env1/sector1/region1/patch.yaml` missing
- `env1/sector2/patch.yaml` exists but `env1/sector1/patch.yaml` missing
- `env2/**/patch.yaml` exists but no patches in `env1`

**Gap detection prevents promotion until sequence is fixed.**

### Phase 2: Parameterized Promotion (Future Enhancement)

#### Extended Command Interface
```bash
hack/promote.py management-cluster hypershift patch-001 --level=region
hack/promote.py management-cluster hypershift patch-001 --level=sector  # default
hack/promote.py management-cluster hypershift patch-001 --level=environment
```

## Technical Requirements

### Input Validation
- Verify cluster-type exists (`management-cluster`)
- Verify application exists in config directory
- Verify patch file exists somewhere in the hierarchy
- Validate patch file syntax (basic YAML validation)

### File Operations
- **Copy**: Preserve exact file content and metadata description
- **Cleanup**: Remove redundant patch files after consolidation
- **Safety**: Never overwrite existing patch files (fail with clear error)

### Discovery Algorithm
1. **Scan Hierarchy**: Find all existing instances of the specified patch
2. **Parse Sequence**: Load `config.yaml` and understand promotion paths
3. **Calculate Next Step**: Determine target location based on current position
4. **Validate Target**: Ensure target location is valid and doesn't already exist

### Consolidation Algorithm
1. **Inventory Check**: For each parent dimension, check if ALL children have the patch
2. **Promote to Parent**: Copy patch to parent level when all children covered
3. **Cleanup Children**: Remove all child-level patches after successful parent promotion
4. **Cascade Check**: Repeat consolidation check at next parent level

## Error Handling

### Validation Errors
- **Missing patch**: "ERROR: patch-001.yaml not found for hypershift in any dimension"
- **Invalid application**: "ERROR: Application 'hypershift-operator' not found. Available: argocd, cert-manager, hypershift, prometheus"
- **Target exists**: "ERROR: Target patch already exists at config/management-cluster/hypershift/integration/int-sector-2/patch-001.yaml"

### Edge Cases
- **Multiple patch locations**: Show all locations, require user to specify source location
- **Sequence gaps**: Handle missing intermediate dimensions gracefully
- **Manual promotion gates**: Respect promotion policies in `config.yaml`

## Output Requirements

### Verbose Output
```bash
$ hack/promote.py management-cluster hypershift patch-001
Found patch: config/management-cluster/hypershift/integration/int-sector-1/patch-001.yaml
Target: config/management-cluster/hypershift/integration/int-sector-2/patch-001.yaml
✓ Copied patch successfully

Checking consolidation opportunities...
✓ All sectors in 'integration' environment now have patch-001
✓ Consolidated to environment level: config/management-cluster/hypershift/integration/patch-001.yaml
✓ Removed sector-level patches: int-sector-1, int-sector-2

Next promotion target: config/management-cluster/hypershift/stage/patch-001.yaml
```

### Integration with Existing Workflow
- **Generate after promotion**: Automatically run `make generate` after successful promotion
- **Validation**: Run basic validation to ensure generated files are consistent

## Implementation Plan

### Phase 1: MVP (Current Request)
1. Parse command line arguments (cluster-type, application, patch-name)
2. Load and parse `config.yaml` for sequence information
3. Implement patch discovery across hierarchy
4. Implement basic sector-to-sector promotion logic
5. Implement consolidation detection and execution
6. Add comprehensive error handling and validation

### Phase 2: Enhancement
1. Add `--level` parameter for flexible promotion levels
2. Add dry-run mode (`--dry-run`)
3. Add interactive mode for ambiguous cases
4. Integration with `make generate` and git workflows

## File Structure Impact

### Before Promotion
```
config/management-cluster/hypershift/
├── values.yaml
├── integration/
│   └── int-sector-1/
│       └── patch-001.yaml
└── stage/
    └── stage-sector-1/
```

### After Promotion
```
config/management-cluster/hypershift/
├── values.yaml
├── integration/
│   └── patch-001.yaml              # Consolidated
└── stage/
    └── stage-sector-1/
        └── patch-001.yaml          # Promoted
```

This approach ensures safe, progressive rollouts while maintaining the existing patch lifecycle patterns established in the CLAUDE.md documentation.