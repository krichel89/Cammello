"""Background QThread workers: upload, login, connection test."""
import os
import re
import traceback
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from .i18n import tr
from .constants import *
from .sdc import *
from .api import MediaWikiApi
from .exif import parse_coordinates
from . import upload_journal as journal_mod


class UploadWorker(QThread):
    progress = pyqtSignal(int, str)   # row, status
    finished = pyqtSignal(str)        # summary message
    error = pyqtSignal(int, str)      # row, error message
    file_started = pyqtSignal(int, str)   # index, target filename

    def __init__(self, api, rows, gallery_prefix, ignore_warnings,
                 journal=None):
        super().__init__()
        self.api = api
        self.log = api.log
        # 0.14.2: crash-safe batch journal. Written through after every
        # file, so an interrupted run can be picked up where it stopped.
        # None means "do not journal" (used by tests).
        self.journal = journal
        # Each row's description_all is already the merged text (upload settings
        # + base + per-file), built by MWEditorMixin._effective_text.
        self.rows = rows
        self.gallery_prefix = gallery_prefix
        self.ignore_warnings = ignore_warnings
        # Set from the GUI thread by cancel(). A bool assignment is atomic
        # under the GIL, so no lock is needed. Checked between files only: an
        # HTTP request already in flight is always finished, never torn down
        # halfway, so no half-uploaded file is left on Commons.
        self._cancelled = False

    def _journal_mark(self, row, status, **kw):
        """Write one status change through to disk. A journal failure must
        never break a running upload - it is a safety net, not a
        dependency."""
        if self.journal is None:
            return
        try:
            self.journal.mark(row, status, **kw)
        except Exception as e:
            self.log.warning('Journal could not be written (%s); the upload '
                             'continues, but a crash would not be '
                             'resumable.', e)

    def _journal_finish(self):
        """Drop the journal when nothing is left to resume; keep it when a
        cancel left files untouched, so they can be picked up later."""
        if self.journal is None:
            return
        try:
            if self.journal.is_resumable():
                done, failed, openc, total = self.journal.counts()
                self.log.info('Journal kept: %d of %d file(s) still to '
                              'upload - the run can be resumed.',
                              openc, total)
            else:
                self.journal.discard()
        except Exception as e:
            self.log.warning('Journal cleanup failed: %s', e)

    def cancel(self):
        """Request a stop. The current file is finished, then the run ends."""
        self._cancelled = True
        self.log.info('Cancel requested: stopping after the current file.')

    def run(self):
        gallery_entries = {}   # gallery_page -> list of (filename, caption)
        if self.journal is not None:
            # A resumed run inherits the gallery entries of the files that
            # went up before the interruption: galleries are written once,
            # at the end, so those were never recorded on-wiki.
            gallery_entries.update(self.journal.collected_gallery())
            if gallery_entries:
                self.log.info('Resuming: %d gallery entry(ies) carried over '
                              'from the interrupted run.',
                              sum(len(v) for v in gallery_entries.values()))
        success_count = 0
        sdc_failures = 0
        cancelled_at = None

        self.log.info('=== Upload run started: %d file(s) ===', len(self.rows))

        for i, row in enumerate(self.rows):
            fname = (row.get('target_name')
                     or os.path.basename(row.get('filepath', ''))
                     or f'#{i}')
            if self._cancelled:
                cancelled_at = i
                self.log.info('Upload cancelled before file %d/%d ("%s").',
                              i + 1, len(self.rows), fname)
                self.progress.emit(i, tr('Cancelled'))
                break
            try:
                self.file_started.emit(i, fname)
                self.progress.emit(i, tr('Uploading…'))

                # Normalize the target filename: ensure extension, strip a
                # "File:" prefix, reject invalid characters.
                filename = normalize_commons_filename(
                    row.get('target_name', ''), row['filepath'])
                fname = filename
                if filename != row.get('source_name'):
                    self.log.info('Target filename: "%s" → "%s"',
                                  row.get('source_name'), filename)

                sd, clean_desc = extract_structured_data(row['description_all'])
                self.log.debug('File "%s": extracted SD=%s', fname, sd)
                for issue in find_description_issues(row['description_all']):
                    self.log.warning('Possible issue in description for "%s": %s',
                                     fname, issue)

                other_templates = row.get('other_templates', '')
                license_text = row.get('license_text', '')

                # Collect categories (deduplicated) from the description.
                cats_seen = set()
                cats = []
                for cat in re.findall(r'\[\[Category:[^\]]+\]\]', clean_desc):
                    if cat not in cats_seen:
                        cats.append(cat)
                        cats_seen.add(cat)
                clean_desc = re.sub(r'\[\[Category:[^\]]+\]\]\n?', '',
                                    clean_desc).strip()

                # Always add the tracking category (deduplicated).
                if TRACKING_CATEGORY_WIKITEXT not in cats_seen:
                    cats.append(TRACKING_CATEGORY_WIKITEXT)
                    cats_seen.add(TRACKING_CATEGORY_WIKITEXT)

                # Depicts override in a WikiPortraits context: add the
                # matching WikiPortraits maintenance category.
                mnt = wikiportraits_maintenance_category(
                    sd, ' '.join(cats) + ' ' + (other_templates or ''))
                if mnt and mnt not in cats_seen:
                    cats.append(mnt)
                    cats_seen.add(mnt)
                    self.log.info('Depicts override "%s": %s added.',
                                  sd.get('depicts_override'), mnt)

                # {{Information}} block
                info = f"{{{{{row.get('template', 'Information')}\n"
                info += f"|description={clean_desc}\n"
                if row.get('date'):
                    info += f"|date={row['date']}\n"
                if row.get('author'):
                    info += f"|author={row['author']}\n"
                if row.get('source'):
                    info += f"|source={row['source']}\n"
                if row.get('permission'):
                    info += f"|permission={row['permission']}\n"
                if row.get('other_fields'):
                    info += f"|other fields={row['other_fields']}\n"
                info += '}}'

                cats_str = '\n'.join(cats)

                parts = [info]
                # 0.12.15: camera position. {{Location dec}} takes decimal
                # degrees and is the wikitext half; the P1259 claim below is
                # the structured half of the same fact.
                coords = parse_coordinates(sd.get('coordinates', ''))
                if coords:
                    parts.append('{{Location dec|%.6f|%.6f}}' % coords)
                elif sd.get('coordinates', '').strip():
                    self.log.warning('Coordinates for "%s" are unusable and '
                                     'were skipped: %r',
                                     fname, sd.get('coordinates'))
                if other_templates:
                    parts.append(other_templates)
                if license_text:
                    parts.append(f'== {{{{int:license-header}}}} ==\n{license_text}')
                if cats_str:
                    parts.append(cats_str)
                wikitext = '\n'.join(parts)

                # Upload. The journal is marked BEFORE the request goes
                # out: if the process dies while the file is in flight, the
                # resume knows to ask Commons whether it arrived instead of
                # blindly uploading it a second time.
                self._journal_mark(row, journal_mod.IN_FLIGHT, target=filename)
                self.api.upload(
                    filename, row['filepath'], wikitext,
                    f'Uploaded with {APP_NAME}', self.ignore_warnings
                )
            except Exception as e:
                # The file never made it to Commons.
                self.log.error('✗ Error for "%s": %s', fname, e, exc_info=True)
                msg = str(e) or f'{type(e).__name__} (no message)'
                self._journal_mark(row, journal_mod.FAILED, error=msg)
                self.error.emit(i, msg)
                self.progress.emit(i, '✗ ' + tr('Error'))
                continue

            # From here on the file EXISTS on Commons. Structured data and the
            # gallery entry are post-processing: if they fail, the upload still
            # counts, it is only flagged. Up to 0.9.11 they shared the handler
            # above, so a file that was already on Commons was reported as
            # "Done: 0/1 file(s) uploaded".
            sdc_ok = True
            try:
                # Structured data
                labels = {}
                claims = []
                for key, val in sd.items():
                    if key.startswith('caption_'):
                        lang = key[8:]
                        labels[lang] = val
                    elif key in PROPERTY_MAP:
                        prop = PROPERTY_MAP[key]
                        if key == 'coordinates':
                            coord = parse_coordinates(val)
                            if coord:
                                claims.append((prop, ('coord',) + coord))
                        elif key == 'depicts':
                            # Separator is ";"; "," is still tolerated so that
                            # older comma-separated values keep working.
                            for qid in re.split(r'[;,]', val):
                                qid = qid.strip()
                                if qid:
                                    claims.append((prop, qid))
                        else:
                            claims.append((prop, val))

                if labels or claims:
                    self.api.clear_token()
                    page_id = self.api.get_page_id(filename)
                    if page_id:
                        self.api.set_structured_data(page_id, labels, claims)
                        # If depicts (P180) was set, purge the file page with a
                        # link-table update so it leaves the "missing SDC"
                        # maintenance categories immediately. Non-fatal.
                        if any(prop == 'P180' for prop, _q in claims):
                            self.api.purge(f'File:{filename}')
                    else:
                        self.log.warning('SDC skipped: no pageid for "%s".', fname)

                # Collect gallery entry. The page title is assembled from the
                # prefix (a setting) and the per-session suffix; the user
                # types neither slash - gallery_page_name puts in exactly one
                # and cleans up whatever they typed around it.
                gallery_suffix = sd.get('gallery_suffix', '').strip()
                prefix = (self.gallery_prefix or '').strip()
                if prefix:
                    gallery_page = gallery_page_name(prefix, gallery_suffix) or None
                elif gallery_suffix:
                    gallery_page = None  # no prefix set -> skip gallery
                    self.log.warning('gallery_suffix set but no gallery prefix '
                                     '-> gallery skipped for "%s".', fname)
                else:
                    gallery_page = None

                caption = sd.get('caption_en', '')
                gallery_entries.setdefault(gallery_page, []).append(
                    (filename, caption)
                )
                self._journal_mark(row, journal_mod.DONE,
                                   gallery=(gallery_page, filename, caption))

            except Exception as e:
                sdc_ok = False
                sdc_failures += 1
                # The file IS on Commons; only the post-processing failed.
                # Marking it done keeps a resume from uploading it again.
                self._journal_mark(row, journal_mod.DONE, target=filename,
                                   error=str(e))
                self.log.error('Uploaded "%s", but post-processing (structured '
                               'data / gallery) failed: %s', fname, e,
                               exc_info=True)
                msg = str(e) or f'{type(e).__name__} (no message)'
                if 'permissiondenied' in msg:
                    # Writing structured data is an edit of the file page, so
                    # it needs the "Edit existing pages" grant. Uploading only
                    # needs an upload grant - which is why the file goes up and
                    # only wbeditentity is refused. (Deduced from the API error,
                    # not verified against the grant documentation.)
                    msg += (' - if you log in with a bot password, check that '
                            'it has the "Edit existing pages" grant (and '
                            '"Create, edit, and move pages" if you use a '
                            'gallery prefix) at Special:BotPasswords.')
                self.error.emit(
                    i, tr('Uploaded, but structured data failed: {msg}').format(msg=msg))

            self.progress.emit(
                i, '✓ ' + (tr('Done') if sdc_ok else tr('Uploaded (SDC failed)')))
            success_count += 1

        # Update galleries. Files that did go up are still added to the
        # gallery, even after a cancel - they exist on Commons now.
        gallery_ok = True
        for gallery_page, entries in gallery_entries.items():
            if not gallery_page:
                continue
            try:
                self.api.update_gallery(gallery_page, entries)
            except Exception as e:
                gallery_ok = False
                self.log.error('✗ Gallery error (%s): %s',
                               gallery_page, e, exc_info=True)
                self.error.emit(-1, f'Gallery error ({gallery_page}): {e}')
        if self.journal is not None and gallery_ok:
            # Written once: a later resume must not add them a second time.
            try:
                self.journal.set_gallery_written()
            except Exception as e:      # a journal problem is never fatal
                self.log.warning('Journal: could not record the gallery '
                                 'state: %s', e)
        self._journal_finish()

        total = len(self.rows)
        # Files that are on Commons but whose structured data could not be
        # written must not be hidden behind a plain "Done".
        sdc_note = (f' {sdc_failures} of them without structured data '
                    f'(see the Log tab).' if sdc_failures else '')
        if cancelled_at is not None:
            skipped = total - cancelled_at
            self.log.info('=== Upload run cancelled: %d/%d succeeded, %d not '
                          'started, %d SDC failure(s) ===',
                          success_count, total, skipped, sdc_failures)
            self.finished.emit(
                f'Cancelled: {success_count}/{total} file(s) uploaded, '
                f'{skipped} not started.{sdc_note}'
            )
        elif self._cancelled:
            # Cancel arrived while the last file was already in flight, so the
            # run completed anyway. Saying "Done" without a word about it would
            # look like the Cancel button did nothing.
            self.log.info('=== Upload run finished (cancel came too late): '
                          '%d/%d succeeded, %d SDC failure(s) ===',
                          success_count, total, sdc_failures)
            self.finished.emit(
                f'Done: {success_count}/{total} file(s) uploaded. The cancel '
                f'arrived while the last file was already being uploaded, so '
                f'the run finished.{sdc_note}'
            )
        else:
            self.log.info('=== Upload run finished: %d/%d succeeded, '
                          '%d SDC failure(s) ===',
                          success_count, total, sdc_failures)
            self.finished.emit(
                f'Done: {success_count}/{total} file(s) uploaded.{sdc_note}'
            )


# ── Login / test worker ────────────────────────────────────────────────────────


class LoginWorker(QThread):
    success = pyqtSignal(object)   # MediaWikiApi instance
    failure = pyqtSignal(str)

    def __init__(self, api_url, username, password, timeout, logger,
                 oauth_token=None, oauth_secret=None):
        super().__init__()
        self.api_url = api_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.logger = logger
        self.oauth_token = oauth_token
        self.oauth_secret = oauth_secret

    def run(self):
        try:
            api = MediaWikiApi(self.api_url, self.username, self.password,
                               timeout=self.timeout, logger=self.logger,
                               oauth_token=self.oauth_token,
                               oauth_secret=self.oauth_secret)
            if api.login():
                self.success.emit(api)
            else:
                self.failure.emit('Invalid credentials.')
        except Exception as e:
            self.logger.error('Login error: %s', e, exc_info=True)
            self.failure.emit(str(e) or f'{type(e).__name__} (no message)')



class TestWorker(QThread):
    done = pyqtSignal(str)
    fail = pyqtSignal(str)

    def __init__(self, api):
        super().__init__()
        self.api = api

    def run(self):
        try:
            info = self.api.whoami()
            name = info.get('name', '?')
            uid = info.get('id', '?')
            groups = ', '.join(info.get('groups', [])) or '–'
            self.done.emit(f'{name} (id {uid}); groups: {groups}')
        except Exception as e:
            self.fail.emit(str(e) or f'{type(e).__name__} (no message)')


# ── Delegate: target filename with a fixed extension ────────────────────────────
