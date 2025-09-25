#!/usr/bin/env python3
# /// script
# dependencies = ["pyyaml"]
# ///

"""
Ultra-simple patch promotion tool.

Usage: uv run hack/promote.py management-cluster hypershift patch-001

Promotes a patch to the next location in the sequence by simply copying the file.
"""

import argparse
import shutil
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import yaml


class Config:
    def __init__(self, root: Path | None = None):
        self.root = Path(__file__).parent.parent / "config" if root is None else root
        config_yaml = self.root / "config.yaml"
        if not config_yaml.exists():
            print(f"ERROR: config.yaml not found at {config_yaml}")
            sys.exit(1)
        with open(config_yaml) as f:
            self.config = yaml.safe_load(f)
        self.dimensions = tuple(self.config["dimensions"])
        self.sequence = self.config["sequence"]


config = Config()


@dataclass
class Patch:
    cluster_type: str
    application: str
    dimensions: tuple[str, ...]
    name: str
    path: Path


# Default level to promote to when moving between top-level dimensions
DEFAULT_PROMOTION_LEVEL = "sectors"
DEFAULT_PROMOTION_LEVEL_NUMBER = (
    config.dimensions.index(DEFAULT_PROMOTION_LEVEL) + 1
)  # sectors = index 1 + 1 = 2


def walk(
    partial_sequence: dict,
    partial_dimensions: tuple[str, ...],
    ancestors: tuple[str, ...],
) -> Iterator[tuple[str, ...]]:
    """Walk the sequence and yield each found dimension node (with ancestors)"""
    current_dimension = partial_dimensions[0]
    next_dimensions = partial_dimensions[1:]

    for d in partial_sequence[current_dimension]:
        yield ancestors + (d["name"],)
        next_dimension = next_dimensions[0] if next_dimensions else None
        if next_dimension:
            yield from walk(d, next_dimensions, ancestors + (d["name"],))


def find_patches(cluster_type: str, app: str, patch_name: str) -> Iterator[Patch]:
    """Find all patches in sequence order."""
    app_dir = config.root / cluster_type / app

    for path_parts in walk(config.sequence, config.dimensions, ()):
        patch = Patch(
            cluster_type=cluster_type,
            application=app,
            dimensions=path_parts,
            name=patch_name,
            path=app_dir / Path(*path_parts) / f"{patch_name}.yaml",
        )
        if patch.path.exists():
            yield patch


def is_patched(
    dimension: tuple[str, ...], patched_dimensions: list[tuple[str, ...]]
) -> bool:
    """Check if a given dimension path is already patched."""
    for patched_dimension in patched_dimensions:
        if dimension[: len(patched_dimension)] == patched_dimension:
            return True
    return False


def detect_gaps(patches: list[Patch]) -> None:
    """Detect gaps in the sequence of patches."""
    if not patches:
        return None
    latest_patch = patches[-1]

    patched_dimensions = [p.dimensions for p in patches]
    all_dimensions = list(walk(config.sequence, config.dimensions, ()))

    for dimension in all_dimensions:
        if dimension == latest_patch.dimensions:
            break  # Stop at latest patch
        if len(dimension) < len(config.dimensions):
            continue  # Skip incomplete paths
        if not is_patched(dimension, patched_dimensions):
            raise ValueError(
                f"Gap detected: patch exists at {'/'.join(latest_patch.dimensions)} but missing from {'/'.join(dimension)}"
            )


def get_next_location(patches: list[Patch], cluster_type: str, app: str) -> Path:
    """Get the next location to promote the patch to."""
    current_patch = patches[-1]
    patched_dimensions = [p.dimensions for p in patches]
    current_patch_dimension_reached = False

    for dimension in walk(config.sequence, config.dimensions, ()):
        if dimension == current_patch.dimensions:
            current_patch_dimension_reached = True
            continue
        if not current_patch_dimension_reached:
            continue

        if is_patched(dimension, patched_dimensions):
            continue  # Skip already patched

        if len(dimension) < DEFAULT_PROMOTION_LEVEL_NUMBER:
            continue  # Do not promote to full environments

        return (
            config.root
            / cluster_type
            / app
            / Path(*dimension)
            / f"{current_patch.name}.yaml"
        )

    print("No promotion target found")
    sys.exit(1)


def promote(patches: list[Patch], cluster_type: str, application: str) -> None:
    """Promote patches to the next location and perform coalescing."""
    # Get next location
    next_patch = get_next_location(patches, cluster_type, application)
    print(f"Promoting to: {next_patch}")

    # Check if target exists
    if next_patch.exists():
        print(f"ERROR: Target already exists: {next_patch}")
        sys.exit(1)

    # Copy the patch
    next_patch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(patches[-1].path, next_patch)


def merge_patch_into_values(patch: Patch, values_file: Path) -> None:
    """Merge patch content into values.yaml, excluding metadata."""
    # Load patch content and strip metadata
    with open(patch.path) as f:
        patch_data = yaml.safe_load(f)

    if "metadata" in patch_data:
        del patch_data["metadata"]

    # Load existing values.yaml
    with open(values_file) as f:
        values_data = yaml.safe_load(f) or {}

    # Deep merge patch into values
    def deep_merge(base, update):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                deep_merge(base[key], value)
            else:
                base[key] = value

    deep_merge(values_data, patch_data)

    # Write merged content back
    with open(values_file, 'w') as f:
        yaml.dump(values_data, f, default_flow_style=False, sort_keys=False)


def coalesce_patches(cluster_type: str, application: str, patch_name: str) -> None:
    """Coalesce patches that can be promoted together."""
    # Find all current patches
    patches = list(find_patches(cluster_type, application, patch_name))
    if not patches:
        return

    # Get all possible dimensions
    all_dimensions = list(walk(config.sequence, config.dimensions, ()))

    patch_by_dimensions = {p.dimensions: p for p in patches}

    print("Coalescing patches")

    for idx in range(1, len(config.dimensions)):
        root_dimensions: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
        for d in all_dimensions:
            if len(d) == len(config.dimensions):
                root_dimensions.setdefault(d[:idx], []).append(d)

        for root, dims in root_dimensions.items():
            # continue if a higher level is patched
            if is_patched(root, patch_by_dimensions.keys()):
                print(f"  DEBUG: skipping {root} as it is already patched")
                continue

            if root in patch_by_dimensions:
                # already patched at this level
                print(f"MIGHT NOT BE NEEDED WITH THE TEST ABOVE: {root}")
                continue

            print(f"  Checking {root}...")
            if all(is_patched(dim, patch_by_dimensions.keys()) for dim in dims):
                # we can coalesce all matching patches into root
                print(f"    Coalescing {dims}")
                new_patch = Patch(
                    cluster_type,
                    application,
                    root,
                    patch_name,
                    config.root
                    / cluster_type
                    / application
                    / Path(*root)
                    / f"{patch_name}.yaml",
                )
                # create new patch in root - use any existing patch for content
                source_patch = list(patch_by_dimensions.values())[0]
                shutil.copy2(source_patch.path, new_patch.path)
                patch_by_dimensions[root] = new_patch
                # remove old patches in children dimensions
                for patch in [p for p in patches if p.dimensions[: len(root)] == root]:
                    patch.path.unlink()
                    del patch_by_dimensions[patch.dimensions]

    # Final consolidation: root-level patches → values.yaml
    all_root_names = {root["name"] for root in config.sequence[config.dimensions[0]]}
    root_patches = [p for p in patch_by_dimensions.values() if len(p.dimensions) == 1]
    root_patch_names = {p.dimensions[0] for p in root_patches}

    if root_patch_names == all_root_names:
        print("  Final consolidation to values.yaml")
        values_file = config.root / cluster_type / application / "values.yaml"
        merge_patch_into_values(root_patches[0], values_file)

        # Remove all root-level patches
        for patch in root_patches:
            patch.path.unlink()


def main():
    parser = argparse.ArgumentParser(description="Promote patches through the fleet")
    parser.add_argument("cluster_type", help="e.g. management-cluster")
    parser.add_argument("application", help="e.g. hypershift")
    parser.add_argument("patch_name", help="e.g. patch-001")

    args = parser.parse_args()

    patches = list(
        find_patches(args.cluster_type, args.application, args.patch_name)
    )
    if not patches:
        print(f"ERROR: No patches found for {args.application}")
        sys.exit(1)

    # Check for gaps first
    detect_gaps(patches)

    # Promote the patch if possible
    promote(patches, args.cluster_type, args.application)

    # Coalesce patches if possible
    coalesce_patches(args.cluster_type, args.application, args.patch_name)

    print("✓ Promoted successfully")
    print("\nNext steps:")
    print("  make generate")
    print("  git add config/")
    print(f"  git commit -m 'Promote {args.patch_name} for {args.application}'")


if __name__ == "__main__":
    main()
