import os
import unittest
from unittest import mock

from master_ui import (
    open_archive_with_default_app,
    resolve_command_executable,
    run_captured_command,
    run_streaming_command,
    subprocess_environment,
    translate_image_progress_from_line,
)


class MasterUiHelperTests(unittest.TestCase):
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
