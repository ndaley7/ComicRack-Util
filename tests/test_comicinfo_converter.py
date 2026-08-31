import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from InfotoComicInfoxml.ComicInfoConverter import (
    TAG_BANK_FILENAME,
    convert_cbz_file,
    convert_file,
)


def sample_info(tags: str) -> str:
    return f"""Sample Gallery
https://example.test/gallery/1
Category: Manga
Language: English
Length: 4 pages
Tags:
{tags}
"""


def read_tag_bank(path: Path) -> dict[str, list[str]]:
    root = ElementTree.parse(path).getroot()
    return {
        category.get("name", ""): [tag.text or "" for tag in category.findall("Tag")]
        for category in root.findall("Category")
    }


class ComicInfoConverterTests(unittest.TestCase):
    def test_convert_file_updates_sorted_universal_tag_bank(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            info_path = source / "info.txt"
            info_path.write_text(
                sample_info(
                    "> female: sword, armor\n"
                    "> character: zelda, link\n"
                ),
                encoding="utf-8",
            )

            convert_file(info_path)

            tag_bank = read_tag_bank(source / TAG_BANK_FILENAME)

            self.assertEqual(list(tag_bank.keys()), ["character", "female"])
            self.assertEqual(tag_bank["character"], ["link", "zelda"])
            self.assertEqual(tag_bank["female"], ["armor", "sword"])

    def test_convert_file_merges_new_tags_without_case_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            first = source / "first-info.txt"
            second = source / "second-info.txt"
            first.write_text(sample_info("> female: sword, armor\n"), encoding="utf-8")
            second.write_text(sample_info("> female: Armor, cape\n> group: knights\n"), encoding="utf-8")

            convert_file(first, source / "FirstComicInfo.xml")
            convert_file(second, source / "SecondComicInfo.xml")

            tag_bank = read_tag_bank(source / TAG_BANK_FILENAME)

            self.assertEqual(list(tag_bank.keys()), ["female", "group"])
            self.assertEqual(tag_bank["female"], ["armor", "cape", "sword"])
            self.assertEqual(tag_bank["group"], ["knights"])

    def test_convert_cbz_file_updates_tag_bank_beside_archive(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            archive_path = source / "Gallery.cbz"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("info.txt", sample_info("> artist: example artist\n"))
                archive.writestr("page.jpg", "image")

            result = convert_cbz_file(archive_path)
            tag_bank = read_tag_bank(source / TAG_BANK_FILENAME)

            self.assertIn("Added ComicInfo.xml", result)
            self.assertEqual(tag_bank, {"artist": ["example artist"]})


if __name__ == "__main__":
    unittest.main()
