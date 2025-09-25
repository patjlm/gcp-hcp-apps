#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml", "pytest"]
# ///

"""
Unit tests for the GitOps fleet generator.
"""

# Import functions from generate.py
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

sys.path.append(str(Path(__file__).parent))
from generate import (
    Target,
    discover_targets,
    find_components,
    merge_component_values,
)


class TestTargetDiscovery:
    """Test target discovery from config.yaml."""

    def test_discover_targets_simple(self):
        """Test basic target discovery."""
        config = {
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
                            }
                        ],
                    }
                ]
            },
        }

        targets = discover_targets(config)

        assert len(targets) == 2
        assert Target(["integration", "int-sector-1", "us-central1"]) in targets
        assert Target(["integration", "int-sector-1", "europe-west1"]) in targets

    def test_discover_targets_multi_environment(self):
        """Test discovery with multiple environments."""
        config = {
            "dimensions": ["environments", "sectors", "regions"],
            "sequence": {
                "environments": [
                    {
                        "name": "integration",
                        "sectors": [
                            {
                                "name": "int-sector-1",
                                "regions": [{"name": "us-central1"}],
                            }
                        ],
                    },
                    {
                        "name": "production",
                        "sectors": [
                            {"name": "prod-sector-1", "regions": [{"name": "us-east1"}]}
                        ],
                    },
                ]
            },
        }

        targets = discover_targets(config)

        assert len(targets) == 2
        assert Target(["integration", "int-sector-1", "us-central1"]) in targets
        assert Target(["production", "prod-sector-1", "us-east1"]) in targets


class TestApplicationDiscovery:
    """Test application discovery."""

    def test_find_components_with_temp_dir(self):
        """Test finding applications in a temporary directory."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create test structure
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            cluster_dir = config_dir / "management-cluster"
            cluster_dir.mkdir()

            # Create app directories with values.yaml
            (cluster_dir / "prometheus").mkdir()
            (cluster_dir / "prometheus" / "values.yaml").touch()

            (cluster_dir / "cert-manager").mkdir()
            (cluster_dir / "cert-manager" / "values.yaml").touch()

            # Create a directory without values.yaml (should be ignored)
            (cluster_dir / "incomplete-app").mkdir()

            # Change working directory to temp dir instead of mocking Path
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                apps = find_components("management-cluster")
            finally:
                os.chdir(original_cwd)

            assert sorted(apps) == ["cert-manager", "prometheus"]


class TestApplicationValueMerging:
    """Test application value merging with temporary files."""

    def test_merge_component_values_with_temp_files(self):
        """Test merging values from temporary config files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create application defaults
            defaults_content = {
                "defaults": {"project": "default", "namespace": "argocd"}
            }
            with open(base_path / "application-defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            # Create app base values
            app_dir = base_path / "prometheus"
            app_dir.mkdir()
            app_values = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.9.1"}}}
            }
            with open(app_dir / "values.yaml", "w") as f:
                yaml.dump(app_values, f)

            # Create environment override
            env_dir = app_dir / "production"
            env_dir.mkdir()
            env_override = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.8.0"}}}
            }
            with open(env_dir / "override.yaml", "w") as f:
                yaml.dump(env_override, f)

            # Mock Path to use our temp directory
            with patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str.startswith("config/"):
                        return Path(temp_dir) / path_str[7:]  # Remove "config/" prefix
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["production", "prod-sector-1", "us-east1"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

            # Verify merging
            assert "applications" in result
            assert "prometheus" in result["applications"]

            # Should have defaults
            assert result["applications"]["prometheus"]["project"] == "default"
            assert result["applications"]["prometheus"]["namespace"] == "argocd"

            # Should have production override
            assert (
                result["applications"]["prometheus"]["source"]["targetRevision"]
                == "77.8.0"
            )


class TestTarget:
    """Test Target dataclass."""

    def test_target_path(self):
        """Test target path generation."""
        target = Target(["integration", "int-sector-1", "us-central1"])
        assert target.path == "integration/int-sector-1/us-central1"


class TestIntegration:
    """Integration tests using actual config files."""

    def test_real_config_discovery(self):
        """Test target discovery with realistic config structure."""
        # Use mock config instead of reading from actual config files
        config = {
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
                            }
                        ],
                    },
                    {
                        "name": "production",
                        "sectors": [
                            {
                                "name": "prod-sector-1",
                                "regions": [
                                    {"name": "us-east1"},
                                    {"name": "europe-east1"},
                                ],
                            }
                        ],
                    },
                ]
            },
        }

        targets = discover_targets(config)

        # Verify we get the expected number of targets
        assert len(targets) == 4

        # Verify specific targets exist
        expected_targets = [
            Target(["integration", "int-sector-1", "us-central1"]),
            Target(["integration", "int-sector-1", "europe-west1"]),
            Target(["production", "prod-sector-1", "us-east1"]),
            Target(["production", "prod-sector-1", "europe-east1"]),
        ]

        for target in expected_targets:
            assert target in targets

    def test_application_discovery_with_mock_structure(self):
        """Test application discovery with mock directory structure."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create mock management-cluster structure
            cluster_dir = Path(temp_dir) / "config" / "management-cluster"
            cluster_dir.mkdir(parents=True)

            # Create app directories with values.yaml
            (cluster_dir / "prometheus" / "values.yaml").parent.mkdir()
            (cluster_dir / "prometheus" / "values.yaml").touch()
            (cluster_dir / "cert-manager" / "values.yaml").parent.mkdir()
            (cluster_dir / "cert-manager" / "values.yaml").touch()

            with patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir) / "config"
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                apps = find_components("management-cluster")

                # Should find our mock applications
                assert "prometheus" in apps
                assert "cert-manager" in apps
                assert len(apps) == 2

    def test_value_merging_with_mock_files(self):
        """Test value merging with mock config files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create minimal structure with defaults
            defaults_content = {"applications": {"default": {"project": "default"}}}
            with open(base_path / "defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            prometheus_dir = base_path / "prometheus"
            prometheus_dir.mkdir()

            # Base values
            base_values = {
                "applications": {
                    "prometheus": {
                        "source": {"targetRevision": "77.9.1"},
                        "destination": {"namespace": "monitoring"},
                    }
                }
            }
            with open(prometheus_dir / "values.yaml", "w") as f:
                yaml.dump(base_values, f)

            # Production override
            prod_dir = prometheus_dir / "production"
            prod_dir.mkdir()
            prod_override = {
                "applications": {
                    "prometheus": {
                        "source": {
                            "targetRevision": "77.8.0",
                            "helm": {
                                "valuesObject": {
                                    "prometheus": {
                                        "prometheusSpec": {"retention": "30d"}
                                    }
                                }
                            },
                        }
                    }
                }
            }
            with open(prod_dir / "override.yaml", "w") as f:
                yaml.dump(prod_override, f)

            with patch("generate.os.chdir"), patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir)
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["production"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

                # Should have merged values
                assert "applications" in result
                assert "prometheus" in result["applications"]

                prometheus_config = result["applications"]["prometheus"]

                # Should have production version override
                assert prometheus_config["source"]["targetRevision"] == "77.8.0"

                # Should have enhanced production resources
                assert (
                    prometheus_config["source"]["helm"]["valuesObject"]["prometheus"][
                        "prometheusSpec"
                    ]["retention"]
                    == "30d"
                )


class TestValidation:
    """Test validation and error handling."""

    def test_missing_config_file_raises_error(self):
        """Test that missing config.yaml raises an error."""
        from generate import load_yaml

        with pytest.raises(FileNotFoundError):
            load_yaml(Path("nonexistent/config.yaml"))

    def test_missing_application_values_raises_error(self):
        """Test that missing app values.yaml raises an error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create config directory structure
            config_dir = Path(temp_dir) / "config"
            config_dir.mkdir()
            base_path = config_dir / "management-cluster"
            base_path.mkdir(parents=True)

            # Create app directory but NO values.yaml
            app_dir = base_path / "prometheus"
            app_dir.mkdir()

            # Change working directory to temp dir
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                target = Target(["integration", "int-sector-1", "us-central1"])

                # Should raise FileNotFoundError when trying to load missing values.yaml
                with pytest.raises(FileNotFoundError):
                    merge_component_values("management-cluster", "prometheus", target)
            finally:
                os.chdir(original_cwd)

    def test_malformed_yaml_raises_error(self):
        """Test that malformed YAML raises an error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            malformed_file = Path(temp_dir) / "malformed.yaml"

            # Write malformed YAML
            with open(malformed_file, "w") as f:
                f.write("invalid: yaml: content: [unclosed")

            from generate import load_yaml

            # Should raise YAML parsing error
            with pytest.raises(yaml.YAMLError):
                load_yaml(malformed_file)

    def test_missing_application_defaults_uses_empty_defaults(self):
        """Test behavior when application-defaults.yaml is missing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create app values but NO application-defaults.yaml
            app_dir = base_path / "prometheus"
            app_dir.mkdir()
            app_values = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.9.1"}}}
            }
            with open(app_dir / "values.yaml", "w") as f:
                yaml.dump(app_values, f)

            with patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str.startswith("config/"):
                        return Path(temp_dir) / path_str[7:]
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["integration", "int-sector-1", "us-central1"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

            # Should work without defaults, just return app values
            assert "applications" in result
            assert "prometheus" in result["applications"]
            assert (
                result["applications"]["prometheus"]["source"]["targetRevision"]
                == "77.9.1"
            )

    def test_patch_files_applied_after_values(self):
        """Test that patch files are applied after values.yaml in each dimension."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create application defaults
            defaults_content = {
                "applications": {
                    "default": {
                        "project": "default",
                        "namespace": "argocd",
                        "syncPolicy": {"automated": {"prune": False, "selfHeal": True}},
                    }
                }
            }
            with open(base_path / "defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            # Create prometheus component structure
            prometheus_dir = base_path / "prometheus"
            prometheus_dir.mkdir()

            # Base values
            base_values = {
                "applications": {
                    "prometheus": {
                        "source": {"targetRevision": "77.9.1"},
                        "destination": {"namespace": "monitoring"},
                    }
                }
            }
            with open(prometheus_dir / "values.yaml", "w") as f:
                yaml.dump(base_values, f)

            # Production dimension with values and patch
            prod_dir = prometheus_dir / "production"
            prod_dir.mkdir()

            # Production values (permanent config)
            prod_values = {
                "applications": {
                    "prometheus": {
                        "source": {"targetRevision": "77.8.0"},  # Stable version
                        "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
                    }
                }
            }
            with open(prod_dir / "override.yaml", "w") as f:
                yaml.dump(prod_values, f)

            # Production patch (temporary change)
            patch_content = {
                "metadata": {
                    "description": "Upgrade to v77.9.0 with security fixes",
                    "dependencies": ["cert-manager/source/targetRevision: >=v1.13.0"],
                },
                "applications": {
                    "prometheus": {
                        "source": {
                            "targetRevision": "77.9.0"
                        },  # Patch overrides stable version
                        "syncPolicy": {
                            "syncOptions": ["ServerSideApply=true"]
                        },  # Adds to list
                    }
                },
            }
            with open(prod_dir / "patch-001.yaml", "w") as f:
                yaml.dump(patch_content, f)

            # Mock os.chdir and Path so merge_component_values finds our temp files
            with patch("generate.os.chdir"), patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir)
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["production"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

            # Verify merging order: defaults -> base -> production values -> production patch
            assert "applications" in result
            assert "prometheus" in result["applications"]

            prometheus_config = result["applications"]["prometheus"]

            # Should have patch version (77.9.0) not production stable version (77.8.0)
            assert prometheus_config["source"]["targetRevision"] == "77.9.0"

            # Should have patch syncOptions (replaces production values per deep_merge behavior)
            sync_options = prometheus_config["syncPolicy"]["syncOptions"]
            assert sync_options == [
                "ServerSideApply=true"
            ]  # Patch overrides production values

            # Should have destination from base values
            assert prometheus_config["destination"]["namespace"] == "monitoring"

    def test_multiple_patches_applied_in_order(self):
        """Test that multiple patch files are applied in filename order."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create minimal structure
            defaults_content = {"applications": {"default": {"project": "default"}}}
            with open(base_path / "defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            prometheus_dir = base_path / "prometheus"
            prometheus_dir.mkdir()

            base_values = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.8.0"}}}
            }
            with open(prometheus_dir / "values.yaml", "w") as f:
                yaml.dump(base_values, f)

            # Create integration dimension with multiple patches
            integration_dir = prometheus_dir / "integration"
            integration_dir.mkdir()

            # First patch
            patch_001 = {
                "metadata": {"description": "First patch"},
                "applications": {
                    "prometheus": {"source": {"targetRevision": "77.9.0"}}
                },
            }
            with open(integration_dir / "patch-001.yaml", "w") as f:
                yaml.dump(patch_001, f)

            # Second patch (should override first)
            patch_002 = {
                "metadata": {"description": "Second patch"},
                "applications": {
                    "prometheus": {"source": {"targetRevision": "77.9.1"}}
                },
            }
            with open(integration_dir / "patch-002.yaml", "w") as f:
                yaml.dump(patch_002, f)

            with patch("generate.os.chdir"), patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir)
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["integration"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

            # Should have the last patch version (002 overrides 001)
            assert (
                result["applications"]["prometheus"]["source"]["targetRevision"]
                == "77.9.1"
            )

    def test_patch_metadata_ignored(self):
        """Test that metadata section in patches is ignored by generator."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create minimal structure
            defaults_content = {"applications": {"default": {"project": "default"}}}
            with open(base_path / "defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            prometheus_dir = base_path / "prometheus"
            prometheus_dir.mkdir()

            base_values = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.8.0"}}}
            }
            with open(prometheus_dir / "values.yaml", "w") as f:
                yaml.dump(base_values, f)

            # Create patch with metadata that should be ignored
            integration_dir = prometheus_dir / "integration"
            integration_dir.mkdir()

            patch_with_metadata = {
                "metadata": {
                    "description": "This should be ignored",
                    "dependencies": ["some/dependency"],
                    "complex": {"nested": "data"},
                },
                "applications": {
                    "prometheus": {"source": {"targetRevision": "77.9.0"}}
                },
            }
            with open(integration_dir / "patch-001.yaml", "w") as f:
                yaml.dump(patch_with_metadata, f)

            with patch("generate.os.chdir"), patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir)
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                target = Target(["integration"])
                result = merge_component_values(
                    "management-cluster", "prometheus", target
                )

            # Should have patch applied but no metadata in result
            assert (
                result["applications"]["prometheus"]["source"]["targetRevision"]
                == "77.9.0"
            )
            assert "metadata" not in result
            assert "description" not in result
            assert "dependencies" not in result

    def test_patch_conflict_detection(self):
        """Test that patch conflicts are detected and reported."""
        with tempfile.TemporaryDirectory() as temp_dir:
            base_path = Path(temp_dir) / "management-cluster"
            base_path.mkdir(parents=True)

            # Create minimal structure
            defaults_content = {"applications": {"default": {"project": "default"}}}
            with open(base_path / "defaults.yaml", "w") as f:
                yaml.dump(defaults_content, f)

            prometheus_dir = base_path / "prometheus"
            prometheus_dir.mkdir()

            base_values = {
                "applications": {"prometheus": {"source": {"targetRevision": "77.8.0"}}}
            }
            with open(prometheus_dir / "values.yaml", "w") as f:
                yaml.dump(base_values, f)

            # Create integration dimension with conflicting patches
            integration_dir = prometheus_dir / "integration"
            integration_dir.mkdir()

            # First patch
            patch_001 = {
                "applications": {
                    "prometheus": {"source": {"targetRevision": "77.9.0"}}
                },
            }
            with open(integration_dir / "patch-001.yaml", "w") as f:
                yaml.dump(patch_001, f)

            # Conflicting patch (same path)
            patch_002 = {
                "applications": {
                    "prometheus": {"source": {"targetRevision": "77.9.1"}}
                },
            }
            with open(integration_dir / "patch-002.yaml", "w") as f:
                yaml.dump(patch_002, f)

            # Capture printed warnings
            import io
            from contextlib import redirect_stdout

            with patch("generate.os.chdir"), patch("generate.Path") as mock_path:

                def path_side_effect(path_str):
                    if path_str == "config":
                        return Path(temp_dir)
                    return Path(path_str)

                mock_path.side_effect = path_side_effect

                # Capture print output
                captured_output = io.StringIO()
                with redirect_stdout(captured_output):
                    target = Target(["integration"])
                    result = merge_component_values(
                        "management-cluster", "prometheus", target
                    )

                # Check that conflict was detected
                output = captured_output.getvalue()
                assert "WARNING: Patch conflict detected:" in output
                assert "patch-002.yaml conflicts with" in output
                assert "patch-001.yaml" in output
                assert "applications.prometheus.source.targetRevision" in output

                # Should have the last patch version (002 overrides 001)
                assert (
                    result["applications"]["prometheus"]["source"]["targetRevision"]
                    == "77.9.1"
                )

    def test_get_patch_paths_function(self):
        """Test the patch path extraction function."""
        from generate import get_patch_paths

        # Simple patch
        patch_data = {
            "applications": {"prometheus": {"source": {"targetRevision": "77.9.0"}}}
        }

        paths = get_patch_paths(patch_data)
        expected_paths = ["applications.prometheus.source.targetRevision"]
        assert paths == expected_paths

        # Complex patch with multiple paths
        complex_patch = {
            "applications": {
                "prometheus": {
                    "source": {"targetRevision": "77.9.0"},
                    "syncPolicy": {"syncOptions": ["ServerSideApply=true"]},
                },
                "cert-manager": {"source": {"targetRevision": "v1.16.0"}},
            }
        }

        paths = get_patch_paths(complex_patch)
        expected_paths = [
            "applications.prometheus.source.targetRevision",
            "applications.prometheus.syncPolicy.syncOptions",
            "applications.cert-manager.source.targetRevision",
        ]
        assert sorted(paths) == sorted(expected_paths)

    def test_invalid_cluster_type_raises_error(self):
        """Test that invalid cluster type raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config directory not found"):
            find_components("nonexistent-cluster-type")

    def test_empty_config_sequence_returns_empty_targets(self):
        """Test that empty sequence returns no targets."""
        config = {"dimensions": ["environments", "sectors", "regions"], "sequence": {}}
        targets = discover_targets(config)
        assert targets == []

    def test_config_missing_sequence_raises_error(self):
        """Test that config missing sequence key raises error."""
        config = {"other_key": "value"}

        # Should raise KeyError when trying to access sequence
        with pytest.raises(KeyError):
            discover_targets(config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
