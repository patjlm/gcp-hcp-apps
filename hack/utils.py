#!/usr/bin/env python3
"""
Shared utilities for the gcp-hcp-apps project.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import yaml


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge of dictionaries.

    Args:
        base: Base dictionary to merge into
        override: Dictionary to merge from (takes precedence)

    Returns:
        New dictionary with merged values

    Note:
        This function returns a new dictionary and does not modify the input dictionaries.
        For recursive merging, nested dictionaries are merged recursively.
        For non-dict values, the override value takes precedence.
    """
    if not isinstance(override, dict):
        return override

    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_yaml(file_path: Path, check_empty: bool = False) -> Dict[str, Any]:
    """Load YAML file.

    Args:
        file_path: Path to the YAML file to load
        check_empty: If True, raise ValueError if the file is empty or invalid

    Returns:
        Dictionary containing the parsed YAML content

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file contains invalid YAML
        ValueError: If check_empty is True and the file is empty or invalid
    """
    with open(file_path, "r") as f:
        data = yaml.safe_load(f)

    if check_empty and not data:
        raise ValueError(f"YAML file is empty: {file_path}")

    return data


def save_yaml(data: Dict[str, Any], file_path: Path, width: int = 1000) -> None:
    """Save data to YAML file.

    Args:
        data: Dictionary to save as YAML
        file_path: Path where to save the file
        width: Maximum line width for YAML output
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=width)


def run_helm_template(
    release_name: str, chart_path: str, values_path: str
) -> subprocess.CompletedProcess:
    """Run helm template command with given parameters.
    
    Args:
        release_name: Name for the Helm release
        chart_path: Path to the Helm chart
        values_path: Path to the values file
        
    Returns:
        CompletedProcess result from subprocess.run
    """
    return subprocess.run(
        [
            "helm",
            "template",
            release_name,
            chart_path,
            "--values",
            values_path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )


def _walk_dimensions(
    sequence: Dict[str, Any],
    dimensions: Tuple[str, ...],
    ancestors: Tuple[str, ...] = (),
) -> Iterator[Tuple[str, ...]]:
    """Walk through dimensional hierarchy and yield dimension paths.

    This function traverses a nested configuration structure and yields
    all possible dimensional combinations (like environment/sector/region).

    Args:
        sequence: The sequence data structure to traverse
        dimensions: The ordered dimension names (e.g. ("environments", "sectors", "regions"))
        ancestors: Current path built so far

    Yields:
        Tuples representing complete dimensional paths

    Example:
        For a config with environments->sectors->regions:
        yield ("integration",)
        yield ("integration", "int-sector-1")
        yield ("integration", "int-sector-1", "us-central1")
    """
    if not dimensions:
        return

    current_dimension = dimensions[0]
    next_dimensions = dimensions[1:]

    if current_dimension not in sequence:
        return

    for dimension_item in sequence[current_dimension]:
        if isinstance(dimension_item, dict) and "name" in dimension_item:
            item_name = dimension_item["name"]
            new_ancestors = ancestors + (item_name,)

            # Always yield current path (matches original walk behavior)
            yield new_ancestors

            if next_dimensions:
                # Recurse deeper into hierarchy
                yield from _walk_dimensions(
                    dimension_item, next_dimensions, new_ancestors
                )


class Config:
    def __init__(self, root: Path | None = None):
        self.root = Path(__file__).parent.parent / "config" if root is None else root
        self.repo_root = self.root.parent
        config_yaml = self.root / "config.yaml"
        self.config = load_yaml(config_yaml)
        self.dimensions = tuple(self.config["dimensions"])
        self.sequence = self.config["sequence"]
        self.cluster_types = self.config["cluster_types"]
        self.rendered_path = self.repo_root / "rendered"

    def path(self, cluster_type: str, component: str | None = None) -> Path:
        if component is None:
            return self.root / cluster_type
        return self.root / cluster_type / component

    def components(self, cluster_type: str) -> list[str]:
        """Find all components for a cluster type."""
        config_dir = self.root / cluster_type
        return [
            component_dir.name
            for component_dir in config_dir.iterdir()
            if component_dir.is_dir() and (component_dir / "values.yaml").exists()
        ]

    @property
    def all_dimensions(self) -> list[Tuple[str, ...]]:
        """Get all possible dimension paths in sequence order."""
        return list(_walk_dimensions(self.sequence, self.dimensions))


_config: Config | None = None


def get_config(root: Path | None = None) -> Config:
    global _config
    if _config is None:
        _config = Config(root)
    return _config


@dataclass
class Patch:
    cluster_type: str
    component: str
    dimensions: tuple[str, ...]
    name: str

    @property
    def path(self) -> Path:
        return (
            get_config().path(self.cluster_type, self.component)
            / Path(*self.dimensions)
            / f"{self.name}.yaml"
        )

    def duplicate(self, dimensions: tuple[str, ...]) -> "Patch":
        return Patch(
            cluster_type=self.cluster_type,
            component=self.component,
            dimensions=dimensions,
            name=self.name,
        )

    def _load(self) -> None:
        data = load_yaml(self.path)
        self._metadata = data.get("metadata", {})
        if "metadata" in data:
            del data["metadata"]
        self._content = data

    @property
    def metadata(self) -> dict:
        if not hasattr(self, "_metadata"):
            self._load()
        return self._metadata

    @property
    def content(self) -> dict:
        if not hasattr(self, "_content"):
            self._load()
        return self._content

    @property
    def patched_fields(self) -> List[str]:
        paths: List[str] = []

        def extract_paths(data: Dict[str, Any], prefix: str = "") -> None:
            for key, value in data.items():
                current_path = f"{prefix}.{key}" if prefix else key
                if isinstance(value, dict):
                    extract_paths(value, current_path)
                else:
                    paths.append(current_path)

        extract_paths(self.content)
        return paths
