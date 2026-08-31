#!/usr/bin/env python3
"""Find duplicate ZIP/CBZ archives by hash and move extras aside."""

from __future__ import annotations

import argparse
import hashlib
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


DUPLICATES_DIR_NAME = "_DUPLICATES"
LOG_FILENAME = "duplicates.log"
SUPPORTED_SUFFIXES = {".cbz", ".zip"}
CHUNK_SIZE = 1024 * 1024
COPY_SUFFIX_RE = re.compile(r"^(?P<base>.+?)\s*\((?P<copy_number>[1-9]\d*)\)$")


def configure_text_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")


@dataclass
class DuplicateMove:
    source: Path
    destination: Path
    keeper: Path
    sha256: str
    size: int


def iter_archive_files(source_dir: Path) -> list[Path]:
    duplicates_dir = source_dir / DUPLICATES_DIR_NAME
    return sorted(
        (
            path
            for path in source_dir.glob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and path.parent != duplicates_dir
        ),
        key=lambda path: path.name.lower(),
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate

    raise RuntimeError(f"Could not find an available duplicate filename for {path}")


def keeper_sort_key(path: Path) -> tuple[int, int, str]:
    suffix_rank = 0 if path.suffix.lower() == ".cbz" else 1
    return (suffix_rank, len(path.stem), path.name.lower())


def numbered_copy_base_name(path: Path) -> str | None:
    match = COPY_SUFFIX_RE.match(path.stem)
    if not match:
        return None

    base = match.group("base").rstrip()
    if not base:
        return None
    return f"{base}{path.suffix}"


def find_duplicate_groups(source_dir: Path) -> list[tuple[Path, list[Path], str]]:
    by_size: dict[int, list[Path]] = {}
    for archive_path in iter_archive_files(source_dir):
        by_size.setdefault(archive_path.stat().st_size, []).append(archive_path)

    groups: list[tuple[Path, list[Path], str]] = []
    for same_size_paths in by_size.values():
        if len(same_size_paths) < 2:
            continue

        by_hash: dict[str, list[Path]] = {}
        for archive_path in same_size_paths:
            by_hash.setdefault(sha256_file(archive_path), []).append(archive_path)

        for digest, same_hash_paths in by_hash.items():
            if len(same_hash_paths) < 2:
                continue
            ordered = sorted(same_hash_paths, key=keeper_sort_key)
            groups.append((ordered[0], ordered[1:], digest))

    return groups


def find_numbered_copy_groups(source_dir: Path, ignored_paths: set[Path]) -> list[tuple[Path, list[Path], str]]:
    archive_paths = iter_archive_files(source_dir)
    archive_by_name = {path.name.lower(): path for path in archive_paths}
    groups: list[tuple[Path, list[Path], str]] = []

    for archive_path in archive_paths:
        if archive_path in ignored_paths:
            continue

        base_name = numbered_copy_base_name(archive_path)
        if base_name is None:
            continue

        keeper = archive_by_name.get(base_name.lower())
        if keeper is None or keeper in ignored_paths or keeper == archive_path:
            continue

        groups.append((keeper, [archive_path], sha256_file(archive_path)))

    return groups


def append_move_log(source_dir: Path, moves: list[DuplicateMove]) -> Path:
    duplicates_dir = source_dir / DUPLICATES_DIR_NAME
    duplicates_dir.mkdir(exist_ok=True)
    log_path = duplicates_dir / LOG_FILENAME
    timestamp = datetime.now().isoformat(timespec="seconds")
    lines = []
    for move in moves:
        lines.append(
            "\t".join(
                [
                    timestamp,
                    f"sha256={move.sha256}",
                    f"size={move.size}",
                    f"kept={move.keeper.name}",
                    f"moved={move.source.name}",
                    f"destination={move.destination.name}",
                ]
            )
        )
    with log_path.open("a", encoding="utf-8", newline="\n") as handle:
        for line in lines:
            handle.write(line + "\n")
    return log_path


def move_duplicate_archives(source_dir: Path, dry_run: bool = False) -> list[str]:
    source_dir = source_dir.expanduser().resolve()
    if not source_dir.exists():
        raise FileNotFoundError(f"Source directory does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"Source path is not a directory: {source_dir}")

    duplicates_dir = source_dir / DUPLICATES_DIR_NAME
    moves: list[DuplicateMove] = []
    messages: list[str] = []

    for keeper, duplicate_paths, digest in find_duplicate_groups(source_dir):
        for duplicate_path in duplicate_paths:
            destination = unique_path(duplicates_dir / duplicate_path.name)
            move = DuplicateMove(
                source=duplicate_path,
                destination=destination,
                keeper=keeper,
                sha256=digest,
                size=duplicate_path.stat().st_size,
            )
            moves.append(move)
            action = "Would move" if dry_run else "Moved"
            messages.append(f"{action} duplicate {duplicate_path.name} -> {destination.name}; kept {keeper.name}")

    planned_sources = {move.source for move in moves}
    for keeper, duplicate_paths, digest in find_numbered_copy_groups(source_dir, planned_sources):
        for duplicate_path in duplicate_paths:
            destination = unique_path(duplicates_dir / duplicate_path.name)
            move = DuplicateMove(
                source=duplicate_path,
                destination=destination,
                keeper=keeper,
                sha256=digest,
                size=duplicate_path.stat().st_size,
            )
            moves.append(move)
            planned_sources.add(duplicate_path)
            action = "Would move" if dry_run else "Moved"
            messages.append(f"{action} duplicate {duplicate_path.name} -> {destination.name}; kept {keeper.name}")

    if not moves:
        return ["No duplicate archives found."]

    if dry_run:
        return messages

    duplicates_dir.mkdir(exist_ok=True)
    for move in moves:
        shutil.move(str(move.source), str(move.destination))

    log_path = append_move_log(source_dir, moves)
    messages.append(f"Logged {len(moves)} duplicate move(s) to {log_path}")
    return messages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare direct-child .zip/.cbz archives by size and SHA-256, then "
            "move duplicate matches and numbered copies into a _DUPLICATES folder."
        )
    )
    parser.add_argument("source", help="ComicRack source directory to inspect.")
    parser.add_argument("--dry-run", action="store_true", help="Report duplicate moves without moving files.")
    return parser.parse_args()


def main() -> int:
    configure_text_output()
    args = parse_args()
    try:
        messages = move_duplicate_archives(Path(args.source), dry_run=args.dry_run)
    except Exception as exc:
        print(f"Failed to remove duplicates: {exc}")
        return 1

    for message in messages:
        print(message)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
