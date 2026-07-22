"""Caption/description editors (the bulk-edit dialog was removed in
0.12.6 - multi-select editing in the editor covers it)."""
import re
from PyQt5.QtWidgets import (QInputDialog, QMessageBox, QWidget, QLabel, QLineEdit, QPushButton,
                             QTextEdit, QVBoxLayout, QHBoxLayout,
                             QFormLayout)
from PyQt5.QtCore import pyqtSignal
from .constants import *
from .constants import _caption_extra_langs
from .sdc import *
from .i18n import tr
from .wikidata import *
from .wikidata import _style_wd_field
from .widgets import *
from .widgets import _VGrip


class CaptionsEditor(QWidget):
    """A small editor for multilingual captions: one row per language with a
    language dropdown, a text field and a remove button, plus an "Add language"
    button. Always keeps at least one row."""

    changed = pyqtSignal()
    committed = pyqtSignal()   # fires on field switch (editing finished), not per keystroke

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = []  # list of dicts: {widget, combo, edit}

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        self._rows_box = QVBoxLayout()
        self._rows_box.setContentsMargins(0, 0, 0, 0)
        self._rows_box.setSpacing(4)
        outer.addLayout(self._rows_box)

        btn_row = FlowLayout(spacing=8)
        btn_row.setContentsMargins(0, 0, 0, 0)
        add_btn = QPushButton(tr('Add language'))
        add_btn.clicked.connect(
            lambda: (self.add_row(), self.changed.emit(), self.committed.emit()))
        btn_row.addWidget(add_btn)
        info_btn = QPushButton(tr('Information from caption'))
        info_btn.setToolTip(
            tr('Fills the Information wikitext of each language with its '
               'caption text, where the Information field is still empty.'))
        info_btn.clicked.connect(self._info_from_captions)
        btn_row.addWidget(info_btn)
        outer.addLayout(btn_row)

        self.add_row()  # start with one empty row

    def add_row(self, lang='en', value='', info=''):
        row_widget = QWidget()
        v = QVBoxLayout(row_widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)

        # NoWheelComboBox: scrolling the page must not change the language
        # (and this combo's action entries open dialogs) - see widgets.
        combo = NoWheelComboBox()
        self._populate_combo(combo, lang)
        combo.setMaximumWidth(150)
        combo.currentIndexChanged.connect(
            lambda _i, c=combo: self._on_lang_combo_changed(c))

        edit = QLineEdit(value)
        edit.setPlaceholderText(tr('Caption, e.g. Harald Krichel at the Berlinale 2026'))
        edit.setToolTip(tr(
            'The short caption of the file, in the language on the left - '
            'ONE sentence,\nno wiki markup: "Harald Krichel at the '
            'Berlinale 2026".\n\n'
            'This is the STRUCTURED caption (Wikibase label). Commons '
            'stores every\nfile TWICE: as wikitext (the Information '
            'template - the field below)\nand as structured data '
            '(machine-readable statements - this field).\nThey say the '
            'same thing in two forms; that is why Cammello asks for\nboth. '
            '"Information from caption" copies this text down.'))

        remove = QPushButton('×')
        remove.setFixedWidth(28)
        remove.setToolTip(tr('Remove this language'))

        top.addWidget(combo)
        top.addWidget(edit, 1)
        top.addWidget(remove)
        v.addLayout(top)

        # Second line: the {{lang|1=…}} description for the Information
        # template. Wide (≈90% of the column), right-aligned, height-resizable.
        bottom = QHBoxLayout()
        bottom.setContentsMargins(0, 0, 0, 0)
        bottom.addStretch(1)                      # ~10% spacer -> right-aligned
        info_edit = QTextEdit()
        info_edit.setPlainText(info)
        info_edit.setPlaceholderText(
            tr('Information wikitext for this language (uploaded as {{%s|1=…}})')
            % lang)
        info_edit.setToolTip(tr(
            'The description in the Information template - the WIKITEXT '
            'half of the\npair (the caption above is the structured half). '
            'May be longer than the\ncaption and may contain links and '
            'templates.\n\n'
            'Uploaded as {{<language>|1=your text}}. Empty is allowed: '
            'then the file\npage shows no description text in this '
            'language.'))
        info_edit.setAcceptRichText(False)
        two_lines = info_edit.fontMetrics().lineSpacing() * 2 + 12
        info_edit.setFixedHeight(two_lines)
        bottom.addWidget(info_edit, 9)            # ~90% of the width
        v.addLayout(bottom)

        # Drag grip to resize the info field's height (aligned under it).
        grip_row = QHBoxLayout()
        grip_row.setContentsMargins(0, 0, 0, 0)
        grip_row.addStretch(1)
        grip_row.addWidget(_VGrip(info_edit, two_lines), 9)
        v.addLayout(grip_row)

        self._rows_box.addWidget(row_widget)

        entry = {'widget': row_widget, 'combo': combo, 'edit': edit,
                 'info': info_edit}
        self._rows.append(entry)

        def _update_info_placeholder():
            info_edit.setPlaceholderText(
                tr('Information wikitext for this language (uploaded as {{%s|1=…}})')
                % combo.currentData())
        combo.currentIndexChanged.connect(lambda *_: _update_info_placeholder())
        combo.currentIndexChanged.connect(lambda *_: self.changed.emit())
        combo.currentIndexChanged.connect(lambda *_: self.committed.emit())
        edit.textChanged.connect(lambda *_: self.changed.emit())
        edit.editingFinished.connect(self.committed)
        # QTextEdit has no editingFinished; live sync uses changed (textChanged).
        info_edit.textChanged.connect(lambda *_: self.changed.emit())
        remove.clicked.connect(lambda: self._remove(entry))

    def _populate_combo(self, combo, want_code):
        """Fill a language combo with the current choices plus the two action
        entries, then select want_code (inserting it ad-hoc if it is not a
        listed choice, e.g. a code still used by a row but no longer saved).
        Also records the selected real code as the combo's fallback."""
        combo.blockSignals(True)
        combo.clear()
        for code, name in caption_language_choices():
            combo.addItem(f'{code} – {name}' if name else code, code)
        combo.addItem(tr('Other (ISO code)…'), '__other__')
        combo.addItem(tr('Remove saved language…'), '__forget__')
        idx = combo.findData(want_code)
        if idx < 0 and want_code and want_code not in ('__other__', '__forget__'):
            combo.insertItem(combo.findData('__other__'),
                             format_caption_language(want_code), want_code)
            idx = combo.findData(want_code)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setProperty('prev_code', combo.currentData())
        combo.blockSignals(False)

    def _restore_combo(self, combo, code):
        """Put combo back on a real language code without emitting signals."""
        combo.blockSignals(True)
        idx = combo.findData(code)
        if idx < 0 and code:
            combo.insertItem(combo.findData('__other__'),
                             format_caption_language(code), code)
            idx = combo.findData(code)
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setProperty('prev_code', combo.currentData())
        combo.blockSignals(False)

    def _rebuild_combos(self):
        """Refill every row's combo from the (just changed) saved list, keeping
        each row on the language it currently shows."""
        for e in self._rows:
            combo = e['combo']
            want = combo.currentData()
            if want in ('__other__', '__forget__', None):
                want = combo.property('prev_code')
            self._populate_combo(combo, want)

    def _on_lang_combo_changed(self, combo):
        """Dispatch the two action entries; for a real language, just record it
        as this combo's fallback selection."""
        data = combo.currentData()
        if data == '__other__':
            self._add_other_language(combo)
            return
        if data == '__forget__':
            self._forget_language_dialog(combo)
            return
        combo.setProperty('prev_code', data)

    def _add_other_language(self, combo):
        """'Other (ISO code)…' selected: ask for a code, validate it, insert
        it into the dropdown, select it, and PERSIST it - freely entered
        codes extend the four-language default list permanently."""
        prev = combo.property('prev_code')
        code, ok = QInputDialog.getText(
            self, tr('Caption language'),
            tr('ISO language code (e.g. nl, pt, ja):'))
        code = (code or '').strip().lower()
        if not ok or not re.fullmatch(r'[a-z]{2,3}', code):
            self._restore_combo(combo, prev)
            if ok:
                QMessageBox.warning(self, tr('Caption language'),
                                    tr('Not a valid ISO code: {code}').format(
                                        code=code or '?'))
            return
        remember_caption_language(code)
        # Rebuild all rows so the new code appears in every dropdown, and put
        # this row on it.
        self._rebuild_combos()
        self._restore_combo(combo, code)
        self.changed.emit()
        self.committed.emit()

    def _forget_language_dialog(self, combo):
        """'Remove saved language…' selected: let the user delete one of the
        codes they previously added, then refresh every dropdown. This row
        keeps whatever language it had; a row still using a removed code keeps
        it as an ad-hoc entry (its caption is never lost)."""
        prev = combo.property('prev_code')
        self._restore_combo(combo, prev)          # this action never moves the row
        extras = _caption_extra_langs()
        if not extras:
            QMessageBox.information(
                self, tr('Caption language'),
                tr('No saved languages to remove. The four default languages '
                   'cannot be removed.'))
            return
        items = [format_caption_language(c) for c in extras]
        choice, ok = QInputDialog.getItem(
            self, tr('Remove saved language'),
            tr('Remove which saved language from the dropdown?'),
            items, 0, False)
        if not ok:
            return
        code = extras[items.index(choice)]
        forget_caption_language(code)
        self._rebuild_combos()
        self.changed.emit()
        self.committed.emit()

    def _info_from_captions(self):
        """Copy each row's caption into its Information field, but only where
        that field is still empty (never overwrite hand-written wikitext)."""
        changed = False
        for e in self._rows:
            caption = e['edit'].text().strip()
            if caption and not e['info'].toPlainText().strip():
                e['info'].setPlainText(caption)
                changed = True
        if changed:
            self.changed.emit()
            self.committed.emit()

    def _remove(self, entry):
        entry['widget'].setParent(None)
        self._rows.remove(entry)
        if not self._rows:
            self.add_row()  # always keep at least one row
        self.changed.emit()
        self.committed.emit()

    def get_captions(self):
        """Return {lang: value} for all non-empty caption rows."""
        out = {}
        for e in self._rows:
            lang = e['combo'].currentData()
            val = e['edit'].text().strip()
            if val:
                out[lang] = val
        return out

    def get_infos(self):
        """Return {lang: wikitext} for all non-empty Information fields."""
        out = {}
        for e in self._rows:
            lang = e['combo'].currentData()
            val = e['info'].toPlainText().strip()
            if val:
                out[lang] = val
        return out

    def set_language_data(self, captions, infos):
        """Rebuild the rows from {lang: caption} and {lang: info}; a language
        present in either dict gets a row."""
        captions = captions or {}
        infos = infos or {}
        for e in list(self._rows):
            e['widget'].setParent(None)
        self._rows = []
        langs = list(dict.fromkeys(list(captions) + list(infos)))
        if langs:
            for lang in langs:
                self.add_row(lang, captions.get(lang, ''), infos.get(lang, ''))
        else:
            self.add_row()

    def set_captions(self, captions):
        self.set_language_data(captions, {})


# Lines that are recognized key=value assignments (used to compute leftover text).

class StructuredDescriptionEditor(QWidget):
    """Structured single-line editor for a description_all value: multilingual
    captions plus depicts (P180), created-during (P10408), a categories field
    and a resizable free-text area for extra wikitext and comments. Used for
    both the per-file and the base description when expert mode is off.

    Creator, copyright and license (P170/P6216/P275) are edited in the
    "Upload settings" section (they apply to every file in the batch) and are
    intentionally NOT part of this widget.

    is_base: created-during and the gallery suffix are only shown in the
    base editor (they apply to every file), so the per-file editor keeps
    only captions, depicts, categories and the extra text.
    """

    changed = pyqtSignal()
    committed = pyqtSignal()   # fires on field switch, not per keystroke
    suggest_requested = pyqtSignal()        # created-during category (base)
    suggest_depicts_requested = pyqtSignal()  # depicts categories (per-file)

    def __init__(self, parent=None, is_base=True):
        super().__init__(parent)
        self.is_base = is_base
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel(tr('Captions:')))
        self.captions_editor = CaptionsEditor()
        self.captions_editor.changed.connect(self.changed)
        self.captions_editor.committed.connect(self.committed)
        layout.addWidget(self.captions_editor)

        form = QFormLayout()

        # Depicts (P180) — per-file only (no depicts in the base description).
        if not self.is_base:
            self.depicts = QLineEdit()
            self.depicts.setPlaceholderText(tr('e.g.') + ' Q42; Q64')
            _style_wd_field(self.depicts, multi=True, searchable=True)
            self._depicts_suggest = WikidataSuggest(self.depicts, multi=True)
            self.depicts.setToolTip(tr(
                'P180 "depicts": what the picture SHOWS, as Wikidata items '
                '- for\nportraits the person in the picture, e.g. Q42 for '
                'Douglas Adams.\nSeveral items separated by ;\n\n'
                'Enter Q-numbers directly, or type a name and pick from the '
                'live\nsuggestions - the field then inserts the Q-number '
                'for you.\n\n'
                'Becomes the structured "depicts" statement (P180) of the '
                'file on Commons.\nRequired for the upload; if the picture '
                'has no suitable item, choose a\nreason in the field '
                'below instead.'))
        else:
            self.depicts = None

        # Depicts override (per-file): depicts is mandatory for the upload,
        # but one of these waives it. A dropdown keeps the full, readable
        # labels (the checkbox texts were too long to sit side by side).
        # itemData: '' = no override; else the depicts_override= value.
        if not self.is_base:
            self.override_combo = NoWheelComboBox()
            self.override_combo.setToolTip(tr(
                'Only used when the depicts field above stays empty - pick '
                'WHY:\n\n'
                '"No Wikidata item": the person or subject shown has no '
                'item (yet).\n'
                '"Not applicable": the picture shows no identifiable '
                'subject.\n'
                '"Unidentified": there is a subject, but you do not know '
                'who or what it is.\n\n'
                'Stored as depicts_override= in the description; the upload '
                'then\nproceeds without a depicts statement.'))
            self.override_combo.addItem(tr('depicts is set (required)'), '')
            self.override_combo.addItem(tr('No Wikidata item'), 'no_item')
            self.override_combo.addItem(tr('Not applicable'), 'not_applicable')
            self.override_combo.addItem(tr('Unidentified'), 'unidentified')
            self.override_combo.currentIndexChanged.connect(
                self._on_override_changed)
        else:
            self.override_combo = None

        # Categories — plain text (not a Wikidata field).
        self.categories = QLineEdit()
        self.categories.setPlaceholderText(tr('e.g.') + ' Berlinale 2026; Portraits')
        self.categories.setToolTip(tr(
            'The Commons categories this file belongs in - category NAMES '
            'only,\nwithout "Category:" and without brackets, several '
            'separated by ;\n\n'
            'e.g.:  Berlinale 2026; Harald Krichel\n\n'
            'Each name becomes a [[Category:...]] line in the wikitext. '
            'The category\nshould already exist on Commons - a red '
            'category leaves the file\npoorly findable. "Suggest" fills '
            'this from the depicts entries.'))

        # Base-only fields.
        if self.is_base:
            self.created_during = QLineEdit()
            self.created_during.setPlaceholderText(tr('e.g.') + ' Q124692383')
            _style_wd_field(self.created_during, searchable=True)
            self._cd_suggest = WikidataSuggest(self.created_during, multi=False)
            self.created_during.setToolTip(tr(
                'P10408 "created during": the event ALL these pictures were '
                'taken at,\nas ONE Wikidata item.\n\n'
                'If the edition has its own item, take that one: '
                '"Berlinale 2026",\nnot "Berlinale". Smaller festivals '
                'often have only one item for the\nwhole series - then '
                'that one is right. Type the name and pick from\nthe '
                'suggestions, or enter the Q-number directly.\n\n'
                'Becomes the "created during" statement (P10408) of every '
                'file, and\n"Suggest" derives the base category from it.'))

            self.gallery_suffix = QLineEdit()
            self.gallery_suffix.setPlaceholderText(tr('e.g.') + ' Berlinale 2026')
            self.gallery_suffix.setToolTip(tr(
                'The part of the gallery page name that is specific to this '
                'batch,\ne.g. the event name: with suffix "Berlinale 2026" '
                'the uploads are\nlisted on <gallery prefix>/Berlinale '
                '2026. Plain text, no brackets.'))
        else:
            self.created_during = None
            self.gallery_suffix = None

        # Signals: changed = per keystroke (used by the base live sync);
        # committed = on field switch / editing finished (used by the per-file
        # table sync so the table updates when you leave a field, not per char).
        watched = [self.categories]
        if not self.is_base:
            watched.append(self.depicts)
        if self.is_base:
            watched += [self.created_during, self.gallery_suffix]
        for w in watched:
            w.textChanged.connect(lambda *_: self.changed.emit())
            w.editingFinished.connect(self.committed)

        # Rows.
        if not self.is_base:
            form.addRow(tr('Depicts (P180):'), self.depicts)
            form.addRow(tr('If no depicts:'), self.override_combo)
        if self.is_base:
            # Plain row: the button that fills a category FROM this field sits
            # on the Categories row below, where its result lands (0.12.5).
            form.addRow(tr('Created during (P10408):'), self.created_during)
        # Categories row - with the Suggest button in the label column, so
        # the input keeps the full field width.
        cat_btn = QPushButton(tr('Suggest'))
        if self.is_base:
            cat_btn.setToolTip(
                tr('Adds a base category from the "created during" event '
                   '(Commons category P373, or the label; a missing year is '
                   'taken from the Date column).'))
            cat_btn.clicked.connect(self.suggest_requested)
        else:
            cat_btn.setToolTip(
                tr('Adds categories from the depicts entries (Commons '
                   'category P373, or the label).'))
            cat_btn.clicked.connect(self.suggest_depicts_requested)
        form.addRow(_label_with_button(tr('Categories:'), cat_btn),
                    self.categories)
        if self.is_base:
            form.addRow(tr('Gallery suffix:'), self.gallery_suffix)
        # The row LABELS carry the same tooltip as their field: someone who
        # wonders what "P180" means points at the label, not the input.
        for w in (self.depicts, self.override_combo, self.categories,
                  self.created_during, self.gallery_suffix):
            if w is not None:
                lbl = form.labelForField(w)
                if lbl is not None:
                    lbl.setToolTip(w.toolTip())
        apply_form_ratio(form)
        layout.addLayout(form)

        layout.addWidget(QLabel(tr('Extra wikitext / comments:')))
        self.extra = QTextEdit()
        self.extra.setPlaceholderText(
            tr('e.g.') + ' {{en|1=…}}\n'
            + tr('# lines starting with # are comments and are not uploaded'))
        # Start at two text lines; the grip below makes it drag-resizable.
        two_lines = self.extra.fontMetrics().lineSpacing() * 2 + 12
        self.extra.setFixedHeight(two_lines)
        self.extra.textChanged.connect(lambda: self.changed.emit())
        # The extra box is a QTextEdit (no editingFinished); commit on focus out.
        self.extra.installEventFilter(self)
        layout.addWidget(self.extra)
        layout.addWidget(_VGrip(self.extra, two_lines))

    def _on_override_changed(self, _index):
        """The override dropdown commits immediately (no editingFinished)."""
        self.changed.emit()
        self.committed.emit()

    def _override_value(self):
        if self.override_combo is None:
            return ''
        return self.override_combo.currentData() or ''

    def _set_override_value(self, value):
        if self.override_combo is None:
            return
        value = canonical_override(value)
        idx = self.override_combo.findData(value or '')
        self.override_combo.blockSignals(True)
        self.override_combo.setCurrentIndex(idx if idx >= 0 else 0)
        self.override_combo.blockSignals(False)

    def eventFilter(self, obj, event):
        if obj is self.extra and event.type() == QEvent.FocusOut:
            self.committed.emit()
        return super().eventFilter(obj, event)

    def load(self, text):
        sd, _ = extract_structured_data(text)
        caps = {k[len('caption_'):]: v for k, v in sd.items()
                if k.startswith('caption_')}
        if self.depicts is not None:
            self.depicts.setText(sd.get('depicts', ''))
            self._set_override_value(
                (sd.get('depicts_override') or '').strip().lower())
        if self.is_base:
            self.created_during.setText(sd.get('created_during', ''))
            self.gallery_suffix.setText(sd.get('gallery_suffix', ''))
        # Split category links out of the leftover text into the categories field,
        # then pull the {{lang|1=…}} information templates into the per-language
        # information fields. Whatever remains is free extra wikitext.
        cats, extra = split_categories(leftover_text(text))
        infos, extra = split_lang_templates(extra)
        self.captions_editor.set_language_data(caps, infos)
        self.categories.setText('; '.join(cats))
        self.extra.setPlainText(extra)

    def assemble(self):
        lines = [f'caption_{lang}={val}'
                 for lang, val in self.captions_editor.get_captions().items()]
        if self.depicts is not None:
            depicts = self.depicts.text().strip()
            if depicts:
                lines.append(f'depicts={depicts}')
            override = self._override_value()
            if override:
                lines.append(f'depicts_override={override}')
        if self.is_base:
            for key, w in (('created_during', self.created_during),
                           ('gallery_suffix', self.gallery_suffix)):
                val = w.text().strip()
                if val:
                    lines.append(f'{key}={val}')
        body = '\n'.join(lines)

        # Per-language {{lang|1=…}} information templates.
        info_lines = '\n'.join(
            f'{{{{{lang}|1={val}}}}}'
            for lang, val in self.captions_editor.get_infos().items())
        if info_lines:
            body = (body + '\n\n' + info_lines).strip()

        extra = self.extra.toPlainText().strip()
        if extra:
            body = (body + '\n\n' + extra).strip()

        cats = [normalize_category_name(c) for c in self.categories.text().split(';')]
        cat_lines = '\n'.join(f'[[Category:{c}]]' for c in cats if c)
        if cat_lines:
            body = (body + '\n' + cat_lines).strip()
        return body


# ── Main window ────────────────────────────────────────────────────────────────



def _label_with_button(text, button):
    """Form label that carries an action button (0.12.4).

    Harald's layout call: the "Suggest" buttons belong in the LEFT half,
    directly after the caption - not squeezed in beside the input field,
    where they ate the field's width. The caption keeps as much room as it
    needs; the button sits right behind it and the input field gets the
    whole right column.
    """
    box = QWidget()
    row = QHBoxLayout(box)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)
    label = QLabel(text)
    label.setWordWrap(True)
    row.addWidget(label, 1)
    button.setMaximumHeight(22)
    row.addWidget(button, 0)
    return box
