#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///

"""
Simple GitOps fleet generator.
Generates ArgoCD resources for multi-dimensional deployment hierarchies.
"""

import enum
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class Target:
    """Represents a deployment target with configurable dimensions."""

    path_parts: List[str]  # e.g., ["production", "prod-sector-1", "us-east1"]

    @property
    def path(self) -> str:
        """Get the file system path for this target."""
        return "/".join(self.path_parts)


def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def save_yaml(data: Dict[str, Any], file_path: Path) -> None:
    """Save data to YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False, width=1000)


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Simple deep merge of dictionaries."""
    if not isinstance(override, dict):
        return override

    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def discover_targets(config: Dict[str, Any]) -> List[Target]:
    """Discover all dimensional combinations from configurable hierarchy.

    Traverses the dimensional structure defined in config.yaml to generate
    all possible environment/sector/region (or other) combinations as deployment targets.
    """

    # Keys that represent metadata, not child dimensions
    METADATA_KEYS = ["name", "promotion"]

    def traverse_dimensions(
        sequence_data: Any, current_path: Optional[List[str]] = None
    ) -> List[Target]:
        """Recursively traverse dimensional hierarchy to find all leaf combinations.

        Args:
            sequence_data: Current level of the dimensional hierarchy
            current_path: Path built so far (e.g., ["production", "prod-sector-1"])

        Returns:
            List of Target objects representing all possible dimensional combinations
        """
        if current_path is None:
            current_path = []
        targets: List[Target] = []

        if isinstance(sequence_data, list):
            # Process each item in the current dimension list
            for dimension_item in sequence_data:
                if isinstance(dimension_item, dict) and "name" in dimension_item:
                    item_name = dimension_item["name"]
                    new_path = current_path + [item_name]

                    # Find child dimensions (exclude metadata keys like 'name', 'promotion')
                    dimension_keys = [
                        k for k in dimension_item.keys() if k not in METADATA_KEYS
                    ]

                    if dimension_keys:
                        # Has child dimensions - recurse deeper into hierarchy
                        for dimension_name in dimension_keys:
                            targets.extend(
                                traverse_dimensions(
                                    dimension_item[dimension_name], new_path
                                )
                            )
                    else:
                        # Leaf node reached - create final deployment target
                        targets.append(Target(new_path))

        elif isinstance(sequence_data, dict):
            # Dictionary container - recurse into all dimension values
            for dimension_values in sequence_data.values():
                targets.extend(traverse_dimensions(dimension_values, current_path))

        return targets

    return traverse_dimensions(config["sequence"])


def find_components(cluster_type: str) -> List[str]:
    """Find all components for a cluster type."""
    config_dir = Path("config") / cluster_type
    components: List[str] = []

    if not config_dir.exists():
        raise FileNotFoundError(f"Config directory not found: {config_dir}")

    for component_dir in config_dir.iterdir():
        if component_dir.is_dir():
            if (component_dir / "values.yaml").exists():
                components.append(component_dir.name)

    return components


def merge_component_values(
    cluster_type: str, component_name: str, target: Target
) -> Dict[str, Any]:
    """Merge component values for a specific target."""
    base_path = Path("config") / cluster_type
    merged: Dict[str, Any] = {}

    # 1. Load defaults for all resource types (mandatory)
    defaults_file = base_path / "defaults.yaml"
    if not defaults_file.exists():
        raise FileNotFoundError(f"Mandatory defaults file not found: {defaults_file}")
    defaults_to_apply = load_yaml(defaults_file)
    if not defaults_to_apply:
        raise ValueError(f"Defaults file is empty or invalid: {defaults_file}")

    # 2. Load base component values (mandatory)
    component_values_file = base_path / component_name / "values.yaml"
    if not component_values_file.exists():
        raise FileNotFoundError(
            f"Mandatory component values file not found: {component_values_file}"
        )

    component_values = load_yaml(component_values_file)
    if not component_values:
        raise ValueError(f"Component values file is empty or invalid: {component_values_file}")
    merged = deep_merge(merged, component_values)

    # 2.5. Apply defaults dynamically based on what sections exist in component_values
    # First, validate that ALL used component types have defaults
    for section_name in component_values.keys():
        if section_name not in defaults_to_apply:
            raise ValueError(
                f"Component uses '{section_name}' but no defaults found for '{section_name}' in {defaults_file}"
            )
        section_defaults = defaults_to_apply[section_name]
        if not section_defaults or "default" not in section_defaults:
            raise ValueError(
                f"Missing 'default' section for '{section_name}' in {defaults_file}"
            )

    # Now apply defaults to each used section
    for section_name in component_values.keys():
        section_defaults = defaults_to_apply[section_name]
        default_values = section_defaults["default"]
        # Apply defaults to each item in this section
        for item_name in component_values[section_name]:
            if section_name not in merged:
                merged[section_name] = {}
            if item_name not in merged[section_name]:
                merged[section_name][item_name] = {}
            # Merge defaults with the item (item takes precedence)
            merged[section_name][item_name] = deep_merge(
                default_values, merged[section_name][item_name]
            )

    # 3. Load dimensional overrides (try each path level)
    # e.g., for ["production", "prod-sector-1", "us-east1"]
    # try: production/values.yaml, prod-sector-1/values.yaml, us-east1/values.yaml
    component_dir = base_path / component_name
    for dimension_value in target.path_parts:
        override_file = component_dir / dimension_value / "values.yaml"
        if override_file.exists():
            override = load_yaml(override_file)
            merged = deep_merge(merged, override)

    return merged


def render_target(cluster_type: str, target: Target) -> None:
    """Render all components for a specific target."""
    print(f"Rendering {cluster_type}/{target.path}")

    # Create target directory
    target_dir = Path("rendered") / cluster_type / target.path
    target_dir.mkdir(parents=True, exist_ok=True)

    # Find components for this cluster type
    components = find_components(cluster_type)

    # Merge values for all components
    merged_values: Dict[str, Any] = {}
    for component_name in components:
        component_values = merge_component_values(cluster_type, component_name, target)
        merged_values = deep_merge(merged_values, component_values)

    # Create temporary values file for helm template
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as temp_values:
        yaml.dump(merged_values, temp_values, default_flow_style=False, sort_keys=False)
        temp_values_path = temp_values.name

        try:
            # Run helm template directly on the chart with custom values
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    f"{cluster_type}-apps",
                    "argocd-apps",  # Use the actual chart directory
                    "--values",
                    temp_values_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            # Create templates directory
            (target_dir / "templates").mkdir(exist_ok=True)

            # Parse all YAML documents and save each resource to its own file
            for doc in yaml.safe_load_all(result.stdout):
                if doc and doc.get("metadata", {}).get("name"):
                    resource_name = doc["metadata"]["name"]
                    with open(
                        target_dir / "templates" / f"{resource_name}.yaml", "w"
                    ) as f:
                        f.write("---\n")
                        yaml.dump(
                            doc,
                            f,
                            default_flow_style=False,
                            sort_keys=False,
                            width=1000,
                        )

            # Create Chart.yaml for this target
            chart_data = {
                "apiVersion": "v2",
                "name": f"{cluster_type}-{target.path.replace('/', '-')}",
                "description": f"Generated ArgoCD resources for {cluster_type}/{target.path}",
                "type": "application",
                "version": "0.1.0",
                "appVersion": "1.0",
            }
            save_yaml(chart_data, target_dir / "Chart.yaml")
            save_yaml(merged_values, target_dir / "values.yaml")

        except subprocess.CalledProcessError as e:
            print(f"Error running helm template: {e}")
            print(f"Stdout: {e.stdout}")
            print(f"Stderr: {e.stderr}")
            raise


def main() -> None:
    """Main generator function."""
    print("GitOps Fleet Generator")
    print("=====================")

    # Change to repository root (parent of hack/ directory)
    repo_root = Path(__file__).parent.parent
    os.chdir(repo_root)
    print(f"Working directory: {repo_root}")

    # Load global config
    config = load_yaml(Path("config/config.yaml"))
    if not config:
        raise ValueError("Global config file config/config.yaml is empty or invalid")

    # Discover all targets
    targets = discover_targets(config)
    print(f"Found {len(targets)} targets")
    for target in targets:
        print(f"  - {target.path}")

    # Clean rendered directory
    rendered_dir = Path("rendered")
    if rendered_dir.exists():
        shutil.rmtree(rendered_dir)

    # Process each cluster type
    for cluster_type_config in config["cluster_types"]:
        cluster_type: str = cluster_type_config["name"]
        print(f"\nProcessing cluster type: {cluster_type}")

        # Render each target
        for target in targets:
            render_target(cluster_type, target)

    print("\nGeneration complete! Check the 'rendered/' directory.")


if __name__ == "__main__":
    main()
