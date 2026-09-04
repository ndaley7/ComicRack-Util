import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from master_ui import (
    ComicRackMasterUI,
    SkipArchive,
    TREE_COLUMNS,
    archive_record_from_path,
    open_archive_with_default_app,
    resolve_command_executable,
    run_captured_command,
    run_streaming_command,
    selected_records_for_run,
    subprocess_environment,
    translate_command,
    translate_image_progress_from_line,
)
from comicrack_master import ArchiveRecord


def write_archive(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


class MasterUiHelperTests(unittest.TestCase):
    def test_tree_columns_show_english_before_comicinfo(self) -> None:
        self.assertLess(TREE_COLUMNS.index("english"), TREE_COLUMNS.index("comicinfo"))

    def test_archive_record_from_path_reads_current_workflow_flags(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "Sample-translatedENG.cbz"
            write_archive(archive_path, {"info.txt": "Language: Japanese", "ComicInfo.xml": "<ComicInfo />"})

            record = archive_record_from_path(source, archive_path)

            self.assertEqual(record.relative_path, "Sample-translatedENG.cbz")
            self.assertTrue(record.cbz)
            self.assertTrue(record.has_info)
            self.assertTrue(record.english)
            self.assertTrue(record.has_comicinfo)

    def test_require_info_archive_skips_missing_info_without_fatal_error(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "NoInfo.cbz"
            write_archive(archive_path, {"page.jpg": "image"})
            ui = object.__new__(ComicRackMasterUI)
            ui.append_log_from_worker = mock.Mock()

            with self.assertRaisesRegex(SkipArchive, "Skipped missing info.txt"):
                ui.require_info_archive(source, archive_path, "Translate")

            ui.append_log_from_worker.assert_not_called()

    def test_ensure_english_archive_logs_already_english_skip(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "AlreadyEnglish.cbz"
            write_archive(archive_path, {"info.txt": "Language: English\n"})
            ui = object.__new__(ComicRackMasterUI)
            ui.append_log_from_worker = mock.Mock()

            result = ui.ensure_english_archive(
                source,
                archive_path,
                Path("TranslateEXGallery"),
                include_cg_galleries=False,
                super_saver_mode=False,
                paddle_ocr_cuda_enabled=False,
            )

            self.assertEqual(result, archive_path)
            ui.append_log_from_worker.assert_any_call("Skipped translation because ENGLISH is already Yes: AlreadyEnglish.cbz")

    def test_selected_records_for_run_orders_selected_entries_by_size(self) -> None:
        records = [
            ArchiveRecord("Large.cbz", "Large.cbz", True, True, True, False, False, False, 300, 0),
            ArchiveRecord("Unselected.cbz", "Unselected.cbz", False, True, True, False, False, False, 1, 0),
            ArchiveRecord("TieB.cbz", "TieB.cbz", True, True, True, False, False, False, 100, 0),
            ArchiveRecord("Small.cbz", "Small.cbz", True, True, True, False, False, False, 20, 0),
            ArchiveRecord("TieA.cbz", "TieA.cbz", True, True, True, False, False, False, 100, 0),
        ]

        ordered = selected_records_for_run(records)

        self.assertEqual(
            [record.relative_path for record in ordered],
            ["Small.cbz", "TieA.cbz", "TieB.cbz", "Large.cbz"],
        )

    def test_translate_command_adds_cuda_flag_only_with_super_saver(self) -> None:
        archive_path = Path("C:/Comics/Sample.cbz")
        output_path = Path("C:/Comics/Sample-translatedENG.cbz")

        self.assertEqual(
            translate_command(archive_path, output_path, super_saver_mode=True, paddle_ocr_cuda_enabled=True),
            [
                "node",
                "src/cli.js",
                "--zip",
                str(archive_path),
                "--out",
                str(output_path),
                "--super-saver",
                "--paddle-ocr-cuda",
            ],
        )
        self.assertNotIn(
            "--paddle-ocr-cuda",
            translate_command(archive_path, output_path, super_saver_mode=False, paddle_ocr_cuda_enabled=True),
        )

    def test_translate_command_keeps_special_characters_inside_path_arguments(self) -> None:
        archive_path = Path("F:/Ex-H/[rbqinori] Sample [Chinese&Textless].cbz")
        output_path = Path("F:/Ex-H/[rbqinori] Sample [Chinese&Textless]-translatedENG.cbz")

        command = translate_command(archive_path, output_path, super_saver_mode=False, paddle_ocr_cuda_enabled=False)

        self.assertEqual(command[0:2], ["node", "src/cli.js"])
        self.assertIn(str(archive_path), command)

    def test_subprocess_environment_forces_safe_python_output_encoding(self) -> None:
        env = subprocess_environment()

        self.assertEqual(env["PYTHONIOENCODING"], "utf-8:backslashreplace")
        self.assertEqual(env.get("PATH"), os.environ.get("PATH"))

    def test_resolve_command_executable_uses_path_extensions(self) -> None:
        with mock.patch("master_ui.shutil.which", return_value=r"C:\Program Files\nodejs\npm.CMD"):
            self.assertEqual(resolve_command_executable("npm"), r"C:\Program Files\nodejs\npm.CMD")

    def test_run_captured_command_launches_resolved_executable(self) -> None:
        completed = mock.Mock()
        with (
            mock.patch("master_ui.shutil.which", return_value=r"C:\Program Files\nodejs\npm.CMD"),
            mock.patch("master_ui.subprocess.run", return_value=completed) as subprocess_run,
        ):
            result = run_captured_command(["npm", "start", "--"])

        self.assertIs(result, completed)
        subprocess_run.assert_called_once()
        self.assertEqual(subprocess_run.call_args.args[0], [r"C:\Program Files\nodejs\npm.CMD", "start", "--"])

    def test_run_captured_command_reports_missing_executable(self) -> None:
        with mock.patch("master_ui.shutil.which", return_value=None):
            with self.assertRaisesRegex(FileNotFoundError, "Required command not found on PATH: npm"):
                run_captured_command(["npm", "start"])

    def test_run_streaming_command_reports_lines_as_they_arrive(self) -> None:
        process = mock.Mock()
        process.stdout = ["[1/2] Translating page-1.jpg\n", "[1/2] Done page-1.jpg.\n"]
        process.wait.return_value = 0
        seen_lines = []

        with (
            mock.patch("master_ui.shutil.which", return_value=r"C:\Program Files\nodejs\npm.CMD"),
            mock.patch("master_ui.subprocess.Popen", return_value=process) as popen,
        ):
            result = run_streaming_command(["npm", "start"], on_line=seen_lines.append)

        popen.assert_called_once()
        self.assertEqual(popen.call_args.args[0], [r"C:\Program Files\nodejs\npm.CMD", "start"])
        self.assertEqual(seen_lines, ["[1/2] Translating page-1.jpg", "[1/2] Done page-1.jpg."])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "[1/2] Translating page-1.jpg\n[1/2] Done page-1.jpg.\n")

    def test_translate_image_progress_from_line_reads_current_image(self) -> None:
        self.assertEqual(translate_image_progress_from_line("[1/200] Translating page-001.jpg"), (1, 200, False))
        self.assertEqual(translate_image_progress_from_line("[1/200] Checking text page-001.jpg"), (1, 200, False))
        self.assertEqual(translate_image_progress_from_line("[1/200] Text check failed page-001.jpg. Translating anyway: bad gif"), (1, 200, False))
        self.assertEqual(translate_image_progress_from_line("[1/200] Text detected page-001.jpg. Boxes: 2."), (1, 200, False))
        self.assertEqual(translate_image_progress_from_line("[2/200] Done page-002.jpg."), (2, 200, True))
        self.assertEqual(translate_image_progress_from_line("[2/200] No text found page-002.jpg."), (2, 200, True))
        self.assertEqual(
            translate_image_progress_from_line("[3/200] Reusing cached translation page-003.jpg"),
            (3, 200, True),
        )
        self.assertEqual(
            translate_image_progress_from_line("[4/200] Keeping original page-004.gif. GIF files are copied without translation."),
            (4, 200, True),
        )
        self.assertIsNone(translate_image_progress_from_line("Credits before: 100"))

    def test_open_archive_with_default_app_uses_windows_file_association(self) -> None:
        startfile = mock.Mock()
        with mock.patch("master_ui.os.startfile", startfile, create=True):
            open_archive_with_default_app(r"C:\Comics\Example.cbz")

        startfile.assert_called_once_with(r"C:\Comics\Example.cbz")


if __name__ == "__main__":
    unittest.main()
