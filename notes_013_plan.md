# Cammello 0.13 — Plan (prepared 2026-07-18)

Scope agreed with Harald: focus peaking + 100% loupe polish, caption
templates/snippets, contact sheet PDF, crop module, exposure correction
±3 EV. Explicitly OUT of 0.13: card ingest pipeline, RAW histogram/clipping
warnings (postponed).

Order of implementation (dependencies first):

## 1. edits.py — non-destructive per-image edits (foundation for crop + EV)
New module holding a per-path edit record: `{crop: (x, y, w, h) in
normalized 0..1 coords | None, ev: float -3.0..+3.0}`.
- Persisted like channel marks: one JSON dict in QSettings(APP_NAME,
  'Edits'), path-keyed via channels.norm(). Corrupt/unknown → dropped.
- NON-destructive: source files are never touched. Edits are applied when a
  file leaves Cammello (Commons upload, FTP upload, Flickr, folder export)
  by rendering an edited JPEG copy to a temp dir and uploading that.
- Render helper `render_edited(path, edits, out_path)`:
  * JPEG source: Pillow open → crop → EV → save quality 95, EXIF preserved
    (Pillow `exif=` passthrough; IPTC/XMP re-written by the existing
    write_iptc step where applicable).
  * RAW source, EV set: rawpy.postprocess(exp_shift=2**ev, no_auto_bright,
    use_camera_wb) for true raw-domain exposure — exp_shift covers
    0.25..8.0 = -2..+3 EV; below -2 EV fall back to sRGB-domain scaling.
  * RAW source, crop only: crop the embedded full-size JPEG (fast path).
  * EV on JPEG: linearize sRGB → multiply by 2**ev → re-encode gamma, via a
    256-entry LUT (Pillow point()); clip highlights.
- Upload paths call a small `effective_upload_path(path)` that returns the
  original path (no edits) or the rendered temp copy. Wire into
  mw_upload rows, _ftp/_flickr gathering, culling folder export.
- Tests: LUT monotonicity, EV=0 identity, crop box math, QSettings
  round-trip, upload-path substitution.

## 2. Crop UI (culling fullscreen + MW tab)
- New mode in culling_view: key C toggles crop overlay on the current
  image; drag handles + rule-of-thirds grid; aspect presets (free, 3:2,
  4:3, 1:1, 16:9, 5:4) via number keys; Enter commits to edits.py, Esc
  cancels, Shift+C removes crop.
- Visual: darken outside region; live size readout (resulting px).
- The filmstrip/table shows a small ✂ badge on cropped items (decoration
  role), tooltip with target size.

## 3. Exposure correction UI (±3 EV)
- Culling fullscreen: keys +/- adjust in 1/3 EV steps (hold Alt: 1 EV),
  overlay shows "EV +0.7"; 0 resets. Live preview by applying the LUT to
  the displayed QImage (cheap, screen-res only) — the accurate raw-domain
  render happens at export time.
- Slider in a small panel (culling toolbar popover) mirroring the keys.

## 4. Caption templates / snippets with variables
- Template store (QSettings 'Templates'): named snippets for the base
  description, per-file description and IPTC caption fields.
- Variables: {n} (sequence), {date}, {event} (IPTC Event field),
  {persons} (Person shown, "; "-joined), {filename}, {camera} (EXIF).
- UI: a "Templates…" button next to the base-description editor and the
  IPTC caption field → dialog with list (add/rename/delete), preview with
  the current file's values, Apply-to-selection.
- Code replacements Photo-Mechanic-style ("\cannes\" → boilerplate) are a
  stretch goal; plain named templates first.

## 5. Focus peaking + loupe polish
- culling_view: key P toggles peaking overlay on the current image:
  grayscale → 3x3 Laplacian magnitude (numpy, on the screen-level QImage)
  → threshold at ~92nd percentile → red 1px outline composited.
  Numpy is already a transitive dep (rawpy); keep it optional-guarded.
- Loupe: the 100% zoom already exists ('full' cache level). Polish: hold
  Space for a temporary 100% loupe centered on the cursor; release returns
  to fit view. Peaking state survives image changes.

## 6. Contact sheet PDF
- "Contact sheet…" button in culling toolbar: selection (or all filtered)
  → QPdfWriter, A4/Letter, grid presets (4x5 / 3x4 / 2x3), each cell =
  thumb + filename + optional rating stars/label dot + EXIF one-liner;
  header with folder name + date + page numbers.
- Uses PreviewCache thumbs (no extra decoding); renders in a worker with
  progress dialog.

## Versioning & tests
- Each shippable slice bumps the patch version (0.13.0 = edits.py + crop,
  then 0.13.x per feature) per the standing rule.
- All 8 CI tests + a new test_edits.py (pure logic: LUT, crop math,
  settings round-trip) must stay green; ship changed test files.

## Open questions for Harald (answer before/while building)
- Crop + EV output format for RAW originals: upload the rendered JPEG copy
  (obvious for Commons/FTP), but should the culling folder export also get
  the edited copy or the untouched original? (Plan: edited copy, name
  suffix "_edit" — confirm.)
- Contact sheet: which metadata line matters most under each thumb —
  filename only, or filename + date + rating?
- Templates: which target fields first — base description (MW tab), IPTC
  caption, or both from the start?
