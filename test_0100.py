"""Offscreen checks for the 0.10.0 changes:

  * upload settings visible again in the MediaWiki tab AND mirrored into the
    Settings tab (bidirectional sync, persistence stays with the primaries),
  * IPTC / FTP settings mirrored the same way,
  * hidden per-tab feature switches (feature_culling / feature_iptc /
    feature_ftp) incl. the references in other tabs,
  * culling: three send targets (MediaWiki / FTP / folder), folder copy
    worker with skip-existing semantics,
  * Wikidata completer popup styled per color scheme.

The feature-switch checks WRITE QSettings keys; previous values are restored
at the end so a run on a real machine does not change the user's setup.
"""
import os
import sys
import tempfile

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

import Cammello  # backwards-compatible shim
from cammello.constants import (APP_NAME, set_current_input_style,
                                completer_popup_style, current_style_is_dark)
from cammello.logging_setup import setup_logging
from cammello.main_window import _apply_feature_cli
from cammello.mw_culling import _FolderCopyWorker
from cammello import iptc as iptc_mod

app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


settings = QSettings(APP_NAME, 'Main')
FEATURE_KEYS = ('feature_culling', 'feature_iptc', 'feature_ftp',
                'feature_flickr')
saved = {k: settings.value(k) for k in FEATURE_KEYS}


def set_features(culling=True, iptc=True, ftp=True, flickr=True):
    settings.setValue('feature_culling', culling)
    settings.setValue('feature_iptc', iptc)
    settings.setValue('feature_ftp', ftp)
    settings.setValue('feature_flickr', flickr)
    settings.sync()


def tab_names(w):
    return [w.tabs.tabText(i) for i in range(w.tabs.count())]


def make_window():
    return Cammello.MainWindow(logger, emitter, gui_handler, log_path)


try:
    # ── 1) All features on: settings visible twice, mirrors sync ─────────────
    set_features(True, True, True)
    w = make_window()
    have_iptc = iptc_mod.available()

    # Upload settings group is back in the MediaWiki tab (0.10.0 regression:
    # it was detached for the Settings-tab move but never re-attached).
    grp = w._mw_settings_group
    check('upload settings attached', grp.parent() is not None)
    check('upload settings in a layout',
          grp.parentWidget() is not None and grp.parentWidget().layout() is not None)

    # Mirrors exist and sync in BOTH directions.
    w.author_edit.setText('primary->mirror')
    check('author primary->mirror',
          w.author_mirror.text() == 'primary->mirror')
    w.author_mirror.setText('mirror->primary')
    check('author mirror->primary',
          w.author_edit.text() == 'mirror->primary')

    w.creator_edit.setText('Q640')
    check('creator primary->mirror', w.creator_mirror.text() == 'Q640')

    if have_iptc:
        check('tabs all-on',
              tab_names(w) == ['Culling', 'MediaWiki', 'IPTC', 'Uploads',
                               'Settings', 'Log', 'About'],
              str(tab_names(w)))
        # FTP mirrors: line edit, combo, checkbox.
        w.ftp_host_edit.setText('ftp.example.org')
        check('ftp host primary->mirror',
              w.ftp_host_mirror.text() == 'ftp.example.org')
        w.ftp_host_mirror.setText('other.example.org')
        check('ftp host mirror->primary',
              w.ftp_host_edit.text() == 'other.example.org')
        w.ftp_protocol_mirror.setCurrentIndex(1)
        check('ftp protocol mirror->primary',
              w.ftp_protocol_combo.currentIndex() == 1)
        w.ftp_store_pw_cb.setChecked(True)
        check('ftp store-pw primary->mirror',
              w.ftp_store_pw_mirror.isChecked())
        w.ftp_store_pw_mirror.setChecked(False)
        check('ftp store-pw mirror->primary',
              not w.ftp_store_pw_cb.isChecked())
        check('ftp password mirror echo',
              w.ftp_password_mirror.echoMode() == w.ftp_password_edit.echoMode())
        # IPTC mirrors.
        w.iptc_export_dir_edit.setText('/tmp/export')
        check('iptc dir primary->mirror',
              w.iptc_export_dir_mirror.text() == '/tmp/export')
        w.iptc_inplace_mirror.setChecked(True)
        check('iptc inplace mirror->primary', w.iptc_inplace_cb.isChecked())
        w.iptc_inplace_mirror.setChecked(False)
        # Culling: three send targets present.
        check('cull ftp button exists', hasattr(w, 'cull_ftp_btn'))
    if hasattr(w, '_cull_wb'):
        w._cull_shutdown()
    w.deleteLater()
    app.processEvents()

    # ── 2) Feature switches ──────────────────────────────────────────────────
    if have_iptc:
        set_features(culling=True, iptc=True, ftp=False)
        w = make_window()
        names = tab_names(w)
        check('ftp off: no FTP tab', 'FTP' not in names, str(names))
        check('ftp off: no cull FTP button', not hasattr(w, 'cull_ftp_btn'))
        check('ftp off: no FTP mirror', not hasattr(w, 'ftp_host_mirror'))
        check('ftp off: IPTC still there', 'IPTC' in names)
        if hasattr(w, '_cull_wb'):
            w._cull_shutdown()
        w.deleteLater(); app.processEvents()

        set_features(culling=True, iptc=False, ftp=True)
        w = make_window()
        names = tab_names(w)
        check('iptc off: no IPTC tab', 'IPTC' not in names, str(names))
        check('iptc off: the uploads module stays', 'Uploads' in names,
              str(names))
        # 0.10.0: the FTP tab has its own file list and an as-is upload
        # button even when IPTC is off (the IPTC-writing variant is gone).
        check('iptc off: FTP upload button is the as-is variant',
              hasattr(w, 'ftp_upload_btn')
              and w.ftp_upload_btn.text() == 'Upload',
              getattr(getattr(w, 'ftp_upload_btn', None), 'text',
                      lambda: 'MISSING')())
        check('iptc off: no IPTC mirror', not hasattr(w, 'iptc_inplace_mirror'))
        check('iptc off: FTP mirror present', hasattr(w, 'ftp_host_mirror'))
        check('iptc off: cull FTP button present', hasattr(w, 'cull_ftp_btn'))
        if hasattr(w, '_cull_wb'):
            w._cull_shutdown()
        w.deleteLater(); app.processEvents()

        set_features(culling=False, iptc=True, ftp=True)
        w = make_window()
        names = tab_names(w)
        check('culling off: no Culling tab', 'Culling' not in names, str(names))
        check('culling off: MediaWiki first', names[0] == 'MediaWiki')
        check('culling off: no culling settings box',
              not hasattr(w, '_cull_settings_box'))
        w.deleteLater(); app.processEvents()

    # ── 3) Hidden CLI switch parsing ─────────────────────────────────────────
    argv = ['Cammello.py', '--disable-tab', 'ftp', '--foo',
            '--enable-tab', 'culling']
    out = _apply_feature_cli(argv)
    check('cli: args consumed', out == ['Cammello.py', '--foo'], str(out))
    check('cli: ftp persisted off',
          settings.value('feature_ftp', True, type=bool) is False)
    check('cli: culling persisted on',
          settings.value('feature_culling', False, type=bool) is True)
    out = _apply_feature_cli(['Cammello.py', '--disable-tab', 'nosuchtab'])
    check('cli: unknown tab ignored', out == ['Cammello.py'])

    # ── 4) Folder copy worker: copies, skips existing ────────────────────────
    with tempfile.TemporaryDirectory() as src, \
            tempfile.TemporaryDirectory() as dst:
        a = os.path.join(src, 'IMG_0001.jpg')
        b = os.path.join(src, 'IMG_0001.cr3')
        sc = os.path.join(src, 'IMG_0001.xmp')
        for p, content in ((a, b'jpegdata'), (b, b'rawdata'), (sc, b'<xmp/>')):
            with open(p, 'wb') as f:
                f.write(content)
        # Pre-existing target: must be skipped, not overwritten.
        with open(os.path.join(dst, 'IMG_0001.jpg'), 'wb') as f:
            f.write(b'OLD')
        worker = _FolderCopyWorker([a, b, sc], dst, logger)
        summaries = []
        worker.done.connect(summaries.append)
        worker.run()          # synchronous: run() directly, no thread needed
        check('copy: raw arrived',
              open(os.path.join(dst, 'IMG_0001.cr3'), 'rb').read() == b'rawdata')
        check('copy: sidecar arrived',
              os.path.exists(os.path.join(dst, 'IMG_0001.xmp')))
        check('copy: existing jpg NOT overwritten',
              open(os.path.join(dst, 'IMG_0001.jpg'), 'rb').read() == b'OLD')
        check('copy: summary counts', summaries and '2/3' in summaries[0]
              and 'skipped' in summaries[0], str(summaries))

    # ── 5) Completer popup style follows the scheme ──────────────────────────
    set_current_input_style(False)
    light = completer_popup_style()
    check('popup light has white bg', 'background: white' in light)
    check('is_dark False', current_style_is_dark() is False)
    set_current_input_style(True)
    dark = completer_popup_style()
    check('popup dark has dark bg', 'background: #2b2b2b' in dark)
    check('popup dark has light text', 'color: #e8e8e8' in dark)
    check('is_dark True', current_style_is_dark() is True)
    set_current_input_style(False)

finally:
    # Restore the user's feature switches.
    for k, v in saved.items():
        if v is None:
            settings.remove(k)
        else:
            settings.setValue(k, v)
    settings.sync()

print('---')
print('FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
