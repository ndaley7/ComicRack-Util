#!/usr/bin/env python3
"""Install the GalleryTagPanel ComicRack script folder."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


PLUGIN_DIR_NAME = "ComicRackGalleryTagPanel"
CLASSIC_APPDATA_PATH = Path("cYo") / "ComicRack" / "Scripts"
CE_APPDATA_PATH = Path("cYo") / "ComicRack Community Edition" / "Scripts"
IGNORED_DIRS = {".git", "__pycache__"}
IGNORED_SUFFIXES = {".pyc", ".pyo"}


def default_scripts_dir(use_classic: bool) -> Path:
    appdata = Path.home() / "AppData" / "Roaming"
    return appdata / (CLASSIC_APPDATA_PATH if use_classic else CE_APPDATA_PATH)


def should_copy(path: Path) -> bool:
    if path.name in IGNORED_DIRS:
        return False
    if path.suffix.lower() in IGNORED_SUFFIXES:
        return False
    return True


def copy_plugin(source_dir: Path, scripts_dir: Path, dry_run: bool = False) -> Path:
    if not source_dir.is_dir():
        raise FileNotFoundError(f"Plugin folder not found: {source_dir}")

    destination_dir = scripts_dir / source_dir.name
    copied = 0

    for source_path in source_dir.rglob("*"):
        if not all(should_copy(part) for part in source_path.relative_to(source_dir).parents):
            continue
        if not should_copy(source_path):
            continue
        if not source_path.is_file():
            continue

        relative_path = source_path.relative_to(source_dir)
        destination_path = destination_dir / relative_path
        copied += 1

        if dry_run:
            print(f"Would copy: {source_path} -> {destination_path}")
            continue

        destination_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination_path)

    if copied == 0:
        raise RuntimeError(f"No plugin files found to copy from: {source_dir}")

    if dry_run:
        print(f"Dry run complete. {copied} files would be copied to {destination_dir}")
    else:
        print(f"Installed {copied} files to {destination_dir}")
        print("Restart ComicRack, then run Right-click -> Automation -> GalleryTagPanel.")

    return destination_dir


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy ComicRackGalleryTagPanel into a ComicRack scripts folder.",
    )
    parser.add_argument(
        "--classic",
        action="store_true",
        help="Install into classic ComicRack instead of ComicRack Community Edition.",
    )
    parser.add_argument(
        "--dest",
        type=Path,
        help="Override the Scripts folder destination.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(__file__).resolve().parent / PLUGIN_DIR_NAME,
        help="Override the source plugin folder.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be copied without writing files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    source_dir = args.source.resolve()
    scripts_dir = (args.dest or default_scripts_dir(args.classic)).resolve()

    try:
        copy_plugin(source_dir, scripts_dir, args.dry_run)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
