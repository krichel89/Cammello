"""0.12.11 tooltips: field explanations in the MediaWiki module.
Run as a file."""
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
    from PyQt5.QtWidgets import QApplication, QFormLayout
    import Cammello                                    # noqa: F401
    from cammello.i18n import set_language
    from cammello.editors import StructuredDescriptionEditor
    from cammello.logging_setup import setup_logging

    app = QApplication.instance() or QApplication(sys.argv)
    set_language('de')

    ed = StructuredDescriptionEditor(is_base=False)
    ed.show()
    app.processEvents()

    # Field explanations: present, translated, and they explain what BELONGS
    # in the field (format + example), not merely what the field is called.
    tip = ed.depicts.toolTip()
    check('depicts explains what belongs there',
          'Q42' in tip and ';' in tip, tip[:50])
    check('depicts tooltip is German', 'Was das Bild ZEIGT' in tip, tip[:30])
    check('override combo explains each choice',
          ed.override_combo.toolTip().count('\u201e') >= 3
          or ed.override_combo.toolTip().count('"') >= 3)
    check('categories tooltip carries an example',
          'Berlinale' in ed.categories.toolTip())

    form = ed.findChild(QFormLayout)
    lbl = form.labelForField(ed.depicts)
    check('the row label answers too',
          lbl is not None and lbl.toolTip() == ed.depicts.toolTip())

    base = StructuredDescriptionEditor(is_base=True)
    check('created-during warns edition vs series',
          'Berlinale 2026' in base.created_during.toolTip())
    check('gallery suffix explains where the name lands',
          bool(base.gallery_suffix.toolTip()))

    # Upload settings: all seven fields explained, incl. what the cryptic
    # SDC defaults MEAN.
    logger, emitter, gui_handler, log_path = setup_logging()
    win = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    win.show()
    app.processEvents()
    fields = [win.author_edit, win.source_edit, win.permission_edit,
              win.license_edit, win.creator_edit, win.license_sdc_edit,
              win.copyright_sdc_edit]
    check('all seven settings fields have explanations',
          all(f.toolTip() for f in fields),
          str([i for i, f in enumerate(fields) if not f.toolTip()]))
    check('author shows the wikitext pattern',
          '[[User:' in win.author_edit.toolTip())
    check('license default Q18199165 is explained',
          'CC BY-SA 4.0' in win.license_sdc_edit.toolTip())
    # 0.12.14: Harald checked the two items I could not verify, so the
    # tooltip explains all three copyright-status values again.
    tip_cr = win.copyright_sdc_edit.toolTip()
    check('copyright tooltip explains all three items',
          all(q in tip_cr for q in ('Q73566113', 'Q50423863', 'Q19652')),
          tip_cr[:40])

    # The property numbers Harald was actually asked for must be NAMED in
    # the tooltip of their own field: looking one up should not require
    # knowing which field it belongs to.
    for label, widget, prop in (
            ('depicts', ed.depicts, 'P180'),
            ('created during', base.created_during, 'P10408'),
            ('creator', win.creator_edit, 'P170'),
            ('license', win.license_sdc_edit, 'P275'),
            ('copyright status', win.copyright_sdc_edit, 'P6216')):
        check(f'{label} tooltip names {prop}', prop in widget.toolTip(),
              widget.toolTip()[:24])

    # The double concept (wikitext half / structured half) must be spelled
    # out wherever two fields state the SAME fact in two forms.
    check('author points at its structured twin',
          'P170' in win.author_edit.toolTip())
    check('creator points back at the author line',
          'Autor' in win.creator_edit.toolTip())
    check('license template points at P275',
          'P275' in win.license_edit.toolTip())
    caption_edit = ed.captions_editor._rows[0]['edit']
    check('caption explains the two storage forms',
          'Wikitext' in caption_edit.toolTip()
          and 'STRUKTURIERTE' in caption_edit.toolTip(),
          caption_edit.toolTip()[:30])
    info_edit = ed.captions_editor._rows[0]['info']
    check('description names itself the wikitext half',
          'WIKITEXT' in info_edit.toolTip())
    # Section headings explain their SCOPE (Harald's wording): forever /
    # one session / one picture. The header button must carry it too -
    # that is what a reader points at.
    from cammello.widgets import CollapsibleGroupBox as _CGB
    groups = {g.title(): g for g in win._mw_tab_widget.findChildren(_CGB)}
    check('all three MediaWiki sections have a tooltip',
          all(g.toolTip() for g in groups.values()),
          str([t for t, g in groups.items() if not g.toolTip()]))
    check('the header button carries it as well',
          all(g._btn.toolTip() == g.toolTip() for g in groups.values()))
    scopes = ' '.join(g.toolTip() for g in groups.values())
    check('the three scopes are distinguishable',
          'immer gleich' in scopes and 'Sitzung' in scopes
          and 'Motiv' in scopes, scopes[:60])

    win.close()

    print('\n' + ('ALL TOOLTIP CHECKS PASSED' if not FAILURES
                   else f'FAILURES: {FAILURES}'))
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
