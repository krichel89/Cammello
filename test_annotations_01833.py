#!/usr/bin/env python3
"""0.18.33: annotations (arrows, outlines, highlights) and PNG in the culling
view - the model, the renderer, the scan, and the annotation mode.

Run headless:  QT_QPA_PLATFORM=offscreen python3 test_annotations_01833.py
"""
import os
import sys
import tempfile
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
_HOME = tempfile.mkdtemp()
os.environ['HOME'] = _HOME
os.environ['USERPROFILE'] = _HOME
os.environ['CAMMELLO_WORKFLOWS'] = os.path.join(_HOME, 'workflows.toml')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PIL import Image, ImageDraw
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import Qt, QEvent, QSettings, QPoint
from PyQt5.QtTest import QTest

import Cammello
from cammello import annotations, edits, culling
from cammello.constants import APP_NAME
from cammello.logging_setup import setup_logging

app = QApplication(sys.argv)
fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


def near(a, b, tol=6):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ── 1. the model ─────────────────────────────────────────────────────────────
good = {'t': 'arrow', 'p': [0.1, 0.1, 0.5, 0.5], 'c': 'blue'}
check('a good note survives', annotations.clean_note(good) == good)
check('unknown tool is dropped',
      annotations.clean_note({'t': 'star', 'p': [0, 0, 1, 1]}) is None)
check('a tiny arrow is dropped',
      annotations.clean_note({'t': 'arrow', 'p': [0.5, 0.5, 0.5, 0.5]}) is None)
check('a sliver box is dropped',
      annotations.clean_note({'t': 'rect', 'p': [0.1, 0.1, 0.1, 0.9]}) is None)
check('NaN is dropped',
      annotations.clean_note({'t': 'rect', 'p': [0, 0, float('nan'), 1]}) is None)
check('garbage is dropped', annotations.clean_note('x') is None
      and annotations.clean_note({'t': 'rect', 'p': 5}) is None)
check('unknown colour falls back to red',
      annotations.clean_note({'t': 'mark', 'p': [0, 0, .5, .5],
                              'c': 'pink'})['c'] == 'red')
check('boxes are ordered, coordinates clamped',
      annotations.clean_note({'t': 'rect', 'p': [0.9, 0.8, -1, 0.2]})['p']
      == [0.0, 0.2, 0.9, 0.8])
check('a list is capped',
      len(annotations.clean_notes([good] * 500)) == annotations.MAX_NOTES)
check('not a list = empty', annotations.clean_notes('x') == []
      and annotations.clean_notes(None) == [])
sq = annotations.make_note('ellipse', (0.2, 0.2), (0.6, 0.3), 'red',
                           square=(1000, 500))
w_px = (sq['p'][2] - sq['p'][0]) * 1000
h_px = (sq['p'][3] - sq['p'][1]) * 500
check('Shift makes a circle', abs(w_px - h_px) < 1, f'{w_px} x {h_px}')
ar = annotations.make_note('arrow', (0.5, 0.5), (0.9, 0.55), 'red',
                           square=(1000, 1000))
check('Shift snaps an arrow to 45 degrees',
      abs(ar['p'][3] - ar['p'][1]) < 1e-6, str(ar))
check('a click without a drag makes nothing',
      annotations.make_note('arrow', (0.3, 0.3), (0.3, 0.3), 'red') is None)

# thickness and neon colours (the second round of 0.18.33)
check('step 0 and the top step span 0.1 % .. 10 %',
      annotations.width_for_step(0) == 0.001
      and annotations.width_for_step(annotations.WIDTH_STEPS) == 0.1)
check('steps grow', all(annotations.width_for_step(i)
                        < annotations.width_for_step(i + 1) for i in range(30)))
check('step <-> width round trip', all(
    annotations.step_for_width(annotations.width_for_step(i)) == i
    for i in range(31)))
check('junk width gives the default step',
      annotations.step_for_width('x') == annotations.DEFAULT_WIDTH_STEP
      and annotations.step_for_width(-1) == annotations.DEFAULT_WIDTH_STEP)
nw = annotations.make_note('rect', (0.1, 0.1), (0.5, 0.5), 'red', width=0.02)
check('a note keeps its own width', nw['w'] == 0.02, str(nw))
check('no width given = no key (older records stay as they are)',
      'w' not in annotations.make_note('rect', (0.1, 0.1), (0.5, 0.5), 'red'))
check('a silly width is clamped',
      annotations.clean_note(dict(nw, w=5))['w'] == annotations.WIDTH_MAX
      and annotations.clean_note(dict(nw, w=1e-9))['w']
      == annotations.WIDTH_MIN)
check('a junk width is dropped, the note stays',
      'w' not in annotations.clean_note(dict(nw, w='x'))
      and 'w' not in annotations.clean_note(dict(nw, w=float('nan'))))
check('stroke follows the note width',
      annotations.stroke_px(2000, 0.02) == 40.0
      and annotations.stroke_px(2000) == 7.0)
check('five neon shades, all known colours',
      len(annotations.NEON_ORDER) == 5
      and all(c in annotations.COLORS for c in annotations.NEON_ORDER))
check('a neon colour survives clean_note',
      annotations.clean_note(dict(nw, c='neon_pink'))['c'] == 'neon_pink')
check('N from a plain colour starts at the first neon',
      annotations.next_neon('red') == 'neon_yellow')
seq = ['neon_yellow']
for _i in range(5):
    seq.append(annotations.next_neon(seq[-1]))
check('N cycles through all five and wraps',
      seq == ['neon_yellow', 'neon_green', 'neon_pink', 'neon_orange',
              'neon_blue', 'neon_yellow'], str(seq))
check('Shift+N goes back',
      annotations.next_neon('neon_yellow', -1) == 'neon_blue')

# ── 2. the edit record ───────────────────────────────────────────────────────
store = {}
path = os.path.join(_HOME, 'x.jpg')
check('an empty list is no edit', not edits.set_notes(store, path, []))
check('adding a note is an edit', edits.add_note(store, path, good)
      and edits.has_edit(store, path))
check('a bad note is refused', not edits.add_note(store, path, {'t': 'zz'}))
edits.add_note(store, path, {'t': 'mark', 'p': [0.2, 0.2, 0.4, 0.3], 'c': 'yellow'})
check('two notes', len(edits.get_notes(store, path)) == 2)
check('remove last', edits.remove_last_note(store, path)
      and len(edits.get_notes(store, path)) == 1)
before = dict(edits.get_edit(store, path))
edits.set_crop(store, path, (0.1, 0.1, 0.5, 0.5))
check('notes and crop live side by side',
      'notes' in store[edits.norm(path)] and 'crop' in store[edits.norm(path)])
edits.apply_record(store, path, before)
check('undo restores the record with its notes',
      edits.get_edit(store, path) == before)
edits.remove_last_note(store, path)
check('the last note gone = no record', not edits.has_edit(store, path))
for _ in range(annotations.MAX_NOTES + 5):
    edits.add_note(store, path, good)
check('the cap holds in the record',
      len(edits.get_notes(store, path)) == annotations.MAX_NOTES)
check('a record with only notes is valid', edits._normalize_record(
    {'notes': [good]}) == {'notes': [good]})
check('a record of junk notes is no record',
      edits._normalize_record({'notes': [{'t': 'zz'}]}) is None)

# ── 3. the renderer ──────────────────────────────────────────────────────────
tmp = tempfile.mkdtemp()
red = annotations.COLORS['red']

# PNG with a transparent border, like a macOS window screenshot
src = os.path.join(tmp, 'shot.png')
im = Image.new('RGBA', (1200, 800), (0, 0, 0, 0))
ImageDraw.Draw(im).rectangle([50, 50, 1150, 750], fill=(240, 240, 240, 255))
im.save(src)
notes = [{'t': 'rect', 'p': [0.25, 0.25, 0.75, 0.75], 'c': 'red'},
         {'t': 'mark', 'p': [0.30, 0.80, 0.70, 0.90], 'c': 'yellow'}]
out = os.path.join(tmp, 'shot_edit.png')
res = edits.render_edited(src, {'notes': notes}, out)
check('PNG renders to PNG', res == out and Image.open(out).format == 'PNG')
o = Image.open(out)
check('PNG keeps its size and transparency',
      o.size == (1200, 800) and o.mode == 'RGBA'
      and o.getpixel((5, 5))[3] == 0, f'{o.size} {o.mode}')
check('the outline is drawn in the palette red',
      near(o.getpixel((300, 400))[:3], red, 8), str(o.getpixel((300, 400))))
check('inside the outline is untouched',
      o.getpixel((600, 400)) == (240, 240, 240, 255))
hl = o.getpixel((600, 680))
check('the highlight is translucent: the picture shows through',
      hl[0] > 200 and hl[2] < 200 and hl != (240, 240, 240, 255), str(hl))
check('a PNG stays out of the .jpg name',
      edits.render_extension(src) == '.png'
      and edits.export_name(src) == 'shot_edit.png'
      and edits.export_name('a.jpg') == 'a_edit.jpg'
      and edits.export_name('a.CR3') == 'a_edit.jpg')

# crop first, then the note lands on the right pixel
rec = {'crop': [0.5, 0.5, 0.5, 0.5],
       'notes': [{'t': 'mark', 'p': [0.5, 0.5, 0.75, 0.75], 'c': 'red'}]}
out2 = os.path.join(tmp, 'crop_edit.png')
edits.render_edited(src, rec, out2)
o2 = Image.open(out2)
check('crop size', o2.size == (600, 400), str(o2.size))
check('the note sits at the cropped corner, not at the old position',
      o2.getpixel((10, 10))[0] > 230 and o2.getpixel((10, 10))[1] < 190
      and o2.getpixel((500, 300))[:3] == (240, 240, 240),
      f'{o2.getpixel((10, 10))} {o2.getpixel((500, 300))}')

# a note outside the crop is simply not there
rec = {'crop': [0.0, 0.0, 0.3, 0.3],
       'notes': [{'t': 'mark', 'p': [0.6, 0.6, 0.9, 0.9], 'c': 'red'}]}
out3 = os.path.join(tmp, 'outside_edit.png')
check('a note outside the crop renders without trouble',
      edits.render_edited(src, rec, out3) == out3)

# white balance must not tint the annotation
jpg = os.path.join(tmp, 'p.jpg')
Image.new('RGB', (800, 600), (128, 128, 128)).save(jpg, quality=95)
# a PNG for the colour check: JPEG chroma smoothing would blur a pure edge
gray = os.path.join(tmp, 'gray.png')
Image.new('RGB', (800, 600), (128, 128, 128)).save(gray)
rec = {'wb': [1.6, 1.0, 0.6],
       'notes': [{'t': 'mark', 'p': [0.0, 0.0, 1.0, 1.0], 'c': 'white'},
                 {'t': 'rect', 'p': [0.2, 0.2, 0.8, 0.8], 'c': 'red'}]}
out4 = os.path.join(tmp, 'wb_edit.png')
edits.render_edited(gray, rec, out4)
px = Image.open(out4).getpixel((160, 300))
check('white balance runs BEFORE the annotation: red stays red',
      near(px, red, 12), str(px))

# JPEG source still goes to JPEG, with its metadata path intact
rec = {'ev': 0.5, 'notes': notes}
out5 = os.path.join(tmp, 'j_edit.jpg')
edits.render_edited(jpg, rec, out5)
check('JPEG stays JPEG', Image.open(out5).format == 'JPEG')

# palette PNG with transparency is widened, not flattened
pal = os.path.join(tmp, 'pal.png')
pim = Image.new('P', (300, 200), 0)
pim.putpalette([255, 255, 255] + [0, 0, 0] * 255)
pim.info['transparency'] = 0
pim.save(pal, transparency=0)
out6 = os.path.join(tmp, 'pal_edit.png')
edits.render_edited(pal, {'notes': [{'t': 'arrow', 'p': [.1, .1, .9, .9],
                                     'c': 'green'}]}, out6)
o6 = Image.open(out6)
check('a palette PNG keeps its transparency',
      o6.mode == 'RGBA' and o6.getpixel((2, 190))[3] == 0, o6.mode)

# upload path
eff = edits.effective_upload_path(src, {edits.norm(src): {'notes': notes}},
                                  tmp)
check('upload gets a rendered PNG',
      eff.endswith('shot_edit.png') and os.path.exists(eff), eff)

# a huge outline must not allocate a huge tile (supersample cap)
big = Image.new('RGB', (6000, 4000), (200, 200, 200))
t0 = time.time()
annotations.draw_notes(big, [{'t': 'ellipse', 'p': [0, 0, 1, 1], 'c': 'red'}],
                       big.size)
check('a full-frame ellipse on 24 MP is quick', time.time() - t0 < 5,
      f'{time.time() - t0:.2f}s')
check('...and drawn', near(big.getpixel((3000, 3)), red, 10)
      or near(big.getpixel((3000, 6)), red, 10), str(big.getpixel((3000, 6))))

# a thick and a thin outline of the same box: width is per note
srcw = os.path.join(tmp, 'wide.png')
Image.new('RGB', (1000, 1000), (20, 20, 20)).save(srcw)
outw = os.path.join(tmp, 'wide_edit.png')
edits.render_edited(srcw, {'notes': [
    {'t': 'rect', 'p': [0.1, 0.1, 0.4, 0.4], 'c': 'neon_green', 'w': 0.002},
    {'t': 'rect', 'p': [0.5, 0.5, 0.9, 0.9], 'c': 'neon_pink', 'w': 0.05}]},
    outw)
ow = Image.open(outw).convert('RGB')


def run_len(img, y, x0):
    n = 0
    while x0 + n < img.width and img.getpixel((x0 + n, y)) != (20, 20, 20):
        n += 1
    return n


thin_w, thick_w = run_len(ow, 250, 100), run_len(ow, 700, 500)
check('thin outline ~2 px, thick one ~50 px',
      1 <= thin_w <= 4 and 45 <= thick_w <= 55, f'{thin_w} / {thick_w}')
check('neon colours land in the pixels',
      near(ow.getpixel((101, 250)), annotations.COLORS['neon_green'], 12)
      and near(ow.getpixel((510, 700)), annotations.COLORS['neon_pink'], 12),
      f"{ow.getpixel((101, 250))} {ow.getpixel((510, 700))}")

# ── 4. PNG in the culling scan ───────────────────────────────────────────────
folder = os.path.join(tmp, 'shots')
os.makedirs(folder)
Image.new('RGB', (900, 600), (250, 250, 250)).save(
    os.path.join(folder, 'a.png'))
Image.new('RGB', (900, 600), (250, 250, 250)).save(
    os.path.join(folder, 'b.jpg'))
items = culling.scan_folder(folder, {}, False)
names = sorted(os.path.basename(i.display_path) for i in items)
check('the scan takes a PNG', names == ['a.png', 'b.jpg'], str(names))
png_item = [i for i in items if i.display_path.endswith('a.png')][0]
check('a PNG entry has a sidecar path',
      png_item.sidecar_path == os.path.join(folder, 'a.xmp'))
jpg_item = [i for i in items if i.display_path.endswith('b.jpg')][0]
check('a JPEG entry has none', jpg_item.sidecar_path is None)
png_before = open(png_item.display_path, 'rb').read()
png_item.rating = 4
culling.write_item_metadata(png_item)
check('rating a PNG writes a sidecar and leaves the PNG alone',
      os.path.exists(os.path.join(folder, 'a.xmp'))
      and open(png_item.display_path, 'rb').read() == png_before)
check('the rating reads back',
      culling.rating_label_for_path(png_item.display_path)[0] == 4)

# ── 5. the annotation mode in the window ─────────────────────────────────────
logger, emitter, gui_handler, log_path = setup_logging()
import logging
for h in logger.handlers:
    h.setLevel(logging.CRITICAL)
settings = QSettings(APP_NAME, 'Main')
for k in ('cull_note_tool', 'cull_note_color', 'cull_note_width',
          'cull_edit_panel', 'edits'):
    settings.remove(k)

w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
w.resize(1200, 800)
w.show()
if not hasattr(w, '_cull_reader'):
    print('SKIP window part (culling off)')
    print('FAILURES:', fails or 'none')
    os._exit(1 if fails else 0)
w.tabs.setCurrentWidget(w._cull_tab_widget)
app.processEvents()


def spin(ms=300):
    end = time.time() + ms / 1000.0
    while time.time() < end:
        app.processEvents()
        time.sleep(0.01)


w._cull_open_folder(folder, False)
spin(800)
check('the folder shows both pictures', len(w._cull_items) == 2,
      str(len(w._cull_items)))
w._cull_show_index(
    [i.display_path for i in w._cull_visible].index(
        os.path.join(folder, 'a.png')))
spin(800)
check('the PNG is on screen', w.cull_view.has_image())


def key(k, mods=Qt.NoModifier):
    w._cull_key(QKeyEvent(QEvent.KeyPress, k, mods))


item = w._cull_current_item()
path = item.display_path
check('not annotating at first', not w._cull_noting)
key(Qt.Key_A)
check('A starts the mode', w._cull_noting
      and not w.cull_view.note_draw.isHidden())
check('the panel shows tools and colours', not w.cull_edit_panel.note_box.isHidden())
key(Qt.Key_2)
key(Qt.Key_B)
check('keys pick tool and colour',
      w._cull_note_tool == 'ellipse' and w._cull_note_color == 'blue')
check('and the choice is remembered',
      settings.value('cull_note_tool') == 'ellipse'
      and settings.value('cull_note_color') == 'blue')
check('the panel marks the choice',
      w.cull_edit_panel._tool_btns['ellipse'].isChecked()
      and w.cull_edit_panel._colour_btns['blue'].isChecked())

# draw with the mouse on the overlay
ov = w.cull_view.note_draw
r = ov._image_rect()
check('the overlay knows where the picture is', r is not None and r.width() > 50,
      str(r))
a = QPoint(int(r.x() + r.width() * 0.2), int(r.y() + r.height() * 0.2))
b = QPoint(int(r.x() + r.width() * 0.6), int(r.y() + r.height() * 0.5))
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, a)
QTest.mouseMove(ov, b)
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, b)
spin(100)
notes_now = edits.get_notes(w._cull_edits, path)
check('a drag stores one note', len(notes_now) == 1, str(notes_now))
if notes_now:
    n = notes_now[0]
    check('with the right kind, colour and place',
          n['t'] == 'ellipse' and n['c'] == 'blue'
          and abs(n['p'][0] - 0.2) < 0.03 and abs(n['p'][3] - 0.5) < 0.03,
          str(n))
check('the strip shows the edit badge', edits.has_edit(w._cull_edits, path))
check('the view bakes it in', len(w.cull_view.notes()) == 1)

# a click without a drag draws nothing
QTest.mouseClick(ov, Qt.LeftButton, Qt.NoModifier, a)
check('a plain click adds nothing',
      len(edits.get_notes(w._cull_edits, path)) == 1)
# a press outside the picture draws nothing
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, QPoint(1, 1))
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, QPoint(300, 300))
check('starting outside the picture adds nothing',
      len(edits.get_notes(w._cull_edits, path)) == 1)

# second note, then Backspace, then undo
key(Qt.Key_1)
key(Qt.Key_R)
QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, a)
QTest.mouseMove(ov, b)
QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, b)
check('two notes', len(edits.get_notes(w._cull_edits, path)) == 2)
key(Qt.Key_Backspace)
check('Backspace removes the last',
      [n['t'] for n in edits.get_notes(w._cull_edits, path)] == ['ellipse'])
w._cull_undo_action()
check('Ctrl+Z puts it back while the mode stays on',
      len(edits.get_notes(w._cull_edits, path)) == 2 and w._cull_noting)
check('the full frame is still shown while annotating',
      w.cull_view.crop_display() is None)
key(Qt.Key_A, Qt.ShiftModifier)
check('Shift+A removes all', edits.get_notes(w._cull_edits, path) == [])
w._cull_undo_action()
check('and Ctrl+Z brings them back',
      len(edits.get_notes(w._cull_edits, path)) == 2)

# Enter ends the mode
key(Qt.Key_Return)
check('Enter ends the mode', not w._cull_noting
      and w.cull_edit_panel.note_box.isHidden()
      and ov.isHidden())
check('the notes stay on the picture', len(w.cull_view.notes()) == 2)

# the edit panel button toggles it, the crop key hands over
w.cull_edit_panel.notes_btn.click()
check('the panel button starts it', w._cull_noting)
key(Qt.Key_C)
check('C leaves annotating and starts the crop',
      not w._cull_noting and w._cull_cropping)
key(Qt.Key_Escape)
check('Esc leaves the crop', not w._cull_cropping)
key(Qt.Key_A)
key(Qt.Key_A)
check('A again ends it', not w._cull_noting)

# stepping to another picture ends the mode and swaps the notes
key(Qt.Key_A)
w._cull_show_index(0 if w._cull_index else 1)
spin(300)
check('a picture change ends the mode', not w._cull_noting)
check('the other picture has no notes', w.cull_view.notes() == [])
w._cull_show_index([i.display_path for i in w._cull_visible].index(path))
spin(500)
check('coming back brings the notes back', len(w.cull_view.notes()) == 2)

# thickness and neon by key and slider, in the window
pic = [i.display_path for i in w._cull_visible].index(path)
w._cull_show_index(pic)
spin(300)
key(Qt.Key_A)
check('A starts the mode again', w._cull_noting)
key(Qt.Key_A, Qt.ShiftModifier)          # start from a clean picture
key(Qt.Key_R)
key(Qt.Key_1)
key(Qt.Key_N)
check('N picks the first neon shade', w._cull_note_color == 'neon_yellow')
key(Qt.Key_N)
check('N again: the next one', w._cull_note_color == 'neon_green')
key(Qt.Key_N, Qt.ShiftModifier)
check('Shift+N: back', w._cull_note_color == 'neon_yellow')
check('the neon swatch is marked in the panel',
      w.cull_edit_panel._colour_btns['neon_yellow'].isChecked()
      and not w.cull_edit_panel._colour_btns['red'].isChecked())
check('the neon choice is remembered',
      settings.value('cull_note_color') == 'neon_yellow')
w.cull_edit_panel._colour_btns['neon_blue'].click()
check('a click on a neon swatch picks it', w._cull_note_color == 'neon_blue')

start = w._cull_note_width
key(Qt.Key_BracketRight)
check('] is thicker, the slider follows',
      w._cull_note_width == start + 1
      and w.cull_edit_panel.note_width.value() == start + 1)
key(Qt.Key_BracketLeft)
key(Qt.Key_BracketLeft)
check('[ is thinner', w._cull_note_width == start - 1)
check('the width is remembered', int(settings.value('cull_note_width')) == start - 1)
w.cull_edit_panel.note_width.setValue(20)
check('the slider sets the pen', w._cull_note_width == 20)
for _i in range(20):
    key(Qt.Key_BracketRight)
check('the pen stops at the top', w._cull_note_width == annotations.WIDTH_STEPS)
w.cull_edit_panel.note_width.setValue(5)


def drag(fx):
    r = ov._image_rect()
    a = QPoint(int(r.x() + r.width() * fx), int(r.y() + r.height() * 0.2))
    b = QPoint(int(r.x() + r.width() * (fx + 0.2)),
               int(r.y() + r.height() * 0.5))
    QTest.mousePress(ov, Qt.LeftButton, Qt.NoModifier, a)
    QTest.mouseMove(ov, b)
    QTest.mouseRelease(ov, Qt.LeftButton, Qt.NoModifier, b)
    spin(100)


w._cull_set_note_color('neon_orange')
drag(0.1)
w.cull_edit_panel.note_width.setValue(25)
drag(0.5)
two = edits.get_notes(w._cull_edits, path)
check('two new notes', len(two) == 2, str(two))
if len(two) == 2:
    check('each keeps the width it was drawn with',
          two[0]['w'] == annotations.width_for_step(5)
          and two[1]['w'] == annotations.width_for_step(25), str(two))
    check('and its neon colour', two[0]['c'] == 'neon_orange')
w._cull_set_note_width(10)
check('changing the pen leaves drawn notes alone',
      [n['w'] for n in edits.get_notes(w._cull_edits, path)]
      == [annotations.width_for_step(5), annotations.width_for_step(25)])
w._cull_undo_action()
check('undo takes one note, the other keeps its width',
      [n['w'] for n in edits.get_notes(w._cull_edits, path)]
      == [annotations.width_for_step(5)])
key(Qt.Key_A)
check('a stored width of the old kind is read as the default',
      annotations.stroke_px(1000, None) == 3.5)

# reset removes them
w._cull_reset_edits()
check('Reset removes the annotations',
      edits.get_notes(w._cull_edits, path) == [] and w.cull_view.notes() == [])

# the export loop renders a PNG as a PNG
rec = {'notes': [good]}
exp_dir = os.path.join(tmp, 'export')
os.makedirs(exp_dir)
from cammello.mw_culling import _FolderCopyWorker
worker = _FolderCopyWorker([path], exp_dir, logger, {path: rec})
worker.run()
check('a folder export of an annotated PNG gives a PNG',
      os.path.exists(os.path.join(exp_dir, 'a_edit.png')),
      str(os.listdir(exp_dir)))

for k in ('cull_note_tool', 'cull_note_color', 'cull_note_width',
          'cull_edit_panel', 'edits'):
    settings.remove(k)
w._cull_shutdown()
print('FAILURES:', fails or 'none')
os._exit(1 if fails else 0)
