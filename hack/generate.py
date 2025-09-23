#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///

"""
Simple GitOps fleet generator.
Generates ArgoCD applications for multi-dimensional deployment hierarchies.
"""

import yaml
import shutil
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Any

@dataclass
class Target:
    """Represents a deployment target with configurable dimensions."""
    path_parts: List[str]  # e.g., ["production", "prod-sector-1", "us-east1"]

    @property
    def path(self) -> str:
        """Get the file system path for this target."""
        return "/".join(self.path_parts)

@dataclass
class ClusterType:
    """Represents a cluster type configuration."""
    name: str
    applications: List[str]

def load_yaml(file_path: Path) -> Dict[str, Any]:
    """Load YAML file."""
    with open(file_path, 'r') as f:
        return yaml.safe_load(f)

def save_yaml(data: Dict[str, Any], file_path: Path) -> None:
    """Save data to YAML file."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, 'w') as f:
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
    """Discover all dimensional combinations from config."""
    def traverse_dimensions(sequence_data: Any, current_path: List[str] = []) -> List[Target]:
        """Recursively traverse dimensional hierarchy."""
        targets: List[Target] = []

        if isinstance(sequence_data, list):
            # This is a list of dimension items
            for item in sequence_data:
                if isinstance(item, dict) and 'name' in item:
                    item_name = item['name']
                    new_path = current_path + [item_name]

                    # Check if this item has child dimensions
                    child_keys = [k for k in item.keys() if k not in ['name', 'promotion']]
                    if child_keys:
                        # Has children, recurse
                        for child_key in child_keys:
                            targets.extend(traverse_dimensions(item[child_key], new_path))
                    else:
                        # Leaf node, create target
                        targets.append(Target(new_path))

        elif isinstance(sequence_data, dict):
            # This is a dimension container, recurse into its values
            for value in sequence_data.values():
                targets.extend(traverse_dimensions(value, current_path))

        return targets

    return traverse_dimensions(config['sequence'])

def find_applications(cluster_type: str) -> List[str]:
    """Find all applications for a cluster type."""
    config_dir = Path(f"config/{cluster_type}")
    apps: List[str] = []

    if not config_dir.exists():
        return apps

    for app_dir in config_dir.iterdir():
        if app_dir.is_dir() and app_dir.name != "application-defaults.yaml":
            if (app_dir / "values.yaml").exists():
                apps.append(app_dir.name)

    return apps

def merge_application_values(cluster_type: str, app_name: str, target: Target) -> Dict[str, Any]:
    """Merge application values for a specific target."""
    base_path = Path(f"config/{cluster_type}")
    merged: Dict[str, Any] = {}

    # 1. Load application defaults
    defaults_file = base_path / "application-defaults.yaml"
    if defaults_file.exists():
        defaults = load_yaml(defaults_file)
        if 'defaults' in defaults:
            merged = deep_merge(merged, {'applications': {app_name: defaults['defaults']}})

    # 2. Load base application values (mandatory)
    app_values_file = base_path / app_name / "values.yaml"
    if not app_values_file.exists():
        raise FileNotFoundError(f"Mandatory application values file not found: {app_values_file}")

    app_values = load_yaml(app_values_file)
    merged = deep_merge(merged, app_values)

    # 3. Load dimensional overrides (try each path level)
    # e.g., for ["production", "prod-sector-1", "us-east1"]
    # try: production/values.yaml, prod-sector-1/values.yaml, us-east1/values.yaml
    app_dir = base_path / app_name
    for dimension_value in target.path_parts:
        override_file = app_dir / dimension_value / "values.yaml"
        if override_file.exists():
            override = load_yaml(override_file)
            merged = deep_merge(merged, override)

    return merged

def render_target(cluster_type: str, target: Target) -> None:
    """Render all applications for a specific target."""
    print(f"Rendering {cluster_type}/{target.path}")

    # Create target directory
    target_dir = Path(f"rendered/{cluster_type}/{target.path}")
    target_dir.mkdir(parents=True, exist_ok=True)

    # Find applications for this cluster type
    applications = find_applications(cluster_type)

    # Merge values for all applications
    merged_values: Dict[str, Any] = {}
    for app_name in applications:
        app_values = merge_application_values(cluster_type, app_name, target)
        merged_values = deep_merge(merged_values, app_values)

    # Create temporary Helm chart for processing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_chart = Path(temp_dir) / "chart"
        temp_chart.mkdir()

        # Copy templates
        templates_dir = Path("templates")

        # Create Chart.yaml
        chart_file = templates_dir / "Chart.yaml"
        if chart_file.exists():
            chart_data = load_yaml(chart_file)
            chart_data['name'] = f"{cluster_type}-apps"
            chart_data['description'] = f"ArgoCD applications for {cluster_type} in {target.path}"
            save_yaml(chart_data, temp_chart / "Chart.yaml")

        # Copy application template
        app_template = templates_dir / "application.yaml"
        if app_template.exists():
            (temp_chart / "templates").mkdir(exist_ok=True)
            shutil.copy2(app_template, temp_chart / "templates" / "application.yaml")

        # Create values.yaml
        save_yaml(merged_values, temp_chart / "values.yaml")

        # Run helm template to generate final manifests
        try:
            result = subprocess.run(
                ["helm", "template", f"{cluster_type}-apps", str(temp_chart)],
                capture_output=True,
                text=True,
                check=True
            )

            # Create templates directory
            (target_dir / "templates").mkdir(exist_ok=True)

            # Split the helm output into separate applications
            raw_output = result.stdout

            # Remove source comments
            lines = raw_output.split('\n')
            filtered_lines = [line for line in lines if not line.startswith('# Source:')]
            clean_output = '\n'.join(filtered_lines)

            # Split by YAML document separators and parse each application
            yaml_docs = clean_output.split('---\n')

            for doc_text in yaml_docs:
                doc_text = doc_text.strip()
                if not doc_text:
                    continue

                # Parse the document to extract application name
                doc = yaml.safe_load(doc_text)
                if doc and doc.get('kind') == 'Application':
                    app_name = doc['metadata']['name']

                    # Save each application to its own file
                    with open(target_dir / "templates" / f"{app_name}.yaml", 'w') as f:
                        f.write('---\n' + doc_text)

            # Save the Chart.yaml and aggregated values.yaml
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
    import os
    os.chdir(repo_root)
    print(f"Working directory: {repo_root}")

    # Load global config
    config = load_yaml(Path("config/config.yaml"))

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
    for cluster_type_config in config['cluster_types']:
        cluster_type: str = cluster_type_config['name']
        print(f"\nProcessing cluster type: {cluster_type}")

        # Render each target
        for target in targets:
            render_target(cluster_type, target)

    print("\nGeneration complete! Check the 'rendered/' directory.")

if __name__ == "__main__":
    main()