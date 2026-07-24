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
    from PIL import Image
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
    if crop is None and ev == 0.0:
        return None
    out = {}
    if crop is not None:
        out['crop'] = list(crop)
    if ev != 0.0:
        out['ev'] = ev
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


def clear_edit(edits, path):
    """Remove all edits for a path. Returns True if there was one."""
    key = norm(path)
    if key in edits:
        del edits[key]
        return True
    return False


def _update(edits, path, crop=None, ev=None):
    key = norm(path)
    rec = dict(edits.get(key) or {})
    if crop is not None:
        _tag, value = crop
        if value is None:
            rec.pop('crop', None)
        else:
            rec['crop'] = list(value)
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

    try:
        if _is_raw(path):
            img = _render_raw(path, ev, log)
            # EV already applied in the raw domain when possible; _render_raw
            # tells us via the returned flag.
            img, ev_done = img
            if img is None:
                return None
            if not ev_done and ev != 0.0:
                img = _apply_ev_image(img, ev)
        else:
            img = Image.open(path)
            exif = img.info.get('exif')
            img = _apply_crop_image(img, crop)
            img = _apply_ev_image(img, ev)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')
            save_kwargs = {'quality': 95}
            if exif:
                save_kwargs['exif'] = exif
            img.save(out_path, 'JPEG', **save_kwargs)
            return out_path

        # RAW path continues here (crop happens after the raw render).
        img = _apply_crop_image(img, crop)
        if img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        img.save(out_path, 'JPEG', quality=95)
        return out_path
    except Exception as e:
        if log:
            log.warning('Could not render edited copy of %s: %s', path, e)
        return None


def _render_raw(path, ev, log=None):
    """-> (PIL image, ev_applied_bool). Uses rawpy when present; falls back
    to the embedded preview via Pillow if rawpy is missing."""
    if HAS_RAWPY:
        try:
            with rawpy.imread(path) as raw:
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
            return Image.fromarray(rgb), ev_done
        except Exception as e:
            if log:
                log.debug('rawpy render failed for %s: %s', path, e)
    # Fallback: the embedded preview (no EV in the raw domain).
    try:
        return Image.open(path), False
    except Exception:
        return None, False


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
