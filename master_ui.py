#!/usr/bin/env python3
"""Tkinter master UI for ComicRack library processing utilities."""

from __future__ import annotations

import os
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
    load_app_settings,
    load_source_state,
    repo_root,
    records_as_copy_list,
    save_app_settings,
    save_source_state,
    scan_source_directory,
    sorted_archive_records,
    sync_selected_archives,
    update_record_selection,
)


YES = "Yes"
NO = "No"
TREE_HEADINGS = {
    "selected": "Use",
    "file": "File",
    "cbz": "CBZ",
    "info": "Info",
    "comicinfo": "ComicInfo",
    "english": "ENGLISH",
    "synced": "Synced",
    "error": "Status",
}


def subprocess_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8:backslashreplace"
    return env


def run_captured_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=str(cwd) if cwd is not None else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=subprocess_environment(),
        check=False,
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
        self.status_var = tk.StringVar(value="Ready")
        self.selected_count_var = tk.StringVar(value="No archives selected")
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
        toolbar.columnconfigure(10, weight=1)

        self._add_button(toolbar, "Rescan", self.rescan, 0, "Force-refresh archive status from the ComicRack Source folder.")
        self._add_button(toolbar, "Select All", self.select_all, 1, "Select every listed archive.")
        self._add_button(toolbar, "Select None", self.select_none, 2, "Clear all archive selections.")
        self._add_button(toolbar, "Zip to CBZ", self.convert_zip_to_cbz, 3, "Rename selected ZIP archives to CBZ and flatten a redundant same-named top-level folder when present.")
        self._add_button(toolbar, "Info -> ComicInfo.xml", self.create_comicinfo, 4, "Add ComicInfo.xml to selected CBZ archives that contain root info.txt.")
        self._add_button(toolbar, "Translate", self.translate_selected, 5, "Run TranslateEXGallery for selected non-English archives.")
        self._add_button(toolbar, "Sync Selected", self.sync_selected, 6, "Copy selected archives to the Remote Sync Target folder.")
        self._add_button(toolbar, "Remove Dups", self.remove_duplicates, 7, "Hash-check direct-source archives and move duplicate matches into _DUPLICATES.")
        self._add_button(toolbar, "Help", self.show_help, 8, "Show a quick guide for this master UI.")

        self.selected_label = ttk.Label(toolbar, textvariable=self.selected_count_var, anchor="e")
        self.selected_label.grid(row=0, column=10, sticky="e", padx=(8, 0))

        list_frame = ttk.Frame(self, padding=(10, 0, 10, 4))
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        columns = ("selected", "file", "cbz", "info", "comicinfo", "english", "synced", "error")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")
        self.configure_tree_headings()
        self.tree.column("selected", width=54, minwidth=54, stretch=False, anchor="center")
        self.tree.column("file", width=430, minwidth=240, stretch=True)
        for column in ("cbz", "info", "comicinfo", "english", "synced"):
            self.tree.column(column, width=92, minwidth=82, stretch=False, anchor="center")
        self.tree.column("error", width=150, minwidth=100, stretch=True)
        self.tree.bind("<ButtonRelease-1>", self.on_tree_click)
        self.tree.bind("<space>", self.toggle_current_selection)

        y_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=y_scroll.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        y_scroll.grid(row=0, column=1, sticky="ns")
        Tooltip(
            self.tree,
            "Click a column heading to sort. Click the Use column or press Space to toggle processing. Only files directly inside ComicRack Source are listed. ZIP files appear first until a sort is selected.",
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
        self.progress = ttk.Progressbar(status_frame, mode="indeterminate", length=220)
        self.progress.grid(row=0, column=2, sticky="e")
        Tooltip(self.progress, "Shows that a scan, conversion, translation, or sync operation is running.")

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

    def begin_busy(self, message: str) -> bool:
        if self.busy:
            messagebox.showinfo("ComicRack Library Master", "An operation is already running.")
            return False

        self.busy = True
        self.status_var.set(message)
        self.progress.start(12)
        for button in self.action_buttons:
            button.state(["disabled"])
        return True

    def end_busy(self) -> None:
        self.busy = False
        self.progress.stop()
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
                    YES if record.has_comicinfo else NO,
                    YES if record.english else NO,
                    YES if record.synced else NO,
                    record.error,
                ),
            )
        self.update_selected_count()

    def update_selected_count(self) -> None:
        count = sum(1 for record in self.records if record.selected)
        noun = "archive" if count == 1 else "archives"
        self.selected_count_var.set(f"{count} {noun} selected")

    def on_tree_click(self, event: tk.Event) -> None:
        region = self.tree.identify("region", event.x, event.y)
        column = self.tree.identify_column(event.x)
        row_id = self.tree.identify_row(event.y)
        if region == "cell" and column == "#1" and row_id:
            self.toggle_record(row_id)

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
        return [record for record in self.records if record.selected]

    def convert_zip_to_cbz(self) -> None:
        source = self.require_source()
        if source is None:
            return
        script = repo_root() / "ZiptoCBZ" / "zip_to_cbz.py"
        targets = [record for record in self.selected_records() if not record.cbz]
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one ZIP archive.")
            return

        def action() -> list[str]:
            total = len(targets)
            failures = []
            for index, record in enumerate(targets, start=1):
                archive_path = source / record.relative_path
                self.append_log_from_worker(f"Zip to CBZ [{index}/{total}]: {record.relative_path}")
                result = run_captured_command([sys.executable, str(script), str(archive_path)])
                output = (result.stdout + result.stderr).strip()
                self.append_log_from_worker(output or f"Processed {record.relative_path}")
                if result.returncode != 0:
                    failures.append(record.relative_path)
                    self.append_log_from_worker(f"ZiptoCBZ failed for {record.relative_path}")
            if failures:
                raise RuntimeError(f"ZiptoCBZ failed for {len(failures)} archive(s). Check the Run Log for details.")
            return []

        self.run_in_worker("Running Zip to CBZ...", action, done_message="Zip to CBZ finished", rescan_after=True)

    def create_comicinfo(self) -> None:
        source = self.require_source()
        if source is None:
            return
        script = repo_root() / "InfotoComicInfoxml" / "ComicInfoConverter.py"
        targets = [record for record in self.selected_records() if record.cbz]
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one CBZ archive.")
            return

        def action() -> list[str]:
            messages = []
            for record in targets:
                archive_path = source / record.relative_path
                result = run_captured_command([sys.executable, str(script), str(archive_path)])
                output = (result.stdout + result.stderr).strip()
                messages.append(output or f"Processed {record.relative_path}")
                if result.returncode != 0:
                    raise RuntimeError(f"Info -> ComicInfo.xml failed for {record.relative_path}:\n{output}")
            return messages

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
        targets = [record for record in self.selected_records() if not record.english]
        if not targets:
            messagebox.showinfo("ComicRack Library Master", "Select at least one non-English archive.")
            return

        def action() -> list[str]:
            messages = []
            for record in targets:
                archive_path = source / record.relative_path
                output_path = archive_path.with_name(f"{archive_path.stem}-translatedENG{archive_path.suffix}")
                result = run_captured_command(
                    ["npm", "start", "--", "--zip", str(archive_path), "--out", str(output_path)],
                    cwd=cli_dir,
                )
                output = (result.stdout + result.stderr).strip()
                messages.append(output or f"Processed {record.relative_path}")
                if result.returncode != 0:
                    raise RuntimeError(f"TranslateEXGallery failed for {record.relative_path}:\n{output}")
            return messages

        self.run_in_worker("Translating selected archives...", action, done_message="Translate selected finished", rescan_after=True)

    def sync_selected(self) -> None:
        source = self.require_source()
        if source is None:
            return
        remote_sync_target = self.remote_var.get().strip()
        if not remote_sync_target:
            messagebox.showinfo("ComicRack Library Master", "Set Remote Sync Target before syncing.")
            return

        def action() -> list[str]:
            return sync_selected_archives(self.records, source, remote_sync_target)

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
            "Status and selections are saved in .comicrack_master_state.json inside ComicRack Source. "
            "The path fields are saved in master_ui_settings.json beside this UI script.",
        )


def main() -> int:
    app = ComicRackMasterUI()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
