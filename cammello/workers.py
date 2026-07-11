"""Background QThread workers: upload, login, connection test."""
import os
import re
import traceback
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from .constants import *
from .sdc import *
from .api import MediaWikiApi


class UploadWorker(QThread):
    progress = pyqtSignal(int, str)   # row, status
    finished = pyqtSignal(str)        # summary message
    error = pyqtSignal(int, str)      # row, error message
    file_started = pyqtSignal(int, str)   # index, target filename

    def __init__(self, api, rows, base_text, gallery_prefix, ignore_warnings):
        super().__init__()
        self.api = api
        self.log = api.log
        self.rows = rows
        self.base_text = base_text
        self.gallery_prefix = gallery_prefix
        self.ignore_warnings = ignore_warnings
        # Set from the GUI thread by cancel(). A bool assignment is atomic
        # under the GIL, so no lock is needed. Checked between files only: an
        # HTTP request already in flight is always finished, never torn down
        # halfway, so no half-uploaded file is left on Commons.
        self._cancelled = False

    def cancel(self):
        """Request a stop. The current file is finished, then the run ends."""
        self._cancelled = True
        self.log.info('Cancel requested: stopping after the current file.')

    def run(self):
        gallery_entries = {}   # gallery_page -> list of (filename, caption)
        success_count = 0
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
                self.progress.emit(i, 'Cancelled')
                break
            try:
                self.file_started.emit(i, fname)
                self.progress.emit(i, 'Uploading…')

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

                # Always add the maintenance category (deduplicated).
                if TRACKING_CATEGORY_WIKITEXT not in cats_seen:
                    cats.append(TRACKING_CATEGORY_WIKITEXT)
                    cats_seen.add(TRACKING_CATEGORY_WIKITEXT)

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
                if other_templates:
                    parts.append(other_templates)
                if license_text:
                    parts.append(f'== {{{{int:license-header}}}} ==\n{license_text}')
                if cats_str:
                    parts.append(cats_str)
                wikitext = '\n'.join(parts)

                # Upload
                self.api.upload(
                    filename, row['filepath'], wikitext,
                    f'Uploaded with {APP_NAME}', self.ignore_warnings
                )

                # Structured data
                labels = {}
                claims = []
                for key, val in sd.items():
                    if key.startswith('caption_'):
                        lang = key[8:]
                        labels[lang] = val
                    elif key in PROPERTY_MAP:
                        prop = PROPERTY_MAP[key]
                        if key == 'depicts':
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

                # Collect gallery entry
                gallery_suffix = sd.get('gallery_suffix', '').strip()
                if self.gallery_prefix:
                    if gallery_suffix:
                        gallery_page = self.gallery_prefix.rstrip('/') + '/' + gallery_suffix
                    else:
                        gallery_page = self.gallery_prefix
                elif gallery_suffix:
                    gallery_page = None  # no prefix set -> skip gallery
                    self.log.warning('gallery_suffix set but no gallery prefix '
                                     '-> gallery skipped for "%s".', fname)
                else:
                    gallery_page = self.gallery_prefix or None

                caption = sd.get('caption_en', '')
                gallery_entries.setdefault(gallery_page, []).append(
                    (filename, caption)
                )

                self.progress.emit(i, '✓ Done')
                success_count += 1

            except Exception as e:
                # Full text + traceback to the log, compact message to the table.
                self.log.error('✗ Error for "%s": %s', fname, e, exc_info=True)
                msg = str(e) or f'{type(e).__name__} (no message)'
                self.error.emit(i, msg)
                self.progress.emit(i, '✗ Error')

        # Update galleries. Files that did go up are still added to the
        # gallery, even after a cancel - they exist on Commons now.
        for gallery_page, entries in gallery_entries.items():
            if not gallery_page:
                continue
            try:
                self.api.update_gallery(gallery_page, entries)
            except Exception as e:
                self.log.error('✗ Gallery error (%s): %s',
                               gallery_page, e, exc_info=True)
                self.error.emit(-1, f'Gallery error ({gallery_page}): {e}')

        total = len(self.rows)
        if cancelled_at is not None:
            skipped = total - cancelled_at
            self.log.info('=== Upload run cancelled: %d/%d succeeded, '
                          '%d not started ===', success_count, total, skipped)
            self.finished.emit(
                f'Cancelled: {success_count}/{total} file(s) uploaded, '
                f'{skipped} not started.'
            )
        else:
            self.log.info('=== Upload run finished: %d/%d succeeded ===',
                          success_count, total)
            self.finished.emit(
                f'Done: {success_count}/{total} file(s) uploaded.'
            )


# ── Login / test worker ────────────────────────────────────────────────────────


class LoginWorker(QThread):
    success = pyqtSignal(object)   # MediaWikiApi instance
    failure = pyqtSignal(str)

    def __init__(self, api_url, username, password, timeout, logger):
        super().__init__()
        self.api_url = api_url
        self.username = username
        self.password = password
        self.timeout = timeout
        self.logger = logger

    def run(self):
        try:
            api = MediaWikiApi(self.api_url, self.username, self.password,
                               timeout=self.timeout, logger=self.logger)
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
