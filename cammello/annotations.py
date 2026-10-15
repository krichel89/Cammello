"""Annotations drawn into a picture: arrows, outlines, highlights (0.18.33).

Made for screenshots in tutorials: an arrow at the button, a circle round
the field, a marker over a line of text. Like crop, exposure and white
balance an annotation is NON-DESTRUCTIVE - it is stored in the picture's
edit record (edits.py, key 'notes') and only rendered into pixels when the
file leaves Cammello (upload, folder export).

This module has NO Qt import, so the model and the pixel renderer are
testable on their own. The on-screen painter in culling_view.py uses the
same geometry helpers (arrow_parts, stroke_px, box_stroke), so what the
culling view shows is what the exported copy contains.

A note is a plain dict:
    {'t': 'arrow' | 'ellipse' | 'rect' | 'mark',
     'p': [x1, y1, x2, y2],      # normalized 0..1 on the FULL upright frame
     'c': 'red' | 'yellow' | 'green' | 'blue' | 'white'
          | 'neon_yellow' | 'neon_green' | 'neon_pink' | 'neon_orange'
          | 'neon_blue',
     'w': 0.0035}                # line width, fraction of the long edge
                                 # (optional; older notes have none)
  arrow:   (x1, y1) is the tail, (x2, y2) the tip.
  ellipse, rect: outline of the box; mark: a translucent filled box.
  Boxes are stored with x1 <= x2 and y1 <= y2.

Coordinates are relative to the frame BEFORE any crop, so changing the crop
never moves an annotation; one outside the crop simply is not rendered. The
line width is a fraction of the long edge of that same frame, so a note
looks the same on a small preview and on the full-size render. Each note
carries its OWN width ('w'); changing the pen only affects new notes.
"""
import math

try:
    from PIL import Image, ImageDraw
    HAS_PIL = True
except ImportError:                      # pragma: no cover - Pillow is required
    HAS_PIL = False

TOOLS = ('arrow', 'ellipse', 'rect', 'mark')

# Fixed palette, picked by key in the culling view. Stored by NAME so a
# later change of a shade does not orphan old records.
COLORS = {
    'red': (230, 30, 30),
    'yellow': (255, 214, 0),
    'green': (40, 190, 70),
    'blue': (30, 110, 235),
    'white': (255, 255, 255),
    # Neon shades (0.18.33): fully saturated, for dark screenshots.
    'neon_yellow': (240, 255, 0),
    'neon_green': (57, 255, 20),
    'neon_pink': (255, 16, 240),
    'neon_orange': (255, 110, 0),
    'neon_blue': (0, 229, 255),
}
COLOR_ORDER = ('red', 'yellow', 'green', 'blue', 'white')
NEON_ORDER = ('neon_yellow', 'neon_green', 'neon_pink', 'neon_orange',
              'neon_blue')
DEFAULT_TOOL = 'arrow'
DEFAULT_COLOR = 'red'

MARK_OPACITY = 0.40            # the highlight: text underneath stays legible
STROKE_FRACTION = 0.0035       # of the long edge; notes without own width
WIDTH_MIN = 0.001              # thinnest / thickest pen: 0.1 % .. 10 % of
WIDTH_MAX = 0.10               # the long edge
WIDTH_STEPS = 30               # slider steps 0..30, geometric in between
DEFAULT_WIDTH_STEP = 8         # ~0.34 %: the look of the first version
STROKE_MIN_PX = 2.0
MAX_NOTES = 200                # per picture; a hand-edited file cannot grow it
MIN_ARROW = 0.004              # shortest arrow / box side kept, normalized
MIN_BOX = 0.003
_TILE_LIMIT = 4096             # largest supersampled tile side, in pixels


def width_for_step(step):
    """Pen width (fraction of the long edge) for a slider step. Geometric,
    so each step is the same visible change from hairline to marker."""
    try:
        step = int(step)
    except (TypeError, ValueError):
        step = DEFAULT_WIDTH_STEP
    step = max(0, min(WIDTH_STEPS, step))
    return round(WIDTH_MIN * (WIDTH_MAX / WIDTH_MIN) ** (step / WIDTH_STEPS),
                 5)


def step_for_width(width):
    """The slider step nearest to a pen width."""
    try:
        width = float(width)
    except (TypeError, ValueError):
        return DEFAULT_WIDTH_STEP
    if not width > 0:
        return DEFAULT_WIDTH_STEP
    ratio = math.log(max(WIDTH_MIN, min(WIDTH_MAX, width)) / WIDTH_MIN)
    return int(round(WIDTH_STEPS * ratio / math.log(WIDTH_MAX / WIDTH_MIN)))


def next_neon(colour, step=1):
    """N cycles the neon shades: the next one after `colour`, or the first
    when `colour` is not a neon shade."""
    if colour not in NEON_ORDER:
        return NEON_ORDER[0]
    return NEON_ORDER[(NEON_ORDER.index(colour) + step) % len(NEON_ORDER)]


# ── Model ───────────────────────────────────────────────────────────────

def _unit(value):
    """One coordinate as a float in 0..1, or None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(v) or math.isinf(v):
        return None
    return max(0.0, min(1.0, v))


def clean_note(note):
    """One stored note, cleaned; None when it is unusable or too small to
    see. A hand-edited or future value must never break the renderer."""
    if not isinstance(note, dict):
        return None
    kind = note.get('t')
    if kind not in TOOLS:
        return None
    try:
        raw = list(note.get('p'))
    except TypeError:
        return None
    if len(raw) != 4:
        return None
    pts = [_unit(v) for v in raw]
    if any(v is None for v in pts):
        return None
    x1, y1, x2, y2 = pts
    if kind == 'arrow':
        if math.hypot(x2 - x1, y2 - y1) < MIN_ARROW:
            return None
    else:
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        if x2 - x1 < MIN_BOX or y2 - y1 < MIN_BOX:
            return None
    colour = note.get('c')
    if colour not in COLORS:
        colour = DEFAULT_COLOR
    out = {'t': kind,
           'p': [round(x1, 6), round(y1, 6), round(x2, 6), round(y2, 6)],
           'c': colour}
    width = _unit(note.get('w')) if 'w' in note else None
    if width is not None and width > 0:
        out['w'] = round(max(WIDTH_MIN, min(WIDTH_MAX, width)), 5)
    return out


def clean_notes(notes):
    """A stored list, cleaned and capped. Anything that is not a list gives
    an empty one."""
    if not isinstance(notes, (list, tuple)):
        return []
    out = []
    for note in notes:
        cleaned = clean_note(note)
        if cleaned is not None:
            out.append(cleaned)
        if len(out) >= MAX_NOTES:
            break
    return out


def make_note(kind, start, end, colour, square=False, width=None):
    """A new note from two points (normalized (x, y) tuples) - what a drag
    produces. `square` (Shift) turns an outline/marker into a square or
    circle and snaps an arrow to 45 degree steps; it needs the frame size
    to be exact, so the caller passes it as `square=(frame_w, frame_h)`.
    `width` is the pen width (fraction of the long edge) kept in the note.
    -> a cleaned note, or None when the drag was too small."""
    x1, y1 = start
    x2, y2 = end
    if square:
        fw, fh = square
        dx, dy = (x2 - x1) * fw, (y2 - y1) * fh
        if kind == 'arrow':
            if dx or dy:
                step = math.pi / 4
                ang = round(math.atan2(dy, dx) / step) * step
                length = math.hypot(dx, dy)
                dx, dy = math.cos(ang) * length, math.sin(ang) * length
        else:
            side = max(abs(dx), abs(dy))
            dx = math.copysign(side, dx) if dx else side
            dy = math.copysign(side, dy) if dy else side
        x2, y2 = x1 + dx / fw, y1 + dy / fh
    note = {'t': kind, 'p': [x1, y1, x2, y2], 'c': colour}
    if width is not None:
        note['w'] = width
    return clean_note(note)


# ── Geometry shared by the pixel renderer and the on-screen painter ─────

def stroke_px(long_edge, width=None):
    """Line width in pixels for a frame whose long edge is `long_edge`;
    `width` is the note's own fraction (None: the default)."""
    frac = STROKE_FRACTION if width is None else width
    return max(STROKE_MIN_PX, frac * float(long_edge))


def box_stroke(stroke, width, height):
    """The outline width actually used for a box: never more than half the
    box, or the ring would swallow the inside."""
    return max(1.0, min(stroke, width / 2.0, height / 2.0))


def arrow_parts(x1, y1, x2, y2, stroke):
    """-> (shaft_polygon, head_polygon), each a list of (x, y), in the
    units of the inputs; None for a zero-length arrow.

    The shaft stops inside the head so no seam shows, and the head shrinks
    on a short arrow so it never outgrows its own shaft."""
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return None
    ux, uy = dx / length, dy / length
    nx, ny = -uy, ux
    head_len = min(6.5 * stroke, length * 0.6)
    head_half = max(0.46 * head_len, stroke * 0.8)
    base_x, base_y = x2 - ux * head_len, y2 - uy * head_len
    join_x, join_y = x2 - ux * head_len * 0.85, y2 - uy * head_len * 0.85
    half = stroke / 2.0
    shaft = [(x1 + nx * half, y1 + ny * half),
             (join_x + nx * half, join_y + ny * half),
             (join_x - nx * half, join_y - ny * half),
             (x1 - nx * half, y1 - ny * half)]
    head = [(x2, y2),
            (base_x + nx * head_half, base_y + ny * head_half),
            (base_x - nx * head_half, base_y - ny * head_half)]
    return shaft, head


# ── Pixel renderer (Pillow) ─────────────────────────────────────────────

def _ensure_colour(img):
    """The image in a mode that can carry coloured marks: RGB, or RGBA when
    it has transparency (a macOS window screenshot keeps its shadow)."""
    if img.mode in ('RGB', 'RGBA'):
        return img
    if img.mode in ('LA', 'PA') or (img.mode == 'P'
                                    and 'transparency' in img.info):
        return img.convert('RGBA')
    return img.convert('RGB')


def _resample_box():
    return getattr(getattr(Image, 'Resampling', Image), 'BOX')


def draw_notes(img, notes, full_size, offset=(0, 0)):
    """Draw `notes` into the PIL image `img` and return it.

    full_size: (width, height) of the frame the coordinates refer to - the
    upright image before any crop. offset: where `img` starts inside that
    frame, in pixels (the crop's top-left), so notes land in the right
    place after a crop. The image is changed in place when it is already
    RGB/RGBA; otherwise a converted copy is returned - always use the
    return value."""
    notes = clean_notes(notes)
    if not notes or not HAS_PIL:
        return img
    img = _ensure_colour(img)
    frame_w, frame_h = full_size
    ox, oy = offset
    long_edge = max(frame_w, frame_h)
    for note in notes:
        stroke = stroke_px(long_edge, note.get('w'))
        x1, y1, x2, y2 = note['p']
        pts = (x1 * frame_w - ox, y1 * frame_h - oy,
               x2 * frame_w - ox, y2 * frame_h - oy)
        _draw_one(img, note['t'], pts, COLORS[note['c']], stroke)
    return img


def _draw_one(img, kind, pts, colour, stroke):
    width, height = img.size
    x1, y1, x2, y2 = pts
    if kind == 'arrow':
        parts = arrow_parts(x1, y1, x2, y2, stroke)
        if parts is None:
            return
        flat = [pt for poly in parts for pt in poly]
        min_x = min(p[0] for p in flat)
        max_x = max(p[0] for p in flat)
        min_y = min(p[1] for p in flat)
        max_y = max(p[1] for p in flat)
    else:
        parts = None
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)
    # The tile is the shape's box cut to the picture: work stays small even
    # for a big picture, and a shape that runs off the edge is clipped.
    left = max(0, int(math.floor(min_x)) - 2)
    upper = max(0, int(math.floor(min_y)) - 2)
    right = min(width, int(math.ceil(max_x)) + 2)
    lower = min(height, int(math.ceil(max_y)) + 2)
    if right <= left or lower <= upper:
        return
    tw, th = right - left, lower - upper

    if kind == 'mark':
        mask = Image.new('L', (tw, th), 0)
        ImageDraw.Draw(mask).rectangle(
            [round(min_x) - left, round(min_y) - upper,
             max(round(min_x), round(max_x) - 1) - left,
             max(round(min_y), round(max_y) - 1) - upper],
            fill=int(round(255 * MARK_OPACITY)))
    else:
        # Supersample so the edges are smooth; the factor shrinks for a big
        # tile so a full-width ellipse cannot eat gigabytes.
        ss = max(1, min(4, _TILE_LIMIT // max(tw, th)))
        big = Image.new('L', (tw * ss, th * ss), 0)
        draw = ImageDraw.Draw(big)

        def scaled(px, py):
            return ((px - left) * ss, (py - upper) * ss)

        if kind == 'arrow':
            for poly in parts:
                draw.polygon([scaled(px, py) for px, py in poly], fill=255)
        else:
            sb = box_stroke(stroke, max_x - min_x, max_y - min_y)
            ax, ay = scaled(min_x, min_y)
            bx, by = scaled(max_x, max_y)
            box = [ax, ay, max(ax, bx - 1), max(ay, by - 1)]
            line = max(1, int(round(sb * ss)))
            if kind == 'ellipse':
                draw.ellipse(box, outline=255, width=line)
            else:
                draw.rectangle(box, outline=255, width=line)
        mask = big if ss == 1 else big.resize((tw, th), _resample_box())

    fill = tuple(colour) + ((255,) if img.mode == 'RGBA' else ())
    img.paste(fill, (left, upper, right, lower), mask)
