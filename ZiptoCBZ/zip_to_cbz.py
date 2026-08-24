#!/usr/bin/env python3
"""Rename ZIP comic archives to CBZ, keeping smaller duplicate archives aside."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


DUPLICATES_DIR_NAME = "Duplicates"


def unique_path(path: Path) -> Path:
    """Return a path that does not already exist by appending a numeric suffix."""
    if not path.exists():
        return path

    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find an available duplicate filename for {path}")


def move_to_duplicates(file_path: Path, duplicates_dir: Path) -> Path:
    duplicates_dir.mkdir(exist_ok=True)
    destination = unique_path(duplicates_dir / file_path.name)
    shutil.move(str(file_path), str(destination))
    return destination


def matching_cbz_path(zip_path: Path) -> Path:
    return zip_path.with_suffix(".cbz")


def iter_zip_files(target_dir: Path, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in target_dir.glob(pattern)
        if path.is_file() and path.suffix.lower() == ".zip"
    )


def convert_zip_file(zip_path: Path, root_duplicates_dir: Path) -> str:
    cbz_path = matching_cbz_path(zip_path)

    if not cbz_path.exists():
        zip_path.rename(cbz_path)
        return f"Renamed: {zip_path} -> {cbz_path}"

    zip_size = zip_path.stat().st_size
    cbz_size = cbz_path.stat().st_size

    if zip_size < cbz_size:
        duplicate_path = move_to_duplicates(zip_path, root_duplicates_dir)
        return (
            f"Duplicate found: kept larger CBZ {cbz_path}; "
            f"moved smaller ZIP to {duplicate_path}"
        )

    if cbz_size < zip_size:
        duplicate_path = move_to_duplicates(cbz_path, root_duplicates_dir)
        zip_path.rename(cbz_path)
        return (
            f"Duplicate found: moved smaller CBZ to {duplicate_path}; "
            f"renamed ZIP to {cbz_path}"
        )

    duplicate_path = move_to_duplicates(zip_path, root_duplicates_dir)
    return (
        f"Duplicate found with equal size: kept existing CBZ {cbz_path}; "
        f"moved ZIP to {duplicate_path}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rename .zip files in a target directory to .cbz. If a same-named "
            ".cbz already exists, move the smaller archive into Duplicates."
        )
    )
    parser.add_argument("target_dir", help="Directory containing .zip files to convert.")
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Also process .zip files in subdirectories.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target_dir = Path(args.target_dir).expanduser().resolve()

    if not target_dir.exists():
        print(f"Target directory does not exist: {target_dir}")
        return 1

    if not target_dir.is_dir():
        print(f"Target path is not a directory: {target_dir}")
        return 1

    zip_files = iter_zip_files(target_dir, args.recursive)
    if not zip_files:
        print(f"No .zip files found in {target_dir}")
        return 0

    duplicates_dir = target_dir / DUPLICATES_DIR_NAME
    for zip_path in zip_files:
        print(convert_zip_file(zip_path, duplicates_dir))

    print(f"Processed {len(zip_files)} .zip file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
