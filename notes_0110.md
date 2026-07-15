## Highlights since v0.9.8

### Added
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

## Earlier in this release (0.10.0)

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

