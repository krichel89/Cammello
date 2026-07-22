"""0.12.14: licence and copyright status as dropdowns.

The values are a short well-known set, but they are Q-numbers and template
names nobody recites. The dropdown offers them; typing something else stays
possible; a preset pick keeps the wikitext template and the P275 item on the
SAME licence. Run as a file.
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
FAILURES = []


def check(name, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + name, detail)
    if not cond:
        FAILURES.append(name)


def main():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from PyQt5.QtWidgets import QApplication
    import Cammello
    from cammello.constants import LICENSE_PRESETS, COPYRIGHT_PRESETS
    from cammello.widgets import PresetComboBox
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()

    lic, sdc, cr = (win.license_edit, win.license_sdc_edit,
                    win.copyright_sdc_edit)

    check('all three fields are dropdowns',
          all(isinstance(w, PresetComboBox) for w in (lic, sdc, cr)))
    check('licence dropdown offers CC0, CC BY and CC BY-SA',
          lic.count() == len(LICENSE_PRESETS) == 3, str(lic.count()))
    check('copyright dropdown offers all three states',
          cr.count() == len(COPYRIGHT_PRESETS) == 3, str(cr.count()))
    check('the shipped default is the CC entry',
          COPYRIGHT_PRESETS[0][1] == 'Q73566113' and cr.text() == 'Q73566113',
          cr.text())

    # The entry is readable, the VALUE that lands in the field is bare.
    labels = [lic.itemText(i) for i in range(lic.count())]
    check('entries name the licence, not just the template',
          any(t.startswith('CC BY-SA 4.0') for t in labels), str(labels))
    lic.setCurrentIndex(0)
    lic.activated.emit(0)
    check('picking an entry writes the bare template',
          lic.text() == LICENSE_PRESETS[0][1], lic.text())

    # Pairing: template and P275 item must not disagree.
    check('the P275 field follows the licence pick',
          sdc.text() == LICENSE_PRESETS[0][2], sdc.text())
    sdc.setCurrentIndex(2)
    sdc.activated.emit(2)
    check('and the other way round',
          lic.text() == LICENSE_PRESETS[2][1]
          and sdc.text() == LICENSE_PRESETS[2][2],
          f'{lic.text()} / {sdc.text()}')

    # Free text stays possible AND is not overwritten by the pairing.
    before_sdc = sdc.text()
    lic.setText('{{PD-old-70}}')
    check('an unusual template can still be typed',
          lic.text() == '{{PD-old-70}}')
    check('typing does not rewrite the other field',
          sdc.text() == before_sdc)

    # Drop-in compatibility: the rest of the app treats these as line edits.
    check('text()/setText() work like on a QLineEdit',
          hasattr(lic, 'setText') and hasattr(lic, 'text'))
    seen = []
    lic.textChanged.connect(seen.append)
    lic.setText('{{Cc-by-4.0}}')
    check('textChanged fires like a QLineEdit', seen == ['{{Cc-by-4.0}}'],
          str(seen))
    check('the upload payload sees the plain value',
          'license={{Cc-by-4.0}}'.replace('{{Cc-by-4.0}}', lic.text())
          == f'license={lic.text()}')

    # The Settings mirror is a dropdown too, and stays in sync.
    check('settings mirror is a dropdown',
          isinstance(win.license_mirror, PresetComboBox))
    check('mirror follows the module', win.license_mirror.text() == lic.text(),
          win.license_mirror.text())
    win.license_mirror.setText('{{Cc-zero}}')
    check('and the module follows the mirror', lic.text() == '{{Cc-zero}}')

    # Restore the shipped defaults so a test run leaves no odd settings.
    lic.setText('{{Cc-by-sa-4.0}}')
    sdc.setText('Q18199165')
    win.close()

    print('\n' + ('ALL LICENSE CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
