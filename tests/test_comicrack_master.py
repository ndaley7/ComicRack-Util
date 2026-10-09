import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from comicrack_master import (
    AppSettings,
    archive_next_step,
    gallery_category_from_info_text,
    info_text_indicates_english,
    is_artist_or_game_cg_archive,
    is_translated_archive_name,
    load_app_settings,
    records_as_copy_list,
    load_source_state,
    move_source_archive_to_translated_folder,
    record_workflow_event,
    save_app_settings,
    save_source_state,
    scan_source_directory,
    sorted_archive_records,
    sync_series_list,
    sync_selected_archives,
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

    def test_scan_treats_translated_eng_filename_as_english(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Sample-translatedENG.cbz", {"info.txt": "Language: Japanese\r\n"})

            records = scan_source_directory(source)

            self.assertTrue(is_translated_archive_name("Sample-translatedENG.cbz"))
            self.assertTrue(records[0].english)

    def test_scan_treats_western_category_as_english(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Western.cbz", {"info.txt": "Category: Western\nLanguage: Japanese\n"})

            records = scan_source_directory(source)

            self.assertTrue(records[0].english)

    def test_scan_ignores_archives_in_subdirectories(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            nested = source / "Nested"
            nested.mkdir()
            write_archive(source / "Root.cbz", {"page.jpg": "image"})
            write_archive(nested / "Ignored.zip", {"page.jpg": "image"})

            records = scan_source_directory(source)

            self.assertEqual([record.relative_path for record in records], ["Root.cbz"])

    def test_move_source_archive_to_translated_folder_removes_original_from_scan(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            original = source / "Original.cbz"
            translated = source / "Original-translatedENG.cbz"
            write_archive(original, {"info.txt": "Language: Chinese", "page.jpg": "image"})
            write_archive(translated, {"info.txt": "Language: English", "page.jpg": "translated image"})

            moved = move_source_archive_to_translated_folder(original)
            records = scan_source_directory(source)

            self.assertEqual(moved, source / "Translated" / "Original.cbz")
            self.assertTrue(moved.is_file())
            self.assertFalse(original.exists())
            self.assertEqual([record.relative_path for record in records], ["Original-translatedENG.cbz"])
            self.assertTrue(records[0].english)

    def test_move_source_archive_to_translated_folder_keeps_existing_backup(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            translated_dir = source / "Translated"
            translated_dir.mkdir()
            write_archive(translated_dir / "Original.cbz", {"page.jpg": "previous"})
            original = source / "Original.cbz"
            write_archive(original, {"page.jpg": "current"})

            moved = move_source_archive_to_translated_folder(original)

            self.assertEqual(moved, translated_dir / "Original (1).cbz")
            self.assertTrue((translated_dir / "Original.cbz").is_file())
            self.assertTrue(moved.is_file())

    def test_gallery_category_from_info_text_reads_category_line(self) -> None:
        category = gallery_category_from_info_text(
            "Title\nhttps://example.test/gallery\n\nCategory: Artist CG\nLanguage: Japanese\n"
        )

        self.assertEqual(category, "Artist CG")

    def test_info_text_indicates_english_for_western_category(self) -> None:
        self.assertTrue(info_text_indicates_english("Language: English\n"))
        self.assertTrue(info_text_indicates_english("Category: Western\nLanguage: Japanese\n"))
        self.assertTrue(info_text_indicates_english("Category = western\nLanguage: Japanese\n"))
        self.assertFalse(info_text_indicates_english("Category: Manga\nLanguage: Japanese\n"))
        self.assertFalse(info_text_indicates_english("Language: Japanese\nUploader Comment:\nEnglish soon\n"))

    def test_is_artist_or_game_cg_archive_detects_skipped_categories(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            artist = source / "Artist.cbz"
            game = source / "Game.cbz"
            manga = source / "Manga.cbz"
            write_archive(artist, {"info.txt": "Category: Artist CG\nLanguage: Japanese\n"})
            write_archive(game, {"nested/info.txt": "Category = Game CG\nLanguage: Japanese\n"})
            write_archive(manga, {"info.txt": "Category: Manga\nLanguage: Japanese\n"})

            self.assertTrue(is_artist_or_game_cg_archive(artist))
            self.assertTrue(is_artist_or_game_cg_archive(game))
            self.assertFalse(is_artist_or_game_cg_archive(manga))

    def test_records_as_copy_list_returns_current_record_paths(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "First.zip", {"page.jpg": "image"})
            write_archive(source / "Second.cbz", {"page.jpg": "image"})

            records = scan_source_directory(source)

            self.assertEqual(records_as_copy_list(records), "First.zip\nSecond.cbz")

    def test_sync_series_list_creates_unsorted_entries_for_all_records(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "First.zip", {"page.jpg": "image"})
            write_archive(source / "Second.cbz", {"page.jpg": "image"})
            records = scan_source_directory(source)

            path = sync_series_list(source, records)

            self.assertTrue(path.read_text(encoding="utf-8").startswith('<?xml version="1.0" encoding="UTF-8"?>'))
            root = ElementTree.parse(path).getroot()
            series = root.find("series")
            self.assertIsNotNone(series)
            self.assertEqual(series.get("name"), "unsorted")
            self.assertEqual(
                [(comic.get("number"), comic.text) for comic in series.findall("comic")],
                [("0", "First.zip"), ("0", "Second.cbz")],
            )

    def test_sync_series_list_preserves_existing_assignments_and_adds_new_unsorted(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Alpha.cbz", {"page.jpg": "image"})
            write_archive(source / "Beta.cbz", {"page.jpg": "image"})
            write_archive(source / "Gamma.cbz", {"page.jpg": "image"})
            (source / "series.xml").write_text(
                '<?xml version="1.0" encoding="UTF-8"?>\n'
                '<comics>\n'
                '  <series name="unsorted">\n'
                '    <comic number="0">Missing.cbz</comic>\n'
                '    <comic number="0">Beta.cbz</comic>\n'
                '  </series>\n'
                '  <series name="Featured">\n'
                '    <comic number="2">Alpha.cbz</comic>\n'
                '  </series>\n'
                '</comics>\n',
                encoding="utf-8",
            )
            records = scan_source_directory(source)

            sync_series_list(source, records)

            root = ElementTree.parse(source / "series.xml").getroot()
            grouped = {
                series.get("name"): [(comic.get("number"), comic.text) for comic in series.findall("comic")]
                for series in root.findall("series")
            }
            self.assertEqual(grouped["Featured"], [("2", "Alpha.cbz")])
            self.assertEqual(grouped["unsorted"], [("0", "Beta.cbz"), ("0", "Gamma.cbz")])
            self.assertNotIn("Missing.cbz", (comic for comics in grouped.values() for _number, comic in comics))

    def test_sync_copies_only_archives_with_root_comicinfo(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw, tempfile.TemporaryDirectory() as remote_raw:
            source = Path(source_raw)
            remote = Path(remote_raw)
            write_archive(source / "Root.cbz", {"ComicInfo.xml": "<ComicInfo />", "page.jpg": "image"})
            write_archive(source / "Nested.cbz", {"Gallery/ComicInfo.xml": "<ComicInfo />", "page.jpg": "image"})
            write_archive(source / "Missing.cbz", {"page.jpg": "image"})
            records = scan_source_directory(source)

            messages = sync_selected_archives(records, source, str(remote))

            self.assertIn("Copied Root.cbz", messages)
            self.assertIn("Skipped Nested.cbz: root ComicInfo.xml not found", messages)
            self.assertIn("Skipped Missing.cbz: root ComicInfo.xml not found", messages)
            self.assertTrue((remote / "Root.cbz").is_file())
            self.assertFalse((remote / "Nested.cbz").exists())
            self.assertFalse((remote / "Missing.cbz").exists())

    def test_sorted_archive_records_sorts_by_clicked_columns(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Beta.cbz", {"info.txt": "Language: English"})
            write_archive(source / "Alpha.zip", {"page.jpg": "image"})
            records = scan_source_directory(source)

            by_file_desc = sorted_archive_records(records, "file", reverse=True)
            by_cbz_desc = sorted_archive_records(records, "cbz", reverse=True)
            by_info_desc = sorted_archive_records(records, "info", reverse=True)

            self.assertEqual([record.relative_path for record in by_file_desc], ["Beta.cbz", "Alpha.zip"])
            self.assertEqual([record.relative_path for record in by_cbz_desc], ["Beta.cbz", "Alpha.zip"])
            self.assertEqual([record.relative_path for record in by_info_desc], ["Beta.cbz", "Alpha.zip"])

    def test_archive_next_step_describes_pipeline_status(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "NeedsTranslation.cbz", {"info.txt": "Language: Japanese"})
            write_archive(source / "Ready.cbz", {"info.txt": "Language: English", "ComicInfo.xml": "<ComicInfo />"})
            records = scan_source_directory(source)

            by_name = {record.relative_path: record for record in records}

            self.assertEqual(archive_next_step(by_name["NeedsTranslation.cbz"]), "Needs translation")
            self.assertEqual(archive_next_step(by_name["Ready.cbz"]), "Ready to sync")

    def test_record_workflow_event_persists_last_run_history(self) -> None:
        with tempfile.TemporaryDirectory() as source_raw:
            source = Path(source_raw)
            write_archive(source / "Ready.cbz", {"info.txt": "Language: English"})
            records = scan_source_directory(source)
            record_workflow_event(records[0], "Translate", "ok", "Confirmed English archive.")
            save_source_state(source, records)

            rescanned = scan_source_directory(source, previous_state=load_source_state(source))

            self.assertEqual(rescanned[0].last_action, "Translate")
            self.assertEqual(rescanned[0].last_result, "ok")
            self.assertEqual(rescanned[0].history[-1]["message"], "Confirmed English archive.")

    def test_app_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as base_raw:
            base = Path(base_raw)
            settings = AppSettings(
                comicrack_source="C:/Comics",
                remote_sync_target="D:/Remote",
                fansadox_source="E:/Fansadox",
                column_widths={"file": 900},
                translate_cg_galleries=True,
                super_saver_mode=True,
                paddle_ocr_cuda_enabled=True,
            )
            save_app_settings(settings, base)

            self.assertEqual(load_app_settings(base), settings)

    def test_app_settings_defaults_paddle_ocr_cuda_disabled_for_old_config(self) -> None:
        with tempfile.TemporaryDirectory() as base_raw:
            base = Path(base_raw)
            (base / "master_ui_settings.json").write_text(
                '{"comicrack_source": "C:/Comics", "super_saver_mode": true}',
                encoding="utf-8",
            )

            settings = load_app_settings(base)

            self.assertTrue(settings.super_saver_mode)
            self.assertFalse(settings.paddle_ocr_cuda_enabled)

    def test_app_settings_ignores_invalid_column_widths(self) -> None:
        with tempfile.TemporaryDirectory() as base_raw:
            base = Path(base_raw)
            (base / "master_ui_settings.json").write_text(
                '{"comicrack_source": "C:/Comics", "column_widths": {"file": "800", "cbz": "bad", "info": 0}}',
                encoding="utf-8",
            )

            settings = load_app_settings(base)

            self.assertEqual(settings.column_widths, {"file": 800})


if __name__ == "__main__":
    unittest.main()
