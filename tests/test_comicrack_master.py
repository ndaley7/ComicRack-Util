import tempfile
import unittest
import zipfile
from pathlib import Path

from comicrack_master import (
    AppSettings,
    load_app_settings,
    records_as_copy_list,
    load_source_state,
    save_app_settings,
    save_source_state,
    scan_source_directory,
)


def write_archive(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


class ComicRackMasterTests(unittest.TestCase):
    def test_scan_lists_zip_first_and_detects_archive_flags(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw, tempfile.TemporaryDirectory() as remote_raw:
            source = Path(source_raw)
            remote = Path(remote_raw)
            write_archive(source / "Beta.cbz", {"info.txt": "Language: English", "ComicInfo.xml": "<ComicInfo />"})
            write_archive(source / "Alpha.zip", {"nested/page.jpg": "image"})
            write_archive(source / "Gamma.cbz", {"nested/info.txt": "Language: Chinese"})
            (remote / "Beta.cbz").write_bytes((source / "Beta.cbz").read_bytes())

            records = scan_source_directory(source, str(remote))

            self.assertEqual([record.relative_path for record in records], ["Alpha.zip", "Beta.cbz", "Gamma.cbz"])
            alpha, beta, gamma = records
            self.assertFalse(alpha.selected)
            self.assertTrue(beta.selected)
            self.assertTrue(beta.cbz)
            self.assertTrue(beta.has_info)
            self.assertTrue(beta.has_comicinfo)
            self.assertTrue(beta.english)
            self.assertTrue(beta.synced)
            self.assertTrue(gamma.has_info)
            self.assertFalse(gamma.english)

    def test_scan_preserves_existing_selection_state(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "KeepMe.cbz", {"page.jpg": "image"})
            initial_records = scan_source_directory(source)
            initial_records[0].selected = False
            save_source_state(source, initial_records)

            records = scan_source_directory(source, previous_state=load_source_state(source))

            self.assertFalse(records[0].selected)

    def test_scan_ignores_archives_in_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            nested = source / "Nested"
            nested.mkdir()
            write_archive(source / "Root.cbz", {"page.jpg": "image"})
            write_archive(nested / "Ignored.zip", {"page.jpg": "image"})

            records = scan_source_directory(source)

            self.assertEqual([record.relative_path for record in records], ["Root.cbz"])

    def test_records_as_copy_list_returns_current_record_paths(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "First.zip", {"page.jpg": "image"})
            write_archive(source / "Second.cbz", {"page.jpg": "image"})

            records = scan_source_directory(source)

            self.assertEqual(records_as_copy_list(records), "First.zip\nSecond.cbz")

    def test_app_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as base_raw:
            base = Path(base_raw)
            settings = AppSettings("C:/Comics", "D:/Remote", "E:/Fansadox")
            save_app_settings(settings, base)

            self.assertEqual(load_app_settings(base), settings)


if __name__ == "__main__":
    unittest.main()
