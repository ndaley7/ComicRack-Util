import tempfile
import unittest
import zipfile
from pathlib import Path

from RemoveDuplicates.remove_duplicates import DUPLICATES_DIR_NAME, move_duplicate_archives


def write_archive(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)


class RemoveDuplicatesTests(unittest.TestCase):
    def test_move_duplicate_archives_moves_hash_matches_and_logs_them(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Keep.cbz", {"page.jpg": "same"})
            (source / "Copy.zip").write_bytes((source / "Keep.cbz").read_bytes())
            write_archive(source / "Different.cbz", {"page.jpg": "different"})

            messages = move_duplicate_archives(source)

            duplicates_dir = source / DUPLICATES_DIR_NAME
            self.assertTrue((source / "Keep.cbz").exists())
            self.assertTrue((source / "Different.cbz").exists())
            self.assertFalse((source / "Copy.zip").exists())
            self.assertTrue((duplicates_dir / "Copy.zip").exists())
            self.assertTrue((duplicates_dir / "duplicates.log").exists())
            self.assertIn("Moved duplicate Copy.zip", "\n".join(messages))
            self.assertIn("moved=Copy.zip", (duplicates_dir / "duplicates.log").read_text(encoding="utf-8"))

    def test_move_duplicate_archives_keeps_cbz_over_zip(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Archive.zip", {"page.jpg": "same"})
            (source / "Archive.cbz").write_bytes((source / "Archive.zip").read_bytes())

            move_duplicate_archives(source)

            self.assertTrue((source / "Archive.cbz").exists())
            self.assertFalse((source / "Archive.zip").exists())
            self.assertTrue((source / DUPLICATES_DIR_NAME / "Archive.zip").exists())

    def test_move_duplicate_archives_does_not_move_same_size_different_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            (source / "First.cbz").write_bytes(b"aaaa")
            (source / "Second.cbz").write_bytes(b"bbbb")

            messages = move_duplicate_archives(source)

            self.assertEqual(messages, ["No duplicate archives found."])
            self.assertTrue((source / "First.cbz").exists())
            self.assertTrue((source / "Second.cbz").exists())
            self.assertFalse((source / DUPLICATES_DIR_NAME).exists())

    def test_move_duplicate_archives_ignores_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            nested = source / "Nested"
            nested.mkdir()
            write_archive(source / "Root.cbz", {"page.jpg": "same"})
            (nested / "NestedCopy.cbz").write_bytes((source / "Root.cbz").read_bytes())

            messages = move_duplicate_archives(source)

            self.assertEqual(messages, ["No duplicate archives found."])
            self.assertTrue((nested / "NestedCopy.cbz").exists())

    def test_move_duplicate_archives_moves_numbered_download_copies_when_base_exists(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Comic.zip", {"page.jpg": "original"})
            write_archive(source / "Comic(1).zip", {"page.jpg": "download copy with different zip bytes"})
            write_archive(source / "Comic (2).zip", {"page.jpg": "another download copy with different zip bytes"})

            messages = move_duplicate_archives(source)

            duplicates_dir = source / DUPLICATES_DIR_NAME
            self.assertTrue((source / "Comic.zip").exists())
            self.assertFalse((source / "Comic(1).zip").exists())
            self.assertFalse((source / "Comic (2).zip").exists())
            self.assertTrue((duplicates_dir / "Comic(1).zip").exists())
            self.assertTrue((duplicates_dir / "Comic (2).zip").exists())
            self.assertIn("Moved duplicate Comic(1).zip", "\n".join(messages))
            self.assertIn("Moved duplicate Comic (2).zip", "\n".join(messages))

    def test_move_duplicate_archives_keeps_numbered_copy_when_base_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Comic(1).zip", {"page.jpg": "only copy"})

            messages = move_duplicate_archives(source)

            self.assertEqual(messages, ["No duplicate archives found."])
            self.assertTrue((source / "Comic(1).zip").exists())
            self.assertFalse((source / DUPLICATES_DIR_NAME).exists())


if __name__ == "__main__":
    unittest.main()
