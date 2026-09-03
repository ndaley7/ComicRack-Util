#!/usr/bin/env python3
"""Tkinter master UI for ComicRack library processing utilities."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable

from comicrack_master import (
    AppSettings,
    ArchiveRecord,
    is_artist_or_game_cg_archive,
    is_translated_archive_name,
    load_app_settings,
    load_source_state,
    move_source_archive_to_translated_folder,
    repo_root,
    records_as_copy_list,
    read_archive_flags,
    save_app_settings,
    save_source_state,
    scan_source_directory,
    sorted_archive_records,
    sync_selected_archives,
    update_record_selection,
)


YES = "Yes"
NO = "No"
PADDLE_OCR_CUDA_FLAG = "--paddle-ocr-cuda"
TREE_HEADINGS = {
    "selected": "Use",
    "file": "File",
    "cbz": "CBZ",
    "info": "Info",
    "english": "ENGLISH",
    "comicinfo": "ComicInfo",
    "synced": "Synced",
    "error": "Status",
}
TREE_COLUMNS = tuple(TREE_HEADINGS.keys())
DEFAULT_COLUMN_WIDTHS = {
    "selected": 54,
    "file": 430,
    "cbz": 92,
    "info": 92,
    "english": 92,
    "comicinfo": 92,
    "synced": 92,
    "error": 150,
}
COLUMN_MIN_WIDTHS = {
    "selected": 54,
    "file": 240,
    "cbz": 82,
    "info": 82,
    "english": 82,
    "comicinfo": 82,
    "synced": 82,
    "error": 100,
}


def subprocess_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    env.setdefault("PYTHON", sys.executable)
    return env


def resolve_command_executable(executable: str) -> str:
    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError(f"Required command not found on PATH: {executable}")
    return resolved


def run_captured_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    if not command:
        raise ValueError("Command cannot be empty.")

    resolved_command = [resolve_command_executable(command[0]), *command[1:]]
    return subprocess.run(
        resolved_command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=subprocess_environment(),
        check=False,
    )


def run_streaming_command(
    command: list[str],
    cwd: Path | None = None,
    on_line: Callable[[str], None] | None = None,
) -> subprocess.CompletedProcess[str]:
    if not command:
        raise ValueError("Command cannot be empty.")

    resolved_command = [resolve_command_executable(command[0]), *command[1:]]
    process = subprocess.Popen(
        resolved_command,
        cwd=str(cwd) if cwd is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=subprocess_environment(),
    )
    output_lines: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip("\r\n")
        output_lines.append(text)
        if on_line is not None:
            on_line(text)
    returncode = process.wait()
    stdout = "\n".join(output_lines)
    if stdout:
        stdout += "\n"
    return subprocess.CompletedProcess(resolved_command, returncode, stdout=stdout, stderr="")


def file_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def archive_english_status(archive_path: Path, info_says_english: bool) -> bool:
    return (
        "english" in archive_path.name.lower()
        or is_translated_archive_name(archive_path.name)
        or info_says_english
    )


def archive_record_from_path(source_dir: Path, archive_path: Path, selected: bool = True) -> ArchiveRecord:
    has_info, has_comicinfo, info_says_english, error = read_archive_flags(archive_path)
    stat = archive_path.stat()
    return ArchiveRecord(
        relative_path=archive_path.relative_to(source_dir).as_posix(),
        filename=archive_path.name,
        selected=selected,
        cbz=archive_path.suffix.lower() == ".cbz",
        has_info=has_info,
        has_comicinfo=has_comicinfo,
        english=archive_english_status(archive_path, info_says_english),
        synced=False,
        size=stat.st_size,
        modified=stat.st_mtime,
        error=error,
    )


def open_archive_with_default_app(path: Path | str) -> None:
    startfile = getattr(os, "startfile", None)
    if not callable(startfile):
        raise RuntimeError("Opening comics from the UI is only supported on Windows.")
    startfile(str(path))


TRANSLATE_IMAGE_PROGRESS_RE = re.compile(
    r"^\[(?P<index>\d+)/(?P<total>\d+)\]\s+(?P<action>Checking text|Text check failed|No text found|Text detected|Translating|Done|Reusing cached translation|Keeping original)\b"
)


def translate_image_progress_from_line(line: str) -> tuple[int, int, bool] | None:
    match = TRANSLATE_IMAGE_PROGRESS_RE.match(line)
    if not match:
        return None

    index = int(match.group("index"))
    total = int(match.group("total"))
    completed = match.group("action") in {"Done", "Reusing cached translation", "No text found", "Keeping original"}
    return index, total, completed


def translate_command(
    archive_path: Path,
    output_path: Path,
    super_saver_mode: bool,
    paddle_ocr_cuda_enabled: bool,
) -> list[str]:
    command = ["npm", "start", "--", "--zip", str(archive_path), "--out", str(output_path)]
    if super_saver_mode:
        command.append("--super-saver")
        if paddle_ocr_cuda_enabled:
            command.append(PADDLE_OCR_CUDA_FLAG)
    return command


def selected_records_for_run(records: list[ArchiveRecord]) -> list[ArchiveRecord]:
    return sorted(
        (record for record in records if record.selected),
        key=lambda record: (record.size, record.relative_path.lower()),
    )


class Tooltip:
    def __init__(self, widget: tk.Widget, text: str) -> None:
        self.widget = widget
        self.text = text
        self.window: tk.Toplevel | None = None
        widget.bind("<Enter>", self.show)
        widget.bind("<Leave>", self.hide)

    def show(self, _event: tk.Event | None = None) -> None:
        if self.window is not None or not self.text:
            return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x}+{y}")
        label = ttk.Label(
            self.window,
            text=self.text,
            padding=(8, 4),
            relief="solid",
            borderwidth=1,
            background="#ffffe0",
        )
        label.pack()

    def hide(self, _event: tk.Event | None = None) -> None:
        if self.window is not None:
            self.window.destroy()
            self.window = None


class SkipArchive(RuntimeError):
    """Raised when one archive should be skipped without failing the full batch."""


class ComicRackMasterUI(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("ComicRack Library Master")
        self.geometry("980x680")
        self.minsize(860, 560)

        self.records: list[ArchiveRecord] = []
        self.settings = load_app_settings()
        self.source_var = tk.StringVar(value=self.settings.comicrack_source)
        self.remote_var = tk.StringVar(value=self.settings.remote_sync_target)
        self.fansadox_var = tk.StringVar(value=self.settings.fansadox_source)
        self.translate_cg_var = tk.BooleanVar(value=self.settings.translate_cg_galleries)
        self.super_saver_var = tk.BooleanVar(value=self.settings.super_saver_mode)
        self.paddle_ocr_cuda_var = tk.BooleanVar(value=self.settings.paddle_ocr_cuda_enabled)
        self.status_var = tk.StringVar(value="Ready")
        self.selected_count_var = tk.StringVar(value="No archives selected")
        self.progress_text_var = tk.StringVar(value="")
        self.busy = False
        self.action_buttons: list[ttk.Button] = []
        self.sort_column: str | None = None
        self.sort_reverse = False

        self._build_ui()
        if self.source_var.get():
            self.after(250, self.rescan)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        path_frame = ttk.LabelFrame(self, text="Library Paths", padding=10)
        path_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        path_frame.columnconfigure(1, weight=1)

        self._add_path_row(
            path_frame,
            0,
            "ComicRack Source",
            self.source_var,
            "Folder scanned for .zip and .cbz archives. Status is stored inside this folder.",
        )
        self._add_path_row(
            path_frame,
            1,
            "Remote Sync Target",
            self.remote_var,
            "Folder used to check and copy selected archives during sync.",
        )
        self._add_path_row(
            path_frame,
            2,
            "Fansadox Source",
            self.fansadox_var,
            "Reference source path reserved for Fansadox-related utilities.",
        )

        toolbar = ttk.Frame(self, padding=(10, 0, 10, 6))
        toolbar.grid(row=1, column=0, sticky="ew")
        toolbar.columnconfigure(12, weight=1)

        self._add_button(toolbar, "Rescan", self.rescan, 0, "Force-refresh archive status from the ComicRack Source folder.")
        self._add_button(toolbar, "Select All", self.select_all, 1, "Select every listed archive.")
        self._add_button(toolbar, "Select None", self.select_none, 2, "Clear all archive selections.")
        self._add_button(toolbar, "Zip to CBZ", self.convert_zip_to_cbz, 3, "Rename selected ZIP archives to CBZ and flatten a redundant same-named top-level folder when present.")
        self._add_button(toolbar, "Translate", self.translate_selected, 4, "Confirm CBZ and info.txt first, then run TranslateEXGallery for selected non-English archives.")
        translate_cg_check = ttk.Checkbutton(
            toolbar,
            text="Artist/Game CG",
            variable=self.translate_cg_var,
            command=lambda: self.save_current_settings(save_archive_state=False),
        )
        translate_cg_check.grid(row=0, column=5, padx=(0, 6), pady=2)
        Tooltip(translate_cg_check, "Allow Translate to process archives whose info.txt category is Artist CG or Game CG.")
        self.action_buttons.append(translate_cg_check)
        super_saver_check = ttk.Checkbutton(
            toolbar,
            text="Super-Saver mode",
            variable=self.super_saver_var,
            command=lambda: self.save_current_settings(save_archive_state=False),
        )
        super_saver_check.grid(row=0, column=6, padx=(0, 6), pady=2)
        Tooltip(super_saver_check, "Use PaddleOCR to skip translating pages where no text boxes are detected.")
        self.action_buttons.append(super_saver_check)
        paddle_ocr_cuda_check = ttk.Checkbutton(
            toolbar,
            text="CUDA OCR",
            variable=self.paddle_ocr_cuda_var,
            command=lambda: self.save_current_settings(save_archive_state=False),
        )
        paddle_ocr_cuda_check.grid(row=0, column=7, padx=(0, 6), pady=2)
        Tooltip(
            paddle_ocr_cuda_check,
            "Run Super-Saver PaddleOCR text detection on CUDA GPU 0. Requires a GPU-enabled PaddlePaddle install.",
        )
        self.action_buttons.append(paddle_ocr_cuda_check)
        self._add_button(toolbar, "Info -> ComicInfo.xml", self.create_comicinfo, 8, "Confirm CBZ, info.txt, and English first, then add ComicInfo.xml.")
        self._add_button(toolbar, "Sync Selected", self.sync_selected, 9, "Copy selected archives to the Remote Sync Target folder.")
        self._add_button(toolbar, "Remove Dups", self.remove_duplicates, 10, "Hash-check direct-source archives and move duplicate matches into _DUPLICATES.")
        self._add_button(toolbar, "Help", self.show_help, 11, "Show a quick guide for this master UI.")

        self.selected_label = ttk.Label(toolbar, textvariable=self.selected_count_var, anchor="e")
        self.selected_label.grid(row=0, column=12, sticky="e", padx=(8, 0))

        list_frame = ttk.Frame(self, padding=(10, 0, 10, 4))
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        self.tree = ttk.Treeview(list_frame, columns=TREE_COLUMNS, show="headings", selectmode="browse")
        self.configure_tree_headings()
        self.configure_tree_columns()
        self.tree.bind("<ButtonRelease-1>", self.on_tree_button_release)
        self.tree.bind("<Double-1>", self.open_tree_comic)
        self.tree.bind("<space>", self.toggle_current_selection)

        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        x_scroll = ttk.Scrollbar(list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll.grid(row=1, column=0, sticky="ew")
        Tooltip(
            self.tree,
            "Double-click a comic to open it. Click a column heading to sort. Drag heading borders to resize columns; widths are saved. Click the Use column or press Space to toggle processing.",
        )

        log_frame = ttk.LabelFrame(self, text="Run Log", padding=6)
        log_frame.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)
        self.log_text = tk.Text(log_frame, height=7, wrap="word")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scroll.set)
        log_scroll.grid(row=0, column=1, sticky="ns")

        status_frame = ttk.Frame(self, padding=(10, 0, 10, 8))
        status_frame.grid(row=4, column=0, sticky="ew")
        status_frame.columnconfigure(0, weight=1)
        status = ttk.Label(status_frame, textvariable=self.status_var, anchor="w")
        status.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        list_button = ttk.Button(status_frame, text="Comic List", command=self.show_logged_comics)
        list_button.grid(row=0, column=1, sticky="e", padx=(0, 8))
        Tooltip(list_button, "Open a copyable list of every comic currently loaded in the table.")
        progress_frame = ttk.Frame(status_frame, width=220, height=22)
        progress_frame.grid(row=0, column=2, sticky="e")
        progress_frame.grid_propagate(False)
        self.progress = ttk.Progressbar(progress_frame, mode="indeterminate", length=220)
        self.progress.place(relx=0, rely=0, relwidth=1, relheight=1)
        progress_label = ttk.Label(progress_frame, textvariable=self.progress_text_var, anchor="center")
        progress_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        Tooltip(progress_frame, "Shows that a scan, conversion, translation, or sync operation is running.")

    def _add_path_row(self, parent: ttk.Frame, row: int, label_text: str, variable: tk.StringVar, tooltip: str) -> None:
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky="w", padx=(0, 8), pady=3)
        entry = ttk.Entry(parent, textvariable=variable)
        entry.grid(row=row, column=1, sticky="ew", pady=3)
        button = ttk.Button(parent, text="Browse...", command=lambda: self.choose_directory(variable))
        button.grid(row=row, column=2, sticky="e", padx=(8, 0), pady=3)
        Tooltip(label, tooltip)
        Tooltip(entry, tooltip)
        Tooltip(button, f"Choose the {label_text} folder.")

    def _add_button(self, parent: ttk.Frame, text: str, command, column: int, tooltip: str) -> None:
        button = ttk.Button(parent, text=text, command=command)
        button.grid(row=0, column=column, padx=(0, 6), pady=2)
        Tooltip(button, tooltip)
        self.action_buttons.append(button)

    def configure_tree_headings(self) -> None:
        for column, label in TREE_HEADINGS.items():
            marker = ""
            if column == self.sort_column:
                marker = " v" if self.sort_reverse else " ^"
            self.tree.heading(column, text=f"{label}{marker}", command=lambda sort_column=column: self.sort_by_column(sort_column))

    def configure_tree_columns(self) -> None:
        saved_widths = self.settings.column_widths
        for column in TREE_COLUMNS:
            width = saved_widths.get(column, DEFAULT_COLUMN_WIDTHS[column])
            minwidth = COLUMN_MIN_WIDTHS[column]
            anchor = "w" if column in {"file", "error"} else "center"
            self.tree.column(column, width=max(width, minwidth), minwidth=minwidth, stretch=False, anchor=anchor)

    def current_column_widths(self) -> dict[str, int]:
        if not hasattr(self, "tree"):
            return dict(self.settings.column_widths)
        return {column: int(self.tree.column(column, "width")) for column in TREE_COLUMNS}

    def save_current_column_widths(self) -> None:
        self.settings.column_widths = self.current_column_widths()
        save_app_settings(self.current_settings())

    def sort_by_column(self, column: str) -> None:
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        self.records = sorted_archive_records(self.records, column, self.sort_reverse)
        self.configure_tree_headings()
        self.populate_tree()

    def choose_directory(self, variable: tk.StringVar) -> None:
        initial_dir = variable.get() or str(Path.home())
        chosen = filedialog.askdirectory(initialdir=initial_dir)
        if chosen:
            variable.set(chosen)
            self.save_current_settings()

    def current_settings(self) -> AppSettings:
        return AppSettings(
            comicrack_source=self.source_var.get().strip(),
            remote_sync_target=self.remote_var.get().strip(),
            fansadox_source=self.fansadox_var.get().strip(),
            column_widths=self.current_column_widths(),
            translate_cg_galleries=self.translate_cg_var.get(),
            super_saver_mode=self.super_saver_var.get(),
            paddle_ocr_cuda_enabled=self.paddle_ocr_cuda_var.get(),
        )

    def save_current_settings(self, save_archive_state: bool = True) -> None:
        self.settings = self.current_settings()
        save_app_settings(self.settings)
        source = self.source_dir_or_none()
        if save_archive_state and source and source.exists():
            save_source_state(source, self.records, self.settings)

    def source_dir_or_none(self) -> Path | None:
        raw = self.source_var.get().strip()
        if not raw:
            return None
        return Path(raw).expanduser()

    def append_log(self, message: str) -> None:
        self.log_text.insert("end", message.rstrip() + "\n")
        self.log_text.see("end")
        self.status_var.set(message.splitlines()[-1] if message else "Ready")

    def append_log_from_worker(self, message: str) -> None:
        self.after(0, lambda text=message: self.append_log(text))

    def set_progress(self, value: int, maximum: int, text: str) -> None:
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=max(maximum, 1), value=max(value, 0))
        self.progress_text_var.set(text)

    def set_progress_from_worker(self, value: int, maximum: int, text: str) -> None:
        self.after(0, lambda: self.set_progress(value, maximum, text))

    def begin_busy(self, message: str) -> bool:
        if self.busy:
            messagebox.showinfo("ComicRack Library Master", "An operation is already running.")
            return False

        self.busy = True
        self.status_var.set(message)
        self.progress_text_var.set("")
        self.progress.configure(mode="indeterminate", value=0)
        self.progress.start(12)
        for button in self.action_buttons:
            button.state(["disabled"])
        return True

    def end_busy(self) -> None:
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="indeterminate", value=0)
        self.progress_text_var.set("")
        for button in self.action_buttons:
            button.state(["!disabled"])

    def run_in_worker(
        self,
        busy_message: str,
        action: Callable[[], Any],
        on_success: Callable[[Any], None] | None = None,
        done_message: str = "Done",
        rescan_after: bool = False,
    ) -> None:
        if not self.begin_busy(busy_message):
            return

        def worker() -> None:
            try:
                result = action()
            except Exception as exc:
                error = str(exc)
                self.after(0, lambda: self.finish_worker_error(error))
                return

            def finish() -> None:
                if on_success is not None:
                    on_success(result)
                elif isinstance(result, list):
                    for message in result:
                        self.append_log(str(message))
                elif result:
                    self.append_log(str(result))
                if done_message:
                    self.append_log(done_message)
                self.end_busy()
                if rescan_after:
                    self.after(50, self.rescan)

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def finish_worker_error(self, error: str) -> None:
        self.end_busy()
        messagebox.showerror("ComicRack Library Master", error)
        self.append_log(f"Error: {error}")

    def rescan(self) -> None:
        self.save_current_settings(save_archive_state=False)
        source = self.source_dir_or_none()
        if source is None:
            messagebox.showinfo("ComicRack Library Master", "Set ComicRack Source before scanning.")
            return

        settings = self.current_settings()

        def action() -> list[ArchiveRecord]:
            state = load_source_state(source)
            records = scan_source_directory(source, settings.remote_sync_target, state)
            save_source_state(source, records, settings)
            return records

        def on_success(records: list[ArchiveRecord]) -> None:
            if self.sort_column:
                self.records = sorted_archive_records(records, self.sort_column, self.sort_reverse)
            else:
                self.records = records
            self.populate_tree()
            self.append_log(f"Scanned {len(self.records)} archive(s) from {source}")

        self.run_in_worker("Scanning archive status...", action, on_success, done_message="")

    def populate_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for record in self.records:
            self.tree.insert(
                "",
                "end",
                iid=record.relative_path,
                values=(
                    "[x]" if record.selected else "[ ]",
                    record.relative_path,
                    YES if record.cbz else NO,
                    YES if record.has_info else NO,
                    YES if record.english else NO,
                    YES if record.has_comicinfo else NO,
                    YES if record.synced else NO,
                    record.error,
                ),
            )
        self.update_selected_count()

    def update_selected_count(self) -> None:
        count = sum(1 for record in self.records if record.selected)
        noun = "archive" if count == 1 else "archives"
        self.selected_count_var.set(f"{count} {noun} selected")

    def on_tree_button_release(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if region == "cell" and column == "#1" and row_id:
            self.toggle_record(row_id)
        self.after(50, self.save_current_column_widths)

    def toggle_current_selection(self, _event: tk.Event | None = None) -> str:
        selected = self.tree.selection()
        if selected:
            self.toggle_record(selected[0])
        return "break"

    def toggle_record(self, relative_path: str) -> None:
        record = next((item for item in self.records if item.relative_path == relative_path), None)
        if record is None:
            return
        record.selected = not record.selected
        update_record_selection(self.records, relative_path, record.selected)
        self.populate_tree()
        self.tree.selection_set(relative_path)
        self.save_current_settings()

    def select_all(self) -> None:
        for record in self.records:
            record.selected = True
        self.populate_tree()
        self.save_current_settings()

    def select_none(self) -> None:
        for record in self.records:
            record.selected = False
        self.populate_tree()
        self.save_current_settings()

    def selected_records(self) -> list[ArchiveRecord]:
        return selected_records_for_run(self.records)

    def open_tree_comic(self, event: tk.Event) -> str:
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.open_comic(row_id)
        return "break"

    def open_comic(self, relative_path: str) -> None:
        source = self.require_source()
        if source is None:
            return

        record = next((item for item in self.records if item.relative_path == relative_path), None)
        if record is None:
            return

        archive_path = source / record.relative_path
        if not archive_path.is_file():
            messagebox.showerror("ComicRack Library Master", f"Comic archive does not exist:\n{archive_path}")
            return

        try:
            open_archive_with_default_app(archive_path)
        except OSError as exc:
            messagebox.showerror("ComicRack Library Master", f"Could not open comic archive:\n{exc}")
            return
        except RuntimeError as exc:
            messagebox.showerror("ComicRack Library Master", str(exc))
            return

        self.status_var.set(f"Opened {record.relative_path}")

    def archive_display_path(self, source: Path, archive_path: Path) -> str:
        try:
            return archive_path.relative_to(source).as_posix()
        except ValueError:
            return str(archive_path)

    def selected_archive_path(self, source: Path, record: ArchiveRecord) -> Path:
        archive_path = source / record.relative_path
        if archive_path.is_file():
            return archive_path
        if archive_path.suffix.lower() == ".zip":
            cbz_path = archive_path.with_suffix(".cbz")
            if cbz_path.is_file():
                return cbz_path
        return archive_path

    def require_existing_archive(self, source: Path, archive_path: Path) -> None:
        if not archive_path.is_file():
            display = self.archive_display_path(source, archive_path)
            raise RuntimeError(f"Comic archive does not exist: {display}")

    def confirmed_flags(self, source: Path, archive_path: Path) -> tuple[bool, bool, bool]:
        self.require_existing_archive(source, archive_path)
        has_info, has_comicinfo, info_says_english, error = read_archive_flags(archive_path)
        if error:
            display = self.archive_display_path(source, archive_path)
            raise RuntimeError(f"Could not confirm archive status for {display}: {error}")
        return has_info, has_comicinfo, archive_english_status(archive_path, info_says_english)

    def ensure_cbz_archive(self, source: Path, archive_path: Path) -> Path:
        self.require_existing_archive(source, archive_path)
        if archive_path.suffix.lower() == ".cbz":
            self.append_log_from_worker(f"Confirmed CBZ: {self.archive_display_path(source, archive_path)}")
            return archive_path
        if archive_path.suffix.lower() != ".zip":
            display = self.archive_display_path(source, archive_path)
            raise RuntimeError(f"Archive is not a ZIP or CBZ file: {display}")

        script = repo_root() / "ZiptoCBZ" / "zip_to_cbz.py"
        display = self.archive_display_path(source, archive_path)
        self.append_log_from_worker(f"Prerequisite Zip to CBZ: {display}")
        result = run_captured_command([sys.executable, str(script), str(archive_path)])
        output = (result.stdout + result.stderr).strip()
        self.append_log_from_worker(output or f"Processed {display}")
        if result.returncode != 0:
            raise RuntimeError(f"ZiptoCBZ failed for {display}:\n{output}")

        cbz_path = archive_path.with_suffix(".cbz")
        if cbz_path.is_file():
            self.append_log_from_worker(f"Confirmed CBZ: {self.archive_display_path(source, cbz_path)}")
            return cbz_path
        raise RuntimeError(f"Zip to CBZ finished, but no CBZ archive was found for {display}.")

    def require_info_archive(self, source: Path, archive_path: Path, step_name: str) -> None:
        has_info, _has_comicinfo, _english = self.confirmed_flags(source, archive_path)
        display = self.archive_display_path(source, archive_path)
        if not has_info:
            raise SkipArchive(f"Skipped missing info.txt for {step_name}: {display}")
        self.append_log_from_worker(f"Confirmed info.txt: {display}")

    def translate_archive_path(
        self,
        source: Path,
        archive_path: Path,
        cli_dir: Path,
        include_cg_galleries: bool,
        super_saver_mode: bool,
        paddle_ocr_cuda_enabled: bool,
    ) -> Path:
        display = self.archive_display_path(source, archive_path)
        if is_translated_archive_name(archive_path.name):
            self.append_log_from_worker(f"Confirmed English: {display}")
            return archive_path
        if not include_cg_galleries and is_artist_or_game_cg_archive(archive_path):
            raise SkipArchive(f"Skipped Artist/Game CG: {display}")

        output_path = archive_path.with_name(f"{archive_path.stem}-translatedENG{archive_path.suffix}")
        output_before = file_signature(output_path)
        self.append_log_from_worker(f"Translate: {display}")

        def on_translate_line(line: str) -> None:
            self.append_log_from_worker(line)
            progress = translate_image_progress_from_line(line)
            if progress is None:
                return
            image_index, image_total, completed = progress
            progress_value = image_index if completed else image_index - 1
            self.set_progress_from_worker(progress_value, image_total, f"({image_index}/{image_total})")

        self.set_progress_from_worker(0, 1, "")
        command = translate_command(archive_path, output_path, super_saver_mode, paddle_ocr_cuda_enabled)
        result = run_streaming_command(command, cwd=cli_dir, on_line=on_translate_line)
        output = (result.stdout + result.stderr).strip()
        if not output:
            self.append_log_from_worker(f"Processed {display}")
        if result.returncode != 0:
            self.append_log_from_worker(f"TranslateEXGallery failed for {display}")
            raise RuntimeError(f"TranslateEXGallery failed for {display}:\n{output}")

        output_after = file_signature(output_path)
        if output_after is not None and output_after != output_before and archive_path.is_file():
            moved_path = move_source_archive_to_translated_folder(archive_path)
            self.append_log_from_worker(f"Moved original to {self.archive_display_path(source, moved_path)}")

        translated_path = output_path if output_path.is_file() else archive_path
        _has_info, _has_comicinfo, english = self.confirmed_flags(source, translated_path)
        if not english:
            translated_display = self.archive_display_path(source, translated_path)
            raise RuntimeError(f"Translate finished, but English was not confirmed for {translated_display}.")
        self.append_log_from_worker(f"Confirmed English: {self.archive_display_path(source, translated_path)}")
        return translated_path

    def ensure_english_archive(
        self,
        source: Path,
        archive_path: Path,
        cli_dir: Path,
        include_cg_galleries: bool,
        super_saver_mode: bool,
        paddle_ocr_cuda_enabled: bool,
    ) -> Path:
        self.require_info_archive(source, archive_path, "Translate")
        _has_info, _has_comicinfo, english = self.confirmed_flags(source, archive_path)
        if english:
            self.append_log_from_worker(f"Confirmed English: {self.archive_display_path(source, archive_path)}")
            return archive_path
        return self.translate_archive_path(
            source,
            archive_path,
            cli_dir,
            include_cg_galleries,
            super_saver_mode,
            paddle_ocr_cuda_enabled,
        )

    def ensure_comicinfo_archive(self, source: Path, archive_path: Path) -> Path:
        self.require_info_archive(source, archive_path, "Info -> ComicInfo.xml")
        _has_info, has_comicinfo, _english = self.confirmed_flags(source, archive_path)
        display = self.archive_display_path(source, archive_path)
        if has_comicinfo:
            self.append_log_from_worker(f"Confirmed ComicInfo.xml: {display}")
            return archive_path

        script = repo_root() / "InfotoComicInfoxml" / "ComicInfoConverter.py"
        self.append_log_from_worker(f"Info -> ComicInfo.xml: {display}")
        result = run_captured_command([sys.executable, str(script), str(archive_path)])
        output = (result.stdout + result.stderr).strip()
        self.append_log_from_worker(output or f"Processed {display}")
        if result.returncode != 0:
            raise RuntimeError(f"Info -> ComicInfo.xml failed for {display}:\n{output}")

        _has_info, has_comicinfo, _english = self.confirmed_flags(source, archive_path)
        if not has_comicinfo:
            raise RuntimeError(f"Info -> ComicInfo.xml finished, but ComicInfo.xml was not confirmed for {display}.")
        self.append_log_from_worker(f"Confirmed ComicInfo.xml: {display}")
        return archive_path

    def prepare_archive_for_translate(
        self,
        source: Path,
        record: ArchiveRecord,
        cli_dir: Path,
        include_cg_galleries: bool,
        super_saver_mode: bool,
        paddle_ocr_cuda_enabled: bool,
    ) -> Path:
        archive_path = self.selected_archive_path(source, record)
        archive_path = self.ensure_cbz_archive(source, archive_path)
        return self.ensure_english_archive(
            source,
            archive_path,
            cli_dir,
            include_cg_galleries,
            super_saver_mode,
            paddle_ocr_cuda_enabled,
        )

    def prepare_archive_for_comicinfo(
        self,
        source: Path,
        record: ArchiveRecord,
        cli_dir: Path,
        include_cg_galleries: bool,
        super_saver_mode: bool,
        paddle_ocr_cuda_enabled: bool,
    ) -> Path:
        archive_path = self.prepare_archive_for_translate(
            source,
            record,
            cli_dir,
            include_cg_galleries,
            super_saver_mode,
            paddle_ocr_cuda_enabled,
        )
        return self.ensure_comicinfo_archive(source, archive_path)

    def prepare_archive_for_sync(
        self,
        source: Path,
        record: ArchiveRecord,
        cli_dir: Path,
        include_cg_galleries: bool,
        super_saver_mode: bool,
        paddle_ocr_cuda_enabled: bool,
    ) -> Path:
        return self.prepare_archive_for_comicinfo(
            source,
            record,
            cli_dir,
            include_cg_galleries,
            super_saver_mode,
            paddle_ocr_cuda_enabled,
        )

    def convert_zip_to_cbz(self) -> None:
        source = self.require_source()
        if source is None:
            return
        targets = [record for record in self.selected_records() if not record.cbz]
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one ZIP archive.")
            return

        def action() -> list[str]:
            total = len(targets)
            for index, record in enumerate(targets, start=1):
                self.append_log_from_worker(f"Zip to CBZ [{index}/{total}]: {record.relative_path}")
                self.ensure_cbz_archive(source, self.selected_archive_path(source, record))
            return []

        self.run_in_worker("Running Zip to CBZ...", action, done_message="Zip to CBZ finished", rescan_after=True)

    def create_comicinfo(self) -> None:
        source = self.require_source()
        if source is None:
            return
        cli_dir = repo_root() / "TranslateEXGallery"
        targets = self.selected_records()
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one archive.")
            return
        include_cg_galleries = self.translate_cg_var.get()
        super_saver_mode = self.super_saver_var.get()
        paddle_ocr_cuda_enabled = self.paddle_ocr_cuda_var.get()

        def action() -> list[str]:
            total = len(targets)
            skipped = 0
            for index, record in enumerate(targets, start=1):
                self.append_log_from_worker(f"Prepare ComicInfo [{index}/{total}]: {record.relative_path}")
                try:
                    self.prepare_archive_for_comicinfo(
                        source,
                        record,
                        cli_dir,
                        include_cg_galleries,
                        super_saver_mode,
                        paddle_ocr_cuda_enabled,
                    )
                except SkipArchive as exc:
                    skipped += 1
                    self.append_log_from_worker(str(exc))
            return [f"Skipped {skipped} archive(s)."] if skipped else []

        self.run_in_worker(
            "Creating ComicInfo.xml...",
            action,
            done_message="Info -> ComicInfo.xml finished",
            rescan_after=True,
        )

    def translate_selected(self) -> None:
        source = self.require_source()
        if source is None:
            return
        cli_dir = repo_root() / "TranslateEXGallery"
        targets = self.selected_records()
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one archive.")
            return
        include_cg_galleries = self.translate_cg_var.get()
        super_saver_mode = self.super_saver_var.get()
        paddle_ocr_cuda_enabled = self.paddle_ocr_cuda_var.get()

        def action() -> list[str]:
            total = len(targets)
            skipped = 0
            for index, record in enumerate(targets, start=1):
                self.append_log_from_worker(f"Prepare Translate [{index}/{total}]: {record.relative_path}")
                try:
                    self.prepare_archive_for_translate(
                        source,
                        record,
                        cli_dir,
                        include_cg_galleries,
                        super_saver_mode,
                        paddle_ocr_cuda_enabled,
                    )
                except SkipArchive as exc:
                    skipped += 1
                    self.append_log_from_worker(str(exc))
            return [f"Skipped {skipped} archive(s)."] if skipped else []

        self.run_in_worker("Translating selected archives...", action, done_message="Translate selected finished", rescan_after=True)

    def sync_selected(self) -> None:
        source = self.require_source()
        if source is None:
            return
        remote_sync_target = self.remote_var.get().strip()
        if not remote_sync_target:
            messagebox.showinfo("ComicRack Library Master", "Set Remote Sync Target before syncing.")
            return
        targets = self.selected_records()
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one archive.")
            return
        cli_dir = repo_root() / "TranslateEXGallery"
        include_cg_galleries = self.translate_cg_var.get()
        super_saver_mode = self.super_saver_var.get()
        paddle_ocr_cuda_enabled = self.paddle_ocr_cuda_var.get()

        def action() -> list[str]:
            total = len(targets)
            prepared_records: list[ArchiveRecord] = []
            skipped = 0
            for index, record in enumerate(targets, start=1):
                self.append_log_from_worker(f"Prepare Sync [{index}/{total}]: {record.relative_path}")
                try:
                    archive_path = self.prepare_archive_for_sync(
                        source,
                        record,
                        cli_dir,
                        include_cg_galleries,
                        super_saver_mode,
                        paddle_ocr_cuda_enabled,
                    )
                except SkipArchive as exc:
                    skipped += 1
                    self.append_log_from_worker(str(exc))
                    continue
                prepared_records.append(archive_record_from_path(source, archive_path))
            messages = sync_selected_archives(prepared_records, source, remote_sync_target)
            if skipped:
                messages.append(f"Skipped {skipped} archive(s).")
            return messages

        self.run_in_worker("Syncing selected archives...", action, done_message="Sync selected finished", rescan_after=True)

    def remove_duplicates(self) -> None:
        source = self.require_source()
        if source is None:
            return
        script = repo_root() / "RemoveDuplicates" / "remove_duplicates.py"

        def action() -> list[str]:
            result = run_captured_command([sys.executable, str(script), str(source)])
            output = (result.stdout + result.stderr).strip()
            messages = output.splitlines() if output else ["Remove duplicates finished."]
            if result.returncode != 0:
                raise RuntimeError(f"Remove duplicates failed:\n{output}")
            return messages

        self.run_in_worker(
            "Removing duplicate archives...",
            action,
            done_message="Remove duplicates finished",
            rescan_after=True,
        )

    def show_logged_comics(self) -> None:
        window = tk.Toplevel(self)
        window.title("Logged Comics")
        window.geometry("700x520")
        window.minsize(520, 360)
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        frame = ttk.Frame(window, padding=10)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        text = tk.Text(frame, wrap="none", undo=False)
        text.grid(row=0, column=0, sticky="nsew")
        y_scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        y_scroll.grid(row=0, column=1, sticky="ns")
        x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=text.xview)
        x_scroll.grid(row=1, column=0, sticky="ew")
        text.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

        list_text = records_as_copy_list(self.records)
        display_text = list_text or "No comics are currently logged."
        text.insert("1.0", display_text)
        text.focus_set()

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        button_frame.columnconfigure(0, weight=1)

        count_label = ttk.Label(button_frame, text=f"{len(self.records)} comic(s)")
        count_label.grid(row=0, column=0, sticky="w")
        copy_button = ttk.Button(button_frame, text="Copy All", command=lambda: self.copy_logged_comics(list_text))
        copy_button.grid(row=0, column=1, sticky="e", padx=(0, 6))
        close_button = ttk.Button(button_frame, text="Close", command=window.destroy)
        close_button.grid(row=0, column=2, sticky="e")
        Tooltip(copy_button, "Copy the full comic list to the clipboard.")
        Tooltip(close_button, "Close this list window.")

    def copy_logged_comics(self, list_text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(list_text)
        self.status_var.set("Copied comic list to clipboard")

    def require_source(self) -> Path | None:
        source = self.source_dir_or_none()
        if source is None:
            messagebox.showinfo("ComicRack Library Master", "Set ComicRack Source first.")
            return None
        return source

    def show_help(self) -> None:
        messagebox.showinfo(
            "ComicRack Library Master Help",
            "Set the three library paths at the top, then use Rescan to refresh archive status.\n\n"
            "The list shows ZIP and CBZ archives directly inside ComicRack Source. Subdirectories are ignored. ZIP files appear first. "
            "CBZ archives are selected by default the first time they are found, and your later selections persist.\n\n"
            "Selected archives are processed from smallest to largest, regardless of the current table sort.\n\n"
            "Workflow columns are ordered as CBZ, Info, ENGLISH, ComicInfo, and Synced. "
            "When a later UI tool is run, the UI first confirms the preceding columns and runs missing prerequisite steps when it can. "
            "Archives without info.txt are skipped for Translate, ComicInfo, or Sync, and the rest of the selected batch continues.\n\n"
            "By default, Translate skips archives whose info.txt category is Artist CG or Game CG. Check Artist/Game CG to include them.\n\n"
            "Super-Saver mode is off by default. When enabled, Translate uses PaddleOCR text detection to skip pages where no text boxes are found.\n\n"
            "CUDA OCR only applies when Super-Saver mode is enabled, and requires PaddleOCR to run under a compatible paddlepaddle-gpu install.\n\n"
            "During translation, the bottom progress bar shows the current image count for the active archive.\n\n"
            "Double-click a comic to open it with the Windows app associated with that archive type.\n\n"
            "Status and selections are saved in .comicrack_master_state.json inside ComicRack Source. "
            "The path fields are saved in master_ui_settings.json beside this UI script.",
        )


def main() -> int:
    app = ComicRackMasterUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
