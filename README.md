# ComicRack-Util

Utilities for working with comic/gallery archives.

## ComicRack Library Master UI

`master_ui.py` is a Tkinter launcher for scanning a ComicRack source folder,
tracking archive status, and running the utility scripts from one place.

```powershell
python .\master_ui.py
```

The UI remembers the `ComicRack Source`, `Remote Sync Target`, and
`Fansadox Source` path fields in `master_ui_settings.json` beside the script.
Per-archive status and checkbox selection state are stored in
`.comicrack_master_state.json` inside the selected ComicRack Source folder.
Use **Rescan** to force-refresh status for ZIP and CBZ files directly inside
the source folder. Subdirectories are ignored. ZIP files are listed first, and
newly discovered CBZ files are selected by default. Scans and utility actions
run in the background, with the bottom progress bar showing when work is in
progress. Click any table column heading to sort by that column; clicking the
same heading again reverses the sort. Drag table heading borders to resize
columns; those widths persist between runs. Use the bottom **Comic List** button
to open a copyable plain-text list of the currently loaded comics.

The workflow columns are ordered as **CBZ**, **Info**, **ENGLISH**,
**ComicInfo**, and **Synced**. When you run a later workflow tool from the UI,
the UI confirms the preceding columns first and runs missing prerequisite steps
when it can. For example, **Translate** first confirms CBZ and `info.txt`, and
**Sync Selected** brings selected archives through CBZ, Info, English, and
ComicInfo before copying. If `info.txt` is missing, that archive is skipped for
Translate, ComicInfo, or Sync, and the rest of the selected batch continues.

## ComicRack Gallery Tag Panel

`ComicRackGalleryTagPanel` is an experimental ComicRack / ComicRack Community
Edition script framework for an E-H-style metadata panel. It shows the selected
comic's cover, title, common ComicInfo metadata, grouped tag chips, and a
matching-comics table. Click one tag to find other comics with that tag; click
more tags to narrow the result set with AND matching. It also includes startup
and `BookOpened` helpers that show a small floating `Tags` launcher while
reading.

Install it by copying the `ComicRackGalleryTagPanel` folder into:

```text
%APPDATA%\cYo\ComicRack Community Edition\Scripts\
```

or, for classic ComicRack:

```text
%APPDATA%\cYo\ComicRack\Scripts\
```

Then restart ComicRack, select a comic, and run
`Right-click -> Automation -> GalleryTagPanel`. See
`ComicRackGalleryTagPanel\README.md` for packaging it as a `.crplugin` and for
the smart-list helper.

You can also install it with the helper script:

```powershell
python .\install_gallery_tag_panel.py
```

If ComicRack CE does not discover scripts from AppData, close ComicRack and
install directly into the bundled script directory:

```powershell
python .\install_gallery_tag_panel.py --dest "C:\Program Files\ComicRack Community Edition\Scripts" --flat
```

The **Remove Dups** button runs the `RemoveDuplicates` utility against the
ComicRack Source folder. It compares direct-child `.zip` and `.cbz` archives by
SHA-256 when they share the same size, moves exact duplicates into
`_DUPLICATES`, also catches numbered copies like `Example(1).zip` when
`Example.zip` is present, and logs moved files to `_DUPLICATES\duplicates.log`.

When **Translate** finishes an archive from the master UI and creates a new
`-translatedENG` archive, the original archive is moved into a `Translated`
subfolder. The UI then rescans the ComicRack Source folder, so the moved
original disappears from the list and the new translated archive is added.
By default, Translate skips archives whose `info.txt` contains
`Category: Artist CG` or `Category: Game CG`; check **Artist/Game CG** beside
the Translate button to include those galleries.
Archives whose `info.txt` contains `Category: Western` are treated as already
translated and show **Yes** in the ENGLISH column.
**Super-Saver mode** is unchecked by default. When checked, Translate uses
PaddleOCR text detection before each uncached page upload and skips pages where
no text boxes are found.
**CUDA OCR** is also unchecked by default. When checked together with
Super-Saver mode, PaddleOCR text detection runs on CUDA GPU 0 and requires a
compatible `paddlepaddle-gpu` install.
While translating, the bottom progress bar switches to the current archive's
image count, such as `(1/200)`, and advances as page translations complete or
cached pages are reused.

Double-click a comic in the table to open it with the Windows app associated
with that archive type.

## RemoveDuplicates

`RemoveDuplicates` moves exact duplicate ZIP/CBZ archives out of the source
folder without deleting them.

```powershell
python .\RemoveDuplicates\remove_duplicates.py "C:\path\to\comics"
```

The script ignores subdirectories. When duplicate hashes are found, it keeps a
preferred copy and moves the rest into `_DUPLICATES`; `.cbz` is preferred over
`.zip`, then shorter and alphabetically earlier names are preferred. Numbered
download copies such as `Example(1).zip` or `Example (2).cbz` are moved only
when the matching unsuffixed archive exists.

## InfotoComicInfoxml

`InfotoComicInfoxml` converts ExHentai/E-Hentai Downloader `info.txt` metadata into `ComicInfo.xml` files for comic archive readers.

Run it against a single loose `info.txt`:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py .\InfotoComicInfoxml\Samples\info.txt
```

That writes `ComicInfo.xml` beside the source `info.txt`.

Run it directly against a `.cbz` archive:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py "C:\path\to\comic.cbz"
```

For `.cbz` input, the converter only uses `info.txt` when it is present at the archive root. If root `info.txt` is missing, the archive is skipped. If root `ComicInfo.xml` already exists, the archive is skipped unless `--force` is passed:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py "C:\path\to\comic.cbz" --force
```

You can also choose an output path:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py .\InfotoComicInfoxml\Samples\info.txt --output .\InfotoComicInfoxml\Samples\ComicInfo.xml --force
```

For directories, the converter can process `info.txt` files recursively:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py "D:\Comics\Incoming" --recursive --force
```

The converter maps gallery metadata into ComicInfo fields such as `Title`, `Series`, `Writer`, `Genre`, `Summary`, `Notes`, `Web`, `PageCount`, `LanguageISO`, `Manga`, `AgeRating`, `Characters`, `Tags`, and posted date fields.

Each successful conversion also updates `UniversalTagBank.xml` in the source directory. The tag bank stores every newly encountered source tag under its original category, with categories and tags sorted for reuse by future tools.

Some source `info.txt` tags may contain sensitive classification terminology. To keep the repository source friendlier for GitHub browsing, those classification trigger terms are ROT13-encoded in the script and decoded only at runtime. This does not encrypt or hide generated metadata; it only avoids storing the raw trigger terms as readable source-code literals.

Local sample archives and generated sample metadata under `InfotoComicInfoxml\Samples` are ignored by Git so private or sensitive gallery metadata does not get pushed accidentally.

## ZiptoCBZ

`ZiptoCBZ` renames `.zip` comic archives to `.cbz`, handles duplicate `.zip`/`.cbz` pairs, and flattens archives that contain one redundant top-level folder with the same name as the archive.
It is safe to run against filenames containing Thai, Korean, Russian,
Japanese, Chinese, and other Unicode characters; utility output is forced to
UTF-8 to avoid Windows console encoding failures.
When run from the master UI, each selected archive is logged as it is processed.
Invalid ZIP/CBZ files are moved into `_PROBLEMS` and logged to
`_PROBLEMS\problems.log`.

Run it against a directory:

```powershell
python .\ZiptoCBZ\zip_to_cbz.py "C:\path\to\comics"
```

Process one archive:

```powershell
python .\ZiptoCBZ\zip_to_cbz.py "C:\path\to\comics\Example.zip"
```

Include subdirectories:

```powershell
python .\ZiptoCBZ\zip_to_cbz.py "C:\path\to\comics" --recursive
```

When both `Example.zip` and `Example.cbz` exist, the script keeps the larger archive and moves the smaller one into a `Duplicates` folder. If they are the same size, it keeps the existing `.cbz`. When flattening an archive, it moves the original `.cbz` into `Duplicates` as a backup before replacing it with the flattened version.

## TranslateEXGallery

`TranslateEXGallery` is a small Node.js CLI tool that translates image files inside an EX/E-Hentai-style gallery ZIP or CBZ using the Torii Image Translator API.

It expects the archive to contain:

- one or more supported images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.gif`, `.tif`, or `.tiff`
- an `info.txt` file anywhere in the archive
- a metadata language line such as `Language: Chinese`

The tool writes a new translated ZIP or CBZ beside the original. It does not overwrite the source archive.
During translation, completed page outputs are stored in a temporary
`<output archive>.work` folder beside the intended output archive. If the run
fails partway through, rerunning the same input/output pair reuses those cached
pages instead of sending them to Torii again. The work folder is removed after
the translated archive is written successfully.

Translation is skipped without contacting Torii when:

- the archive filename contains the word `English`, case-insensitively
- the archive filename stem ends with `translatedENG`, case-insensitively
- the archive does not contain an `info.txt` file

## Setup

Install dependencies:

```powershell
cd TranslateEXGallery
npm install
```

Super-Saver mode is optional and needs Python PaddleOCR dependencies.
PaddlePaddle currently publishes Windows wheels for Python 3.9 through 3.13,
so use a supported Python for this feature. For a typical CPU-only Windows
setup:

```powershell
py -3.13 -m pip install -r .\requirements-super-saver.txt
```

To use **CUDA OCR** from the master UI, install a compatible GPU build of
PaddlePaddle in the Python environment used by PaddleOCR, then leave
`PADDLEOCR_PYTHON` pointed at that environment.

From the repository root, `py -3.13 -m pip install -r .\requirements.txt`
installs the Python dependencies for every tool in the suite.
If the master UI is running under a different Python, set `PADDLEOCR_PYTHON`
to the supported Python executable before launching it.

Set your Torii API key:

```powershell
$env:TORII_API="your_api_key"
```

In `cmd.exe`:

```cmd
set TORII_API=your_api_key
```

`%TORII_API%` is the `cmd.exe` syntax for expanding the variable. The variable name itself should be `TORII_API`.

If you set `TORII_API` through Windows environment settings or with `setx`, open a new terminal before running the tool. The CLI also checks the persisted Windows User and Machine environment values as a fallback.

## Usage

Run the CLI:

```powershell
npm start
```

The tool will prompt for:

- the ZIP or CBZ file path
- an output archive path, defaulting to `<original filename>-translatedENG.<original extension>`

You can also pass paths directly:

```powershell
npm start -- --zip "..\SAMPLES\[Miwerjooggetser] Yelan Nama Onaho-ka (Genshin Impact) [Chinese].zip" --out "..\SAMPLES\sample-translatedENG.zip"
```

For CBZ files, the default output keeps the `.cbz` extension, for example `sample.cbz` becomes `sample-translatedENG.cbz`.

Enable PaddleOCR preflight text detection from the CLI with:

```powershell
npm start -- --zip "C:\path\to\comic.cbz" --super-saver
```

Use CUDA GPU 0 for that PaddleOCR text detection with:

```powershell
npm start -- --zip "C:\path\to\comic.cbz" --super-saver --paddle-ocr-cuda
```

## Behavior

For each supported image in the archive, the tool:

- sends the image to Torii with `target_lang=en`
- replaces the archive entry with Torii's translated image result
- processes images sequentially to respect Torii's rate limit
- copies `.gif` entries unchanged instead of sending them to Torii or PaddleOCR
- reuses cached page translations from a previous failed run when available
- in Super-Saver mode, skips Torii uploads for uncached pages where PaddleOCR detects no text boxes
- with `--paddle-ocr-cuda`, asks PaddleOCR to use `gpu:0` for Super-Saver text detection
- retries transient failures such as `429`, upstream `5xx` errors, and network timeouts
- logs remaining Torii credits after each image when Torii returns the `credits` response header

For `info.txt`, the tool:

- finds it case-insensitively anywhere in the archive
- updates only the main metadata `Language:` line to `English`
- leaves tag lines such as `> language: chinese` unchanged
- preserves the rest of the file content

For credits, the tool:

- checks Torii credits before and after the job with `GET https://api.toriitranslate.com/api/credits`
- prints `creditsBefore`, `creditsAfter`, and `creditsUsed` in the final summary when available
- prints estimated USD cost using `$13 / 6000 credits`
- continues translation if a credits lookup fails, while printing a warning

## Tests

Run the test suite:

```powershell
npm test
```
