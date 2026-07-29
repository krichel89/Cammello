"""Non-destructive per-image edits (0.13): crop and exposure correction.

The design mirrors channels.py: one JSON object in QSettings, keyed by the
normalized absolute path, defensive against corrupt or future data, and with
NO Qt import so the logic is testable on its own. The QSettings object is
passed in by the caller.

An edit record is:
    {'crop': (x, y, w, h) | None,   # normalized 0..1, fraction of the image
     'ev':   float}                 # -3.0 .. +3.0 exposure stops, 0 = none

Nothing here touches the source file. Edits are applied only when a file
LEAVES Cammello - Commons upload, FTP, Flickr, or a culling folder export -
by rendering an edited copy to a temporary path and handing THAT to the
uploader. effective_upload_path() is the single entry point the upload
paths call; render_edited() does the pixel work.

Crop is stored in normalized coordinates on purpose: it stays correct
whether it is later applied to the full-size RAW render or to an embedded
preview of a different pixel size.
"""
import json
import os

try:
    from PIL import Image, ImageOps
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# rawpy is optional; only needed to render RAW originals with an EV change.
try:
    import rawpy
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False

_SETTINGS_KEY = 'edits'

EV_MIN = -3.0
EV_MAX = 3.0
# Harald works in sixths of a stop (0.14) - finer than the third-stop steps
# a camera dial offers, which is the point of correcting on screen.
EV_STEP = 1.0 / 6.0

# White balance is stored as per-channel gains with green pinned to 1.0, so
# the value is independent of how it was picked and can be applied to any
# rendering of the same file.
WB_MIN = 0.2
WB_MAX = 5.0

# Suffix for rendered copies in a folder export (Harald, 0.13: the export
# gets the edited copy, not the original).
EDIT_SUFFIX = '_edit'

RAW_EXTENSIONS = {'.cr2', '.cr3', '.nef', '.arw', '.dng', '.raf', '.rw2',
                  '.orf', '.pef', '.srw', '.raw'}


def norm(path):
    """Normalized absolute path used as the edit key (matches channels.norm
    and MWFilesMixin._norm_path)."""
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _clamp_ev(value):
    try:
        ev = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(EV_MIN, min(EV_MAX, ev))


def _valid_wb(wb):
    """Three positive gains in a sane range, green normalized to 1.0.
    Anything else -> None, so a hand-edited or future value cannot break the
    renderer. Neutral gains are not an edit."""
    if wb is None:
        return None
    try:
        r, g, b = (float(v) for v in wb)
    except (TypeError, ValueError):
        return None
    if g <= 0:
        return None
    r, b = r / g, b / g
    if not (WB_MIN <= r <= WB_MAX) or not (WB_MIN <= b <= WB_MAX):
        return None
    if abs(r - 1.0) < 1e-4 and abs(b - 1.0) < 1e-4:
        return None
    return (r, 1.0, b)


def _srgb_to_linear(value):
    """One 0-255 channel value as linear light (0..1)."""
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def wb_from_neutral(r, g, b):
    """Gains that turn the sampled pixel (0-255 each) into a neutral grey.

    Computed in LINEAR light, because that is where the gains are applied -
    deriving them from the encoded values would leave a visible part of the
    cast behind. Green is the reference (it carries most of the luminance
    and is the least noisy), so green stays at 1.0 and only red and blue
    move. Returns None for a pixel too dark to judge, where the gains would
    only amplify sensor noise.
    """
    if min(r, g, b) < 8 or g <= 0:
        return None
    r_lin, g_lin, b_lin = (_srgb_to_linear(v) for v in (r, g, b))
    if r_lin <= 0 or b_lin <= 0:
        return None
    return _valid_wb((g_lin / r_lin, 1.0, g_lin / b_lin))


def _valid_crop(crop):
    """A crop must be four numbers in 0..1 with a positive, in-bounds box.
    Anything else -> None, so a manual edit or a future format cannot crash
    the renderer."""
    if crop is None:
        return None
    try:
        x, y, w, h = (float(v) for v in crop)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    if x < 0 or y < 0 or x + w > 1.0001 or y + h > 1.0001:
        return None
    # A full-frame crop is not a crop.
    if x <= 0 and y <= 0 and w >= 1 and h >= 1:
        return None
    return (x, y, min(w, 1.0 - x), min(h, 1.0 - y))


def _normalize_record(rec):
    """A stored record, cleaned. Returns None when it carries no real edit,
    so empty records never accumulate in the settings."""
    if not isinstance(rec, dict):
        return None
    crop = _valid_crop(rec.get('crop'))
    ev = _clamp_ev(rec.get('ev', 0.0))
    wb = _valid_wb(rec.get('wb'))
    if crop is None and ev == 0.0 and wb is None:
        return None
    out = {}
    if crop is not None:
        out['crop'] = list(crop)
    if ev != 0.0:
        out['ev'] = ev
    if wb is not None:
        out['wb'] = list(wb)
    return out


def load_edits(settings):
    """-> {normalized_path: record} from QSettings; unusable entries dropped
    rather than raising."""
    raw = settings.value(_SETTINGS_KEY, '') or ''
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    for k, v in data.items():
        rec = _normalize_record(v)
        if rec is not None:
            out[str(k)] = rec
    return out


def save_edits(settings, edits):
    settings.setValue(_SETTINGS_KEY, json.dumps(edits, ensure_ascii=False))
    settings.sync()


def get_edit(edits, path):
    """The record for one path, or None."""
    return edits.get(norm(path))


def set_crop(edits, path, crop):
    """Set (or, with crop=None, clear) the crop for a path, in place.
    Returns True if anything changed. An edit that ends up empty is removed
    entirely."""
    return _update(edits, path, crop=('set', _valid_crop(crop)))


def set_ev(edits, path, ev):
    """Set the EV for a path, in place. ev=0 clears it. Returns True on
    change."""
    return _update(edits, path, ev=('set', _clamp_ev(ev)))


def set_wb(edits, path, wb):
    """Set (or, with wb=None, clear) the white balance gains. -> True on
    change."""
    return _update(edits, path, wb=('set', _valid_wb(wb)))


def get_ev(edits, path):
    rec = get_edit(edits, path)
    return rec.get('ev', 0.0) if rec else 0.0


def get_wb(edits, path):
    rec = get_edit(edits, path)
    return tuple(rec['wb']) if rec and 'wb' in rec else None


def clear_edit(edits, path):
    """Remove all edits for a path. Returns True if there was one."""
    key = norm(path)
    if key in edits:
        del edits[key]
        return True
    return False


def _update(edits, path, crop=None, ev=None, wb=None):
    key = norm(path)
    rec = dict(edits.get(key) or {})
    if crop is not None:
        _tag, value = crop
        if value is None:
            rec.pop('crop', None)
        else:
            rec['crop'] = list(value)
    if wb is not None:
        _tag, value = wb
        if value is None:
            rec.pop('wb', None)
        else:
            rec['wb'] = list(value)
    if ev is not None:
        _tag, value = ev
        if value == 0.0:
            rec.pop('ev', None)
        else:
            rec['ev'] = value
    cleaned = _normalize_record(rec)
    before = edits.get(key)
    if cleaned is None:
        if key in edits:
            del edits[key]
            return True
        return False
    if cleaned != before:
        edits[key] = cleaned
        return True
    return False


def has_edit(edits, path):
    return norm(path) in edits


# ── Rendering ───────────────────────────────────────────────────────────

def _ev_lut(ev):
    """A 256-entry 8-bit lookup table for an exposure change of `ev` stops,
    applied in LINEAR light: decode sRGB -> multiply by 2**ev -> re-encode,
    clipping highlights. Returned as a flat list for PIL's point().

    EV 0 returns the identity table, so callers can apply it unconditionally.
    """
    factor = 2.0 ** ev
    table = []
    for i in range(256):
        c = i / 255.0
        # sRGB decode
        lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        lin *= factor
        lin = 0.0 if lin < 0 else (1.0 if lin > 1 else lin)
        # sRGB encode
        enc = (lin * 12.92 if lin <= 0.0031308
               else 1.055 * (lin ** (1 / 2.4)) - 0.055)
        table.append(max(0, min(255, round(enc * 255))))
    return table


def _apply_ev_image(img, ev):
    """Apply an EV change to a PIL image via the LUT. RGB and greyscale only;
    an alpha channel is preserved untouched."""
    if ev == 0.0:
        return img
    lut = _ev_lut(ev)
    if img.mode in ('RGB',):
        return img.point(lut * 3)
    if img.mode == 'RGBA':
        r, g, b, a = img.split()
        r, g, b = (ch.point(lut) for ch in (r, g, b))
        return Image.merge('RGBA', (r, g, b, a))
    if img.mode == 'L':
        return img.point(lut)
    return img.convert('RGB').point(lut * 3)


def _wb_lut(gain):
    """A 256-entry table for one channel gain, applied in LINEAR light for
    the same reason as the exposure LUT: scaling the encoded values would
    shift the tone curve, not just the colour."""
    table = []
    for i in range(256):
        c = i / 255.0
        lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        lin *= gain
        lin = 0.0 if lin < 0 else (1.0 if lin > 1 else lin)
        enc = (lin * 12.92 if lin <= 0.0031308
               else 1.055 * (lin ** (1 / 2.4)) - 0.055)
        table.append(max(0, min(255, round(enc * 255))))
    return table


def _apply_wb_image(img, wb):
    """Apply per-channel gains. Greyscale has no colour to balance, so it is
    returned untouched."""
    if not wb:
        return img
    r_gain, g_gain, b_gain = wb
    if img.mode == 'L':
        return img
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    luts = [_wb_lut(g) for g in (r_gain, g_gain, b_gain)]
    if img.mode == 'RGBA':
        r, g, b, a = img.split()
        r, g, b = (ch.point(l) for ch, l in zip((r, g, b), luts))
        return Image.merge('RGBA', (r, g, b, a))
    return img.point(luts[0] + luts[1] + luts[2])


def _combined_lut(gain, ev):
    """One 256-entry table for channel gain AND exposure together: decode
    sRGB once, scale by gain*2**ev in linear light, re-encode once. Doing WB
    and EV as ONE pass avoids the second 8-bit quantization that two chained
    LUTs would add (0.14.1)."""
    factor = gain * (2.0 ** ev)
    table = []
    for i in range(256):
        c = i / 255.0
        lin = c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        lin *= factor
        lin = 0.0 if lin < 0 else (1.0 if lin > 1 else lin)
        enc = (lin * 12.92 if lin <= 0.0031308
               else 1.055 * (lin ** (1 / 2.4)) - 0.055)
        table.append(max(0, min(255, round(enc * 255))))
    return table


def _apply_wb_ev_image(img, wb, ev):
    """Apply white balance and exposure in a single LUT pass. Either may be
    absent (wb=None / ev=0.0); with both absent the image is returned as is.
    Greyscale gets exposure only - it has no colour to balance."""
    if not wb and ev == 0.0:
        return img
    if img.mode == 'L' or (img.mode not in ('RGB', 'RGBA') and not wb):
        return _apply_ev_image(img, ev)
    if not wb:
        return _apply_ev_image(img, ev)
    r_gain, g_gain, b_gain = wb
    if img.mode not in ('RGB', 'RGBA'):
        img = img.convert('RGB')
    luts = [_combined_lut(g, ev) for g in (r_gain, g_gain, b_gain)]
    if img.mode == 'RGBA':
        r, g, b, a = img.split()
        r, g, b = (ch.point(l) for ch, l in zip((r, g, b), luts))
        return Image.merge('RGBA', (r, g, b, a))
    return img.point(luts[0] + luts[1] + luts[2])


_ORIENTATION_TAG = 274                  # EXIF 0x0112


def _exif_upright(exif_bytes):
    """EXIF bytes with the orientation tag reset to 1 (upright).

    Rendered copies get their pixels rotated upright (exif_transpose /
    rawpy flip), so a surviving orientation flag would make viewers rotate
    the already-rotated result a second time. Returns the input unchanged
    when it cannot be parsed - a stale flag is still better than dropping
    the camera metadata."""
    if not exif_bytes:
        return exif_bytes
    try:
        exif = Image.Exif()
        exif.load(exif_bytes)
        if exif.get(_ORIENTATION_TAG, 1) != 1:
            exif[_ORIENTATION_TAG] = 1
            return exif.tobytes()
        return exif_bytes
    except Exception:
        return exif_bytes


def _apply_crop_image(img, crop):
    """Crop a PIL image with a normalized (x, y, w, h) box."""
    if crop is None:
        return img
    x, y, w, h = crop
    W, H = img.size
    left = int(round(x * W))
    upper = int(round(y * H))
    right = int(round((x + w) * W))
    lower = int(round((y + h) * H))
    left = max(0, min(left, W - 1))
    upper = max(0, min(upper, H - 1))
    right = max(left + 1, min(right, W))
    lower = max(upper + 1, min(lower, H))
    return img.crop((left, upper, right, lower))


def _is_raw(path):
    return os.path.splitext(path)[1].lower() in RAW_EXTENSIONS


def render_edited(path, record, out_path, log=None):
    """Render an edited copy of `path` to `out_path` (a JPEG). Returns
    out_path on success, or None if nothing could be rendered (the caller
    then uploads the original).

    - JPEG/other Pillow-readable source: open -> crop -> EV -> save q95,
      EXIF passed through so the camera metadata survives.
    - RAW source with an EV change: rawpy postprocess with exp_shift for a
      true raw-domain exposure where the range allows (exp_shift 0.25..8.0 =
      -2..+3 EV); outside that, fall back to the sRGB-domain LUT.
    - RAW source, crop only: crop the embedded preview if one is available,
      else the full postprocessed image.
    """
    if not HAS_PIL:
        return None
    rec = _normalize_record(record)
    if rec is None:
        return None
    crop = tuple(rec['crop']) if 'crop' in rec else None
    ev = rec.get('ev', 0.0)
    wb = tuple(rec['wb']) if 'wb' in rec else None

    try:
        if _is_raw(path):
            # rawpy applies the camera flip during postprocess, so the pixels
            # already match what the culling view showed; the crop box (drawn
            # on that view) applies directly. The embedded-preview fallback
            # goes through the same upright step as the JPEG branch.
            img, ev_done, exif = _render_raw(path, ev, log)
            if img is None:
                return None
        else:
            img = Image.open(path)
            # The culling view shows the image UPRIGHT (previews.py applies
            # the EXIF orientation), and the crop box is normalized against
            # that upright frame. Rotate here too, or a portrait shot gets
            # the box applied to the unrotated axes - the wrong region
            # (0.14.1; reproduced with an orientation-6 test image).
            img = ImageOps.exif_transpose(img)
            exif = img.info.get('exif')
            img = _apply_crop_image(img, crop)
            img = _apply_wb_ev_image(img, wb, ev)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            save_kwargs = {'quality': 95}
            exif = _exif_upright(exif)
            if exif:
                save_kwargs['exif'] = exif
            img.save(out_path, 'JPEG', **save_kwargs)
            return out_path

        # RAW path continues here (crop happens after the raw render).
        img = _apply_crop_image(img, crop)
        img = _apply_wb_ev_image(img, wb, 0.0 if ev_done else ev)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        save_kwargs = {'quality': 95}
        exif = _exif_upright(exif)
        if exif:
            save_kwargs['exif'] = exif
        img.save(out_path, 'JPEG', **save_kwargs)
        return out_path
    except Exception as e:
        if log:
            log.warning('Could not render edited copy of %s: %s', path, e)
        return None


def _render_raw(path, ev, log=None):
    """-> (PIL image, ev_applied_bool, exif_bytes_or_None). Uses rawpy when
    present; falls back to the embedded preview via Pillow if rawpy is
    missing.

    The rawpy render carries no metadata of its own, which used to mean the
    exported edit lost the camera EXIF entirely (date, camera, GPS). The
    embedded preview JPEG usually holds the full camera EXIF, so it is read
    from there (0.14.1); orientation is reset by the caller because the
    rendered pixels are already upright."""
    if HAS_RAWPY:
        try:
            with rawpy.imread(path) as raw:
                exif = _raw_embedded_exif(raw, log)
                kwargs = dict(use_camera_wb=True, no_auto_bright=True,
                              output_bps=8)
                ev_done = False
                if ev != 0.0:
                    shift = 2.0 ** ev
                    if 0.25 <= shift <= 8.0:
                        kwargs['exp_shift'] = shift
                        kwargs['exp_correc'] = True
                        ev_done = True
                rgb = raw.postprocess(**kwargs)
            return Image.fromarray(rgb), ev_done, exif
        except Exception as e:
            if log:
                log.debug('rawpy render failed for %s: %s', path, e)
    # Fallback: the embedded preview (no EV in the raw domain). Rotate it
    # upright so the crop box matches the culling view, like the JPEG branch.
    try:
        img = ImageOps.exif_transpose(Image.open(path))
        return img, False, img.info.get('exif')
    except Exception:
        return None, False, None


def _raw_embedded_exif(raw, log=None):
    """EXIF bytes from an open rawpy file's embedded JPEG preview, or None.
    Bitmap thumbnails carry no EXIF; every failure is non-fatal - the render
    then simply ships without metadata, as before."""
    try:
        thumb = raw.extract_thumb()
        if thumb.format == rawpy.ThumbFormat.JPEG:
            import io
            with Image.open(io.BytesIO(thumb.data)) as t:
                return t.info.get('exif')
    except Exception as e:
        if log:
            log.debug('No EXIF from embedded preview: %s', e)
    return None


def effective_upload_path(path, edits, tmp_dir, log=None):
    """The path an uploader should send for `path`.

    No edit -> the original path, unchanged (zero cost, the common case).
    An edit -> a rendered temp copy in tmp_dir; on any render failure the
    original path is returned, so an upload never silently produces nothing.
    """
    rec = get_edit(edits, path)
    if rec is None:
        return path
    stem = os.path.splitext(os.path.basename(path))[0]
    out_path = os.path.join(tmp_dir, stem + EDIT_SUFFIX + '.jpg')
    rendered = render_edited(path, rec, out_path, log)
    return rendered or path


def export_name(path):
    """The filename an edited copy gets in a folder export: '<stem>_edit.jpg'
    (Harald, 0.13). Unedited files keep their own name - the caller decides
    which to use via has_edit()."""
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem + EDIT_SUFFIX + '.jpg'


# ── Undo (0.15.0) ────────────────────────────────────────────────────────────
# Harald: "Command-Z bzw. CTRL-Z für einen Schritt zurück", scope "nur
# Bildbearbeitung". So this covers crop, exposure and white balance - not
# ratings, not renames, not coordinates. Those have their own consequences
# (a rename touches the file system) and would need their own machinery.
#
# The history stores the record as it was BEFORE a change, together with the
# path it belonged to. Undo therefore restores a whole record rather than
# replaying an inverse operation: with three independent values that is both
# simpler and impossible to get out of step.
UNDO_DEPTH = 50


class EditHistory:
    """Bounded stack of previous edit records. Qt-free on purpose."""

    def __init__(self, depth=UNDO_DEPTH):
        self._depth = max(1, int(depth))
        self._stack = []

    def __len__(self):
        return len(self._stack)

    def clear(self):
        self._stack.clear()

    def push(self, path, record):
        """Remember the state BEFORE a change. `record` may be None, which
        is the honest representation of "this file had no edits yet" - undo
        then removes the edit again instead of leaving a stale one."""
        key = norm(path)
        self._stack.append((key, dict(record) if record else None))
        if len(self._stack) > self._depth:
            del self._stack[0]

    def pop(self):
        """-> (path, record_or_None), or None when there is nothing left."""
        if not self._stack:
            return None
        return self._stack.pop()

    def peek_path(self):
        """Which file the next undo would touch, without consuming it."""
        return self._stack[-1][0] if self._stack else None


def apply_record(edits, path, record):
    """Put a whole record back (undo). Returns True when something changed."""
    key = norm(path)
    before = edits.get(key)
    if record:
        clean = _normalize_record(record)
        if clean is None:
            edits.pop(key, None)
        else:
            edits[key] = clean
    else:
        edits.pop(key, None)
    return edits.get(key) != before
