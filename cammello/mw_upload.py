"""Part of MainWindow, split out as a mixin. See main_window.py for the class
that combines these mixins. Mixins are plain classes holding grouped methods;
they rely on attributes created in MainWindow.__init__ / _build_* and on the
COL_* / COLS class attributes defined on MainWindow."""
import os
import sys
import traceback
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QTextEdit, QFileDialog, QMessageBox, QProgressBar, QSplitter,
    QGroupBox, QFormLayout, QHeaderView, QAbstractItemView, QDialog,
    QDialogButtonBox, QCheckBox, QStatusBar, QTabWidget, QPlainTextEdit,
    QStyledItemDelegate, QComboBox, QScrollArea, QCompleter)
from PyQt5.QtCore import (Qt, QThread, pyqtSignal, QSettings, QObject, QUrl,
                          QSize, QRegExp, QTimer, QStringListModel, QEvent,
                          QItemSelectionModel)
from PyQt5.QtGui import (QPixmap, QFont, QDesktopServices, QIcon, QImageReader,
                         QRegExpValidator)
from .constants import *
from .i18n import tr
from .sdc import (extract_structured_data, DEPICTS_OVERRIDES,
                  canonical_override)
from .constants import __version__, _WD_SINGLE_RE, _WD_LIST_RE
from . import upload_journal
from .logging_setup import *
from . import channels
from .sdc import *
from .sdc import _strip_sd_lines
from .exif import *
from .api import *
from .workers import *
from .wikidata import *
from .wikidata import _style_wd_field
from .widgets import *
from .editors import *


class MWUploadMixin:
    def _upload_rows(self):
        """Table rows the Upload button acts on.

        Selected rows only; if nothing is selected, every row. Rows marked
        for the commercial channel (0.12.1) are excluded either way - their
        items are disabled (unselectable), but the all-rows path and any
        stale selection are filtered here as well. Returns a sorted list of
        table row indices.
        """
        selected = sorted({idx.row() for idx in self.table.selectedIndexes()})
        rows = selected if selected else list(range(self.table.rowCount()))
        out = []
        excluded = 0
        for r in rows:
            item = self.table.item(r, self.COL_FILENAME)
            fp = item.data(Qt.UserRole) if item else None
            if fp and self._channel_mark(fp) == channels.MARK_COMMERCIAL:
                excluded += 1
                continue
            out.append(r)
        if excluded:
            self.logger.info(
                'Commons upload: %d file(s) excluded (marked commercial).',
                excluded)
        return out

    def _update_upload_btn(self):
        """Keep the button label honest about what a click would do."""
        total = self.table.rowCount()
        selected = {idx.row() for idx in self.table.selectedIndexes()}
        if selected:
            self.upload_btn.setText(
                tr('Upload selected ({n})').format(n=len(selected)))
            self.upload_btn.setToolTip(
                tr('Uploads the selected rows. Deselect everything to upload all '
                'files.'))
        else:
            self.upload_btn.setText(
                tr('Upload all ({n})').format(n=total) if total
                else tr('Upload all'))
            self.upload_btn.setToolTip(
                tr('Nothing is selected, so all files are uploaded. Select rows '
                'to upload only those.'))

    def _qid_problems(self, rows=None):
        """Collect fields whose Wikidata value is not a valid QID.

        Covers the searchable fields (creator, depicts, created_during) plus
        the fixed copyright/license fields, in the upload settings, the base
        description and the per-file descriptions of the rows about to be
        uploaded (rows=None: all rows). Returns human-readable strings; empty
        list means everything is fine.
        """
        if rows is None:
            rows = range(self.table.rowCount())
        problems = []
        problems += invalid_qid_problems('Creator (P170)',
                                         self.creator_edit.text())
        problems += invalid_qid_problems('Copyright (P6216)',
                                         self.copyright_sdc_edit.text())
        problems += invalid_qid_problems('License (P275)',
                                         self.license_sdc_edit.text())
        base_sd, _ = extract_structured_data(self.base_text_edit.toPlainText())
        problems += invalid_qid_problems('Base: created during (P10408)',
                                         base_sd.get('created_during', ''))
        problems += invalid_qid_problems('Base: depicts (P180)',
                                         base_sd.get('depicts', ''), multi=True)
        for r in rows:
            item = self.table.item(r, self.COL_DESC)
            if not item:
                continue
            sd, _ = extract_structured_data(item.text())
            if 'depicts' in sd:
                problems += invalid_qid_problems(
                    f'Row {r + 1}: depicts (P180)', sd.get('depicts', ''),
                    multi=True)
            if 'created_during' in sd:
                problems += invalid_qid_problems(
                    f'Row {r + 1}: created during (P10408)',
                    sd.get('created_during', ''))
        return problems

    def _depicts_problems(self, upload_rows):
        """Rows without depicts AND without an override checkbox.

        depicts is mandatory (WikiPortraits QA): either the file has at
        least one P180 QID (its own or inherited from a depicts= line in the
        base description), or one of the per-file overrides ('No Wikidata
        item' / 'Not applicable' / 'Unidentified') is set."""
        base_sd, _ = extract_structured_data(self.base_text_edit.toPlainText())
        base_depicts = (base_sd.get('depicts') or '').strip()
        problems = []
        for r in upload_rows:
            item = self.table.item(r, self.COL_DESC)
            sd, _ = extract_structured_data(item.text() if item else '')
            has_depicts = bool((sd.get('depicts') or '').strip()
                               or base_depicts)
            override = canonical_override(sd.get('depicts_override'))
            if has_depicts or override in DEPICTS_OVERRIDES:
                continue
            name_item = self.table.item(r, self.COL_FILENAME)
            problems.append(name_item.text() if name_item else f'#{r + 1}')
        return problems

    def start_upload(self):
        # These early exits used to be silent in the log, which made an
        # apparently dead Upload button impossible to diagnose from the Log tab.
        if not self.api:
            # Not logged in: take the user straight to the login instead of a
            # dead-end warning (0.12.4). After a successful login they press
            # Upload again - the table and all edits are untouched.
            self.logger.info('Upload requested while not logged in: opening '
                             'the login.')
            self.do_login()
            return
        if self.table.rowCount() == 0:
            self.logger.info('Upload aborted: the file table is empty.')
            QMessageBox.warning(self, tr('No files'), tr('Please add files first.'))
            return

        # Flush any not-yet-committed edit in the per-file editor to the table
        # before reading the descriptions.
        self._commit_editor()

        # Selected rows only; nothing selected means all rows.
        upload_rows = self._upload_rows()
        selection_used = bool({idx.row() for idx in self.table.selectedIndexes()})
        self.logger.info('Upload requested for %d of %d row(s) (%s).',
                         len(upload_rows), self.table.rowCount(),
                         'selection' if selection_used else 'no selection: all')

        problems = self._qid_problems(upload_rows)
        if problems:
            self.logger.info('Upload aborted: %d invalid Wikidata ID(s).',
                             len(problems))
            shown = '\n'.join(problems[:15])
            if len(problems) > 15:
                shown += '\n' + tr('… (+{n} more)').format(n=len(problems) - 15)
            QMessageBox.warning(
                self, tr('Invalid Wikidata IDs'),
                tr('The following fields must contain Wikidata QIDs (e.g. Q640).\n'
                'Pick an entry from the suggestion list or enter a valid QID:')
                + '\n\n' + shown)
            return

        # depicts is mandatory: block files that have neither a P180 QID nor
        # one of the three override checkboxes.
        missing = self._depicts_problems(upload_rows)
        if missing:
            shown = '\n'.join(missing[:15])
            if len(missing) > 15:
                shown += '\n' + tr('… (+{n} more)').format(n=len(missing) - 15)
            self.logger.info('Upload aborted: %d file(s) without depicts or '
                             'override.', len(missing))
            QMessageBox.warning(
                self, tr('Depicts is missing'),
                tr('depicts (P180) is mandatory. Enter a QID, or check one '
                   'of the overrides ("No Wikidata item", "Not applicable", '
                   '"Unidentified") for these files:') + '\n\n' + shown)
            return

        self._save_settings()
        # Apply the timeout to the active session in case it was changed.
        self.api.timeout = self._get_timeout()

        rows = []
        # Maps a worker index (0..n-1) back to its table row, which is not the
        # same thing as soon as only a selection is uploaded.
        self.upload_row_map = list(upload_rows)
        for r in upload_rows:
            filepath = self.table.item(r, self.COL_FILENAME).data(Qt.UserRole)
            source_name = self.table.item(r, self.COL_FILENAME).text()
            date = self.table.item(r, self.COL_DATE).text() if self.table.item(r, self.COL_DATE) else ''
            per_file_desc = self.table.item(r, self.COL_DESC).text() if self.table.item(r, self.COL_DESC) else ''

            # Same function as the Wikitext preview column: what you see in the
            # table is byte-for-byte what gets uploaded.
            combined, merge_warnings = self._effective_text(per_file_desc,
                                                            with_warnings=True)
            for warn in merge_warnings:
                self.logger.warning('Row %d ("%s"): %s', r + 1, source_name, warn)

            # Target filename on Commons (may differ from the source name);
            # empty -> source filename. The extension is ensured in the worker.
            target_item = self.table.item(r, self.COL_TITLE)
            target_name = target_item.text().strip() if target_item else ''
            if not target_name:
                target_name = source_name

            rows.append({
                'filepath': filepath,
                'target_name': target_name,
                'source_name': source_name,
                'date': date,
                'description_all': combined,
                'author': self.author_edit.text(),
                'source': self.source_edit.text(),
                'permission': self.permission_edit.text(),
                'license_text': self.license_edit.text(),
                'other_templates': self.other_templates_edit.text(),
                'other_fields': self.other_fields_edit.text(),
                'template': 'Information',
            })

        # Uploading to Commons IS the channel decision (0.12.4): mark these
        # files as the CC/Commons channel so they are greyed out and skipped
        # in the FTP/Flickr lists from now on. Done at the start, not on
        # success, so an interrupted run still leaves the decision recorded.
        self._mark_uploaded_channel([r['filepath'] for r in rows],
                                    channels.MARK_COMMONS)

        # 0.14.2: open a crash-safe journal for this batch. It carries the
        # complete rows, so a resume after a crash does not depend on the
        # table still holding them.
        journal = None
        try:
            journal = upload_journal.Journal.start(
                rows,
                gallery_prefix=self.gallery_prefix_edit.text(),
                ignore_warnings=self.ignore_warnings_cb.isChecked(),
                api_url=getattr(self.api, 'api_url', ''),
                username=getattr(self.api, 'username', '') or '')
            self.logger.info('Upload journal opened for %d file(s): %s',
                             len(rows), upload_journal.journal_path())
        except Exception as e:
            # Never block an upload because the journal could not be
            # created - the batch simply is not resumable then.
            self.logger.warning('Upload journal could not be created (%s); '
                                'the upload runs without crash recovery.', e)

        self._launch_upload_worker(rows, journal)

    def _launch_upload_worker(self, rows, journal, resumed=False):
        """Start the worker for `rows`. Shared by a fresh upload and a
        resumed one (0.14.2) - the worker never touches the table, it works
        purely off the row dicts, which is what makes a resume possible."""
        self.progress_bar.setVisible(True)
        self.progress_bar.setMaximum(len(rows))
        self.progress_bar.setValue(0)
        self.upload_btn.setEnabled(False)

        # Map worker index -> table row via the file path. On a resume the
        # rows may not be in the table at all; -1 then means "no row to
        # update", which on_progress already tolerates.
        self.upload_row_map = self._rows_to_table_rows(rows) if resumed \
            else getattr(self, 'upload_row_map', list(range(len(rows))))

        # Progress window with a Cancel button. Modeless on purpose: the table
        # stays readable (per-row status keeps updating behind it) while the
        # run is going on.
        self._progress_dlg = UploadProgressDialog(len(rows), self)
        self._done_count = 0

        gallery_prefix = (journal.data.get('gallery_prefix', '') if
                          (resumed and journal is not None)
                          else self.gallery_prefix_edit.text())
        ignore_warnings = (journal.data.get('ignore_warnings', False) if
                           (resumed and journal is not None)
                           else self.ignore_warnings_cb.isChecked())

        # No base_text argument any more: each row already carries the fully
        # merged description_all (settings SDC + base + per-file). The worker
        # used to take a base_text it never read.
        self.worker = UploadWorker(self.api, rows, gallery_prefix,
                                   ignore_warnings, journal=journal,
                                   capture_sdc=self.settings.value(
                                       'exif_capture_sdc', True, type=bool),
                                   edits_store=getattr(self, '_cull_edits',
                                                       None))
        self.worker.progress.connect(self.on_progress)
        self.worker.error.connect(self.on_error)
        self.worker.finished.connect(self.on_finished)
        self.worker.file_started.connect(self._progress_dlg.set_current)
        # Queued across threads by Qt: the flag is set in the worker object,
        # the worker thread picks it up before the next file.
        self._progress_dlg.cancel_requested.connect(self.worker.cancel)
        self._progress_dlg.show()
        self.worker.start()

    # ── Resuming an interrupted batch (0.14.2) ───────────────────────────
    def has_resumable_upload(self):
        """True if an interrupted batch is waiting. Cheap and offline: it
        reads one small file, no network and no keyring."""
        try:
            return upload_journal.load_resumable() is not None
        except Exception:
            return False

    def offer_resume_on_start(self):
        """Called once after the window is up. Asks - never resumes on its
        own: uploading is not something to start behind the user's back."""
        try:
            j = upload_journal.load_resumable()
        except Exception:
            return
        if j is None:
            return
        done, failed, openc, total = j.counts()
        self.logger.info('An interrupted upload was found: %d/%d done, %d '
                         'still open (started %s).',
                         done, total, openc, j.data.get('started', '?'))
        box = QMessageBox(self)
        box.setWindowTitle(tr('Interrupted upload'))
        box.setIcon(QMessageBox.Question)
        box.setText(tr('An upload from {when} was interrupted.').format(
            when=j.data.get('started', '?')))
        detail = tr('{done} of {total} file(s) were uploaded; '
                    '{open} still to go.').format(done=done, total=total,
                                                  open=openc)
        if failed:
            detail += '\n' + tr('{n} file(s) failed and will not be '
                                'retried.').format(n=failed)
        # 0.16.1: unreadable files ARE resumed, so say so - otherwise they
        # sit inside the "still to go" number with no explanation of why
        # they did not go up the first time.
        unreadable = len(j.unreadable_entries())
        if unreadable:
            detail += '\n' + tr(
                '{n} file(s) could not be read from disk last time (offline '
                'files, a disconnected drive). Make sure they are available, '
                'then resume.').format(n=unreadable)
        box.setInformativeText(detail + '\n\n'
                               + tr('Resume it now?'))
        resume_btn = box.addButton(tr('Resume'), QMessageBox.AcceptRole)
        later_btn = box.addButton(tr('Later'), QMessageBox.RejectRole)
        box.addButton(tr('Discard'), QMessageBox.DestructiveRole)
        box.setDefaultButton(later_btn)
        box.exec()
        clicked = box.clickedButton()
        if clicked is resume_btn:
            self.resume_upload()
        elif clicked is later_btn:
            self.statusBar().showMessage(
                tr('The interrupted upload is kept - resume it from the '
                   'Upload menu.'), 8000)
        else:
            j.discard()
            self.logger.info('The interrupted upload was discarded by the '
                             'user.')

    def resume_upload(self):
        """Continue an interrupted batch where it stopped."""
        try:
            j = upload_journal.load_resumable()
        except Exception as e:
            self.logger.error('The upload journal could not be read: %s', e)
            j = None
        if j is None:
            QMessageBox.information(
                self, tr('Interrupted upload'),
                tr('There is no interrupted upload to resume.'))
            return
        if not self.api:
            self.logger.info('Resume requested while not logged in: opening '
                             'the login.')
            self._resume_after_login = True
            self.do_login()
            return

        # The journal may come from a different wiki or account - uploading
        # someone else's batch into the wrong place would be hard to undo.
        was_url = j.data.get('api_url', '')
        if was_url and was_url != getattr(self.api, 'api_url', ''):
            if QMessageBox.warning(
                    self, tr('Interrupted upload'),
                    tr('That upload was started against a different wiki '
                       '({url}). Resume it here anyway?').format(url=was_url),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No) != QMessageBox.Yes:
                return

        self._settle_in_flight(j)
        rows = j.pending_rows()
        if not rows:
            self.logger.info('Nothing left to resume; the journal was '
                             'cleared.')
            j.discard()
            QMessageBox.information(
                self, tr('Interrupted upload'),
                tr('Every file of that batch is already on Commons.'))
            return

        missing = [r for r in rows if not os.path.exists(r.get('filepath', ''))]
        if missing:
            names = '\n'.join(os.path.basename(r.get('filepath', '?'))
                               for r in missing[:15])
            if len(missing) > 15:
                names += '\n' + tr('… (+{n} more)').format(
                    n=len(missing) - 15)
            self.logger.warning('%d file(s) of the interrupted batch are no '
                                'longer at their old path.', len(missing))
            if QMessageBox.warning(
                    self, tr('Interrupted upload'),
                    tr('{n} file(s) are no longer where they were. They will '
                       'be skipped:').format(n=len(missing))
                    + '\n\n' + names + '\n\n' + tr('Continue?'),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes) != QMessageBox.Yes:
                return
            skipped = {id(r) for r in missing}
            for r in missing:
                j.mark(r, upload_journal.FAILED,
                       error='file not found at resume', save=False)
            j.save()
            rows = [r for r in rows if id(r) not in skipped]
            if not rows:
                return

        self.api.timeout = self._get_timeout()
        self.logger.info('=== Resuming the interrupted upload: %d file(s) '
                         '===', len(rows))
        self._launch_upload_worker(rows, j, resumed=True)

    def _settle_in_flight(self, j):
        """Resolve entries that were in flight when the process died.

        The upload request went out, but no answer was recorded - the file
        may be on Commons already. Asking beats guessing: re-uploading
        blindly would either fail with an "exists" warning or, with
        "ignore warnings" on, silently overwrite the file with itself.
        At most one entry can be in this state, so this is one request.
        """
        for e in j.in_flight_entries():
            target = e.get('target') or e['row'].get('target_name', '')
            if not target:
                e['status'] = upload_journal.PENDING
                continue
            try:
                page_id = self.api.get_page_id(target)
            except Exception as exc:
                self.logger.warning('Could not check whether "%s" arrived on '
                                    'Commons (%s); it will be uploaded '
                                    'again.', target, exc)
                e['status'] = upload_journal.PENDING
                continue
            if page_id:
                self.logger.info('"%s" was already on Commons - counted as '
                                 'uploaded, not sent again.', target)
                e['status'] = upload_journal.DONE
            else:
                self.logger.info('"%s" never arrived on Commons - it will be '
                                 'uploaded again.', target)
                e['status'] = upload_journal.PENDING
        j.save()

    def _rows_to_table_rows(self, rows):
        """Best-effort mapping row dict -> table row index (-1 if absent)."""
        by_path = {}
        for r in range(self.table.rowCount()):
            item = self.table.item(r, self.COL_FILENAME)
            if item is not None:
                by_path[item.data(Qt.UserRole)] = r
        return [by_path.get(row.get('filepath'), -1) for row in rows]

    def _table_row(self, worker_index):
        """Translate a worker index into a table row (see upload_row_map)."""
        mapping = getattr(self, 'upload_row_map', None)
        if mapping and 0 <= worker_index < len(mapping):
            return mapping[worker_index]
        return worker_index

    def on_progress(self, index, status):
        row = self._table_row(index)
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(status)
        total = len(getattr(self, 'upload_row_map', []) or []) or self.table.rowCount()
        self.progress_bar.setValue(index + 1)
        self.status_bar.showMessage(
            tr('Uploading {i}/{total}…').format(i=index + 1, total=total))
        # The bar counts finished files, not started ones.
        if status.startswith(('✓', '✗')):
            self._done_count = getattr(self, '_done_count', 0) + 1
            dlg = getattr(self, '_progress_dlg', None)
            if dlg is not None:
                dlg.set_done(self._done_count)

    def on_error(self, index, msg):
        if index < 0:
            # Gallery/global errors are shown only in the log/status bar.
            self.status_bar.showMessage(msg, 8000)
            return
        row = self._table_row(index)
        item = self.table.item(row, self.COL_STATUS)
        if item:
            item.setText(f'✗ {msg[:60]}')
            item.setToolTip(msg)

    def on_finished(self, summary):
        self.progress_bar.setVisible(False)
        self.upload_btn.setEnabled(True)
        self._update_upload_btn()
        self.status_bar.showMessage(summary)
        dlg = getattr(self, '_progress_dlg', None)
        if dlg is not None:
            dlg.force_close()   # plain close() is swallowed by reject()
            self._progress_dlg = None
        cancelled = summary.startswith('Cancelled')
        QMessageBox.information(
            self, 'Upload cancelled' if cancelled else 'Upload complete',
            summary + '\n\nDetails in the Log tab.')
