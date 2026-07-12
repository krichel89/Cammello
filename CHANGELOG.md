# Changelog

All notable changes to Cammello are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.9.12] - 2026-07-12

### Fixed
- The upload settings (creator, copyright, license) never reached Commons:
  start_upload() put them into a base_text argument that UploadWorker assigned
  and never read, while row['description_all'] was built without them. P170,
  P6216 and P275 were therefore never written - although the preview column
  showed them, because the preview assembled its text differently. Preview and
  upload now both go through merge_descriptions(), so what the Wikitext column
  shows is what gets uploaded. The dead base_text argument is gone.
- Base and per-file description are merged by rule instead of being
  concatenated and re-parsed (where extract_structured_data() took the FIRST
  occurrence for creator/copyright/license/depicts/created_during/
  gallery_suffix - the base silently won - but the LAST one for caption_XX -
  there the file won):
  * depicts: base and file merged, duplicates removed, order kept
  * caption_XX, creator, copyright, license, created_during: the file overrides
    the base (not merged: these are written as a single QID per property)
  * gallery_suffix: base only; a per-file value is ignored
  * free wikitext: base first, then the file
  Overridden or dropped values are written to the log as warnings.
- A permissiondenied error from wbeditentity now says what it usually means:
  the bot password is missing the "Edit existing pages" grant. The upload
  itself only needs an upload grant, which is why the file goes up and only
  the structured data is refused.
- A file that was uploaded but whose structured data (or gallery entry) could
  not be written was reported as a failure: the summary said "Done: 0/1
  file(s) uploaded" although the file was on Commons. Upload and
  post-processing now have separate error handlers. The upload counts as soon
  as the file is on Commons; a failure afterwards is flagged in the row status
  ("Uploaded (SDC failed)"), in the message ("Uploaded, but structured data
  failed: ...") and in the summary ("1 of them without structured data").
- The progress window did not close when the upload finished. QDialog.close()
  raises a close event, which QDialog answers by calling reject() - and
  reject() was overridden in 0.9.11 to mean "cancel", so it swallowed the
  close. There is now an explicit force_close(); Esc and the window's close
  box still mean "cancel".
- Cancelling a run whose last file is already in flight can no longer finish
  with a bare "Done": the summary says the cancel arrived too late.

## [0.9.11] - 2026-07-11

### Added
- A progress window appears when an upload run starts: "Uploading 3 of 12
  file(s)", the name of the file currently going up, a progress bar counting
  finished files, and a Cancel button.
- Cancel. The file currently in flight is finished first, then the run stops,
  so no file is left half-uploaded on Commons. Files already uploaded are still
  added to the gallery page. The summary reports what happened ("Cancelled:
  3/12 file(s) uploaded, 9 not started."). Esc routes into Cancel instead of
  closing the window behind a running upload.

### Changed
- The tab formerly called "Upload" is now called "Files" - it holds the file
  table, it does not start an upload. Emojis removed from both tab labels.

## [0.9.10] - 2026-07-11

### Changed
- The Upload button now acts on the **selected** rows; if no row is selected it
  uploads all of them (as before). The button label follows the selection
  ("Upload selected (3)" / "Upload all (12)"), and the QID check only inspects
  the rows that are actually going to be uploaded, so an invalid QID in an
  unrelated row no longer blocks the upload.

### Fixed
- The worker's row index is mapped back to the table row (`upload_row_map`).
  Without it, uploading a selection would have written status messages into
  the wrong rows.
- The early exits in `start_upload()` (not logged in / no files / invalid QIDs)
  now write a line to the log. They only raised a message box before, so an
  Upload button that appeared to do nothing left no trace in the Log tab.

## [0.9.9] - 2026-07-11

### Fixed
- Login was broken since the package split: `widgets.py` used `QSettings` in
  `LoginDialog.__init__` without importing it, so clicking Login raised
  `NameError: name 'QSettings' is not defined` and no dialog ever appeared.
- Same class of bug, found by an AST scan of all modules and fixed before it
  could surface: `workers.py` used `MediaWikiApi` without importing it (the
  login would have failed again right after the dialog), and `api.py` used
  `os` (in `upload()`) and `extract_name_from_caption` (in the gallery page
  update) without importing either. In the pre-0.9.0 monolith these names were
  module-level globals and visible everywhere; the split did not carry them
  over. Uploads could not have worked in 0.9.x.
- New static test (`test_imports.py`) walks the AST of every module and fails
  if any global name does not resolve in that module's namespace, so this bug
  class cannot come back unnoticed. `test_login.py` exercises the full chain
  LoginDialog -> LoginWorker -> MediaWikiApi.

## [0.9.8] - 2026-07-11

### Changed
- The preview thumbnails in the file table are 50% larger (icons 96x64 ->
  144x96 px, thumbnail column 104 -> 156 px, default row height 70 -> 105 px).
- The "Description" column (the effective wikitext of a file) is now called
  "Wikitext" and is noticeably wider: its neighbours were narrowed (source
  file 250 -> 180 px, target filename 240 -> 200 px, status 150 -> 110 px)
  and the splitter gives the table more room (720:420 -> 880:400). All three
  columns stay interactive and can be resized by hand.
- The Wikitext column no longer grows a row without limit. A new
  CappedRowHeightDelegate limits it to 12 text lines (WIKITEXT_MAX_LINES in
  constants.py); longer text is clipped in the cell but remains complete in
  the cell tooltip.

## [0.9.7] - 2026-07-10

### Fixed
- Dark mode on macOS made the app unusable: input fields forced a white (or
  light-blue, for Wikidata fields) background but never set an explicit text
  color, so Qt5 used the system's dark-mode text color (light) on top of it,
  producing white-on-white text. All stylesheets that force a light background
  now also force a matching dark text color (#1a1a1a), independent of the
  system theme.

## [0.9.6] - 2026-07-07

### Changed
- The collapsible sections use a simple collapse arrow (down = expanded,
  right = collapsed) in the section title instead of a checkbox.
- All input fields have higher-contrast borders; the per-language Information
  wikitext boxes get the same border as the other fields. The Wikidata fields
  keep their light-blue background and gain the same border.
- Form labels are narrower (fixed width, word-wrapped) and the input fields
  take the remaining width — approximately a 30:70 split. The width cap on
  single-value Wikidata fields was removed so they grow with the form.
- All emojis removed from button and checkbox labels.

## [0.9.5] - 2026-07-07

### Added
- After the structured data of an upload includes depicts (P180), the file page
  is purged via `action=purge` with `forcelinkupdate=1`. A plain purge only
  re-renders the page; only the link-table update refreshes category
  membership, so the file leaves the "missing SDC statements" maintenance
  categories immediately instead of waiting for the next re-parse. Purge
  failures are logged and never abort the upload.

## [0.9.4] - 2026-07-07

### Fixed
- Performance: selecting a row decoded the image at full resolution just to
  show the 300x200 preview (~720 ms per click on a 45 MP JPEG in testing). The
  preview now uses the same scaled QImageReader path as the thumbnails
  (~23 ms, ~30x faster). No functional change.

### Audit notes (0.9.4 review)
- Security review found no dangerous calls (no eval/exec/subprocess/pickle),
  HTTPS-only endpoints, request timeouts everywhere, passwords never persisted
  and masked in logs. Known by design: the debug log contains per-file wikitext,
  and the BotPassword is held in memory for auto-relogin.

## [0.9.3] - 2026-07-03

### Changed
- Internal refactor only (no behaviour change): the large `MainWindow` class was
  split across mixin modules — `mw_settings.py` (settings + log helpers),
  `mw_files.py` (login + file table), `mw_editor.py` (row/editor sync, effective
  column, bulk edit) and `mw_upload.py` (upload + validation). `main_window.py`
  keeps `__init__`, the UI builders and `main()`, and `MainWindow` now inherits
  the mixins. `main_window.py` shrank from ~1280 to ~400 lines.

## [0.9.2] - 2026-07-03

### Changed
- Internal refactor only (no behaviour change): the single ~3300-line
  `Cammello.py` was split into a `cammello/` package (constants, logging_setup,
  sdc, exif, api, workers, wikidata, widgets, editors, main_window). `Cammello.py`
  remains as a thin backward-compatible entry point that re-exports the package,
  so `python Cammello.py` and the PyInstaller build keep working. The duplicate
  `IMAGE_EXTS` definition was consolidated into the single ordered tuple in
  `constants.py`.

## [0.9.1] - 2026-07-03

### Added
- The "Upload settings", "Base description" and "Selected file" sections are
  collapsible: click the checkbox in the section title to fold/unfold them.

### Changed
- The per-language Information wikitext field is now a wide (~90% of the row),
  right-aligned, height-resizable multi-line box (drag the grip beneath it).
- Depicts (P180) removed from the base description; it is per-file only. An
  existing `depicts=` in a base description is dropped.

## [0.9.0] - 2026-07-03

### Added
- Each language row in the structured editor has a second field for the
  Information-template wikitext of that language, uploaded as `{{lang|1=…}}`
  (e.g. `{{de|1=…}}`). Existing simple `{{lang|1=…}}` lines in a description are
  loaded into the field automatically; bulk caption edits keep the information
  wikitext intact.

### Note
- Templates whose value contains a nested template (e.g.
  `{{en|1=With {{other}} inside}}`) are intentionally not extracted and remain
  in the extra text unchanged.

## [0.8.8] - 2026-07-03

### Fixed
- Performance: typing in the base description or the upload-settings QID fields
  refreshed every table row on every keystroke (~1.3 s per keystroke at 200
  rows). The Description-column refresh is now debounced (one refresh 250 ms
  after typing stops), skips unchanged cells and batches the repaint; keystroke
  latency at 200 rows is ~3 ms. Upload correctness is unaffected (upload reads
  the underlying data, not the display column).

## [0.8.7] - 2026-07-02

### Changed
- The table shows a single "Description" column containing the combined
  effective text (base + file). The separate per-file description column is
  hidden but kept internally as the editable data store (the side editor writes
  to it and upload reads it). Long entries wrap, rows grow to show the full
  text, and the full text is also shown as a tooltip.

## [0.8.6] - 2026-07-02

### Added
- New read-only table column "Effective (base + file)" that shows, per row, the
  combined description as it will be uploaded: creator/copyright/license (from
  Upload settings) + the base description + the per-file description. It updates
  live when any of those change, making the effect of the base description on
  each file visible in the table.

## [0.8.5] - 2026-07-02

### Changed
- The three section headings (Upload settings, Base description, Selected file)
  are highlighted with a bold, colored title badge.

## [0.8.4] - 2026-07-02

### Fixed
- The per-file editor writes to the table's Description column live on every
  edit again (as before 0.8.2). The 0.8.2 "update on field switch only"
  trigger depended on GUI focus events (editingFinished / focus-out) that did
  not fire reliably in every environment, which could make edits appear not to
  be saved. Live sync uses textChanged and does not depend on focus events.
  The robust item-based commit target from 0.8.3 is kept, so edits still land
  on the correct file after sorting or row removal.

## [0.8.3] - 2026-07-02

### Fixed
- Per-file edits could be written to the wrong row (or appear to go missing)
  after the table was sorted or a row was removed, because the editor tracked a
  fixed row number that then pointed at a different file. The editor is now
  bound to the file's table item, so a commit always targets the correct file
  regardless of sorting or removal; a removed item is detected and skipped.
  The description is committed to the table on field switch and on row change.

## [0.8.2] - 2026-07-02

### Changed
- The per-file editor writes its changes into the table's Description column on
  field switch (a field losing focus / editing finished) rather than on every
  keystroke. Row switching, expert-mode toggle, upload start, bulk edit and
  save-to-file each flush the current edit first, so no edit is lost.

## [0.8.1] - 2026-07-02

### Changed
- The Wikidata suggestion list is larger and more readable: bigger font, wider
  popup and more visible rows.

### Note
- No change was needed for the maintenance category — every upload already
  adds `[[Category:Uploaded with Cammello]]` (present since the early
  "automatic maintenance category" feature). This was verified, not added.

## [0.8.0] - 2026-07-02

### Added
- Wikidata name search on the Creator, Depicts and Created-during fields: type
  a name (e.g. "Harald Krichel") to get a live suggestion list showing label,
  description and QID (Wikidata `wbsearchentities` API). Selecting an entry
  inserts the QID; for the multi-value Depicts field only the current token is
  replaced. These fields now accept free text while typing.
- Pre-upload validation: before uploading, all Wikidata fields (creator,
  copyright, license, depicts, created-during — in the upload settings, the
  base description and every per-file description) are checked to contain valid
  QIDs. If not, the upload is blocked with a list of the offending fields.
- Bulk edit: select several rows (Ctrl/Shift-click) and set one field for all
  of them at once via a dialog — Depicts (with Wikidata search), Categories,
  Caption (en/de) or Date. An empty value clears the field.

### Changed
- The strict "Q + digits only" validator is kept on the Copyright and License
  fields but removed from the now-searchable Creator, Depicts and
  Created-during fields (they are validated before upload instead).

### Note
- The live Wikidata search requires network access to www.wikidata.org.

## [0.7.5] - 2026-07-02

### Added
- Duplicate check when adding files: a file already in the table (matched by
  its normalized absolute source path) is skipped rather than added a second
  time. Works for both drag-and-drop and the file dialog; the status bar
  reports the number of duplicates skipped.
- The file table is sortable by clicking a column header (e.g. "Source file"
  or "Target filename"). Sorting is temporarily disabled while files are being
  inserted so rows are not reshuffled while only partially populated.

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
