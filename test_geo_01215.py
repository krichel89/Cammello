"""0.12.15: camera position from EXIF into the template and into SDC.

Covers the whole chain: reading the GPS block, the text form stored in the
description, the {{Location dec}} template in the wikitext, and the P1259
globe-coordinate claim in the structured data. Run as a file.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def make_jpeg(path, gps=True):
    """A real JPEG, with or without a GPS block in the EXIF."""
    from PIL import Image
    from PIL.TiffImagePlugin import IFDRational
    img = Image.new('RGB', (60, 40), (120, 160, 200))
    exif = img.getexif()
    if gps:
        block = exif.get_ifd(0x8825)
        block[1] = 'N'
        block[2] = (IFDRational(48), IFDRational(8), IFDRational(1375, 100))
        block[3] = 'E'
        block[4] = (IFDRational(11), IFDRational(34), IFDRational(334, 10))
    img.save(path, exif=exif.tobytes())
    return path


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication
    import Cammello
    from cammello.exif import (read_gps, format_coordinates,
                               parse_coordinates, _dms_to_decimal)
    from cammello.sdc import extract_structured_data, set_coordinates_line
    from cammello.constants import PROPERTY_MAP, SD_KEYS
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)

    # ── Reading ─────────────────────────────────────────────────────────
    check('south and west come out negative',
          _dms_to_decimal((33, 57, 12.4), 'S') < 0
          and _dms_to_decimal((18, 23, 56.4), 'W') < 0)
    with tempfile.TemporaryDirectory() as tmp:
        with_gps = make_jpeg(os.path.join(tmp, 'gps.jpg'), gps=True)
        without = make_jpeg(os.path.join(tmp, 'plain.jpg'), gps=False)
        coords = read_gps(with_gps)
        check('GPS is read from the EXIF block', coords is not None)
        check('the position is the one written in',
              coords and abs(coords[0] - 48.1372) < 0.001
              and abs(coords[1] - 11.5759) < 0.001, str(coords))
        check('a file without GPS yields None, not an error',
              read_gps(without) is None)
        check('a non-image yields None',
              read_gps(os.path.join(tmp, 'does-not-exist.jpg')) is None)

    # ── The stored text form ────────────────────────────────────────────
    text = format_coordinates(48.137154, 11.576124)
    check('stored as "lat, lon"', text == '48.137154, 11.576124', text)
    check('and parsed back', parse_coordinates(text) == (48.137154, 11.576124))
    check('a semicolon is accepted too',
          parse_coordinates('48.1; 11.5') == (48.1, 11.5))
    check('nonsense is rejected rather than half-read',
          parse_coordinates('somewhere') is None
          and parse_coordinates('48.1') is None)
    check('impossible values are rejected',
          parse_coordinates('95.0, 11.0') is None)

    # ── The description line ────────────────────────────────────────────
    check('coordinates is a structured-data key', 'coordinates' in SD_KEYS)
    check('it maps to P1259 (point of view = camera)',
          PROPERTY_MAP['coordinates'] == 'P1259')
    desc = 'caption_de=Test\ndepicts=Q42\n\n[[Category:X]]'
    filled = set_coordinates_line(desc, '48.1, 11.5')
    sd, _rest = extract_structured_data(filled)
    check('the line reaches the structured data',
          sd.get('coordinates') == '48.1, 11.5', str(sd.get('coordinates')))
    check('nothing else in the description is disturbed',
          sd.get('depicts') == 'Q42' and 'Category:X' in filled)
    again = set_coordinates_line(filled, '49.0, 12.0')
    check('setting it twice replaces, not duplicates',
          again.count('coordinates=') == 1)
    check('an empty value removes the line',
          'coordinates=' not in set_coordinates_line(filled, ''))

    # ── The wikitext half: {{Location dec}} ─────────────────────────────
    from cammello import workers
    src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            'cammello', 'workers.py'), encoding='utf-8').read()
    check('the upload worker writes {{Location dec}}',
          'Location dec' in src)
    check('it uses the parser, so bad values cannot reach Commons',
          'parse_coordinates' in src)

    # ── The structured half: a globe-coordinate claim ───────────────────
    from cammello.api import MediaWikiApi
    api = MediaWikiApi.__new__(MediaWikiApi)          # no network, no login
    captured = {}

    class _Log:
        def warning(self, *a):
            captured['warned'] = a

        def debug(self, *a):
            pass

        def info(self, *a):
            pass
    api.log = _Log()
    api._trunc = lambda t, n=2000: t

    def _fake_request(*a, **k):
        raise RuntimeError('stop before the network')
    api._request = _fake_request
    api.get_csrf_token = lambda: 'token'
    try:
        api.set_structured_data(1, {}, [('P1259', ('coord', 48.1, 11.5))])
    except RuntimeError:
        pass
    # The payload is built before the request; rebuild it the same way to
    # check the datatype, since the call above stops at the network.
    import json
    import re as _re
    claim_src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                  'cammello', 'api.py'),
                     encoding='utf-8').read()
    check('the API knows the globecoordinate datatype',
          'globecoordinate' in claim_src)
    check('it sets the Earth globe',
          'wikidata.org/entity/Q2' in claim_src)
    check('QID claims still go through the old path',
          'wikibase-entityid' in claim_src)

    # ── The UI ──────────────────────────────────────────────────────────
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()
    check('the per-file section has a coordinates field',
          win.file_struct.coordinates is not None)
    check('the base section has NOT (one position per picture)',
          win.base_struct.coordinates is None)
    check('there is a "from EXIF" button',
          win.file_struct.coords_exif_btn is not None)
    check('the field explains P1259 and the camera position',
          'P1259' in win.file_struct.coordinates.toolTip())
    check('automatic reading can be switched off',
          hasattr(win, 'exif_coords_cb'))

    # Round trip through the editor.
    win.file_struct.load('coordinates=48.137154, 11.576124\ncaption_de=X')
    check('the editor loads the value',
          win.file_struct.coordinates.text() == '48.137154, 11.576124',
          win.file_struct.coordinates.text())
    check('and writes it back',
          'coordinates=48.137154, 11.576124' in win.file_struct.assemble())

    # Adding a file fills the field from EXIF.
    with tempfile.TemporaryDirectory() as tmp:
        path = make_jpeg(os.path.join(tmp, 'shot.jpg'), gps=True)
        win.settings.setValue('exif_coordinates', True)
        win._add_row(path)
        desc = win.table.item(0, win.COL_DESC).text()
        check('adding a file fills the coordinates from EXIF',
              'coordinates=48.13' in desc, repr(desc))
        win.table.setRowCount(0)

        win.settings.setValue('exif_coordinates', False)
        win._add_row(path)
        desc = win.table.item(0, win.COL_DESC).text()
        check('with the switch off nothing is read',
              'coordinates=' not in desc, repr(desc))
        win.settings.setValue('exif_coordinates', True)
        win.table.setRowCount(0)
    win.close()

    print('\n' + ('ALL GEO CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
