#!/usr/bin/env python3
"""Rename ZIP comic archives to CBZ and flatten redundant archive folders."""

from __future__ import annotations

import argparse
import shutil
import zipfile
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


def is_inside_duplicates(path: Path, target_dir: Path) -> bool:
    relative_parts = path.relative_to(target_dir).parts
    return any(part.lower() == DUPLICATES_DIR_NAME.lower() for part in relative_parts)


def iter_archive_files(target_dir: Path, recursive: bool, suffixes: set[str]) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    return sorted(
        path
        for path in target_dir.glob(pattern)
        if (
            path.is_file()
            and path.suffix.lower() in suffixes
            and not is_inside_duplicates(path, target_dir)
        )
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


def top_level_name(archive_name: str) -> str:
    return archive_name.replace("\\", "/").strip("/").split("/", 1)[0]


def redundant_folder_prefix(archive_path: Path, names: list[str]) -> str | None:
    file_names = [name for name in names if not name.replace("\\", "/").endswith("/")]
    if not file_names:
        return None

    expected_folder = archive_path.stem
    top_levels = {top_level_name(name) for name in file_names}
    if top_levels != {expected_folder}:
        return None

    prefix = f"{expected_folder}/"
    if all(name.replace("\\", "/").startswith(prefix) for name in file_names):
        return prefix

    return None


def flattened_info(info: zipfile.ZipInfo, prefix: str) -> zipfile.ZipInfo | None:
    normalized_name = info.filename.replace("\\", "/")
    if normalized_name == prefix:
        return None

    if not normalized_name.startswith(prefix):
        return info

    flattened_name = normalized_name[len(prefix) :]
    if not flattened_name:
        return None

    new_info = zipfile.ZipInfo(flattened_name, info.date_time)
    new_info.comment = info.comment
    new_info.extra = info.extra
    new_info.internal_attr = info.internal_attr
    new_info.external_attr = info.external_attr
    new_info.create_system = info.create_system
    new_info.compress_type = info.compress_type
    return new_info


def flatten_redundant_folder(archive_path: Path, duplicates_dir: Path) -> str:
    temp_path = archive_path.with_name(f".{archive_path.name}.tmp")

    with zipfile.ZipFile(archive_path, "r") as source:
        names = source.namelist()
        prefix = redundant_folder_prefix(archive_path, names)
        if prefix is None:
            return f"Archive already flat or has a different structure: {archive_path}"

        with zipfile.ZipFile(temp_path, "w") as destination:
            for info in source.infolist():
                new_info = flattened_info(info, prefix)
                if new_info is None:
                    continue
                destination.writestr(new_info, source.read(info.filename))

    backup_path = move_to_duplicates(archive_path, duplicates_dir)
    try:
        shutil.move(str(temp_path), str(archive_path))
    except Exception:
        if not archive_path.exists():
            shutil.move(str(backup_path), str(archive_path))
        raise

    return f"Flattened redundant folder in: {archive_path}; backup moved to {backup_path}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Rename .zip files in a target directory to .cbz, flatten redundant "
            "same-named top-level archive folders, and move smaller duplicate "
            "archives into Duplicates."
        )
    )
    parser.add_argument(
        "target",
        help=(
            "Directory containing archives to process, or a single .zip/.cbz file "
            "to process by itself."
        ),
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Also process .zip files in subdirectories.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target).expanduser().resolve()

    if not target.exists():
        print(f"Target does not exist: {target}")
        return 1

    if target.is_file():
        duplicates_dir = target.parent / DUPLICATES_DIR_NAME
        suffix = target.suffix.lower()

        if suffix == ".zip":
            print(convert_zip_file(target, duplicates_dir))
            cbz_path = matching_cbz_path(target)
            if cbz_path.exists():
                print(flatten_redundant_folder(cbz_path, duplicates_dir))
            print("Processed 1 file target.")
            return 0

        if suffix == ".cbz":
            print(flatten_redundant_folder(target, duplicates_dir))
            print("Processed 1 file target.")
            return 0

        print(f"Target file is not a .zip or .cbz archive: {target}")
        return 1

    if not target.is_dir():
        print(f"Target is not a file or directory: {target}")
        return 1

    duplicates_dir = target / DUPLICATES_DIR_NAME
    zip_files = iter_archive_files(target, args.recursive, {".zip"})
    for zip_path in zip_files:
        print(convert_zip_file(zip_path, duplicates_dir))

    cbz_files = iter_archive_files(target, args.recursive, {".cbz"})
    for cbz_path in cbz_files:
        print(flatten_redundant_folder(cbz_path, duplicates_dir))

    print(f"Processed {len(zip_files)} .zip file(s) and {len(cbz_files)} .cbz file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
