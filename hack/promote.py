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

from utils import Config, deep_merge, load_yaml, save_yaml, walk_dimensions

config = Config()


@dataclass
class Patch:
    cluster_type: str
    application: str
    dimensions: tuple[str, ...]
    name: str

    @property
    def path(self) -> Path:
        return (
            config.path(self.cluster_type, self.application)
            / Path(*self.dimensions)
            / f"{self.name}.yaml"
        )

    def duplicate(self, dimensions: tuple[str, ...]) -> "Patch":
        return Patch(
            cluster_type=self.cluster_type,
            application=self.application,
            dimensions=dimensions,
            name=self.name,
        )


# Default level to promote to when moving between top-level dimensions
DEFAULT_PROMOTION_LEVEL = "sectors"
DEFAULT_PROMOTION_LEVEL_NUMBER = (
    config.dimensions.index(DEFAULT_PROMOTION_LEVEL) + 1
)  # sectors = index 1 + 1 = 2


def find_patches(cluster_type: str, app: str, patch_name: str) -> Iterator[Patch]:
    """Find all patches in sequence order."""
    for path_parts in walk_dimensions(config.sequence, config.dimensions):
        patch = Patch(
            cluster_type=cluster_type,
            application=app,
            dimensions=path_parts,
            name=patch_name,
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
    all_dimensions = list(walk_dimensions(config.sequence, config.dimensions))

    for dimension in all_dimensions:
        if dimension == latest_patch.dimensions:
            break  # Stop at latest patch
        if len(dimension) < len(config.dimensions):
            continue  # Skip incomplete paths
        if not is_patched(dimension, patched_dimensions):
            raise ValueError(
                f"Gap detected: patch exists at {'/'.join(latest_patch.dimensions)} but missing from {'/'.join(dimension)}"
            )


def get_next_location(patches: list[Patch]) -> Path | None:
    """Get the next location to promote the patch to."""
    current_patch = patches[-1]
    patched_dimensions = [p.dimensions for p in patches]
    current_patch_dimension_reached = False

    for dimension in walk_dimensions(config.sequence, config.dimensions):
        if dimension == current_patch.dimensions:
            current_patch_dimension_reached = True
            continue
        if not current_patch_dimension_reached:
            continue

        if is_patched(dimension, patched_dimensions):
            continue  # Skip already patched

        if len(dimension) < DEFAULT_PROMOTION_LEVEL_NUMBER:
            continue  # Do not promote to full environments

        next_patch = current_patch.duplicate(dimension)
        return next_patch.path

    print("No promotion target found")
    return None


def promote(patches: list[Patch]) -> None:
    """Promote patches to the next location and perform coalescing."""
    # Get next location
    next_patch = get_next_location(patches)
    if next_patch is None:
        return

    if next_patch.exists():
        raise FileExistsError(f"ERROR: Target already exists: {next_patch}")
    print(f"Promoting to: {next_patch}")

    next_patch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(patches[-1].path, next_patch)


def merge_patch_into_values(patch: Patch, values_file: Path) -> None:
    """Merge patch content into values.yaml, excluding metadata."""
    # Load patch content and strip metadata
    patch_data = load_yaml(patch.path)

    if "metadata" in patch_data:
        del patch_data["metadata"]

    # Load existing values.yaml
    values_data = load_yaml(values_file, check_empty=True)

    # Deep merge patch into values
    values_data = deep_merge(values_data, patch_data)

    # Write merged content back
    save_yaml(values_data, values_file)


def _perform_coalescing(
    root: tuple[str, ...],
    patches_to_remove: list[Patch],
    patch_by_dimensions: dict[tuple[str, ...], Patch],
) -> None:
    """Perform the actual coalescing: create new patch and remove old ones."""
    source_patch = patches_to_remove[0]

    # Create new patch in root
    new_patch = source_patch.duplicate(root)

    shutil.copy2(source_patch.path, new_patch.path)
    patch_by_dimensions[root] = new_patch

    # Remove old patches in children dimensions
    for patch in patches_to_remove:
        patch.path.unlink()
        del patch_by_dimensions[patch.dimensions]


def coalesce_patches(cluster_type: str, application: str, patch_name: str) -> None:
    """Coalesce patches that can be promoted together."""
    # Find all current patches
    patches = list(find_patches(cluster_type, application, patch_name))
    if not patches:
        return

    # Get all possible dimensions
    all_dimensions = list(walk_dimensions(config.sequence, config.dimensions))

    patch_by_dimensions = {p.dimensions: p for p in patches}

    for idx in range(1, len(config.dimensions)):
        root_dimensions: dict[tuple[str, ...], list[tuple[str, ...]]] = {}
        for d in all_dimensions:
            if len(d) == len(config.dimensions):
                root_dimensions.setdefault(d[:idx], []).append(d)

        for root, dims in root_dimensions.items():
            # continue if this level or a higher level is already patched
            if is_patched(root, list(patch_by_dimensions)):
                continue

            if all(is_patched(dim, list(patch_by_dimensions)) for dim in dims):
                # we can coalesce all matching patches into root
                patches_to_remove = [
                    p for p in patches if p.dimensions[: len(root)] == root
                ]
                _perform_coalescing(root, patches_to_remove, patch_by_dimensions)

    # Final consolidation: root-level patches → values.yaml
    all_root_names = {root["name"] for root in config.sequence[config.dimensions[0]]}
    root_patches = [p for p in patch_by_dimensions.values() if len(p.dimensions) == 1]
    root_patch_names = {p.dimensions[0] for p in root_patches}

    if root_patch_names == all_root_names:
        values_file = config.path(cluster_type, application) / "values.yaml"
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

    patches = list(find_patches(args.cluster_type, args.application, args.patch_name))
    if not patches:
        print(f"ERROR: No patches found for {args.application}")
        sys.exit(1)

    # Check for gaps first
    detect_gaps(patches)

    # Promote the patch if possible
    promote(patches)

    # Coalesce patches if possible
    coalesce_patches(args.cluster_type, args.application, args.patch_name)

    print("✓ Promoted successfully")
    print("\nNext steps:")
    print("  make generate")
    print("  git add config/ rendered/")
    print(f"  git commit -m 'Promote {args.patch_name} for {args.application}'")


if __name__ == "__main__":
    main()
