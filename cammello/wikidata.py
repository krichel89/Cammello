"""Wikidata entity search, completer and field styling."""
import re
import weakref
import requests
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QObject, QTimer,
                          QStringListModel)
from PyQt5.QtWidgets import QCompleter
from PyQt5.QtGui import QRegExpValidator
from .constants import *
from .constants import _WD_SINGLE_RE, _WD_LIST_RE


_WD_FIELDS = weakref.WeakSet()


def wd_field_style():
    """Wikidata-field stylesheet: a BLUE BORDER only.

    0.11.0 removes the field-specific background/text color entirely: the
    special background was the last field-level color in the app and kept
    producing wrongly colored fields on macOS (renderer behavior we cannot
    reproduce in CI). With no background/color property of their own, the WD
    fields inherit exactly what every other input field shows - the blue
    border alone marks them as Wikidata fields."""
    if current_style_is_dark():
        border, focus = '#5a8fc0', '#4a9fe0'
    else:
        border, focus = '#2a6db0', '#1d4f85'
    return (
        f'QLineEdit {{'
        f' border: 1px solid {border}; border-radius: 3px;'
        f' padding: 2px 4px; }}'
        f'QLineEdit:focus {{ border: 2px solid {focus};'
        f' padding: 1px 3px; }}')


def refresh_wd_fields():
    """Re-style every live Wikidata field; called by _apply_color_scheme
    after a scheme switch."""
    for edit in list(_WD_FIELDS):
        try:
            edit.setStyleSheet(wd_field_style())
        except RuntimeError:
            pass                          # C++ side already gone


def _style_wd_field(edit, multi=False, searchable=False):
    """Apply the Wikidata look-and-feel: light-blue background with a
    high-contrast border (matches INPUT_STYLE).

    searchable=True means the user may type a name to search Wikidata, so the
    strict "Q + digits only" validator is NOT applied (letters must be
    allowed). Such fields are checked for valid QIDs before upload instead.
    Non-searchable fields keep the strict QID validator. Fields grow with the
    form (no fixed width cap) so the 30:70 label/field split holds.
    """
    edit.setStyleSheet(wd_field_style())
    _WD_FIELDS.add(edit)
    if not searchable:
        edit.setValidator(QRegExpValidator(_WD_LIST_RE if multi else _WD_SINGLE_RE,
                                           edit))


def current_token(text, multi):
    """Return the token currently being edited.

    For a multi-value (semicolon-separated) field this is the part after the
    last ';'. For a single-value field it is the whole (stripped) text.
    """
    if multi:
        return text.rpartition(';')[2].strip()
    return text.strip()



class WikidataSearchWorker(QThread):
    """Runs one wbsearchentities query off the GUI thread.

    Emits results(seq, items) where items is a list of (qid, label,
    description) tuples. seq lets the caller ignore stale (out-of-order)
    responses. Network/parse errors yield an empty list rather than raising.
    """
    results = pyqtSignal(int, list)

    def __init__(self, query, lang, seq, timeout=8, parent=None):
        super().__init__(parent)
        self._query = query
        self._lang = lang or 'en'
        self._seq = seq
        self._timeout = timeout

    def run(self):
        items = []
        try:
            resp = requests.get(
                WD_API_ENDPOINT,
                params={
                    'action': 'wbsearchentities',
                    'search': self._query,
                    'language': self._lang,
                    'uselang': self._lang,
                    'type': 'item',
                    'limit': 10,
                    'format': 'json',
                },
                headers={'User-Agent': WD_USER_AGENT},
                timeout=self._timeout,
            )
            data = resp.json()
            for entry in data.get('search', []):
                items.append((
                    entry.get('id', ''),
                    entry.get('label', ''),
                    entry.get('description', ''),
                ))
        except Exception:
            items = []
        self.results.emit(self._seq, items)


class WikidataCompleter(QCompleter):
    """Completer whose popup lists 'label — description (Qxxx)' entries.

    On selection it writes the bare QID into the field (for a multi-value
    field it replaces only the token after the last ';'). The suggestion list
    is supplied externally via set_suggestions(); the completer does not
    filter it (UnfilteredPopupCompletion), because filtering already happened
    on Wikidata's side.
    """
    _QID_IN_TEXT = re.compile(r'\((Q\d+)\)\s*$')

    def __init__(self, multi=False, parent=None):
        super().__init__(parent)
        self._multi = multi
        self._model = QStringListModel(self)
        self.setModel(self._model)
        self.setCompletionMode(QCompleter.UnfilteredPopupCompletion)
        self.setCaseSensitivity(Qt.CaseInsensitive)
        # Make the suggestion list a bit bigger / more readable.
        self.setMaxVisibleItems(12)
        self.popup().setMinimumWidth(420)
        self.refresh_style()

    def refresh_style(self):
        """Colors for the popup, matching the ACTIVE color scheme.

        The popup is a top-level QListView (not a child of the main window),
        so it gets neither the window stylesheet nor the repolish pass of a
        scheme switch. Called at construction AND before every show (see
        WikidataSuggest._on_results), so switching the scheme at runtime is
        reflected the next time the list opens.
        """
        self.popup().setStyleSheet(completer_popup_style())

    def set_suggestions(self, display_list):
        self._model.setStringList(display_list)

    def splitPath(self, path):  # noqa: N802 (Qt override)
        # Unfiltered popup: matching is not needed, return the token as-is.
        return [current_token(path, self._multi)]

    def pathFromIndex(self, index):  # noqa: N802 (Qt override)
        display = self.model().data(index, Qt.DisplayRole) or ''
        m = self._QID_IN_TEXT.search(display)
        qid = m.group(1) if m else display
        if not self._multi:
            return qid
        widget = self.widget()
        text = widget.text() if widget is not None else ''
        head, sep, _tail = text.rpartition(';')
        return f'{head}; {qid}' if sep else qid


class WikidataSuggest(QObject):
    """Wire a QLineEdit to live Wikidata suggestions.

    Debounces typing, runs wbsearchentities in a background thread, and feeds
    a WikidataCompleter. Only the newest query's results are shown (older,
    slower responses are ignored via a sequence counter).
    """
    def __init__(self, line_edit, lang='en', multi=False, timeout=8, parent=None):
        super().__init__(parent or line_edit)
        self.edit = line_edit
        self.lang = lang
        self.multi = multi
        self.timeout = timeout
        self._enabled = True
        self._seq = 0
        self._workers = set()

        self.completer = WikidataCompleter(multi=multi, parent=self.edit)
        self.edit.setCompleter(self.completer)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(300)
        self._timer.timeout.connect(self._run_search)

        # textEdited fires only on user input, not on programmatic setText,
        # so setting the QID on selection does not trigger another search.
        self.edit.textEdited.connect(self._on_text_edited)

    def set_enabled(self, on):
        """Turn suggestions on/off (used when a field is not a Wikidata field)."""
        self._enabled = bool(on)
        if not on:
            self._timer.stop()
            self.completer.set_suggestions([])

    def _on_text_edited(self, _text):
        if not self._enabled:
            return
        token = current_token(self.edit.text(), self.multi)
        # Don't search bare QIDs or very short fragments.
        if len(token) < 2 or QID_RE.match(token):
            self._timer.stop()
            return
        self._timer.start()

    def _run_search(self):
        token = current_token(self.edit.text(), self.multi)
        if len(token) < 2 or QID_RE.match(token):
            return
        self._seq += 1
        worker = WikidataSearchWorker(token, self.lang, self._seq,
                                      self.timeout, parent=self)
        worker.results.connect(self._on_results)
        self._workers.add(worker)
        worker.finished.connect(lambda w=worker: self._workers.discard(w))
        worker.start()

    def _on_results(self, seq, items):
        if seq != self._seq:
            return  # stale response, a newer query is in flight
        display = []
        for qid, label, desc in items:
            label = label or qid
            display.append(f'{label} — {desc} ({qid})' if desc
                           else f'{label} ({qid})')
        self.completer.set_suggestions(display)
        if display:
            # Scheme may have changed since the last popup: refresh first.
            self.completer.refresh_style()
            self.completer.complete()


# ── Category suggestions (0.11.0) ─────────────────────────────────────────────

def fetch_commons_categories(qids, timeout=8):
    """{qid: (commons_category_or_None, label_or_'')} for up to 50 QIDs via
    one wbgetentities call. The Commons category is Wikidata property P373;
    the label falls back en -> de -> any."""
    qids = [q for q in qids if q]
    if not qids:
        return {}
    r = requests.get(
        'https://www.wikidata.org/w/api.php',
        params={'action': 'wbgetentities', 'ids': '|'.join(qids[:50]),
                'props': 'claims|labels', 'languages': 'en|de',
                'format': 'json'},
        headers={'User-Agent': WD_USER_AGENT}, timeout=timeout)
    r.raise_for_status()
    out = {}
    for qid, ent in (r.json().get('entities') or {}).items():
        cat = None
        for claim in (ent.get('claims', {}).get('P373') or []):
            val = (claim.get('mainsnak', {}).get('datavalue', {})
                   .get('value'))
            if isinstance(val, str) and val.strip():
                cat = val.strip()
                break
        labels = ent.get('labels', {})
        label = (labels.get('en') or labels.get('de') or {}).get('value', '')
        if not label and labels:
            label = next(iter(labels.values())).get('value', '')
        out[qid] = (cat, label)
    return out


_YEAR_RE = re.compile(r'\b(19|20)\d{2}\b')


def category_suggestions(depicts_qids, created_qid, fetched, date_text,
                         existing_cats):
    """Pure suggestion builder (unit-testable, no network).

    depicts entries suggest their Commons category (P373) or, failing that,
    their label. The created-during event does the same, and if the result
    carries NO year (the Wikidata label of a recurring event often does not),
    the year from the file's Date column is appended - 'Berlinale' with a
    2026-02-14 date becomes 'Berlinale 2026'. Existing categories are kept
    (case-insensitive dedup); returns only the NEW names, in source order."""
    existing = {c.strip().lower() for c in existing_cats if c.strip()}
    year_m = _YEAR_RE.search(date_text or '')
    year = year_m.group(0) if year_m else ''
    out = []

    def add(name):
        name = (name or '').strip()
        if name and name.lower() not in existing:
            existing.add(name.lower())
            out.append(name)

    for qid in depicts_qids:
        cat, label = fetched.get(qid, (None, ''))
        add(cat or label)
    if created_qid:
        cat, label = fetched.get(created_qid, (None, ''))
        name = (cat or label or '').strip()
        if name and not _YEAR_RE.search(name) and year:
            name = f'{name} {year}'
        add(name)
    return out
