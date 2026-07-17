# Changelog

All notable changes to Cammello are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/).

## [0.11.3] - 2026-07-16

### Added
- **Culling: Home / End** jump to the first / last image, in both loupe and
  grid view.
- **Culling: double-click** on the image toggles fullscreen (same behaviour
  as the F key; the view resets to fit before going fullscreen so the first
  click's zoom-to-100% is not carried in).
- **Culling: `i`** toggles an EXIF info overlay in the top-left of the image
  view — filename, camera, lens, and `focal · aperture · shutter · ISO ·
  captured`. JPEGs are read with Pillow; RAW files with libraw (rawpy), so the
  overlay also works for RAW-only shots. The camera name for RAW additionally
  uses `exifread` when it is installed, and is simply omitted otherwise.

### Changed
- RAW thumbnail extraction runs in parallel across the loader pool again,
  restoring the pre-0.11.1 scan speed. It was temporarily serialized while
  investigating the 0.11.1 crash; that cause was unrelated (pyexiv2 on the
  scan path, removed in 0.11.2), so the serialization — and its speed cost —
  is no longer needed.

### Dependencies
- Added optional `exifread` (pure Python), used only to read the camera name
  from RAW files for the culling EXIF overlay.

## [0.11.2] - 2026-07-16

### Fixed
- **macOS app: Culling / IPTC / FTP tabs no longer disappear.** The pyexiv2
  wheel's bundled `libexiv2.dylib` links against Homebrew libraries
  (inih, brotli, gettext) that were absent on the build runner, so the frozen
  app failed to `dlopen` it and silently disabled every pyexiv2-backed tab.
  The macOS build now runs `brew install exiv2`, which pulls those libraries
  in so PyInstaller bundles them; the app is self-contained without Homebrew.
- **Windows: hard crash (access violation) when opening a folder in the
  Culling tab.** exiv2 could crash the process while reading metadata during a
  folder scan (reproduced on Panasonic `.RW2`, but not limited to it). The
  scan read path no longer calls pyexiv2 at all: rating (`xmp:Rating`) and
  colour label (`xmp:Label`) are parsed as text directly from the XMP of the
  sidecar and JPEG. Writing ratings still uses pyexiv2 (one file, on demand).
- **Portrait photos shown sideways (Windows).** Image orientation is now read
  via Pillow for JPEGs and via libraw (rawpy) for RAW files, so previews are
  displayed upright.

### Added
- **Remove a saved caption language.** ISO codes added through
  "Other (ISO code)…" are persisted in the dropdown; a new
  "Remove saved language…" entry deletes one again. The four default
  languages (en, de, es, fr) cannot be removed. A row still using a removed
  code keeps it (its caption is never lost); the code just stops being
  offered as a default choice.

## [0.11.1] - 2026-07-15

### Added
- **Multi-select editing**: selecting several files no longer disables the
  per-file editor. The anchor row is loaded; a field the user CHANGES is
  applied to every selected file - only that field, each file's other
  fields, categories and free wikitext stay untouched (categories are
  replaced only when the categories field itself was edited). The status
  bar announces the mode ("{n} files selected ...").
- **Caption languages**: the dropdown shows four defaults (en, de, es, fr);
  "Other (ISO code)..." accepts any ISO code, which is validated, selected
  and PERSISTED - the dropdown grows with the codes actually used.
- **Frozen-build diagnostics**: the log's second line now states the
  pyexiv2 status (with the import error when unavailable) and every feature
  flag - a binary that hides tabs now says exactly why.
- **MediaWiki account in the Settings tab**: username and password next to
  the other service credentials (QSettings scope 'Login', shared with the
  login dialog, which is prefilled from it). The password is stored in plain
  text with a warning; leaving it empty keeps the old ask-per-session flow.
- **"Clear base description" button** below the base editor (with
  confirmation); the live sync then updates the wikitext of every row.
- **"Information from caption" button** (captions editor): fills each
  language's Information wikitext with its caption text, but only where that
  Information field is still empty (never overwrites hand-written wikitext).
- **depicts is mandatory**: the upload blocks files that have neither a
  P180 QID (their own or from a depicts= line in the base description) nor
  one of three per-file override checkboxes under the depicts field:
  "No Wikidata item", "Not applicable", "Unidentified" - presented as a
  single dropdown ("If no depicts:") so the full labels stay readable. The
  choice is stored as `depicts_override=` in the file description.
- **WikiPortraits maintenance categories**: when an override is set AND the
  upload sits in a WikiPortraits context (a {{WikiPortraits ...}} template or
  a WikiPortraits (sub)category), the matching category is added at upload
  time: needing Wikidata item / without identifiable person / needing
  identification.
- **Category suggestions** (two "Suggest category" buttons): the per-file
  one derives Commons categories from the depicts QIDs; the base one, next
  to "created during", adds the event category to the BASE description.
  Wikidata P373 first, label as fallback, one wbgetentities call. An event
  without a year in its name gets the year from the Date column appended
  ("Berlinale" + 2026-02-14 -> "Berlinale 2026"). Case-insensitive dedup.
  VERIFY: the live wbgetentities call could not be exercised from the build
  environment (logic is unit-tested against a fake fetch).

### Fixed
- **Multi-select editing now also propagates FREE-TEXT changes** - the
  per-language Information templates ({{en|1=...}}) and expert/extra
  wikitext. The diff was rewritten to work on decomposed FIELDS (captions,
  depicts, override, info:<lang>, extra) instead of key=value lines only,
  so a changed Information or expert-mode text is applied to every selected
  file while each file keeps its own untouched fields.
- **"Not applicable" no longer implies a person**: its stored value was
  `no_person`, named for people only, though the option also covers
  buildings, landscapes etc. The value is now `not_applicable`; existing
  descriptions carrying `no_person` still map to the same maintenance
  category.
- **Binaries were built without the assets** (`--collect-submodules`
  collects modules, not data files): the logo/icon was missing from every
  .app/.exe. The build workflow now bundles `cammello/assets` via
  `--add-data` on all three platforms and ships paramiko explicitly.
- **Application-level stylesheet**: the input/group/About rules moved from
  the main window and per-widget setStyleSheet() calls onto the
  QApplication. Per-widget stylesheets on the collapsible groups kept
  producing captions/description fields with wrong (dark) backgrounds on
  macOS; an application-level sheet reaches every widget unconditionally.
- **About tab is dark by design** now (#16222e with light text and
  inline-colored links) - it hosts the dark logo tile, and its contrast no
  longer depends on the platform's rendering of the color scheme.
- **Application icon** now has rounded corners (macOS-style, radius ~22%).
- **Wikidata fields no longer carry their OWN background color**: the blue
  border alone marks them. The special light-blue background was the last
  field-level color in the app and kept producing wrongly colored fields on
  macOS (a renderer interaction we could not reproduce in CI) - with no
  background/color property of their own, the WD fields now inherit exactly
  what every other input field shows, by construction.
- **Wrongly colored fields (macOS dark mode)**: at construction the LIGHT
  input-style variant was always applied, so scheme='system' on a dark
  desktop mixed light inputs into a dark UI - and the Wikidata fields
  (light-blue) were styled ONCE at build time and never followed the scheme
  at all. The input variant now syncs with the actual palette before any
  styling, the WD fields have a dark variant and are re-styled on every
  scheme switch.
- **The per-file subtitle** is now "Selected file(s) - description" (it
  edits every selected row, not one file).
- **created_during= leaked into the extra-wikitext box**: the key was
  missing from the assignment-line filter, so a base description round-trip
  showed the line as free wikitext.

## [0.10.0] - 2026-07-15

Consolidated development between the 0.9.12 release and the next release.
(Earlier internal version numbers 0.10.0-0.15.0 were collapsed into this one
entry; no release was made from them.)

### Added
- **Merged FTP / Flickr tab**: one shared file list (multi-select) and one
  status area serve both services; the FTP server/upload groups and the
  Flickr account/upload groups sit side by side. The tab title follows the
  enabled features (`FTP / Flickr`, `FTP`, or `Flickr`).
- **Flickr license selection**: a license chosen in the upload group
  (account default, All rights reserved, the CC 2.0 family, CC0, Public
  Domain Mark) is applied per photo via `flickr.photos.licenses.setLicense`
  right after the upload; the choice is persisted.
  VERIFY: license IDs are the documented Flickr table, not re-checked live.
- **Release default**: the IPTC tab is HIDDEN by default; `--enable-tab
  iptc` brings it back (persists). Culling, FTP, Flickr are on.
- **Flickr upload** (new tab + Culling target `-> Flickr`, hidden switch
  `feature_flickr`, independent of pyexiv2). OAuth 1.0a is implemented with
  the standard library and verified against the OAuth-spec example vector in
  `test_flickr.py`; HTTP goes through `requests` - no new dependency. The
  multipart upload body carries ONLY the photo (RFC 5849 and Flickr's legacy
  signing rules then agree on the signature); the title (target filename) is
  set afterwards via `flickr.photos.setMeta`. One-time browser authorization
  with out-of-band verifier; key/secret/token live in QSettings.
  VERIFY: not tested against the live Flickr API from the build environment.
- **FTP tab rebuilt** to mirror the IPTC tab: shared file list on the left
  (multi-select), server settings/actions in a scroll area on the right. The
  upload now follows the SELECTION (nothing selected = all files); with the
  IPTC feature off the button uploads the files as they are.
- **About tab** (logo when `cammello/assets/icon.png` exists, version,
  tagline, links, CC0 license, component list). `main()` sets the window/Dock
  icon from the same file; see `cammello/assets/README.md`.
- **Selection counts everywhere**: Culling status shows `n selected`, the
  IPTC/FTP/Flickr lists show `x of n selected` / `n file(s)` labels (the
  MediaWiki upload button already carried its count).
- **Grid navigation**: Up/Down move one ROW in the culling grid (column
  count read off the actual layout), one image in loupe view.
- **Five UI languages** (English, Deutsch, Español, Français, Italiano),
  chosen in the Settings tab. English is the source language and the
  translation key, so an untranslated string falls back to English instead of
  showing a key. The choice is persisted as `ui_language` and applied at the
  NEXT start (`main()` sets the language before the window is built - live
  retranslation of an already-built window was deliberately not done: it
  would touch the MediaWiki core for cosmetics). First start follows the
  system locale if it is one of the five. Log messages stay English on
  purpose (diagnostic channel). New module `i18n.py` (241 keys, no Qt
  dependency); `test_i18n.py` checks coverage against every literal `tr()`
  in the source, per-language completeness, that every `{placeholder}`
  survives translation (a dropped one would crash `.format()`), and that the
  window builds in all five languages.
- **Culling: three send targets** for the selection (no selection = every
  image passing the filter; RAW+JPEG pairs follow the pair selector):
  *MediaWiki* (the file table, as before), *FTP* (uploads the files as they
  are - no IPTC writing - to the server configured in the FTP tab, with the
  usual progress/cancel dialog), and *Folder…* (copies - never moves - into a
  local folder off the GUI thread; a copied RAW brings its `.xmp` sidecar
  along, the write-behind queue is flushed first so fresh ratings are on
  disk, and existing files in the target folder are never overwritten).
- **Settings duplicated where they are used**: the MediaWiki upload settings,
  the IPTC write settings and the FTP server settings now appear BOTH in
  their functional tab (primary widgets - persistence unchanged) and in the
  Settings tab, as linked mirror widgets that sync bidirectionally
  (`widgets.link_line_edits` & Co.; every sync handler compares before
  setting, so the update chain always terminates).
- **Hidden per-tab switches**: `feature_culling`, `feature_iptc` and
  `feature_ftp` (QSettings booleans, default on, no UI) disable the Culling,
  IPTC and FTP tabs individually, INCLUDING their references elsewhere: the
  Settings-tab mirror sections, the Culling "-> FTP" button (needs FTP), and
  the FTP tab's "Write IPTC + upload all" button (needs IPTC; with IPTC off
  the FTP tab keeps only the server settings, which the Culling target still
  uses). Flip them once from the command line - `--disable-tab ftp` /
  `--enable-tab ftp` (names: `culling`, `iptc`, `ftp`) - the choice is
  persisted and the app starts normally. pyexiv2 remains the hard gate for
  all three. The IPTC/FTP settings persistence was split accordingly
  (`_iptc_save/load_settings` vs. `_ftp_save/load_settings`), so each part
  only touches widgets of a tab that was actually built.
- The progress dialog takes an optional verb/title (defaults unchanged), so
  the culling folder export can say "Copying" instead of "Uploading".
- **IPTC module** (new tab, strictly additive): reads/edits 12 IPTC fields per
  file (shared file list with the Files tab), "Fill from MediaWiki data"
  (captions, categories -> keywords, author, date, target filename - QIDs are
  deliberately not resolved), "Caption -> Wikitext as <lang>", writing to
  copies in an export folder (default) or into the originals (opt-in); empty
  fields delete the tag, foreign IPTC tags are left alone, the envelope is
  marked UTF-8.
- **FTP tab**: agency upload via FTP / FTPS / SFTP with progress dialog and
  cancel; own status area. Password asked per session; storing it is opt-in
  and PLAIN TEXT. Files, IPTC data and write settings come from the IPTC tab.
- **Culling tab** (Photo Mechanic replacement, phase 1): folder scan with
  case-insensitive RAW+JPEG pairing, preview pipeline on the embedded
  full-resolution camera JPEG (scaled decode inside the decoder, visible-range
  lazy thumbnails, two-level LRU cache, browsing-direction prefetch,
  full-level for 100% zoom), ratings 0-5 / reject / color labels as standard
  XMP (sidecars for RAWs - never touched -, embedded for JPEGs, pairs get
  both; Lightroom sidecars amended, not replaced; in-camera ratings read),
  localized label sets (de/en, matched across languages on read), coalescing
  write-behind queue, filters (min stars, rejects), grid view (G), image-only
  fullscreen (F/Esc) with a bottom-right overlay showing stars and the label
  color, continuous zoom (slider + Cmd/Ctrl +/-), E = standard view,
  multi-selection (rating keys apply to all selected), "Selection -> file
  table" and drag-and-drop onto the Files tab (tab bar switches on hover),
  discreet color marking as a bottom bar in filmstrip/grid cells.
- **Settings tab**: EVERYTHING configurable in one place, saved on close -
  the MediaWiki upload settings (moved out of the Files tab), the IPTC write
  settings, the FTP server, and the culling preferences (auto-advance after
  rating, color label set, RAW+JPEG pair handling). The tab exists regardless
  of pyexiv2; feature sections appear only when available.
- Culling: the zoom has a value display ('Fit' or the percentage), the
  slider snaps at 100% and ranges from the Fill scale of the current image up
  to 200%.
- Appearance: a color scheme selector (system / light / dark) in the Settings
  tab, applied app-wide via a Fusion palette and persisted; the system
  palette is snapshotted once per application. The dropdown POPUP of combo
  boxes is now styled explicitly (the forced-light combo showed the system's
  light text on dark systems - unreadable), and combos size themselves to
  their contents (a stylesheet disables the native width logic on macOS).
- Culling selection marking, scheme-aware and as FRAMES (the thumbnail
  itself stays untouched): selected images carry a medium-gray frame in the
  filmstrip AND the grid; the current image carries a white frame on the dark
  scheme / a black frame on the light scheme (drawn inside the selection
  frame when both apply). The MediaWiki upload settings section arrives
  collapsed in the Settings tab.
- Zoom: the slider was replaced by +/- buttons with a percent display and a
  ladder of 12 roughly proportional, mental-arithmetic-friendly steps
  (5, 10, 15, 25, 33, 50, 67, 100, 150, 200, 300, 400%); Cmd/Ctrl +/- walk
  the same ladder. Combo boxes reserve room for the drop-down indicator (the
  widest entry was clipped).
- The scheme switch is applied for real now: the input stylesheet has a dark
  variant that is re-applied on switch (fields were hardwired light), dialogs
  pick the active variant, and the whole widget tree is repolished after a
  palette/style change.
- Grid/fullscreen transitions: F from the grid leaves the grid and goes
  fullscreen (used to silently do nothing), G from fullscreen leaves
  fullscreen into the grid; returning from fullscreen rescrolls the strip to
  the current image. Selection/current frames are 5 px wide; the label color
  bar sits inset past both frames (under the stars) so it is never covered.
- The files-table header shows a split cursor on draggable column edges (an
  explicit filter - not reliable natively with app-level stylesheets on
  macOS). Settings fields have content-appropriate widths: the column is
  capped at 720 px, QID fields at 180 px, the FTP port at 90 px.
- The Files and FTP tabs were not clickable: the tab-bar drag switcher was
  accidentally a QWidget - an invisible child widget of default size sitting
  on top of the leftmost tabs and swallowing their clicks. It is a QObject
  now; a test clicks every tab.
- Tab order: Culling is now the first tab (most-used in a shoot workflow).
  Upload settings are shown in the MediaWiki tab (where they are used), FTP
  server settings in the FTP tab, and IPTC write settings in the IPTC tab.
  The Settings tab keeps Appearance and Culling preferences.
- The "Files" tab is called "MediaWiki" now (it holds the Commons workflow;
  the name also distinguishes it from the IPTC/FTP side).
- Culling cells: the delegate draws the whole bottom area itself - the file
  name line (with [P] = RAW+JPEG pair / [T] = already in the file table,
  both explained in a tooltip), and below it ONE band shared 50/50: stars on
  the left, the color bar on the right. Item text is empty; nothing can
  collide with anything anymore.
- The thumbnail column of the MediaWiki table is draggable between 1x and 2x
  (156-312 px); the icon size follows the column width, and the source
  pixmaps are rendered at 2x so the enlarged view does not blur.
- The IPTC file list shows thumbnail + name per row (matching the MediaWiki
  tab) and COPIES the icons from the main table - zero decoding, which also
  removes the delay when opening the tab.
- Filmstrip: the color bar covered the stars (both fought for the same
  pixels of the 140-px cell as item text). The delegate now draws the stars
  line and the color bar itself in a controlled bottom band - stars above,
  bar below, both inside the frames; cells are slightly taller.
- Two crash drivers in the scheme switch removed: QApplication.setStyle is
  only called when the style actually differs (it destroys the previous
  QStyle app-wide - reliable segfault when applied per window construction),
  and the repolish pass runs only on a user-triggered switch, never during
  window construction.
- New OPTIONAL dependencies: pyexiv2 (without it the IPTC/FTP/Culling/Settings
  tabs are hidden, the MediaWiki side is unaffected), paramiko (SFTP only),
  rawpy (RAW previews only). macOS: the pyexiv2 wheel links against Homebrew
  libraries - `brew install exiv2` (see README).
- CI: Node-24 actions, offscreen test suite as a required stage before the
  builds, --collect-all for pyexiv2/rawpy, workflow_dispatch takes the target
  tag as input.
- New test suites: test_merge, test_iptc, test_culling, test_cullview;
  test_imports auto-discovers the package modules.

### Security
- **FTPS now verifies server certificates**: `ftplib.FTP_TLS`'s default
  context performs NO certificate verification; the client now uses
  `ssl.create_default_context()` (verification + hostname check).
- **SFTP now verifies the server host key** against `~/.ssh/known_hosts`
  instead of trusting whatever answers (MITM protection). Unknown or
  mismatching keys are rejected with an instructive message; add a new host
  once via the `sftp`/`ssh` command line.

### Fixed
- **Combo boxes were stretched to the full form column** (a 440 px wide
  dropdown for "ftp"): short-content combos are capped now (protocol 110 px
  incl. its mirror, color scheme 130, language 140, culling combos 110/150).
- **The IPTC language dropdown clipped its two letters**: a fixed 60 px
  collided with the 24 px the stylesheet reserves for the drop-down
  indicator; it has a minimum width now instead of a fixed one.
- **The MediaWiki upload settings were invisible in BOTH tabs**: the group
  was detached from the Files tab for the "everything in the Settings tab"
  move but never added to the Settings tab either (an orphaned widget). It
  now lives in the MediaWiki tab again (attribute names unchanged) and is
  mirrored into the Settings tab.
- **Wikidata suggestion dropdowns unreadable on the dark scheme**: the
  completer popup is a TOP-LEVEL QListView, so neither the window stylesheet
  nor the repolish pass of a scheme switch reaches it - it kept the platform
  default background under the dark palette's light text. The popup now gets
  explicit scheme-matched colors, refreshed right before every show, so a
  runtime scheme switch is picked up. (VERIFY on macOS: this was the one
  remaining unstyled dropdown class; if the plain combo popups still look
  wrong there, that is a separate issue - a screenshot would help.)
- The upload settings (creator/copyright/license) never reached Commons (the
  worker's base_text argument was assigned and never read); preview and upload
  now share merge_descriptions() as the single source of truth, with agreed
  merge rules (depicts merged; captions and single-QID keys: file overrides
  base; gallery_suffix base-only) and log warnings for overridden values.
- A permissiondenied from wbeditentity now explains the missing bot-password
  grant ("Edit existing pages").
- The Wikitext column is drag-resizable (was a Stretch section); the IPTC tab
  scrolls instead of squeezing field rows; batch adds to the file table no
  longer freeze the GUI (row-height relayout suspended during the batch);
  thumbnail decode no longer decodes full resolution; browsing no longer
  alters the selection.

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
