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
    deep_merge,
    discover_targets,
    find_components,
    merge_component_values,
)


class TestTargetDiscovery:
    """Test target discovery from config.yaml."""

    def test_discover_targets_simple(self):
        """Test basic target discovery."""
        config = {
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
            }
        }

        targets = discover_targets(config)

        assert len(targets) == 2
        assert Target(["integration", "int-sector-1", "us-central1"]) in targets
        assert Target(["integration", "int-sector-1", "europe-west1"]) in targets

    def test_discover_targets_multi_environment(self):
        """Test discovery with multiple environments."""
        config = {
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
            }
        }

        targets = discover_targets(config)

        assert len(targets) == 2
        assert Target(["integration", "int-sector-1", "us-central1"]) in targets
        assert Target(["production", "prod-sector-1", "us-east1"]) in targets


class TestValueMerging:
    """Test value merging logic."""

    def test_deep_merge_simple(self):
        """Test simple deep merge."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}, "e": 4}

        result = deep_merge(base, override)

        expected = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        assert result == expected

    def test_deep_merge_override(self):
        """Test deep merge with override."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"a": 10, "b": {"c": 20}}

        result = deep_merge(base, override)

        expected = {"a": 10, "b": {"c": 20}}
        assert result == expected

    def test_deep_merge_lists(self):
        """Test deep merge with lists (should replace)."""
        base = {"items": [1, 2, 3]}
        override = {"items": [4, 5]}

        result = deep_merge(base, override)

        expected = {"items": [4, 5]}
        assert result == expected


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
            with open(env_dir / "values.yaml", "w") as f:
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
        """Test target discovery with real config.yaml."""
        from generate import load_yaml

        # Load our actual config
        config = load_yaml(Path("config/config.yaml"))
        targets = discover_targets(config)

        # Verify we get the expected number of targets
        assert len(targets) == 8

        # Verify some specific targets exist
        expected_targets = [
            Target(["integration", "int-sector-1", "us-central1"]),
            Target(["production", "prod-sector-1", "us-east1"]),
            Target(["stage", "stage-sector-1", "europe-west1"]),
        ]

        for target in expected_targets:
            assert target in targets

    def test_real_application_discovery(self):
        """Test application discovery with real config."""
        apps = find_components("management-cluster")

        # Should find our configured applications
        assert "argocd" in apps
        assert "prometheus" in apps
        assert "cert-manager" in apps
        assert "hypershift" in apps
        assert len(apps) == 4

    def test_real_value_merging(self):
        """Test value merging with real config files."""
        target = Target(["production", "prod-sector-1", "us-east1"])

        # Test prometheus merging
        result = merge_component_values("management-cluster", "prometheus", target)

        # Should have merged values
        assert "applications" in result
        assert "prometheus" in result["applications"]

        prometheus_config = result["applications"]["prometheus"]

        # Should have production version override
        assert prometheus_config["source"]["targetRevision"] == "77.8.0"

        # Should have enhanced production resources
        assert "prometheus" in prometheus_config["source"]["helm"]["valuesObject"]
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

    def test_invalid_cluster_type_raises_error(self):
        """Test that invalid cluster type raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Config directory not found"):
            find_components("nonexistent-cluster-type")

    def test_empty_config_sequence_returns_empty_targets(self):
        """Test that empty sequence returns no targets."""
        config = {"sequence": {}}
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
