#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml", "pytest"]
# ///

"""
Unit tests for patch promotion tool.

Run with: uv run pytest hack/test_promote.py -v
"""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Add the hack directory to Python path so we can import promote
sys.path.insert(0, os.path.dirname(__file__))

import promote


class MockConfig:
    """Mock Config class for testing."""

    def __init__(self, config_dict, root_path):
        self.config = config_dict
        self.dimensions = tuple(config_dict["dimensions"])
        self.sequence = config_dict["sequence"]
        self.cluster_types = config_dict.get("cluster_types", [])
        self.root = root_path

    def path(self, cluster_type: str, application: str = None) -> Path:
        if application is None:
            return self.root / cluster_type
        return self.root / cluster_type / application


def create_test_config():
    """Create a simple test configuration."""
    return {
        "dimensions": ["environments", "sectors", "regions"],
        "sequence": {
            "environments": [
                {
                    "name": "env1",
                    "sectors": [
                        {
                            "name": "sector1",
                            "regions": [{"name": "region1"}, {"name": "region2"}],
                        },
                        {"name": "sector2", "regions": [{"name": "region1"}]},
                    ],
                },
                {
                    "name": "env2",
                    "sectors": [{"name": "sector1", "regions": [{"name": "region1"}]}],
                },
            ]
        },
    }


def create_test_filesystem(base_dir, patches):
    """Create test filesystem with patches at specified locations."""
    app_dir = base_dir / "config" / "management-cluster" / "test-app"

    for patch_location in patches:
        patch_dir = app_dir / Path(*patch_location.split("/"))
        patch_dir.mkdir(parents=True, exist_ok=True)
        (patch_dir / "patch-001.yaml").write_text("test: patch")

    return app_dir


def test_gap_detection_no_gaps():
    """Test gap detection with proper sequence - no gaps."""
    config = create_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create first patch - should be valid (no previous siblings)
        patches = ["env1/sector1/region1"]
        create_test_filesystem(base_dir, patches)

        # Mock the config object
        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            # Should detect no gaps
            os.chdir(base_dir)
            # Get patches and test gap detection
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            # No exception should be raised for valid sequence
            promote.detect_gaps(all_patches)


def test_gap_detection_region_gap():
    """Test gap detection with missing region - should detect gap."""
    config = create_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in region2 but missing region1 - this is a gap!
        patches = ["env1/sector1/region2"]
        create_test_filesystem(base_dir, patches)

        # Mock the config object
        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Get patches and test gap detection
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            # Should raise ValueError for gap
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "env1/sector1/region2" in gap_error
            assert "env1/sector1/region1" in gap_error


def test_gap_detection_sector_gap():
    """Test gap detection with missing sector - should detect gap."""
    config = create_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in sector2 but missing sector1 - this is a gap!
        patches = ["env1/sector2"]
        create_test_filesystem(base_dir, patches)

        # Mock the config object
        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Get patches and test gap detection
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            # Should raise ValueError for gap
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "env1/sector2" in gap_error
            assert "env1/sector1" in gap_error


def test_gap_detection_environment_gap():
    """Test gap detection with missing environment - should detect gap."""
    config = create_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in env2 but missing env1 - this is a gap!
        patches = ["env2/sector1"]
        create_test_filesystem(base_dir, patches)

        # Mock the config object
        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Get patches and test gap detection
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            # Should raise ValueError for gap
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "env2" in gap_error
            assert "env1" in gap_error


def test_walk_function():
    """Test what the walk function actually generates."""
    config = create_test_config()

    # Test all possible walk paths
    all_paths = list(
        promote.walk_dimensions(config["sequence"], tuple(config["dimensions"]))
    )

    expected_paths = [
        ("env1",),
        ("env1", "sector1"),
        ("env1", "sector1", "region1"),
        ("env1", "sector1", "region2"),
        ("env1", "sector2"),
        ("env1", "sector2", "region1"),
        ("env2",),
        ("env2", "sector1"),
        ("env2", "sector1", "region1"),
    ]

    assert all_paths == expected_paths


def create_real_test_config():
    """Create realistic test configuration matching the actual fleet."""
    return {
        "dimensions": ["environments", "sectors", "regions"],
        "sequence": {
            "environments": [
                {
                    "name": "integration",
                    "sectors": [
                        {
                            "name": "int-sector-1",
                            "regions": [
                                {"name": "us-central1"},
                                {"name": "europe-west1"},
                            ],
                        },
                        {"name": "int-sector-2", "regions": [{"name": "us-central1"}]},
                    ],
                },
                {
                    "name": "stage",
                    "sectors": [
                        {"name": "stage-sector-1", "regions": [{"name": "us-east1"}]},
                        {
                            "name": "stage-sector-2",
                            "regions": [{"name": "europe-west1"}],
                        },
                    ],
                },
                {
                    "name": "production",
                    "sectors": [
                        {"name": "prod-canary", "regions": [{"name": "us-east1"}]},
                        {
                            "name": "prod-sector-1",
                            "regions": [{"name": "us-east1"}, {"name": "europe-east1"}],
                        },
                    ],
                },
            ]
        },
    }


def test_real_config_gap_detection_region_gap():
    """Test region gap detection with realistic config."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in europe-west1 but missing us-central1 - this is a gap!
        patches = ["integration/int-sector-1/europe-west1"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "integration/int-sector-1/europe-west1" in gap_error
            assert "integration/int-sector-1/us-central1" in gap_error


def test_real_config_gap_detection_sector_gap():
    """Test sector gap detection with realistic config."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in int-sector-2 but missing int-sector-1 - this is a gap!
        patches = ["integration/int-sector-2"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "integration/int-sector-2" in gap_error
            assert "integration/int-sector-1/us-central1" in gap_error


def test_real_config_gap_detection_environment_gap():
    """Test environment gap detection with realistic config."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in stage but missing integration - this is a gap!
        patches = ["stage"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            with pytest.raises(ValueError) as exc_info:
                promote.detect_gaps(all_patches)

            gap_error = str(exc_info.value)
            assert "stage" in gap_error
            assert "integration/int-sector-1/us-central1" in gap_error


def test_valid_region_to_region_promotion():
    """Test valid region-to-region promotion."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in first region
        patches = ["integration/int-sector-1/us-central1"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should not raise any errors (no gaps)
            promote.detect_gaps(all_patches)

            # Should promote to next region
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml"
            )
            assert next_location == expected


def test_valid_region_to_sector_promotion():
    """Test valid promotion from last region in sector to next sector."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches in both regions of first sector
        patches = [
            "integration/int-sector-1/us-central1",
            "integration/int-sector-1/europe-west1",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should not raise any errors (no gaps)
            promote.detect_gaps(all_patches)

            # Should promote to next sector (respecting DEFAULT_PROMOTION_LEVEL)
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            )
            assert next_location == expected


def test_valid_sector_to_sector_promotion():
    """Test valid sector-to-sector promotion."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create sector-level patch
        patches = ["integration/int-sector-1"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should not raise any errors (no gaps)
            promote.detect_gaps(all_patches)

            # Should promote to next sector
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            )
            assert next_location == expected


def test_valid_environment_to_environment_promotion():
    """Test valid cross-environment promotion."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create environment-level patch
        patches = ["integration"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should not raise any errors (no gaps)
            promote.detect_gaps(all_patches)

            # Should promote to next environment at default level (sector)
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/stage/stage-sector-1/patch-001.yaml"
            )
            assert next_location == expected


def test_no_patches_found():
    """Test error when no patches exist."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create empty filesystem (no patches)
        app_dir = base_dir / "config" / "management-cluster" / "test-app"
        app_dir.mkdir(parents=True, exist_ok=True)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            assert len(all_patches) == 0


def test_end_of_sequence():
    """Test end of sequence detection."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches throughout the entire sequence to reach the final position
        patches = [
            "integration",
            "stage/stage-sector-1",
            "stage/stage-sector-2",
            "production/prod-canary",
            "production/prod-sector-1/us-east1",
            "production/prod-sector-1/europe-east1",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should not raise any errors (no gaps)
            promote.detect_gaps(all_patches)

            # Should return None for end of sequence
            next_location = promote.get_next_location(all_patches)
            assert next_location is None


def test_complete_promotion_flow():
    """Test complete promotion flow through all steps."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)

            # Step 1: Start with first region
            patches = ["integration/int-sector-1/us-central1"]
            create_test_filesystem(base_dir, patches)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml"
            )
            assert next_location == expected

            # Step 2: Add second region, should promote to next sector
            patches.append("integration/int-sector-1/europe-west1")
            create_test_filesystem(base_dir, patches)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            )
            assert next_location == expected

            # Step 3: Add sector, should promote to cross-environment
            patches.append("integration/int-sector-2")
            create_test_filesystem(base_dir, patches)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )
            next_location = promote.get_next_location(all_patches)
            expected = (
                base_dir
                / "config/management-cluster/test-app/stage/stage-sector-1/patch-001.yaml"
            )
            assert next_location == expected


def test_coalesce_patches_region_to_sector():
    """Test coalescing region-level patches to sector level."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches at both regions in a sector
        patches = [
            "integration/int-sector-1/us-central1",
            "integration/int-sector-1/europe-west1",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce to sector level
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify sector-level patch was created
            sector_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            )
            assert sector_patch.exists()

            # Verify region-level patches were removed
            region1_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-001.yaml"
            )
            region2_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml"
            )
            assert not region1_patch.exists()
            assert not region2_patch.exists()


def test_coalesce_patches_sector_to_environment():
    """Test coalescing sector-level patches to environment level."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches at both sectors in an environment
        patches = [
            "integration/int-sector-1",
            "integration/int-sector-2",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce to environment level
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify environment-level patch was created
            env_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/patch-001.yaml"
            )
            assert env_patch.exists()

            # Verify sector-level patches were removed
            sector1_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            )
            sector2_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            )
            assert not sector1_patch.exists()
            assert not sector2_patch.exists()


def test_coalesce_patches_mixed_levels():
    """Test coalescing with patches at different levels (region + sector)."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches: complete coverage of one sector + full sector coverage
        patches = [
            "integration/int-sector-1/us-central1",  # Region level
            "integration/int-sector-1/europe-west1",  # Complete int-sector-1 coverage
            "integration/int-sector-2",  # Sector level (covers all int-sector-2)
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce to environment level since both sectors are covered
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify environment-level patch was created
            env_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/patch-001.yaml"
            )
            assert env_patch.exists()

            # Verify original patches were removed
            region_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-001.yaml"
            )
            sector_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            )
            assert not region_patch.exists()
            assert not sector_patch.exists()


def test_coalesce_patches_incomplete_coverage():
    """Test that coalescing doesn't happen with incomplete coverage."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch at only one region (incomplete sector coverage)
        patches = [
            "integration/int-sector-1/us-central1",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should NOT coalesce since europe-west1 is missing
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify original patch still exists
            region_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-001.yaml"
            )
            assert region_patch.exists()

            # Verify no sector-level patch was created
            sector_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            )
            assert not sector_patch.exists()


def test_coalesce_patches_already_at_higher_level():
    """Test that coalescing skips when higher level patch already exists."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches: regions + sector level already exists
        patches = [
            "integration/int-sector-1",  # Sector level (higher)
            "integration/int-sector-1/us-central1",  # Region level (redundant)
            "integration/int-sector-1/europe-west1",  # Region level (redundant)
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should skip coalescing since sector level already exists
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify sector-level patch still exists
            sector_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            )
            assert sector_patch.exists()

            # Region patches should still exist (not removed by coalescing)
            region1_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-001.yaml"
            )
            region2_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml"
            )
            assert region1_patch.exists()
            assert region2_patch.exists()


def test_coalesce_patches_cross_environment():
    """Test coalescing across multiple environments."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches covering all sectors in integration and stage
        patches = [
            "integration/int-sector-1",
            "integration/int-sector-2",
            "stage/stage-sector-1",
            "stage/stage-sector-2",
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce each environment separately
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify environment-level patches were created
            int_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/patch-001.yaml"
            )
            stage_patch = (
                base_dir / "config/management-cluster/test-app/stage/patch-001.yaml"
            )
            assert int_patch.exists()
            assert stage_patch.exists()

            # Verify sector-level patches were removed
            assert not (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            ).exists()
            assert not (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-2/patch-001.yaml"
            ).exists()
            assert not (
                base_dir
                / "config/management-cluster/test-app/stage/stage-sector-1/patch-001.yaml"
            ).exists()
            assert not (
                base_dir
                / "config/management-cluster/test-app/stage/stage-sector-2/patch-001.yaml"
            ).exists()


def test_coalesce_patches_partial_cross_environment():
    """Test that cross-environment coalescing doesn't happen with partial coverage."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches: complete integration, partial stage
        patches = [
            "integration/int-sector-1",
            "integration/int-sector-2",
            "stage/stage-sector-1",  # Missing stage-sector-2
        ]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce integration only
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify integration was coalesced
            int_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/patch-001.yaml"
            )
            assert int_patch.exists()

            # Verify stage was NOT coalesced (incomplete)
            stage_patch = (
                base_dir / "config/management-cluster/test-app/stage/patch-001.yaml"
            )
            assert not stage_patch.exists()

            # Verify stage sector-1 still exists
            stage_sector_patch = (
                base_dir
                / "config/management-cluster/test-app/stage/stage-sector-1/patch-001.yaml"
            )
            assert stage_sector_patch.exists()


def test_coalesce_patches_empty_input():
    """Test coalescing with no patches found."""
    # This test is about behavior when no patches exist, so we use a non-existent patch name
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should handle empty patches gracefully
            promote.coalesce_patches(
                "management-cluster", "test-app", "nonexistent-patch"
            )


def test_coalesce_patches_content_preservation():
    """Test that patch content is preserved during coalescing."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches with specific content at both regions
        app_dir = base_dir / "config" / "management-cluster" / "test-app"

        region1_dir = app_dir / "integration/int-sector-1/us-central1"
        region1_dir.mkdir(parents=True, exist_ok=True)
        region1_content = "test: region1-specific-content"
        (region1_dir / "patch-001.yaml").write_text(region1_content)

        region2_dir = app_dir / "integration/int-sector-1/europe-west1"
        region2_dir.mkdir(parents=True, exist_ok=True)
        region2_content = "test: region2-specific-content"
        (region2_dir / "patch-001.yaml").write_text(region2_content)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should coalesce and preserve content from first patch
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify sector-level patch has content from first region
            sector_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/patch-001.yaml"
            )
            assert sector_patch.exists()
            coalesced_content = sector_patch.read_text()
            assert coalesced_content == region1_content


def test_final_consolidation_to_values_yaml():
    """Test final consolidation when all root dimensions have patches."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches at all root-level dimensions (all environments)
        patches = ["integration", "stage", "production"]
        create_test_filesystem(base_dir, patches)

        # Create base values.yaml with existing content
        app_dir = base_dir / "config" / "management-cluster" / "test-app"
        values_file = app_dir / "values.yaml"
        values_file.write_text("""
applications:
  test-app:
    existing: config
    source:
      targetRevision: "v1.0.0"
""")

        # Create patch with metadata that should be stripped
        patch_content = """
metadata:
  description: "Test patch for consolidation"

applications:
  test-app:
    source:
      targetRevision: "v2.0.0"
    new_field: "added by patch"
"""
        (app_dir / "integration" / "patch-001.yaml").write_text(patch_content)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should consolidate to values.yaml
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify values.yaml was updated
            assert values_file.exists()
            with open(values_file) as f:
                merged_data = f.read()

            # Check that patch content was merged
            assert "v2.0.0" in merged_data
            assert "added by patch" in merged_data
            assert "existing: config" in merged_data

            # Check that metadata was NOT included
            assert "metadata" not in merged_data
            assert "Test patch for consolidation" not in merged_data

            # Verify root-level patches were removed
            assert not (app_dir / "integration" / "patch-001.yaml").exists()
            assert not (app_dir / "stage" / "patch-001.yaml").exists()
            assert not (app_dir / "production" / "patch-001.yaml").exists()


def test_no_final_consolidation_with_partial_coverage():
    """Test that final consolidation doesn't happen with partial root coverage."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patches at only some root dimensions (missing production)
        patches = ["integration", "stage"]
        create_test_filesystem(base_dir, patches)

        # Create base values.yaml
        app_dir = base_dir / "config" / "management-cluster" / "test-app"
        values_file = app_dir / "values.yaml"
        values_file.write_text("applications:\n  test-app:\n    existing: config")

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            # Should NOT consolidate (missing production)
            promote.coalesce_patches("management-cluster", "test-app", "patch-001")

            # Verify values.yaml was NOT modified
            with open(values_file) as f:
                content = f.read()
            assert content == "applications:\n  test-app:\n    existing: config"

            # Verify root-level patches still exist
            assert (app_dir / "integration" / "patch-001.yaml").exists()
            assert (app_dir / "stage" / "patch-001.yaml").exists()


def test_merge_patch_into_values_function():
    """Test the merge_patch_into_values function directly."""

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch with metadata
        patch_content = """
metadata:
  description: "Test patch"
  owner: "team@example.com"

applications:
  test-app:
    source:
      targetRevision: "v2.0.0"
    new_config:
      enabled: true
"""
        app_dir = base_dir / "management-cluster" / "test-app"
        app_dir.mkdir(parents=True, exist_ok=True)
        patch_file = app_dir / "integration" / "patch-001.yaml"
        patch_file.parent.mkdir(parents=True, exist_ok=True)
        patch_file.write_text(patch_content)

        # Create existing values.yaml
        values_file = app_dir / "values.yaml"
        values_file.write_text("""
applications:
  test-app:
    existing: config
    source:
      targetRevision: "v1.0.0"
      chart: test-chart
""")

        # Create a mock config that points to our temp directory
        original_config = promote.config
        mock_config_data = {
            "dimensions": ["environments", "sectors", "regions"],
            "sequence": {
                "environments": [
                    {
                        "name": "integration",
                        "sectors": [
                            {"name": "int-sector-1", "regions": ["us-central1"]}
                        ],
                    }
                ]
            },
        }
        promote.config = MockConfig(mock_config_data, base_dir)

        try:
            # Create patch object - no need to pass path, it's computed
            patch_obj = promote.Patch(
                "management-cluster", "test-app", ("integration",), "patch-001"
            )

            # Test the merge function
            promote.merge_patch_into_values(patch_obj, values_file)

            # Verify merged content
            import yaml

            with open(values_file) as f:
                merged_data = yaml.safe_load(f)

            assert merged_data["applications"]["test-app"]["existing"] == "config"
            assert (
                merged_data["applications"]["test-app"]["source"]["targetRevision"]
                == "v2.0.0"
            )
            assert (
                merged_data["applications"]["test-app"]["source"]["chart"]
                == "test-chart"
            )
            assert (
                merged_data["applications"]["test-app"]["new_config"]["enabled"] is True
            )

            # Verify metadata was stripped
            assert "metadata" not in merged_data
        finally:
            # Restore original config
            promote.config = original_config


def test_promote_function():
    """Test the full promote function workflow."""
    config = create_real_test_config()

    with tempfile.TemporaryDirectory() as tmp_dir:
        base_dir = Path(tmp_dir)

        # Create patch in first region
        patches = ["integration/int-sector-1/us-central1"]
        create_test_filesystem(base_dir, patches)

        mock_config = MockConfig(config, base_dir / "config")

        with (
            patch("promote.config", mock_config),
            patch.object(Path, "cwd", return_value=base_dir),
        ):
            os.chdir(base_dir)
            all_patches = list(
                promote.find_patches("management-cluster", "test-app", "patch-001")
            )

            # Should promote to next region
            promote.promote(all_patches)

            # Verify new patch was created
            next_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/europe-west1/patch-001.yaml"
            )
            assert next_patch.exists()

            # Verify original patch still exists
            original_patch = (
                base_dir
                / "config/management-cluster/test-app/integration/int-sector-1/us-central1/patch-001.yaml"
            )
            assert original_patch.exists()


def test_is_patched_function():
    """Test the is_patched function behavior."""
    from promote import is_patched

    # Test exact match
    dimension = ("integration", "int-sector-1")
    patched_dims = [("integration", "int-sector-1")]
    assert is_patched(dimension, patched_dims)

    # Test ancestor match (patch at higher level covers lower level)
    dimension = ("integration", "int-sector-1", "us-central1")
    patched_dims = [("integration", "int-sector-1")]
    assert is_patched(dimension, patched_dims)

    # Test no match (different branches)
    dimension = ("integration", "int-sector-1")
    patched_dims = [("integration", "int-sector-2")]
    assert not is_patched(dimension, patched_dims)

    # Test empty list
    dimension = ("integration", "int-sector-1")
    patched_dims = []
    assert not is_patched(dimension, patched_dims)

    # Test multiple patches (should find match in list)
    dimension = ("integration", "int-sector-1", "us-central1")
    patched_dims = [("stage",), ("integration", "int-sector-1")]
    assert is_patched(dimension, patched_dims)

    # Test dimension shorter than patch (should NOT match)
    dimension = ("integration",)
    patched_dims = [("integration", "int-sector-1", "us-central1")]
    assert not is_patched(dimension, patched_dims)

    # Test root level dimension
    dimension = ("integration",)
    patched_dims = [("integration",)]
    assert is_patched(dimension, patched_dims)

    # Test partial prefix match (should NOT match)
    dimension = ("integration", "different-sector")
    patched_dims = [("integration", "int-sector-1")]
    assert not is_patched(dimension, patched_dims)


if __name__ == "__main__":
    # Run tests with improved gap detection
    test_gap_detection_no_gaps()
    test_gap_detection_region_gap()
    test_gap_detection_sector_gap()
    test_gap_detection_environment_gap()

    # Run coalescing tests
    test_coalesce_patches_region_to_sector()
    test_coalesce_patches_sector_to_environment()
    test_coalesce_patches_mixed_levels()
    test_coalesce_patches_incomplete_coverage()
    test_coalesce_patches_already_at_higher_level()
    test_coalesce_patches_cross_environment()
    test_coalesce_patches_partial_cross_environment()
    test_coalesce_patches_empty_input()
    test_coalesce_patches_content_preservation()

    # Run promote function test
    test_promote_function()

    # Run final consolidation tests
    test_final_consolidation_to_values_yaml()
    test_no_final_consolidation_with_partial_coverage()
    test_merge_patch_into_values_function()

    print("✅ All tests passed!")
