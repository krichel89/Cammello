# CommonsSDC

A Python/PyQt6 batch upload tool for [Wikimedia Commons](https://commons.wikimedia.org), replacing VicunaUploader with full structured data (SDC) support.

## Features

- **Batch upload** with a table view (filename, title, date, description per file)
- **Automatic EXIF date** reading from image files
- **Shared base text** for all files (creator, copyright, license, templates)
- **Per-file `description_all`** field with `key=value` structured data tags
- **Structured Data on Commons** (captions, creator, depicts, license, copyright) set in a single `wbeditentity` API call
- **Gallery update** – appends uploaded files to an existing Commons gallery page
- **Name extraction** from captions for gallery labels (everything before "at", "bei", "à", etc.)
- Login with Wikimedia account credentials (bot or main account)
- Overwrite mode (ignore warnings)

## Installation

```bash
pip install -r requirements.txt
python CommonsSDC.py
```

Tested with Python 3.11+ on Windows, macOS, and Linux.

## Usage

### Login
Enter your Wikimedia Commons credentials (same account as for the browser).

### Upload Settings (right panel)
- **Author** – e.g. `[[User:Harald Krichel|Harald Krichel]]`
- **Source** – e.g. `{{own}}`
- **License** – e.g. `{{Cc-by-sa-4.0}}`
- **Other templates** – e.g. `{{WikiPortraits Cannes Film Festival 2025}}`
- **Gallery prefix** – e.g. `User:Harald Krichel` or `User:Harald Krichel/Berlinale 2025`

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

| Key | Description |
|-----|-------------|
| `caption_en` | English caption (set as SDC label) |
| `caption_de` | German caption |
| `caption_fr` | French caption |
| `caption_it` | Italian caption |
| `caption_es` | Spanish caption |
| `caption_nl` | Dutch caption |
| `caption_pl` | Polish caption |
| `caption_ru` | Russian caption |
| `caption_zh` | Chinese caption |
| `creator` | Wikidata QID for creator (P170) |
| `copyright` | Wikidata QID for copyright status (P6216) |
| `license` | Wikidata QID for license (P275) |
| `depicts` | Wikidata QID(s) for depicted items (P180), comma-separated |
| `gallery_suffix` | Appended to gallery prefix, e.g. `Berlinale 2025` |

All `key=value` lines are **removed** from the wikitext before upload and sent via the Wikibase API instead.

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

## License

MIT
