import os
import unittest
from unittest import mock

from master_ui import (
    open_archive_with_default_app,
    resolve_command_executable,
    run_captured_command,
    subprocess_environment,
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

    def test_open_archive_with_default_app_uses_windows_file_association(self) -> None:
        startfile = mock.Mock()
        with mock.patch("master_ui.os.startfile", startfile, create=True):
            open_archive_with_default_app(r"C:\Comics\Example.cbz")

        startfile.assert_called_once_with(r"C:\Comics\Example.cbz")


if __name__ == "__main__":
    unittest.main()
