"""UI guards added in 0.12.8: the wheel trap and the section headings.

Run as a file (main guard: the package pulls in multiprocessing).
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
    from PyQt5.QtWidgets import QApplication, QComboBox
    from PyQt5.QtGui import QWheelEvent
    from PyQt5.QtCore import Qt, QPoint, QPointF
    import Cammello                                   # noqa: F401
    from cammello.widgets import NoWheelComboBox, CollapsibleGroupBox
    from cammello import constants

    app = QApplication.instance() or QApplication(sys.argv)
    app.setStyleSheet(constants.app_style())

    def wheel(widget):
        ev = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, -120),
                         QPoint(0, -120), Qt.NoButton, Qt.NoModifier,
                         Qt.NoScrollPhase, False)
        app.sendEvent(widget, ev)
        return ev

    # ── The wheel must not change a language combo ──────────────────────
    combo = NoWheelComboBox()
    combo.addItems(['de', 'en', 'Other (ISO code)…'])
    combo.setCurrentIndex(0)
    combo.show()
    fired = []
    combo.currentIndexChanged.connect(fired.append)
    ev = wheel(combo)
    check('wheel leaves the selection alone', combo.currentIndex() == 0,
          str(combo.currentIndex()))
    check('no currentIndexChanged from the wheel', fired == [], str(fired))
    check('the event is passed on to the scroll area',
          not ev.isAccepted())

    # Control: a plain QComboBox DOES change - this is the behaviour being
    # guarded against, so if Qt ever stops doing it the guard is moot.
    plain = QComboBox()
    plain.addItems(['de', 'en', 'Other (ISO code)…'])
    plain.show()
    wheel(plain)
    check('control: a plain combo still changes on wheel',
          plain.currentIndex() == 1, str(plain.currentIndex()))

    # ── Section headings: bigger than the body text, and readable ───────
    group = CollapsibleGroupBox('Author and license')
    group.show()
    app.processEvents()
    body = app.font().pointSizeF()
    head = group._btn.font().pointSizeF()
    # 0.12.8 (Harald, tuned by eye): a step above the body text - 1.25 was
    # too loud, 1.0 too quiet. The point is that it stays a FACTOR, so the
    # heading follows the adjustable UI font.
    check('heading is a little larger than the body text',
          body < head <= body * 1.2, f'{head} vs {body}')
    check('heading is bold', group._btn.font().bold())

    light = constants.group_title_style(False)
    dark = constants.group_title_style(True)
    # 0.12.8 (Harald): white headings. "White" only means white on the DARK
    # scheme - on a light background the same intent is near-black, since
    # white would be invisible. Both are neutral and maximal-contrast.
    check('heading colour differs per colour scheme', light != dark)
    check('dark scheme heading is white', '#ffffff' in dark, dark[:80])
    check('light scheme heading is near-black', '#1a1a1a' in light,
          light[:80])
    check('light scheme heading is NOT white', '#ffffff' not in light)

    constants.set_current_input_style(True)
    check('app_style follows the active scheme',
          '#ffffff' in constants.app_style())
    constants.set_current_input_style(False)
    check('app_style switches back',
          '#1a1a1a' in constants.app_style())

    # ── Collapse arrows: a visible glyph, not the style's tiny triangle ──
    check('expanded header carries the open glyph',
          group._btn.text().startswith(CollapsibleGroupBox.ARROW_EXPANDED),
          repr(group._btn.text()[:12]))
    group.setChecked(False)
    check('collapsed header carries the closed glyph',
          group._btn.text().startswith(CollapsibleGroupBox.ARROW_COLLAPSED),
          repr(group._btn.text()[:12]))
    check('the arrow never leaks into title()',
          group.title() == 'Author and license', group.title())
    check('the glyph rides on the heading font, not the body font',
          group._btn.font().pointSizeF() > app.font().pointSizeF())
    group.setChecked(True)

    # ── IPTC: the constant creator/rights block sits in the RIGHT column ──
    from PyQt5.QtWidgets import QSplitter
    from cammello.logging_setup import setup_logging
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()
    iptc_tab = win._iptc_tab_widget
    splitter = iptc_tab.findChild(QSplitter)
    right_groups = [g.title()
                    for g in splitter.widget(1).findChildren(CollapsibleGroupBox)]
    left_groups = [g.title()
                   for g in splitter.widget(0).findChildren(CollapsibleGroupBox)]
    check('creator/rights block is in the right column',
          any('Creator' in t for t in right_groups), str(right_groups))
    check('it is NOT in the file-list column',
          not any('Creator' in t for t in left_groups), str(left_groups))
    check('it is no longer a full-width band above the splitter',
          not any(isinstance(c, CollapsibleGroupBox)
                  for c in iptc_tab.children()), 'direct children of the tab')
    # ── FTP tab: the sections fold, and start open ──────────────────────
    ftp_tab = win._ftpflickr_tab_widget
    ftp_groups = ftp_tab.findChildren(CollapsibleGroupBox)
    from PyQt5.QtWidgets import QGroupBox
    plain = [g for g in ftp_tab.findChildren(QGroupBox)
             if not isinstance(g, CollapsibleGroupBox)]
    check('FTP tab sections are collapsible', len(ftp_groups) >= 1,
          str([g.title() for g in ftp_groups]))
    check('no plain group boxes left in the FTP tab', plain == [],
          str([g.title() for g in plain]))
    check('every FTP section starts expanded',
          all(g.isChecked() for g in ftp_groups))
    if ftp_groups:
        g0 = ftp_groups[0]
        # isHidden(), not isVisible(): the tab is not the current page here,
        # so everything on it reports invisible regardless - which would make
        # the "folds away" check pass for the wrong reason and the "unfolds"
        # check fail for the wrong reason.
        g0.setChecked(False)
        check('an FTP section really folds away', g0.content.isHidden())
        g0.setChecked(True)
        check('and unfolds again', not g0.content.isHidden())

    win.close()

    print('\n' + ('ALL UI CHECKS PASSED' if not FAILURES
                  else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
