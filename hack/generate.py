#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///

"""
Simple GitOps fleet generator.
Generates ArgoCD resources for multi-dimensional deployment hierarchies.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

import yaml
from utils import Config, Patch, deep_merge, get_config, load_yaml, save_yaml


@dataclass
class Target:
    """Represents a deployment target with configurable dimensions."""

    path_parts: List[str]  # e.g., ["production", "prod-sector-1", "us-east1"]

    @property
    def path(self) -> str:
        """Get the file system path for this target."""
        return "/".join(self.path_parts)


def discover_targets(config: Config) -> List[Target]:
    """Discover all dimensional combinations from configurable hierarchy.

    Traverses the dimensional structure defined in config.yaml to generate
    all possible environment/sector/region (or other) combinations as deployment targets.
    """
    targets = []
    for path_parts in config.all_dimensions:
        # Only keep complete leaf paths (full dimensional depth)
        if len(path_parts) == len(config.dimensions):
            targets.append(Target(list(path_parts)))

    return targets


def load_base_component_values(
    cluster_type: str, component_name: str
) -> Dict[str, Any]:
    """Load base component values including defaults."""
    base_path = get_config().path(cluster_type)
    merged: Dict[str, Any] = {}

    # 1. Load defaults for all resource types (mandatory)
    defaults_file = base_path / "defaults.yaml"
    defaults_to_apply = load_yaml(defaults_file, check_empty=True)

    # 2. Load base component values (mandatory)
    component_values_file = base_path / component_name / "values.yaml"
    component_values = load_yaml(component_values_file, check_empty=True)
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

    # Now apply defaults to each used section ("applications", "applicationsets", etc.)
    for section_name in component_values.keys():
        default_values = defaults_to_apply[section_name]["default"]
        # Apply defaults to each item in this section
        for item_name in component_values[section_name]:
            merged[section_name].setdefault(item_name, {})
            # Merge defaults with the item (item takes precedence)
            merged[section_name][item_name] = deep_merge(
                default_values, merged[section_name][item_name]
            )

    return merged


def warn_on_conflicts(
    patch: Patch,
    applied_patches: List[Patch],
) -> None:
    """Check for conflicts with previously applied patches, warn if found, and track this patch."""
    patch_jsonpaths = patch.patched_fields

    for previous_patch in applied_patches:
        conflicts = set(patch_jsonpaths) & set(previous_patch.patched_fields)
        if conflicts:
            print("WARNING: Patch conflict detected:")
            print(f"  {patch.path} conflicts with {previous_patch.path}")
            print(f"  Conflicting paths: {', '.join(sorted(conflicts))}")

    applied_patches.append(patch)


def merge_component_values(
    config: Config, cluster_type: str, component_name: str, target: Target
) -> Dict[str, Any]:
    """Merge component values for a specific target."""
    component_dir = config.path(cluster_type, component_name)

    # Load base component values with defaults
    merged = load_base_component_values(cluster_type, component_name)

    # e.g., for ["production", "prod-sector-1", "us-east1"]
    # try: production/, production/prod-sector-1/, production/prod-sector-1/us-east1/
    for i in range(len(target.path_parts)):
        dimensions = target.path_parts[: i + 1]
        dimension_dir = component_dir / "/".join(dimensions)

        if not dimension_dir.exists():
            continue

        # Apply permanent values first
        override_file = dimension_dir / "override.yaml"
        if override_file.exists():
            override = load_yaml(override_file)
            merged = deep_merge(merged, override)

        # Apply patches second (in filename order)
        applied_patches: List[Patch] = []

        for patch_file in sorted(dimension_dir.glob("patch-*.yaml")):
            patch = Patch(
                cluster_type=cluster_type,
                component=component_name,
                dimensions=tuple(dimensions),
                name=patch_file.stem,
            )

            # Check for conflicts with previously applied patches
            warn_on_conflicts(patch, applied_patches)

            merged = deep_merge(merged, patch.content)

    return merged


def render_target(cluster_type: str, target: Target, config: Config) -> None:
    """Render all components for a specific target."""
    print(f"Rendering {cluster_type}/{target.path}")

    # Create target directory
    target_dir = config.rendered_path / cluster_type / target.path
    (target_dir / "templates").mkdir(parents=True, exist_ok=True)

    # Find components for this cluster type
    components = config.components(cluster_type)

    # Merge values for all components
    merged_values: Dict[str, Any] = {}
    for component_name in sorted(components):
        component_values = merge_component_values(
            config, cluster_type, component_name, target
        )
        merged_values = deep_merge(merged_values, component_values)

    # Create temporary values file for helm template
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False
    ) as temp_values:
        temp_values_path = temp_values.name
        save_yaml(merged_values, Path(temp_values_path))

        try:
            # Run helm template directly on the chart with custom values
            result = subprocess.run(
                [
                    "helm",
                    "template",
                    f"{cluster_type}-apps",
                    "argocd-apps",
                    "--values",
                    temp_values_path,
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse all YAML documents and save each resource to its own file
            for doc in yaml.safe_load_all(result.stdout):
                if doc and doc.get("metadata", {}).get("name"):
                    resource_name = doc["metadata"]["name"]
                    resource_file = target_dir / "templates" / f"{resource_name}.yaml"
                    save_yaml(doc, resource_file)

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
    os.chdir(repo_root)  # TODO: check if needed
    print(f"Working directory: {repo_root}")

    # Load global config
    config = get_config()

    # Discover all targets
    targets = discover_targets(config)
    print(f"Found {len(targets)} targets")
    for target in targets:
        print(f"  - {target.path}")

    # Clean rendered directory
    rendered_dir = repo_root / "rendered"
    if rendered_dir.exists():
        shutil.rmtree(rendered_dir)

    # Process each cluster type
    for cluster_type_config in config.cluster_types:
        cluster_type: str = cluster_type_config["name"]
        print(f"\nProcessing cluster type: {cluster_type}")

        # Render each target
        for target in targets:
            render_target(cluster_type, target, config)

    print("\nGeneration complete! Check the 'rendered/' directory.")


if __name__ == "__main__":
    main()
