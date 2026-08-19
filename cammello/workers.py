"""Background QThread workers: upload, login, connection test."""
import os
import re
import shutil
import tempfile
import traceback
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from .i18n import tr
from .constants import *
from .sdc import *
from .api import MediaWikiApi, LocalFileError
from .exif import (parse_coordinates, read_capture_settings,
                   read_camera_ids)
from . import camera_map
from . import edits as edits_mod
from . import upload_journal as journal_mod
from . import music


class UploadWorker(QThread):
    progress = pyqtSignal(int, str)   # row, status
    finished = pyqtSignal(str)        # summary message
    error = pyqtSignal(int, str)      # row, error message
    file_started = pyqtSignal(int, str)   # index, target filename

    def __init__(self, api, rows, gallery_prefix, ignore_warnings,
                 journal=None, capture_sdc=False, edits_store=None):
        super().__init__()
        self.api = api
        self.log = api.log
        # 0.15.0 (Harald): copy the EXIF capture settings (exposure time,
        # f-number, ISO, focal length) into the structured data,
        # transparently at upload. Off by default at the worker level - the
        # GUI passes the setting.
        self.capture_sdc = bool(capture_sdc)
        # 0.15.0: the long-standing gap - crop, exposure and white balance
        # were applied in the culling export but NOT on upload, so the
        # original went to Commons. The edited copy is rendered here, in
        # the upload loop, where the progress bar already is. `filepath`
        # stays the SOURCE for metadata reads (EXIF, camera, date); only
        # the bytes that are sent change.
        self.edits_store = edits_store or {}
        self._edit_tmp = None
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

    def _music_categories(self, row, seen):
        """Generated audio categories that Commons actually has.

        The candidates are computed without the network (music.py); this
        method is the half that asks. Every unknown name is dropped, the
        same "no sitelink means no link" rule LrMediaWiki2 follows - a
        category is built from a link TARGET and a guess about English
        naming, so getting one wrong is normal and a red link on every
        upload is not acceptable.

        A failing check is not a failing upload: if Commons cannot be
        asked, nothing is added and the file goes up with the categories
        the description already carried.
        """
        candidates = [c for c in music.category_candidates(row)
                      if f'[[Category:{c}]]' not in seen]
        if not candidates:
            return []
        try:
            existing = self.api.existing_pages(
                [f'Category:{c}' for c in candidates])
        except Exception as e:
            self.log.warning('Categories could not be checked (%s); none '
                             'were added automatically.', e)
            return []
        out = []
        for c in candidates:
            if f'Category:{c}' in existing:
                out.append(f'[[Category:{c}]]')
                seen.add(f'[[Category:{c}]]')
            else:
                self.log.info('Category "%s" does not exist on Commons '
                              'and was skipped.', c)
        return out

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

    def _path_to_send(self, filepath, fname):
        """The bytes that actually go to Commons (0.15.0).

        Unedited files return their own path at zero cost. An edited file
        is rendered once into a temp directory; if the render fails, the
        ORIGINAL is uploaded rather than nothing - an upload must not
        silently vanish because a crop could not be applied.
        """
        if not self.edits_store or not edits_mod.has_edit(self.edits_store,
                                                          filepath):
            return filepath
        if self._edit_tmp is None:
            self._edit_tmp = tempfile.mkdtemp(prefix='cammello_upload_')
        send = edits_mod.effective_upload_path(
            filepath, self.edits_store, self._edit_tmp, self.log)
        if send == filepath:
            self.log.warning('Edited copy of "%s" could not be rendered - '
                             'uploading the original.', fname)
        else:
            self.log.info('Uploading the edited copy of "%s".', fname)
        return send

    def _cleanup_edit_tmp(self):
        if self._edit_tmp:
            shutil.rmtree(self._edit_tmp, ignore_errors=True)
            self._edit_tmp = None

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
        unreadable_count = 0
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

                # 0.18.0: the music workflow builds its file page from a
                # different layout - roles in the author line, two licence
                # blocks, see music.py for the full list of differences.
                # The photograph path below is untouched and still
                # produces byte-for-byte what 0.16.1 produced.
                if row.get('music'):
                    cats += self._music_categories(row, cats_seen)
                    wikitext = music.build_wikitext(
                        row, clean_desc, cats, other_templates)
                else:
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
                    # 0.15.0: position of the depicted object - a DIFFERENT
                    # template from the camera position above, on purpose.
                    obj = parse_coordinates(sd.get('object_coordinates', ''))
                    if obj:
                        parts.append('{{Object location dec|%.6f|%.6f}}' % obj)
                    elif sd.get('object_coordinates', '').strip():
                        self.log.warning('Object coordinates for "%s" are '
                                         'unusable and were skipped: %r',
                                         fname, sd.get('object_coordinates'))
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
                send_path = self._path_to_send(row['filepath'], fname)
                self.api.upload(
                    filename, send_path, wikitext,
                    f'Uploaded with {APP_NAME}', self.ignore_warnings
                )
            except LocalFileError as e:
                # 0.16.1: the file could not be read from disk, so nothing
                # was ever sent. Logged WITHOUT a traceback - the sentence
                # says everything the stack does not, and a traceback here
                # reads like a crash in Cammello when the problem is the
                # user's storage. Marked UNREADABLE, not FAILED, so a resume
                # picks it up once the file is available again.
                self.log.error('✗ Cannot read "%s": %s', e.path, e.reason)
                msg = str(e)
                self._journal_mark(row, journal_mod.UNREADABLE, error=msg)
                self.error.emit(i, msg)
                self.progress.emit(i, '✗ ' + tr('Unreadable'))
                unreadable_count += 1
                continue
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
                    elif key.startswith('alt_'):
                        # 0.15.2: alt text -> P11265, a MONOLINGUAL value,
                        # so the language rides along with the text. There
                        # is no wikitext counterpart on Commons: {{Alt}} is
                        # the language template for Southern Altai (ISO
                        # code "alt"), NOT an alt-text template - using it
                        # would tag the text as Altai.
                        if val.strip():
                            claims.append((ALT_TEXT_PROPERTY,
                                           ('monolingual', val.strip(),
                                            key[4:])))
                    elif key in PROPERTY_MAP:
                        prop = PROPERTY_MAP[key]
                        if key in ('coordinates', 'object_coordinates'):
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

                if self.capture_sdc:
                    # 0.15.0: the EXIF capture settings as quantity claims.
                    # Read from the file at upload time - transparent, no
                    # field to fill. Property and unit QIDs were verified on
                    # wikidata.org (see exif.read_capture_settings).
                    cap = read_capture_settings(row['filepath'], self.log)
                    for key, prop, unit in (
                            ('exposure_time', 'P6757', 'Q11574'),
                            ('f_number', 'P6790', None),
                            ('iso', 'P6789', None),
                            ('focal_length', 'P2151', 'Q174789')):
                        if key in cap:
                            claims.append(
                                (prop, ('quantity', cap[key], unit)))
                    # Camera (P4082) and lens (P11385) - ONLY when the EXIF
                    # string maps to exactly one Wikidata item. The camera
                    # table is generated from Wikidata's own P2009/P2010
                    # statements (make_camera_map.py); ambiguous strings
                    # are not in it, so a hit IS the uniqueness rule.
                    ids = read_camera_ids(row['filepath'], self.log)
                    qid = camera_map.camera_qid(ids.get('make'),
                                                ids.get('model'))
                    if qid:
                        claims.append(('P4082', qid))
                    elif ids.get('model'):
                        self.log.info('Camera "%s" not in the map (or '
                                      'ambiguous) - no P4082 for "%s".',
                                      ids['model'], fname)
                    lq = camera_map.lens_qid(ids.get('lens_model'))
                    if lq:
                        claims.append(('P11385', lq))
                    # Inception (P571, day precision) from the capture
                    # date, and the media type (P1163) from the extension.
                    date_part = (row.get('date') or '')[:10]
                    if re.match(r'^\d{4}-\d{2}-\d{2}$', date_part):
                        claims.append(('P571', ('time', date_part)))
                    ext = os.path.splitext(row['filepath'])[1].lower()
                    mime = {'.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                            '.png': 'image/png', '.tif': 'image/tiff',
                            '.tiff': 'image/tiff', '.webp': 'image/webp'
                            }.get(ext)
                    if mime:
                        claims.append(('P1163', ('string', mime)))
                    # Source of file (P7482) - ONLY the unambiguous case:
                    # the source field says "own work". A Flickr import or
                    # a scan needs a judgement this cannot make, and gets
                    # no statement rather than a guessed one.
                    src = (row.get('source') or '').strip()
                    bare = src.strip('{} ').strip().lower()
                    if bare in OWN_WORK_TEMPLATES:
                        claims.append((SOURCE_PROPERTY, SOURCE_OWN_WORK))

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

                # Collect gallery entry.
                # 0.15.2 (Harald): ONE field. What stands in the base
                # description IS the gallery page name - no prefix setting,
                # no composition. A value left over from the old
                # prefix+suffix days is migrated when the description is
                # loaded, so nothing has to be retyped.
                gallery_page = sd.get('gallery_suffix', '').strip() or None

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
        # 0.15.0: the rendered copies are throwaway - remove them however
        # the run ended (finished, cancelled, or after an error).
        self._cleanup_edit_tmp()
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
                          '%d/%d succeeded, %d SDC failure(s), '
                          '%d unreadable ===',
                          success_count, total, sdc_failures,
                          unreadable_count)
            self.finished.emit(
                f'Done: {success_count}/{total} file(s) uploaded. The cancel '
                f'arrived while the last file was already being uploaded, so '
                f'the run finished.{sdc_note}'
            )
        else:
            self.log.info('=== Upload run finished: %d/%d succeeded, '
                          '%d SDC failure(s), %d unreadable ===',
                          success_count, total, sdc_failures,
                          unreadable_count)
            # 0.16.1: a run that ends "11/501" without a word about the
            # other 490 tells the user nothing. If files could not be read,
            # say so here - that is the one line they will actually see.
            note = sdc_note
            if unreadable_count:
                note += ' ' + tr(
                    '{n} file(s) could not be read from disk and were not '
                    'uploaded - see the log for the paths. They stay in the '
                    'queue and can be resumed.').format(n=unreadable_count)
            self.finished.emit(
                f'Done: {success_count}/{total} file(s) uploaded.{note}'
            )


# ── Login / test worker ────────────────────────────────────────────────────────


class LoginWorker(QThread):
    success = pyqtSignal(object)   # MediaWikiApi instance
    failure = pyqtSignal(str)

    def __init__(self, api_url, username, password, timeout, logger,
                 oauth_token=None, oauth_secret=None,
                 bearer_token=None, bearer_refresher=None):
        super().__init__()
        self.api_url = api_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.logger = logger
        self.oauth_token = oauth_token
        self.oauth_secret = oauth_secret
        self.bearer_token = bearer_token
        self.bearer_refresher = bearer_refresher

    def run(self):
        try:
            api = MediaWikiApi(self.api_url, self.username, self.password,
                               timeout=self.timeout, logger=self.logger,
                               oauth_token=self.oauth_token,
                               oauth_secret=self.oauth_secret,
                               bearer_token=self.bearer_token,
                               bearer_refresher=self.bearer_refresher)
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
