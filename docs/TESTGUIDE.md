# Test Guide: Patch Promotion Tool

## Overview

This guide provides comprehensive test scenarios to validate the patch promotion tool (`hack/promote.py`) works correctly in all real-world situations.

## Prerequisites

```bash
# Ensure you're in the repo root
cd /path/to/gcp-hcp-apps

# Tool is ready to use
uv run hack/promote.py --help
```

## Test Scenarios

### 1. Gap Detection Tests

These tests verify the tool correctly identifies promotion sequence violations.

#### 1.1 Region Gap Detection
**Setup**: Create a patch in region2 but skip region1
```bash
# Create the gap
mkdir -p config/management-cluster/test-app/integration/int-sector-1/europe-west1
cat > config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml << EOF
metadata:
  description: "Test region gap"
applications:
  test-app:
    source:
      targetRevision: "v1.0.0"
EOF

# Should detect gap
uv run hack/promote.py management-cluster test-app patch-001
# Expected: ERROR - missing from us-central1 (first region)
```

#### 1.2 Sector Gap Detection
**Setup**: Create a patch in sector2 but skip sector1
```bash
# Create the gap
mkdir -p config/management-cluster/test-app/integration/int-sector-2
cat > config/management-cluster/test-app/integration/int-sector-2/patch-002.yaml << EOF
metadata:
  description: "Test sector gap"
applications:
  test-app:
    source:
      targetRevision: "v1.1.0"
EOF

# Should detect gap
uv run hack/promote.py management-cluster test-app patch-002
# Expected: ERROR - missing from int-sector-1
```

#### 1.3 Environment Gap Detection
**Setup**: Create a patch in stage but skip integration
```bash
# Create the gap
mkdir -p config/management-cluster/test-app/stage/stage-sector-1
cat > config/management-cluster/test-app/stage/stage-sector-1/patch-003.yaml << EOF
metadata:
  description: "Test environment gap"
applications:
  test-app:
    source:
      targetRevision: "v1.2.0"
EOF

# Should detect gap
uv run hack/promote.py management-cluster test-app patch-003
# Expected: ERROR - missing from integration environment
```

#### 1.4 Real-World Gap (Current cert-manager)
```bash
# Should detect existing gap
uv run hack/promote.py management-cluster cert-manager patch-001
# Expected: ERROR - missing from production/prod-canary
```

### 2. Valid Promotion Tests

These tests verify successful promotion through the sequence.

#### 2.1 Region-to-Region Promotion
**Setup**: Start with first region, promote to second
```bash
# Create valid starting patch
mkdir -p config/management-cluster/test-app/integration/int-sector-1/us-central1
cat > config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-004.yaml << EOF
metadata:
  description: "Valid region start"
applications:
  test-app:
    source:
      targetRevision: "v2.0.0"
EOF

# Should promote successfully
uv run hack/promote.py management-cluster test-app patch-004
# Expected: Promotes to europe-west1
# Verify: Check config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-004.yaml exists
```

#### 2.2 Region-to-Sector Promotion (Last Region)
**Setup**: Complete all regions in a sector
```bash
# From previous test, we should have both regions
# Running again should promote to sector level with default promotion level logic
uv run hack/promote.py management-cluster test-app patch-004
# Expected: Promotes to int-sector-2 (next sector, respecting DEFAULT_PROMOTION_LEVEL)
```

#### 2.3 Sector-to-Sector Promotion
**Setup**: Test sector level promotion
```bash
# Create sector-level patch
mkdir -p config/management-cluster/test-app/integration/int-sector-1
cat > config/management-cluster/test-app/integration/int-sector-1/patch-005.yaml << EOF
metadata:
  description: "Sector level test"
applications:
  test-app:
    source:
      targetRevision: "v2.1.0"
EOF

# Should promote to next sector
uv run hack/promote.py management-cluster test-app patch-005
# Expected: Promotes to int-sector-2
```

#### 2.4 Environment-to-Environment Promotion
**Setup**: Test environment level promotion
```bash
# Create environment-level patch
mkdir -p config/management-cluster/test-app/integration
cat > config/management-cluster/test-app/integration/patch-006.yaml << EOF
metadata:
  description: "Environment level test"
applications:
  test-app:
    source:
      targetRevision: "v2.2.0"
EOF

# Should promote to next environment at default level (sector)
uv run hack/promote.py management-cluster test-app patch-006
# Expected: Promotes to stage/stage-sector-1 (first sector of next environment)
```

### 3. Default Promotion Level Tests

These tests verify the `DEFAULT_PROMOTION_LEVEL = "sectors"` behavior.

#### 3.1 Cross-Environment Promotion
```bash
# When promoting from environment level, should land at sector level
# (Covered in test 2.4 above)
```

#### 3.2 Skip Environment-Only Levels
```bash
# Tool should skip environment-only positions and land at sector level
# Create a scenario where next possible location is environment-only
# Verify it skips to first sector instead
```

### 4. Edge Cases

#### 4.1 No Patches Found
```bash
uv run hack/promote.py management-cluster nonexistent-app patch-999
# Expected: ERROR - patch not found
```

#### 4.2 Target Already Exists
**Setup**: Create duplicate target
```bash
# Create both source and target
mkdir -p config/management-cluster/test-app/integration/int-sector-1/{us-central1,europe-west1}
cat > config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-007.yaml << EOF
metadata:
  description: "Source patch"
applications:
  test-app:
    source:
      targetRevision: "v3.0.0"
EOF

cat > config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-007.yaml << EOF
metadata:
  description: "Target exists"
applications:
  test-app:
    source:
      targetRevision: "v3.1.0"
EOF

# Should fail - target exists
uv run hack/promote.py management-cluster test-app patch-007
# Expected: ERROR - target already exists
```

#### 4.3 End of Sequence
**Setup**: Patch at final location
```bash
# Create patch at final production location
mkdir -p config/management-cluster/test-app/production
cat > config/management-cluster/test-app/production/patch-008.yaml << EOF
metadata:
  description: "Final location"
applications:
  test-app:
    source:
      targetRevision: "v4.0.0"
EOF

# Should fail - no promotion target
uv run hack/promote.py management-cluster test-app patch-008
# Expected: ERROR - no promotion target found
```

### 5. Integration Tests

#### 5.1 Complete Promotion Flow
**Goal**: Test a complete patch lifecycle from region to final environment
```bash
# Start at first region
mkdir -p config/management-cluster/test-app/integration/int-sector-1/us-central1
cat > config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-flow.yaml << EOF
metadata:
  description: "Complete flow test"
applications:
  test-app:
    source:
      targetRevision: "v5.0.0"
EOF

# Promote multiple times and verify each step
uv run hack/promote.py management-cluster test-app patch-flow  # → europe-west1
uv run hack/promote.py management-cluster test-app patch-flow  # → int-sector-2
uv run hack/promote.py management-cluster test-app patch-flow  # → integration level
uv run hack/promote.py management-cluster test-app patch-flow  # → stage/stage-sector-1
# Continue until fully promoted...
```

#### 5.2 Multiple Applications
**Goal**: Verify tool works with different applications
```bash
# Test with existing applications
uv run hack/promote.py management-cluster argocd patch-test
uv run hack/promote.py management-cluster prometheus patch-test
uv run hack/promote.py management-cluster hypershift patch-test
```

### 6. Validation Steps

After each test:

1. **Verify File Creation**: Check that patch files are created in expected locations
2. **Verify File Content**: Ensure content is copied exactly
3. **Run Generation**: `make generate` should work without errors
4. **Check Git Status**: `git status` to see what files were created
5. **Cleanup**: Remove test files before next test

### 7. Automated Test Suite

Run the existing unit tests:
```bash
# Run all tests
uv run pytest hack/ -v

# Run just promotion tests
uv run pytest hack/test_promote.py -v
```

### 8. Performance Tests

For large configs:
```bash
# Time the gap detection on real data
time uv run hack/promote.py management-cluster cert-manager patch-001

# Should complete in < 1 second for typical configs
```

## Test Cleanup

After testing, clean up test files:
```bash
# Remove test patches
find config/ -name "*patch-00*.yaml" -path "*/test-app/*" -delete
find config/ -name "*patch-flow.yaml" -delete
find config/ -name "*patch-test.yaml" -delete

# Remove empty test directories
find config/ -type d -name "test-app" -exec rm -rf {} + 2>/dev/null || true
```

## Success Criteria

- ✅ All gap detection scenarios correctly identify violations
- ✅ All valid promotions succeed and create correct files
- ✅ Default promotion level behavior works as expected
- ✅ Edge cases handled gracefully with clear error messages
- ✅ Tool performance is acceptable (< 1 second)
- ✅ Generated files pass `make generate` validation
- ✅ Unit tests pass

## Notes

- The tool is designed to fail fast on gaps - this is correct behavior
- Default promotion level can be changed by modifying `DEFAULT_PROMOTION_LEVEL` in the code
- Real cert-manager patches have gaps that need to be fixed before promotion works
- Future enhancements may include consolidation and automated gap fixing