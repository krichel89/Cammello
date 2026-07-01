# Cammello

A Python/PyQt5 batch upload tool for [Wikimedia Commons](https://commons.wikimedia.org), replacing VicunaUploader with full structured data (SDC) support.

> Formerly named *CommonsSDC*.

## Features

- **Batch upload** with a table view (thumbnail, source file, target filename, date, description per file)
- **Per-file thumbnail preview** (loaded downscaled, with EXIF orientation applied)
- **Custom target filename** on Commons per file — the extension is taken from the source file and cannot be changed
- **Automatic EXIF date** reading from image files
- **Shared base text** for all files (creator, copyright, license, templates)
- **Per-file `description_all`** field with `key=value` structured data tags
- **Structured Data on Commons** (captions, creator, depicts, license, copyright) set in a single `wbeditentity` API call
- **Gallery update** – appends uploaded files to an existing Commons gallery page
- **Name extraction** from captions for gallery labels (everything before "at", "bei", "à", etc.)
- **Automatic maintenance category** `[[Category:Uploaded with Cammello]]` on every file
- Login with Wikimedia account credentials (bot or main account), plus a **Test connection** button
- **Detailed logging** (file + live log tab) and a configurable HTTP timeout for easier troubleshooting
- **Saved settings** – the upload settings and the base description are persisted and restored on the next start
- Overwrite mode (ignore warnings)
- English user interface

## Installation

```
pip install -r requirements.txt
python Cammello.py
```

Tested with Python 3.11+ on Windows, macOS, and Linux.

## Usage

### Login

Enter your Wikimedia Commons credentials (same account as for the browser). For bot logins, use a BotPassword (`Special:BotPasswords`). After logging in, use **Test connection** to verify the session.

### Upload Settings (right panel)

- **Author** – e.g. `[[User:Harald Krichel|Harald Krichel]]`
- **Source** – e.g. `{{own}}`
- **License** – e.g. `{{Cc-by-sa-4.0}}`
- **Other templates** – e.g. `{{WikiPortraits Cannes Film Festival 2025}}`
- **Gallery prefix** – e.g. `User:Harald Krichel` or `User:Harald Krichel/Berlinale 2025`
- **HTTP timeout (s)** – default 120

Use the **Save settings** button to persist these settings together with the base description; they are also saved automatically when you close the window and restored on the next start.

### Target filename

Each row has a **Target filename** column (the name the file gets on Commons). Edit it freely; leave it empty to use the source filename. The file extension is fixed (taken from the source file) and cannot be changed.

### Base description_all

Text that applies to **all** files in the batch. Typically contains shared structured data:

```
creator=Q640
copyright=Q73566113
license=Q18199165
{{Berlinale 2025|type=red carpet}}
```

### Per-file description_all

Individual text per file. Supports the following `key=value` tags:

| Key              | Description                                                |
| ---------------- | ---------------------------------------------------------- |
| `caption_XX`     | Caption in language `XX` (any language code), set as SDC label |
| `creator`        | Wikidata QID for creator (P170)                            |
| `copyright`      | Wikidata QID for copyright status (P6216)                  |
| `license`        | Wikidata QID for license (P275)                            |
| `depicts`        | Wikidata QID(s) for depicted items (P180), comma-separated |
| `gallery_suffix` | Appended to gallery prefix, e.g. `Berlinale 2025`          |

Language codes for captions are detected dynamically, e.g. `caption_en`, `caption_de`, `caption_fr`, `caption_it`, `caption_es`, `caption_nl`, `caption_pl`, `caption_ru`, `caption_zh`.

All `key=value` lines are **removed** from the wikitext before upload and sent via the Wikibase API instead. Lines starting with `#` are treated as comments.

### Example description_all

```
caption_de=Chloé Zhao bei der Berlinale 2026
caption_en=Chloé Zhao at the 2026 Berlin International Film Festival
caption_fr=Chloé Zhao à la Berlinale 2026
creator=Q640
depicts=Q220647
copyright=Q73566113
license=Q18199165
gallery_suffix=Berlinale 2026

{{en|1=[[:en:Chloé Zhao|Chloé Zhao]] at the photo call at the 2026 Berlin International Film Festival}}
{{de|1=[[:de:Chloé Zhao|Chloé Zhao]] beim Photocall bei der Berlinale 2026}}
[[Category:Chloé Zhao]]
[[Category:Photographs by Harald Krichel from 2026]]
```

### Log / troubleshooting

The **Log** tab shows a live log; the full log (including the assembled wikitext and SDC payload per file) is also written to `~/Cammello/cammello_debug.log`. Enable **Verbose logging** for more detail. Credentials and tokens are masked in the log.

## Building a standalone executable

A Windows `.exe` or macOS `.app` can be built with [PyInstaller](https://pyinstaller.org/):

```
pip install pyinstaller
pyinstaller --onefile --windowed --name Cammello Cammello.py
```

PyInstaller cannot cross-compile, so each platform must be built on that platform. A GitHub Actions workflow (`.github/workflows/build.yml`) builds the Windows and macOS versions in the cloud and attaches them to the release.

## License

CC0
