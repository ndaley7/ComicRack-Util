# ComicRack-Util

Utilities for working with comic/gallery archives.

## InfotoComicInfoxml

`InfotoComicInfoxml` converts ExHentai/E-Hentai Downloader `info.txt` metadata into `ComicInfo.xml` files for comic archive readers.

Run it against a single `info.txt`:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py .\InfotoComicInfoxml\Samples\info.txt
```

That writes `ComicInfo.xml` beside the source `info.txt`.

You can also choose an output path:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py .\InfotoComicInfoxml\Samples\info.txt --output .\InfotoComicInfoxml\Samples\ComicInfo.xml --overwrite
```

For directories, the converter can process `info.txt` files recursively:

```powershell
python .\InfotoComicInfoxml\ComicInfoConverter.py "D:\Comics\Incoming" --recursive --overwrite
```

The converter maps gallery metadata into ComicInfo fields such as `Title`, `Series`, `Writer`, `Genre`, `Summary`, `Notes`, `Web`, `PageCount`, `LanguageISO`, `Manga`, `AgeRating`, `Characters`, `Tags`, and posted date fields.

Some source `info.txt` tags may contain sensitive classification terminology. To keep the repository source friendlier for GitHub browsing, those classification trigger terms are ROT13-encoded in the script and decoded only at runtime. This does not encrypt or hide generated metadata; it only avoids storing the raw trigger terms as readable source-code literals.

Local sample archives and generated sample metadata under `InfotoComicInfoxml\Samples` are ignored by Git so private or sensitive gallery metadata does not get pushed accidentally.

## ZiptoCBZ

`ZiptoCBZ` renames `.zip` comic archives to `.cbz`, handles duplicate `.zip`/`.cbz` pairs, and flattens archives that contain one redundant top-level folder with the same name as the archive.

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

Translation is skipped without contacting Torii when:

- the archive filename contains the word `English`, case-insensitively
- the archive does not contain an `info.txt` file

## Setup

Install dependencies:

```powershell
cd TranslateEXGallery
npm install
```

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

## Behavior

For each supported image in the archive, the tool:

- sends the image to Torii with `target_lang=en`
- replaces the archive entry with Torii's translated image result
- processes images sequentially to respect Torii's rate limit
- retries transient failures such as `429`, `503`, and network timeouts
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
