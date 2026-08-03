"""Uploads-Modul, Filterleiste und Commons-Upload (0.16.1).

Prueft die Filterlogik (Sterne als Schwelle, Farben und Kanaele als ODER,
Gruppen mit UND), die Wirkung auf Auswahl und Graufaerbung, den neuen
Commons-Knopf und die Sicherung gegen den "nichts ausgewaehlt = alles"-
Rueckfall.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
os.environ.setdefault('CAMMELLO_WORKFLOWS',
                      os.path.join(tempfile.mkdtemp(), 'workflows.toml'))

from PIL import Image
from PyQt5.QtWidgets import QApplication, QMessageBox

import Cammello
from cammello import channels, culling
from cammello.filters import NO_CHANNEL, NO_COLOR, FileFilter
from cammello.logging_setup import setup_logging
from cammello.widgets import FilterBar

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    if cond:
        print('PASS', name, detail)
    else:
        print('FAIL', name, detail)
        fails.append(name)


# ── 1. Die Logik, ohne Oberflaeche ───────────────────────────────────────
check('an untouched filter is not active', not FileFilter().active)
check('and lets everything through', FileFilter().matches(0, None, None))

f = FileFilter(min_rating=3)
check('stars are a threshold, not a choice',
      f.matches(3) and f.matches(5) and not f.matches(2))
check('a rejected file never passes a star filter', not f.matches(-1))
check('rejects pass while the star filter is off', FileFilter().matches(-1))

f = FileFilter(colors={0, 2})
check('colours are OR', f.matches(0, 0) and f.matches(0, 2))
check('and exclude the others', not f.matches(0, 3))
check('an unlabelled file is not caught by a colour', not f.matches(0, None))
check('but "no label" can be asked for explicitly',
      FileFilter(colors={NO_COLOR}).matches(0, None))
check('an unknown label text counts as "no label"',
      culling.label_index('Chartreuse') is None)

f = FileFilter(channels={channels.MARK_COMMONS})
check('channels are OR too', f.matches(0, None, channels.MARK_COMMONS))
check('and exclude the other mark',
      not f.matches(0, None, channels.MARK_COMMERCIAL))
check('unmarked files can be asked for',
      FileFilter(channels={NO_CHANNEL}).matches(0, None, None))

f = FileFilter(min_rating=2, colors={0})
check('the groups combine with AND',
      f.matches(3, 0) and not f.matches(3, 1) and not f.matches(1, 0))

# ── 2. Ratings von der Platte ────────────────────────────────────────────
_XMP = ('<?xpacket begin="" ?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
        '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        '<rdf:Description xmlns:xmp="http://ns.adobe.com/xap/1.0/" '
        'xmp:Rating="{r}" xmp:Label="{l}"/></rdf:RDF></x:xmpmeta>'
        '<?xpacket end="w"?>')
_dir = tempfile.mkdtemp()


def make(stem, rating, label, ext='.jpg'):
    path = os.path.join(_dir, stem + ext)
    Image.new('RGB', (40, 30)).save(path)
    with open(os.path.join(_dir, stem + '.xmp'), 'w', encoding='utf-8') as fh:
        fh.write(_XMP.format(r=rating, l=label))
    return path


_paths = [make('a', 5, 'Red'), make('b', 3, 'Green'), make('c', 1, 'Red'),
          make('d', 0, ''), make('e', -1, 'Blue')]
check('a sidecar rating is read without pyexiv2',
      culling.rating_label_for_path(_paths[0]) == (5, 'Red'),
      str(culling.rating_label_for_path(_paths[0])))
check('a file with no sidecar reads as unrated, it does not raise',
      culling.rating_label_for_path(os.path.join(_dir, 'nope.jpg')) == (0, ''))
check('a German label text is recognised', culling.label_index('Rot') == 0)

# ── 3. Das Widget ────────────────────────────────────────────────────────
_bar = FilterBar()
_seen = []
_bar.changed.connect(lambda flt: _seen.append(flt))
check('the bar starts switched off', not _bar.current_filter().active)
_bar._on_star(3)
check('clicking a star sets the threshold',
      _bar.current_filter().min_rating == 3)
check('the filled stars show it',
      [b.text() for b in _bar.star_btns] == ['★', '★', '★', '☆', '☆'])
_bar._on_star(3)
check('clicking the same star again switches it off',
      _bar.current_filter().min_rating == 0)
_bar.color_btns[0].setChecked(True)
_bar.color_btns[-1].setChecked(True)
_bar._emit()
check('the last swatch means "no label"',
      _bar.current_filter().colors == {0, NO_COLOR},
      str(_bar.current_filter().colors))
_bar.channel_btns[0].setChecked(True)
_bar._emit()
check('the channel dots carry their mark',
      _bar.current_filter().channels == {channels.MARK_COMMONS},
      str(_bar.current_filter().channels))
_bar.clear()
check('the cross switches everything off', not _bar.current_filter().active)
check('every change was announced', len(_seen) >= 5, str(len(_seen)))

# ── 4. Im laufenden Fenster ──────────────────────────────────────────────
w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
_titles = [w.tabs.tabText(i) for i in range(w.tabs.count())]
check('the last module is called Uploads', _titles[-1] == 'Uploads',
      str(_titles))
check('it no longer names only two of the three channels',
      not any('FTP / Flickr' == t for t in _titles), str(_titles))
check('the filter bar sits in that module', hasattr(w, 'ftp_filter_bar'))
check('the Commons button is there', hasattr(w, 'commons_upload_btn'))

w._add_paths(_paths)
w._ftp_refresh_list()
check('the list holds every file', w.ftp_list.count() == len(_paths),
      str(w.ftp_list.count()))


def selected_names():
    return sorted(w.ftp_list.item(i).text()
                  for i in range(w.ftp_list.count())
                  if w.ftp_list.item(i).isSelected())


def dimmed_names():
    """Items greyed by the filter - alpha is the marker, so this does not
    confuse them with the hard grey of a disabled channel item."""
    out = []
    for i in range(w.ftp_list.count()):
        it = w.ftp_list.item(i)
        if it.foreground().color().alpha() < 255:
            out.append(it.text())
    return sorted(out)


_bar = w.ftp_filter_bar
_bar._on_star(3)
check('the star filter selects, it does not hide',
      selected_names() == ['a.jpg', 'b.jpg'], str(selected_names()))
check('every file stays visible',
      all(not w.ftp_list.item(i).isHidden()
          for i in range(w.ftp_list.count())))
check('what does not match is greyed lightly',
      dimmed_names() == ['c.jpg', 'd.jpg', 'e.jpg'], str(dimmed_names()))
_bar._on_star(3)

_bar.color_btns[0].setChecked(True)
_bar._emit()
check('one colour selects that colour',
      selected_names() == ['a.jpg', 'c.jpg'], str(selected_names()))
_bar.color_btns[2].setChecked(True)
_bar._emit()
check('two colours are OR',
      selected_names() == ['a.jpg', 'b.jpg', 'c.jpg'], str(selected_names()))
_bar._on_star(2)
check('stars AND colours narrow together',
      selected_names() == ['a.jpg', 'b.jpg'], str(selected_names()))
_bar.clear()
check('clearing releases the selection', selected_names() == [])
check('and takes the greying with it', dimmed_names() == [],
      str(dimmed_names()))

# The dangerous case: a filter that matches nothing must not mean "all".
check('with no filter, an empty selection still means all files',
      w._ftp_selected_paths() is None)
_bar.color_btns[4].setChecked(True)      # purple - nothing has it
_bar._emit()
check('a filter matching nothing selects nothing', selected_names() == [])
check('and does NOT fall back to all files',
      w._ftp_selected_paths() == set(), repr(w._ftp_selected_paths()))
_bar.clear()

# Channel filter, and the interaction with disabled items.
w._set_channel_mark([_paths[0]], channels.MARK_COMMONS)
w._ftp_refresh_list()
_bar.channel_btns[1].setChecked(True)    # commercial
_bar._emit()
check('a commons-marked file is never selected in the commercial list',
      'a.jpg' not in selected_names(), str(selected_names()))
_bar.clear()
w._set_channel_mark([_paths[0]], None)
w._ftp_refresh_list()

# A refresh must not silently drop an active filter.
_bar._on_star(3)
w._ftp_refresh_list()
check('the filter survives a list refresh',
      selected_names() == ['a.jpg', 'b.jpg'], str(selected_names()))
_bar.clear()

# ── 5. Der Commons-Knopf ─────────────────────────────────────────────────
_orig_info = QMessageBox.information
_told = []
QMessageBox.information = staticmethod(
    lambda parent, title, text, *a, **k: _told.append(text))
_started = []
_orig_start = w.start_upload
w.start_upload = lambda: _started.append(
    sorted({i.row() for i in w.table.selectedIndexes()}))
try:
    _bar._on_star(3)
    w._uploads_start_commons()
    check('the list selection becomes the table selection',
          _started and len(_started[-1]) == 2, str(_started[-1:]))
    check('and the ordinary upload path runs', len(_started) == 1)
    check('it switches to the module that reports progress',
          w.tabs.tabText(w.tabs.currentIndex()) == 'MediaWiki',
          w.tabs.tabText(w.tabs.currentIndex()))

    _bar.clear()
    w.table.clearSelection()
    w._uploads_start_commons()
    check('no filter and no selection still means all files',
          _started[-1] == [], str(_started[-1]))

    _bar.color_btns[4].setChecked(True)   # matches nothing
    _bar._emit()
    _before = len(_started)
    w._uploads_start_commons()
    check('an empty filter result uploads NOTHING at all',
          len(_started) == _before, str(len(_started) - _before))
    check('and says so instead of failing silently', bool(_told))
    _bar.clear()
finally:
    QMessageBox.information = _orig_info
    w.start_upload = _orig_start
    w.close()

print('---')
print('FAILURES:', fails if fails else 'none')
print(f'{len(fails)} failure(s)')
sys.exit(1 if fails else 0)
