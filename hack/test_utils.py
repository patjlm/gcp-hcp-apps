#!/usr/bin/env python3
# /// script
# dependencies = ["pytest", "pyyaml"]
# ///

"""
Comprehensive tests for utils module.
"""

import tempfile
from pathlib import Path

import pytest
import yaml
from utils import Config, _walk_dimensions, deep_merge, load_yaml, save_yaml


class TestDeepMerge:
    """Test cases for the deep_merge function."""

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

    def test_deep_merge_immutable(self):
        """Test that deep_merge doesn't modify input dictionaries."""
        base = {"a": 1, "b": {"c": 2}}
        override = {"b": {"d": 3}, "e": 4}

        original_base = base.copy()
        original_override = override.copy()

        result = deep_merge(base, override)

        # Verify inputs weren't modified
        assert base == original_base
        assert override == original_override

        # Verify result is correct
        expected = {"a": 1, "b": {"c": 2, "d": 3}, "e": 4}
        assert result == expected

    def test_deep_merge_empty_dicts(self):
        """Test deep merge with empty dictionaries."""
        # Empty base
        result = deep_merge({}, {"a": 1, "b": {"c": 2}})
        assert result == {"a": 1, "b": {"c": 2}}

        # Empty override
        base = {"a": 1, "b": {"c": 2}}
        result = deep_merge(base, {})
        assert result == base

        # Both empty
        result = deep_merge({}, {})
        assert result == {}

    def test_deep_merge_nested_deep(self):
        """Test deep merge with deeply nested structures."""
        base = {
            "level1": {"level2": {"level3": {"existing": "value", "array": [1, 2, 3]}}}
        }
        override = {
            "level1": {
                "level2": {
                    "level3": {"new": "addition", "array": [4, 5]},
                    "level2b": "new_branch",
                }
            },
            "new_root": "value",
        }

        result = deep_merge(base, override)

        expected = {
            "level1": {
                "level2": {
                    "level3": {
                        "existing": "value",
                        "array": [4, 5],  # Replaced
                        "new": "addition",
                    },
                    "level2b": "new_branch",
                }
            },
            "new_root": "value",
        }
        assert result == expected

    def test_deep_merge_type_replacement(self):
        """Test that non-dict values replace dict values and vice versa."""
        # Dict replaces non-dict
        base = {"config": "simple_string"}
        override = {"config": {"complex": "object"}}
        result = deep_merge(base, override)
        assert result == {"config": {"complex": "object"}}

        # Non-dict replaces dict
        base = {"config": {"complex": "object"}}
        override = {"config": "simple_string"}
        result = deep_merge(base, override)
        assert result == {"config": "simple_string"}

    def test_deep_merge_non_dict_override(self):
        """Test deep_merge with non-dict override (edge case)."""
        base = {"a": 1, "b": 2}

        # When override is not a dict, it should be returned directly
        result = deep_merge(base, "not_a_dict")
        assert result == "not_a_dict"

        result = deep_merge(base, 42)
        assert result == 42

        result = deep_merge(base, None)
        assert result is None

        result = deep_merge(base, [1, 2, 3])
        assert result == [1, 2, 3]

    def test_deep_merge_complex_structures(self):
        """Test deep merge with complex real-world-like structures."""
        base = {
            "applications": {
                "prometheus": {
                    "source": {
                        "repoURL": "https://charts.example.com",
                        "targetRevision": "1.0.0",
                        "helm": {
                            "valuesObject": {
                                "replicas": 1,
                                "resources": {"requests": {"memory": "512Mi"}},
                            }
                        },
                    },
                    "syncPolicy": {"syncOptions": ["CreateNamespace=true"]},
                }
            }
        }

        override = {
            "applications": {
                "prometheus": {
                    "source": {
                        "targetRevision": "2.0.0",
                        "helm": {
                            "valuesObject": {
                                "replicas": 3,
                                "resources": {
                                    "requests": {"cpu": "100m"},
                                    "limits": {"memory": "1Gi"},
                                },
                            }
                        },
                    },
                    "syncPolicy": {"syncOptions": ["ServerSideApply=true"]},
                },
                "grafana": {
                    "source": {"repoURL": "https://grafana.github.io/helm-charts"}
                },
            }
        }

        result = deep_merge(base, override)

        expected = {
            "applications": {
                "prometheus": {
                    "source": {
                        "repoURL": "https://charts.example.com",
                        "targetRevision": "2.0.0",  # Override
                        "helm": {
                            "valuesObject": {
                                "replicas": 3,  # Override
                                "resources": {
                                    "requests": {
                                        "memory": "512Mi",  # From base
                                        "cpu": "100m",  # From override
                                    },
                                    "limits": {"memory": "1Gi"},  # From override
                                },
                            }
                        },
                    },
                    "syncPolicy": {
                        "syncOptions": [
                            "ServerSideApply=true"
                        ]  # Override (list replaced)
                    },
                },
                "grafana": {  # New application
                    "source": {"repoURL": "https://grafana.github.io/helm-charts"}
                },
            }
        }
        assert result == expected


class TestYamlOperations:
    """Test cases for YAML loading and saving functions."""

    def test_load_yaml_success(self):
        """Test successful YAML loading."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            test_data = {"key": "value", "nested": {"item": 123}}
            yaml.dump(test_data, f)
            temp_path = Path(f.name)

        try:
            result = load_yaml(temp_path)
            assert result == test_data
        finally:
            temp_path.unlink()

    def test_load_yaml_file_not_found(self):
        """Test load_yaml with non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_yaml(Path("/nonexistent/file.yaml"))

    def test_save_yaml_creates_directories(self):
        """Test that save_yaml creates parent directories."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            test_path = Path(tmp_dir) / "nested" / "dirs" / "test.yaml"
            test_data = {"test": "data"}

            save_yaml(test_data, test_path)

            assert test_path.exists()
            loaded_data = load_yaml(test_path)
            assert loaded_data == test_data

    def test_save_yaml_with_custom_width(self):
        """Test save_yaml with custom line width."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            temp_path = Path(f.name)

        try:
            test_data = {"very_long_key_name": "very_long_value_that_might_wrap"}
            save_yaml(test_data, temp_path, width=20)

            # Verify file was created and can be loaded
            loaded_data = load_yaml(temp_path)
            assert loaded_data == test_data
        finally:
            temp_path.unlink()


class TestConfigLoading:
    """Test cases for configuration loading."""

    def test_load_config_with_explicit_path(self):
        """Test loading config with explicit path."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = Path(temp_dir)
            config_file = config_dir / "config.yaml"
            config_data = {
                "dimensions": ["env", "sector", "region"],
                "sequence": {"env": [{"name": "test"}]},
                "cluster_types": [{"name": "test-cluster"}],
            }
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            config = Config(config_dir)
            assert config.config == config_data
            assert config.dimensions == tuple(config_data["dimensions"])
            assert config.sequence == config_data["sequence"]
            assert config.cluster_types == config_data["cluster_types"]

    def test_load_config_file_not_found_exits(self):
        """Test Config constructor raises FileNotFoundError when file not found."""
        with pytest.raises(FileNotFoundError):
            Config(Path("/nonexistent"))


class TestWalkDimensions:
    """Test cases for the walk_dimensions function."""

    def test_walk_dimensions_simple(self):
        """Test walking a simple dimensional structure."""
        sequence = {"environments": [{"name": "env1"}, {"name": "env2"}]}
        dimensions = ("environments",)

        paths = list(_walk_dimensions(sequence, dimensions))
        expected = [("env1",), ("env2",)]
        assert paths == expected

    def test_walk_dimensions_nested(self):
        """Test walking nested dimensional structure."""
        sequence = {
            "environments": [
                {"name": "env1", "sectors": [{"name": "sector1"}, {"name": "sector2"}]}
            ]
        }
        dimensions = ("environments", "sectors")

        paths = list(_walk_dimensions(sequence, dimensions))
        expected = [("env1",), ("env1", "sector1"), ("env1", "sector2")]
        assert paths == expected

    def test_walk_dimensions_three_levels(self):
        """Test walking three-level dimensional structure."""
        sequence = {
            "environments": [
                {
                    "name": "env1",
                    "sectors": [
                        {
                            "name": "sector1",
                            "regions": [{"name": "region1"}, {"name": "region2"}],
                        }
                    ],
                }
            ]
        }
        dimensions = ("environments", "sectors", "regions")

        paths = list(_walk_dimensions(sequence, dimensions))
        expected = [
            ("env1",),
            ("env1", "sector1"),
            ("env1", "sector1", "region1"),
            ("env1", "sector1", "region2"),
        ]
        assert paths == expected

    def test_walk_dimensions_missing_dimension(self):
        """Test walking when a dimension key is missing."""
        sequence = {"environments": [{"name": "env1"}]}
        dimensions = ("missing_key",)

        paths = list(_walk_dimensions(sequence, dimensions))
        assert paths == []

    def test_walk_dimensions_empty_dimensions(self):
        """Test walking with empty dimensions tuple."""
        sequence = {"environments": [{"name": "env1"}]}
        dimensions = ()

        paths = list(_walk_dimensions(sequence, dimensions))
        assert paths == []

    def test_walk_dimensions_complex_structure(self):
        """Test walking a complex multi-environment structure."""
        sequence = {
            "environments": [
                {
                    "name": "integration",
                    "sectors": [
                        {"name": "int-sector-1", "regions": [{"name": "us-central1"}]}
                    ],
                },
                {
                    "name": "production",
                    "sectors": [
                        {
                            "name": "prod-sector-1",
                            "regions": [{"name": "us-east1"}, {"name": "europe-east1"}],
                        }
                    ],
                },
            ]
        }
        dimensions = ("environments", "sectors", "regions")

        paths = list(_walk_dimensions(sequence, dimensions))
        expected = [
            ("integration",),
            ("integration", "int-sector-1"),
            ("integration", "int-sector-1", "us-central1"),
            ("production",),
            ("production", "prod-sector-1"),
            ("production", "prod-sector-1", "us-east1"),
            ("production", "prod-sector-1", "europe-east1"),
        ]
        assert paths == expected
