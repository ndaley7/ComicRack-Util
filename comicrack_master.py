#!/usr/bin/env python3
"""Shared scanning and persistence helpers for the ComicRack master UI."""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree


APP_CONFIG_FILENAME = "master_ui_settings.json"
STATE_FILENAME = ".comicrack_master_state.json"
SERIES_FILENAME = "series.xml"
SUPPORTED_SUFFIXES = {".cbz", ".zip"}
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
TRANSLATED_DIR_NAME = "Translated"
CG_GALLERY_CATEGORIES = {"artist cg", "game cg"}
TRANSLATED_CATEGORIES = {"western"}
TRANSLATED_ENG_SUFFIX = "translatedeng"


@dataclass
class AppSettings:
    comicrack_source: str = ""
    remote_sync_target: str = ""
    fansadox_source: str = ""
    column_widths: dict[str, int] = field(default_factory=dict)
    translate_cg_galleries: bool = False
    super_saver_mode: bool = False
    paddle_ocr_cuda_enabled: bool = False


@dataclass
class ArchiveRecord:
    relative_path: str
    filename: str
    selected: bool
    cbz: bool
    has_info: bool
    has_comicinfo: bool
    english: bool
    synced: bool
    size: int
    modified: float
    error: str = ""
    last_action: str = ""
    last_result: str = ""
    last_message: str = ""
    last_timestamp: str = ""
    history: list[dict[str, str]] = field(default_factory=list)


def repo_root() -> Path:
    return Path(__file__).resolve().parent


def app_config_path(base_dir: Path | None = None) -> Path:
    return (base_dir or repo_root()) / APP_CONFIG_FILENAME


def source_state_path(source_dir: Path) -> Path:
    return source_dir / STATE_FILENAME


def series_list_path(source_dir: Path) -> Path:
    return source_dir / SERIES_FILENAME


def load_app_settings(base_dir: Path | None = None) -> AppSettings:
    path = app_config_path(base_dir)
    if not path.exists():
        return AppSettings()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppSettings()

    raw_widths = data.get("column_widths", {})
    column_widths = {}
    if isinstance(raw_widths, dict):
        for key, value in raw_widths.items():
            try:
                width = int(value)
            except (TypeError, ValueError):
                continue
            if width > 0:
                column_widths[str(key)] = width

    return AppSettings(
        comicrack_source=str(data.get("comicrack_source", "")),
        remote_sync_target=str(data.get("remote_sync_target", "")),
        fansadox_source=str(data.get("fansadox_source", "")),
        column_widths=column_widths,
        translate_cg_galleries=bool(data.get("translate_cg_galleries", False)),
        super_saver_mode=bool(data.get("super_saver_mode", False)),
        paddle_ocr_cuda_enabled=bool(data.get("paddle_ocr_cuda_enabled", False)),
    )


def save_app_settings(settings: AppSettings, base_dir: Path | None = None) -> None:
    path = app_config_path(base_dir)
    payload = asdict(settings)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8", newline="\n")


def load_source_state(source_dir: Path) -> dict[str, Any]:
    path = source_state_path(source_dir)
    if not path.exists():
        return {"archives": {}}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"archives": {}}

    if not isinstance(data, dict):
        return {"archives": {}}
    if not isinstance(data.get("archives"), dict):
        data["archives"] = {}
    return data


def save_source_state(source_dir: Path, records: list[ArchiveRecord], settings: AppSettings | None = None) -> None:
    payload: dict[str, Any] = {
        "comicrack_source": str(source_dir),
        "archives": {record.relative_path: asdict(record) for record in records},
    }
    if settings is not None:
        payload["remote_sync_target"] = settings.remote_sync_target
        payload["fansadox_source"] = settings.fansadox_source

    source_state_path(source_dir).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
        newline="\n",
    )


def archive_comicinfo_writer(archive_path: Path) -> str:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for name in archive.namelist():
                if archive_basename(name) != "comicinfo.xml":
                    continue
                try:
                    root = ElementTree.fromstring(archive.read(name))
                except (KeyError, RuntimeError, ElementTree.ParseError, zipfile.BadZipFile):
                    return ""
                writer = root.findtext("Writer") or ""
                return writer.strip()
    except (OSError, zipfile.BadZipFile):
        return ""

    return ""


def series_duplicate_key(name: str) -> str:
    normalized = normalized_archive_name(name)
    archive_path = Path(normalized)
    stem = archive_path.stem
    suffix_marker = f"-{TRANSLATED_ENG_SUFFIX}"
    if stem.casefold().endswith(suffix_marker):
        stem = stem[: -len(suffix_marker)]
    return (archive_path.parent / stem).as_posix().casefold()


def series_export_records(records: list[ArchiveRecord]) -> list[ArchiveRecord]:
    by_key: dict[str, ArchiveRecord] = {}

    def priority(record: ArchiveRecord) -> tuple[int, int, int, str]:
        return (
            int(is_translated_archive_name(record.filename)),
            int(record.english),
            int(record.cbz),
            record.relative_path.casefold(),
        )

    for record in records:
        key = series_duplicate_key(record.relative_path)
        previous = by_key.get(key)
        if previous is None or priority(record) > priority(previous):
            by_key[key] = record

    return [record for record in records if by_key[series_duplicate_key(record.relative_path)] is record]


def sync_series_list(source_dir: Path, records: list[ArchiveRecord]) -> Path:
    path = series_list_path(source_dir)
    export_records = series_export_records(records)
    current_comics = {record.relative_path for record in export_records}
    current_keys = {series_duplicate_key(record.relative_path) for record in export_records}
    assignments: dict[str, tuple[str, str, str]] = {}
    assignment_keys: dict[str, tuple[str, str, str]] = {}
    series_order: list[str] = []

    if path.exists():
        try:
            root = ElementTree.parse(path).getroot()
        except (OSError, ElementTree.ParseError):
            root = None

        if root is not None and root.tag == "comics":
            for series in root.findall("series"):
                series_name = series.get("name") or "unsorted"
                if series_name not in series_order:
                    series_order.append(series_name)
                for comic in series.findall("comic"):
                    comic_name = (comic.text or "").strip()
                    if not comic_name:
                        continue
                    assignment = (series_name, comic.get("number") or "0", comic.get("writer") or "")
                    if comic_name in current_comics and comic_name not in assignments:
                        assignments[comic_name] = assignment
                    duplicate_key = series_duplicate_key(comic_name)
                    if duplicate_key in current_keys and duplicate_key not in assignment_keys:
                        assignment_keys[duplicate_key] = assignment

    if "unsorted" not in series_order:
        series_order.insert(0, "unsorted")

    grouped: dict[str, list[tuple[str, str, str]]] = {series_name: [] for series_name in series_order}
    for record in export_records:
        series_name, number, existing_writer = assignments.get(
            record.relative_path,
            assignment_keys.get(series_duplicate_key(record.relative_path), ("unsorted", "0", "")),
        )
        writer = archive_comicinfo_writer(source_dir / record.relative_path) or existing_writer
        if series_name not in grouped:
            grouped[series_name] = []
            series_order.append(series_name)
        grouped[series_name].append((number, writer, record.relative_path))

    root = ElementTree.Element("comics")
    for series_name in series_order:
        comics = grouped.get(series_name, [])
        if not comics and series_name != "unsorted":
            continue
        series = ElementTree.SubElement(root, "series", {"name": series_name})
        for number, writer, comic_name in comics:
            comic = ElementTree.SubElement(series, "comic", {"number": number, "writer": writer})
            comic.text = comic_name

    ElementTree.indent(root, space="  ")
    xml_body = ElementTree.tostring(root, encoding="unicode")
    path.write_text(
        f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}\n',
        encoding="utf-8",
        newline="\n",
    )
    return path


def workflow_timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def record_workflow_event(record: ArchiveRecord, action: str, result: str, message: str = "") -> None:
    timestamp = workflow_timestamp()
    event = {
        "timestamp": timestamp,
        "action": action,
        "result": result,
        "message": message,
    }
    record.last_action = action
    record.last_result = result
    record.last_message = message
    record.last_timestamp = timestamp
    record.history = [*record.history[-19:], event]


def iter_candidate_archives(source_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in source_dir.glob("*")
            if path.is_file()
            and path.suffix.lower() in SUPPORTED_SUFFIXES
            and STATE_FILENAME.lower() not in {part.lower() for part in path.parts}
        ),
        key=lambda path: (0 if path.suffix.lower() == ".zip" else 1, path.name.lower(), str(path).lower()),
    )


def normalized_archive_name(name: str) -> str:
    return name.replace("\\", "/").lstrip("/")


def archive_basename(name: str) -> str:
    return Path(normalized_archive_name(name)).name.lower()


def is_root_archive_file(name: str, expected_name: str) -> bool:
    normalized = normalized_archive_name(name)
    return "/" not in normalized and normalized.lower() == expected_name.lower()


def archive_has_root_comicinfo(archive_path: Path) -> tuple[bool, str]:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            return any(is_root_archive_file(name, "ComicInfo.xml") for name in archive.namelist()), ""
    except zipfile.BadZipFile:
        return False, "Invalid ZIP/CBZ archive."
    except OSError as exc:
        return False, str(exc)


def is_translated_archive_name(name: str) -> bool:
    return Path(name).stem.casefold().endswith(TRANSLATED_ENG_SUFFIX)


def unique_destination_path(destination: Path) -> Path:
    if not destination.exists():
        return destination

    for index in range(1, 10000):
        candidate = destination.with_name(f"{destination.stem} ({index}){destination.suffix}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Could not find an available destination for: {destination}")


def move_source_archive_to_translated_folder(archive_path: Path) -> Path:
    translated_dir = archive_path.parent / TRANSLATED_DIR_NAME
    translated_dir.mkdir(parents=True, exist_ok=True)
    destination = unique_destination_path(translated_dir / archive_path.name)
    return Path(shutil.move(str(archive_path), str(destination)))


def archive_info_text(archive_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for name in archive.namelist():
                if archive_basename(name) == "info.txt":
                    try:
                        return archive.read(name).decode("utf-8-sig", errors="replace")
                    except (KeyError, RuntimeError, zipfile.BadZipFile):
                        return ""
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def gallery_category_from_info_text(content: str) -> str | None:
    for line in content.splitlines():
        match = re.match(r"\s*Category\s*[:=]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def is_artist_or_game_cg_archive(archive_path: Path) -> bool:
    content = archive_info_text(archive_path)
    if content is None:
        return False
    category = gallery_category_from_info_text(content)
    return category is not None and category.strip().casefold() in CG_GALLERY_CATEGORIES


def info_text_indicates_english(content: str) -> bool:
    category = gallery_category_from_info_text(content)
    if category is not None and category.strip().casefold() in TRANSLATED_CATEGORIES:
        return True

    for line in content.splitlines():
        match = re.match(r"\s*Language\s*[:=]\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            return "english" in match.group(1).casefold()

    return False


def read_archive_flags(archive_path: Path) -> tuple[bool, bool, bool, str]:
    has_info = False
    has_comicinfo = False
    info_says_english = False

    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            for name in archive.namelist():
                basename = archive_basename(name)
                if basename == "comicinfo.xml":
                    has_comicinfo = True
                if basename == "info.txt":
                    has_info = True
                    try:
                        content = archive.read(name).decode("utf-8-sig", errors="replace")
                    except (KeyError, RuntimeError, zipfile.BadZipFile):
                        content = ""
                    if info_text_indicates_english(content):
                        info_says_english = True
    except zipfile.BadZipFile:
        return False, False, False, "Invalid ZIP/CBZ archive."
    except OSError as exc:
        return False, False, False, str(exc)

    return has_info, has_comicinfo, info_says_english, ""


def is_synced(source_file: Path, source_dir: Path, remote_sync_target: str) -> bool:
    if not remote_sync_target:
        return False

    remote_dir = Path(remote_sync_target).expanduser()
    if not remote_dir.exists():
        return False

    try:
        relative_path = source_file.relative_to(source_dir)
    except ValueError:
        relative_path = Path(source_file.name)

    remote_file = remote_dir / relative_path
    if not remote_file.is_file():
        return False

    try:
        return remote_file.stat().st_size == source_file.stat().st_size
    except OSError:
        return False


def scan_source_directory(
    source_dir: Path,
    remote_sync_target: str = "",
    previous_state: dict[str, Any] | None = None,
) -> list[ArchiveRecord]:
    if not source_dir.exists():
        raise FileNotFoundError(f"ComicRack Source does not exist: {source_dir}")
    if not source_dir.is_dir():
        raise NotADirectoryError(f"ComicRack Source is not a directory: {source_dir}")

    previous_archives = (previous_state or {}).get("archives", {})
    if not isinstance(previous_archives, dict):
        previous_archives = {}

    records: list[ArchiveRecord] = []
    for archive_path in iter_candidate_archives(source_dir):
        relative_path = archive_path.relative_to(source_dir).as_posix()
        previous = previous_archives.get(relative_path, {})
        has_info, has_comicinfo, info_says_english, error = read_archive_flags(archive_path)
        suffix = archive_path.suffix.lower()
        default_selected = suffix == ".cbz"
        selected = bool(previous.get("selected", default_selected)) if isinstance(previous, dict) else default_selected
        history = previous.get("history", []) if isinstance(previous, dict) else []
        if not isinstance(history, list):
            history = []
        filename_says_english = "english" in archive_path.name.lower()
        filename_says_translated = is_translated_archive_name(archive_path.name)

        stat = archive_path.stat()
        records.append(
            ArchiveRecord(
                relative_path=relative_path,
                filename=archive_path.name,
                selected=selected,
                cbz=suffix == ".cbz",
                has_info=has_info,
                has_comicinfo=has_comicinfo,
                english=filename_says_english or filename_says_translated or info_says_english,
                synced=is_synced(archive_path, source_dir, remote_sync_target),
                size=stat.st_size,
                modified=stat.st_mtime,
                error=error,
                last_action=str(previous.get("last_action", "")) if isinstance(previous, dict) else "",
                last_result=str(previous.get("last_result", "")) if isinstance(previous, dict) else "",
                last_message=str(previous.get("last_message", "")) if isinstance(previous, dict) else "",
                last_timestamp=str(previous.get("last_timestamp", "")) if isinstance(previous, dict) else "",
                history=[event for event in history if isinstance(event, dict)][-20:],
            )
        )

    return records


def update_record_selection(records: list[ArchiveRecord], relative_path: str, selected: bool) -> None:
    for record in records:
        if record.relative_path == relative_path:
            record.selected = selected
            return


def selected_paths(records: list[ArchiveRecord], source_dir: Path) -> list[Path]:
    return [source_dir / record.relative_path for record in records if record.selected]


def records_as_copy_list(records: list[ArchiveRecord]) -> str:
    return "\n".join(record.relative_path for record in records)


def archive_next_step(record: ArchiveRecord) -> str:
    if record.error:
        return "Problem"
    if record.synced:
        return "Done"
    if not record.cbz:
        return "Convert to CBZ"
    if not record.has_info:
        return "Needs info.txt"
    if not record.english:
        return "Needs translation"
    if not record.has_comicinfo:
        return "Needs ComicInfo.xml"
    return "Ready to sync"


def archive_matches_filter(record: ArchiveRecord, filter_name: str) -> bool:
    if filter_name == "Needs Work":
        return archive_next_step(record) not in {"Done", "Ready to sync"}
    if filter_name == "Ready to Sync":
        return archive_next_step(record) == "Ready to sync"
    if filter_name == "Problems":
        return bool(record.error)
    if filter_name == "Already Synced":
        return record.synced
    if filter_name == "Non-English":
        return record.has_info and not record.english
    if filter_name == "Missing Info":
        return not record.has_info
    return True


def archive_image_count(archive_path: Path) -> tuple[int, str]:
    try:
        with zipfile.ZipFile(archive_path, "r") as archive:
            count = sum(
                1
                for name in archive.namelist()
                if Path(archive_basename(name)).suffix.lower() in SUPPORTED_IMAGE_SUFFIXES
            )
            return count, ""
    except zipfile.BadZipFile:
        return 0, "Invalid ZIP/CBZ archive."
    except OSError as exc:
        return 0, str(exc)


def sorted_archive_records(records: list[ArchiveRecord], column: str, reverse: bool = False) -> list[ArchiveRecord]:
    def sort_key(record: ArchiveRecord) -> tuple[Any, str]:
        if column == "selected":
            value: Any = int(record.selected)
        elif column == "file":
            value = record.relative_path.lower()
        elif column == "cbz":
            value = int(record.cbz)
        elif column == "info":
            value = int(record.has_info)
        elif column == "comicinfo":
            value = int(record.has_comicinfo)
        elif column == "english":
            value = int(record.english)
        elif column == "synced":
            value = int(record.synced)
        elif column == "next":
            value = archive_next_step(record).lower()
        elif column == "last":
            value = record.last_timestamp.lower()
        elif column == "error":
            value = record.error.lower()
        else:
            value = record.relative_path.lower()
        return value, record.relative_path.lower()

    return sorted(records, key=sort_key, reverse=reverse)


def sync_selected_archives(records: list[ArchiveRecord], source_dir: Path, remote_sync_target: str) -> list[str]:
    if not remote_sync_target:
        raise ValueError("Final Library Destination is not set.")

    remote_dir = Path(remote_sync_target).expanduser()
    remote_dir.mkdir(parents=True, exist_ok=True)
    messages: list[str] = []

    for record in records:
        if not record.selected:
            continue
        source_file = source_dir / record.relative_path
        has_root_comicinfo, error = archive_has_root_comicinfo(source_file)
        if error:
            messages.append(f"Skipped {record.relative_path}: could not check root ComicInfo.xml ({error})")
            continue
        if not has_root_comicinfo:
            messages.append(f"Skipped {record.relative_path}: root ComicInfo.xml not found")
            continue

        destination = remote_dir / record.relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, destination)
        record.synced = is_synced(source_file, source_dir, str(remote_dir))
        messages.append(f"Copied {record.relative_path}")

    return messages


def sync_archive_path(archive_path: Path, source_dir: Path, remote_sync_target: str) -> str:
    if not remote_sync_target:
        raise ValueError("Final Library Destination is not set.")

    has_root_comicinfo, error = archive_has_root_comicinfo(archive_path)
    display = archive_path.relative_to(source_dir).as_posix() if archive_path.is_relative_to(source_dir) else archive_path.name
    if error:
        raise RuntimeError(f"Skipped {display}: could not check root ComicInfo.xml ({error})")
    if not has_root_comicinfo:
        raise RuntimeError(f"Skipped {display}: root ComicInfo.xml not found")

    remote_dir = Path(remote_sync_target).expanduser()
    remote_dir.mkdir(parents=True, exist_ok=True)
    try:
        relative_path = archive_path.relative_to(source_dir)
    except ValueError:
        relative_path = Path(archive_path.name)

    destination = remote_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(archive_path, destination)
    return f"Copied {relative_path.as_posix()}"
