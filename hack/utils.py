#!/usr/bin/env python3
"""
Shared utilities for the gcp-hcp-apps project.
"""

import sys
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple

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


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file.

    Args:
        file_path: Path to the YAML file to load

    Returns:
        Dictionary containing the parsed YAML content

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file contains invalid YAML
    """
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


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


def load_config(config_path: Path | None = None) -> Dict[str, Any]:
    """Load the main configuration file.

    Args:
        config_path: Optional path to config.yaml. If None, uses default location.

    Returns:
        Dictionary containing the parsed configuration

    Raises:
        SystemExit: If config.yaml is not found
    """
    if config_path is None:
        # Default: config/config.yaml relative to the calling script
        config_path = Path(__file__).parent.parent / "config" / "config.yaml"

    if not config_path.exists():
        print(f"ERROR: config.yaml not found at {config_path}")
        sys.exit(1)

    return load_yaml(config_path)


def walk_dimensions(
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
        yields ("integration", "int-sector-1", "us-central1")
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
                yield from walk_dimensions(
                    dimension_item, next_dimensions, new_ancestors
                )
