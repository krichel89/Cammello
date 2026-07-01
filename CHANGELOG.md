# Changelog

All notable changes to Cammello are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.7.4] - 2026-07-02

### Fixed
- Dragging several files onto the table at once loaded only a single file.
  The `viewport().setAcceptDrops()` call introduced in 0.7.3 let Qt's
  built-in item-view drop handling intercept the drop and collapse it to one
  item. The drop-receiving configuration is restored to the 0.7.2 behaviour
  (widget-level `setAcceptDrops` only); the defensive per-file filtering from
  0.7.3 is kept, so a mixed drop of valid and invalid files adds every valid
  file and skips the rest.

## [0.7.3] - 2026-07-02

### Changed
- Creator (P170), Copyright (P6216) and License (P275) moved out of the base
  description into dedicated fields in the "Upload settings" section,
  positioned next to their `{{Information}}` counterparts. Copyright defaults
  to Q73566113, license to Q18199165. The license field is a plain text
  input again (the 0.7.2 dropdown is gone).
- All Wikidata QID fields (creator, copyright, license, depicts,
  created-during) have a light-blue background and a validator that only
  accepts `Q` followed by digits; depicts accepts a semicolon-separated
  list. The grey example labels next to each field are gone.
- On first start with an older profile, `creator=`, `copyright=` and
  `license=` lines are migrated from the saved base description into the new
  upload-settings fields.

### Fixed
- Drag-and-drop no longer breaks when the drop contains a mix of supported
  and unsupported files. Each URL and each file is processed independently:
  unsupported entries, non-existent paths and per-file errors are logged and
  skipped so the rest of the drop still succeeds.

## [0.7.2] - 2026-07-01

### Changed
- Creator (P170), Copyright (P6216), License (P275) and Created during
  (P10408) are shown only in the base editor. They apply to every file in
  the batch; the per-file editor keeps only captions, depicts, categories
  and free-text wikitext.
- Copyright (Q73566113) and license (Q18199165) are preset in the base
  editor instead of appearing as empty example placeholders.
- License is an editable dropdown offering the two most common choices —
  Cc-by-sa-4.0 (Q18199165) and Cc-zero (Q6938433). Any other QID can still
  be typed in.

### Added
- Drag-and-drop of one or many image files onto the file table. Dropping a
  folder adds the image files directly inside it (non-recursive).

## [0.7.1] - 2026-07-01

### Added
- Structured field "Created during (P10408)" for the event a file was
  produced during (e.g. Q124692383, 81st Venice International Film
  Festival).

### Changed
- Single-value Wikidata QID fields (creator, copyright, license, created
  during) use a fixed standard width instead of stretching across the panel.

## [0.7.0] - 2026-07-01

### Changed
- The mode toggle is now "Expert mode" (raw `description_all` text),
  disabled by default. What used to be "Beginner mode" is the standard
  structured editor.
- Multi-value separator for `depicts` and categories is now `;`; `,` is
  still tolerated when reading older data.
- The gallery-suffix field lives on the base editor only; the per-file
  editor drops it.
- The extra-wikitext box starts at two lines and can be drag-resized.
- Copyright (Q73566113) and license (Q18199165) are preset in the base via
  the default base text. Each Wikidata field carries an explanatory hint
  next to it (e.g. `Q73566113 (CC-licensed)`, `e.g. Q640 (Harald Krichel)`).
- Example placeholders now consistently use Harald Krichel / Q640.

### Added
- Dedicated "Categories" field in the structured editor
  (semicolon-separated, without the `[[Category:]]` wrapper).
- Import/export of settings to a plain text file, optionally including the
  currently selected file's description.

## [0.6.0]

### Added
- Beginner mode with structured single-line fields for both the per-file
  and the base description; multilingual captions via a language dropdown
  with "Add language".
- Right panel scrolls so input fields are never compressed; extra-wikitext
  box is multi-line and accepts `#` comment lines (stripped at upload).
- Copyright (Q73566113) and License (Q18199165) default into the base
  section.
- Login dialog: API URL hidden, with a link to Special:BotPasswords and the
  list of required grants.

## [0.5.1]

### Added
- BotPassword-first login, session verification, automatic re-login.
- Automatic maintenance category on uploaded files.
- Saved settings and base description across sessions.

### Fixed
- EXIF capture-date reading.
- Validation warnings for common description typos.

## [0.5.0]

### Changed
- Renamed from CommonsSDC to Cammello.
- Fully English user interface, comments and log messages.
