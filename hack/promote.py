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
        self.dimensions = self.config["dimensions"]
        self.sequence = self.config["sequence"]


config = Config()


@dataclass
class Patch:
    cluster_type: str
    application: str
    dimensions: list[str]
    name: str
    path: Path


# Default level to promote to when moving between top-level dimensions
DEFAULT_PROMOTION_LEVEL = "sectors"
DEFAULT_PROMOTION_LEVEL_NUMBER = (
    config.dimensions.index(DEFAULT_PROMOTION_LEVEL) + 1
)  # sectors = index 1 + 1 = 2


def walk(
    partial_sequence: dict, partial_dimensions: list[str], ancestors: list[str]
) -> Iterator[list[str]]:
    """Walk the sequence and yield each found dimension node (with ancestors)"""
    current_dimension = partial_dimensions[0]
    next_dimensions = partial_dimensions[1:]

    for d in partial_sequence[current_dimension]:
        yield ancestors + [d["name"]]
        next_dimension = next_dimensions[0] if next_dimensions else None
        if next_dimension:
            yield from walk(d, next_dimensions, ancestors + [d["name"]])


def find_all_patches(cluster_type: str, app: str, patch_name: str) -> Iterator[Patch]:
    """Find all patches in sequence order."""
    app_dir = config.root / cluster_type / app

    for path_parts in walk(config.sequence, config.dimensions, []):
        patch = Patch(
            cluster_type=cluster_type,
            application=app,
            dimensions=path_parts,
            name=patch_name,
            path=app_dir / Path(*path_parts) / f"{patch_name}.yaml",
        )
        if patch.path.exists():
            yield patch


def is_patched(dimension: list[str], patched_dimensions: list[list[str]]) -> bool:
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
    all_dimensions = list(walk(config.sequence, config.dimensions, []))

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

    for dimension in walk(config.sequence, config.dimensions, []):
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


def main():
    parser = argparse.ArgumentParser(description="Promote patches through the fleet")
    parser.add_argument("cluster_type", help="e.g. management-cluster")
    parser.add_argument("application", help="e.g. hypershift")
    parser.add_argument("patch_name", help="e.g. patch-001")

    args = parser.parse_args()

    patches = list(
        find_all_patches(args.cluster_type, args.application, args.patch_name)
    )
    if not patches:
        print(f"ERROR: No patches found for {args.application}")
        sys.exit(1)

    # Check for gaps first
    detect_gaps(patches)

    # Get next location
    next_patch = get_next_location(patches, args.cluster_type, args.application)
    print(f"Promoting to: {next_patch}")

    # Check if target exists
    if next_patch.exists():
        print(f"ERROR: Target already exists: {next_patch}")
        sys.exit(1)

    # Copy the patch
    next_patch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(patches[-1].path, next_patch)

    print("✓ Promoted successfully")
    print("\nNext steps:")
    print("  make generate")
    print("  git add config/")
    print(f"  git commit -m 'Promote {args.patch_name} for {args.application}'")


if __name__ == "__main__":
    main()
