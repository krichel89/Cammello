"""Caption/description editors and the bulk-edit dialog."""
import re
import os
from PyQt5.QtWidgets import (QInputDialog, QMessageBox, QWidget, QLabel, QLineEdit, QPushButton,
                             QComboBox, QTextEdit, QVBoxLayout, QHBoxLayout,
                             QFormLayout, QDialog, QDialogButtonBox)
from PyQt5.QtCore import Qt, pyqtSignal
from .constants import *
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

        btn_row = QHBoxLayout()
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
        btn_row.addStretch()
        outer.addLayout(btn_row)

        self.add_row()  # start with one empty row

    def add_row(self, lang='en', value='', info=''):
        row_widget = QWidget()
        v = QVBoxLayout(row_widget)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(2)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)

        combo = QComboBox()
        for code, name in caption_language_choices():
            combo.addItem(f'{code} – {name}' if name else code, code)
        combo.addItem(tr('Other (ISO code)…'), '__other__')
        idx = combo.findData(lang)
        if idx < 0:                       # unknown code (e.g. from advanced mode)
            combo.insertItem(combo.count() - 1, lang, lang)
            idx = combo.findData(lang)
        combo.setCurrentIndex(idx)
        combo.setMaximumWidth(150)
        combo.currentIndexChanged.connect(
            lambda _i, c=combo: self._on_lang_combo_changed(c))

        edit = QLineEdit(value)
        edit.setPlaceholderText(tr('Caption, e.g. Harald Krichel at the Berlinale 2026'))

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

    def _on_lang_combo_changed(self, combo):
        """'Other (ISO code)…' selected: ask for a code, validate it, insert
        it into the dropdown, select it, and PERSIST it - freely entered
        codes extend the four-language default list permanently."""
        if combo.currentData() != '__other__':
            return
        code, ok = QInputDialog.getText(
            self, tr('Caption language'),
            tr('ISO language code (e.g. nl, pt, ja):'))
        code = (code or '').strip().lower()
        combo.blockSignals(True)
        if not ok or not re.fullmatch(r'[a-z]{2,3}', code):
            combo.setCurrentIndex(0)
            combo.blockSignals(False)
            if ok:
                QMessageBox.warning(self, tr('Caption language'),
                                    tr('Not a valid ISO code: {code}').format(
                                        code=code or '?'))
            return
        idx = combo.findData(code)
        if idx < 0:
            combo.insertItem(combo.count() - 1,
                             format_caption_language(code), code)
            idx = combo.findData(code)
            remember_caption_language(code)
        combo.setCurrentIndex(idx)
        combo.blockSignals(False)
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
        else:
            self.depicts = None

        # Depicts override (per-file): depicts is mandatory for the upload,
        # but one of these waives it. A dropdown keeps the full, readable
        # labels (the checkbox texts were too long to sit side by side).
        # itemData: '' = no override; else the depicts_override= value.
        if not self.is_base:
            self.override_combo = QComboBox()
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

        # Base-only fields.
        if self.is_base:
            self.created_during = QLineEdit()
            self.created_during.setPlaceholderText(tr('e.g.') + ' Q124692383')
            _style_wd_field(self.created_during, searchable=True)
            self._cd_suggest = WikidataSuggest(self.created_during, multi=False)

            self.gallery_suffix = QLineEdit()
            self.gallery_suffix.setPlaceholderText(tr('e.g.') + ' Berlinale 2026')
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
            # 'created during' lives in the base description; its category
            # suggestion belongs here too (was wrongly in the per-file editor).
            cd_row = QHBoxLayout()
            cd_row.addWidget(self.created_during, 1)
            suggest_btn = QPushButton(tr('Suggest category'))
            suggest_btn.setToolTip(
                tr('Adds a base category from the "created during" event '
                   '(Commons category P373, or the label; a missing year is '
                   'taken from the Date column).'))
            suggest_btn.clicked.connect(self.suggest_requested)
            cd_row.addWidget(suggest_btn)
            form.addRow(tr('Created during (P10408):'), cd_row)
        if not self.is_base:
            cat_row = QHBoxLayout()
            cat_row.addWidget(self.categories, 1)
            depicts_cat_btn = QPushButton(tr('Suggest category'))
            depicts_cat_btn.setToolTip(
                tr('Adds categories from the depicts entries (Commons '
                   'category P373, or the label).'))
            depicts_cat_btn.clicked.connect(self.suggest_depicts_requested)
            cat_row.addWidget(depicts_cat_btn)
            form.addRow(tr('Categories:'), cat_row)
        else:
            form.addRow(tr('Categories:'), self.categories)
        if self.is_base:
            form.addRow(tr('Gallery suffix:'), self.gallery_suffix)
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


class BulkEditDialog(QDialog):
    """Pick one field and a value to apply to all selected rows.

    Fields:
      depicts / categories  -> per-file description keys
      caption:en / caption:de -> per-file caption in that language
      date                  -> the Date column
    An empty value clears that field on the selected rows.
    """
    FIELDS = [
        ('Depicts (P180)', 'depicts'),
        ('Categories', 'categories'),
        ('Caption (en)', 'caption:en'),
        ('Caption (de)', 'caption:de'),
        ('Date', 'date'),
    ]

    def __init__(self, n_selected, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr('Bulk edit selected files'))
        self.setStyleSheet(current_input_style())
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            tr('Apply a value to the {n} selected file(s):').format(
                n=n_selected)))

        form = QFormLayout()
        self.field_combo = QComboBox()
        for label, key in self.FIELDS:
            self.field_combo.addItem(tr(label), key)
        self.value_edit = QLineEdit()
        form.addRow(tr('Field:'), self.field_combo)
        form.addRow(tr('Value:'), self.value_edit)
        apply_form_ratio(form)
        layout.addLayout(form)

        self.hint = QLabel('')
        self.hint.setStyleSheet('color:#888;')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Wikidata suggestions on the value field, active only for Depicts.
        self._suggest = WikidataSuggest(self.value_edit, multi=True)
        self.field_combo.currentIndexChanged.connect(self._on_field_changed)
        self._on_field_changed()

    def _on_field_changed(self):
        key = self.field_combo.currentData()
        is_depicts = (key == 'depicts')
        self._suggest.set_enabled(is_depicts)
        if is_depicts:
            _style_wd_field(self.value_edit, multi=True, searchable=True)
        else:
            self.value_edit.setStyleSheet('')
        hints = {
            'depicts': tr('Semicolon-separated QIDs; type a name to search Wikidata.'),
            'categories': tr('Semicolon-separated, without [[Category:]].'),
            'caption:en': tr('Sets the English SDC caption.'),
            'caption:de': tr('Sets the German SDC caption.'),
            'date': tr('Sets the Date column (e.g. 2026-02-15).'),
        }
        self.hint.setText(hints.get(key, '') + '  Empty value clears this field.')

    def result_field_value(self):
        return self.field_combo.currentData(), self.value_edit.text().strip()
