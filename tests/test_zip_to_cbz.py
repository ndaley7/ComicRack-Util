import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "ZiptoCBZ" / "zip_to_cbz.py"
PROBLEMS_DIR_NAME = "_PROBLEMS"


class ZipToCbzTests(unittest.TestCase):
    def test_cli_handles_unicode_filenames_when_console_encoding_is_limited(self) -> None:
        unicode_names = [
            "ภาษาไทย",
            "클로저스 시리즈",
            "русский архив",
            "日本語アーカイブ",
            "中文漫画",
        ]

        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            for archive_stem in unicode_names:
                with self.subTest(archive_stem=archive_stem):
                    archive_path = source / f"{archive_stem}.zip"
                    with zipfile.ZipFile(archive_path, "w") as archive:
                        archive.writestr("page.jpg", "image")

                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "cp1252"
                    result = subprocess.run(
                        [sys.executable, str(SCRIPT), str(archive_path)],
                        capture_output=True,
                        env=env,
                        check=False,
                    )

                    output = (result.stdout + result.stderr).decode("utf-8", errors="replace")
                    self.assertEqual(result.returncode, 0, output)
                    self.assertIn("Processed 1 file target.", output)
                    self.assertTrue((source / f"{archive_stem}.cbz").exists())

    def test_cli_moves_invalid_zip_to_problems_without_traceback_after_rename(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "Not Really Zip.zip"
            archive_path.write_text("not a zip file", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(archive_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("Moved invalid ZIP/CBZ archive to _PROBLEMS", output)
            self.assertNotIn("Traceback", output)
            self.assertFalse((source / "Not Really Zip.zip").exists())
            self.assertFalse((source / "Not Really Zip.cbz").exists())
            self.assertTrue((source / PROBLEMS_DIR_NAME / "Not Really Zip.cbz").exists())
            self.assertIn(
                "reason=Invalid ZIP/CBZ archive",
                (source / PROBLEMS_DIR_NAME / "problems.log").read_text(encoding="utf-8"),
            )

    def test_cli_moves_invalid_cbz_to_problems(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "Broken.cbz"
            archive_path.write_text("not a zip file", encoding="utf-8")

            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(archive_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )

            output = result.stdout + result.stderr
            self.assertEqual(result.returncode, 0, output)
            self.assertIn("Moved invalid ZIP/CBZ archive to _PROBLEMS", output)
            self.assertFalse(archive_path.exists())
            self.assertTrue((source / PROBLEMS_DIR_NAME / "Broken.cbz").exists())


if __name__ == "__main__":
    unittest.main()
