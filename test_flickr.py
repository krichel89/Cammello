"""Flickr support checks (0.10.0).

Live calls to flickr.com are NOT possible from the test environment, so the
signing machinery is verified against the canonical worked example from the
OAuth Core 1.0 specification (Appendix A.5.1/A.5.2): with the documented
consumer/token secrets and fixed nonce/timestamp the HMAC-SHA1 signature MUST
be tR3+Ty81lMeYAr/Fid0kMTYa/WM= - anything else means the base-string
construction or encoding is wrong and every real request would fail.
The upload worker is exercised with a mock client (no network).
"""
import os
import sys

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import QSettings

import Cammello  # noqa: F401
from cammello.flickr import (oauth_signature, oauth_base_params,
                             FlickrClient, FlickrUploadWorker)
from cammello.constants import APP_NAME
from cammello.logging_setup import setup_logging
from cammello.i18n import set_language

fails = []


def check(name, cond, detail=''):
    print(('PASS' if cond else 'FAIL'), name, detail)
    if not cond:
        fails.append(name)


# ── 1) OAuth 1.0 spec vector ─────────────────────────────────────────────────
params = {
    'oauth_consumer_key': 'dpf43f3p2l4k3l03',
    'oauth_token': 'nnch734d00sl2jdk',
    'oauth_signature_method': 'HMAC-SHA1',
    'oauth_timestamp': '1191242096',
    'oauth_nonce': 'kllo9940pd9333jh',
    'oauth_version': '1.0',
    'file': 'vacation.jpg',
    'size': 'original',
}
sig = oauth_signature('GET', 'http://photos.example.net/photos', params,
                      'kd94hf93k423kf44', 'pfkkdhi9sl3r4s00')
check('OAuth spec vector signature', sig == 'tR3+Ty81lMeYAr/Fid0kMTYa/WM=',
      sig)

# Percent-encoding edge cases: space, plus, tilde, umlaut.
sig2 = oauth_signature('POST', 'https://api.flickr.com/services/rest/',
                       {'a': 'x y+z~ä', 'oauth_nonce': 'n'}, 's')
check('signature with special chars is stable', isinstance(sig2, str)
      and len(sig2) == 28, sig2)

base = oauth_base_params('key', 'tok')
check('base params complete',
      {'oauth_consumer_key', 'oauth_nonce', 'oauth_signature_method',
       'oauth_timestamp', 'oauth_version', 'oauth_token'} == set(base))
check('authorize url', FlickrClient.authorize_url('T')
      == 'https://www.flickr.com/services/oauth/authorize?oauth_token=T&perms=write')

# ── 2) Upload worker with a mock client (no network) ─────────────────────────
app = QApplication(sys.argv)
logger, emitter, gui_handler, log_path = setup_logging()
set_language('en')


class _MockClient:
    def __init__(self):
        self.uploaded, self.titles = [], []

    def upload(self, path):
        if 'bad' in path:
            raise RuntimeError('boom')
        self.uploaded.append(path)
        return f'id{len(self.uploaded)}'

    def set_title(self, photo_id, title, description=''):
        self.titles.append((photo_id, title))


mock = _MockClient()
worker = FlickrUploadWorker(mock, [('/tmp/a.jpg', 'Title A'),
                                   ('/tmp/bad.jpg', 'Bad'),
                                   ('/tmp/c.jpg', 'Title C')], logger)
summaries, statuses = [], []
worker.finished.connect(summaries.append)
worker.progress.connect(lambda i, s: statuses.append(s))
worker.run()
check('worker: 2 uploaded', mock.uploaded == ['/tmp/a.jpg', '/tmp/c.jpg'])
check('worker: titles set', mock.titles == [('id1', 'Title A'),
                                            ('id2', 'Title C')])
check('worker: summary counts', summaries and '2/3' in summaries[0]
      and '1 failed' in summaries[0], str(summaries))
done = [s for s in statuses if s.startswith(('✓', '✗'))]
check('worker: 3 completion statuses', len(done) == 3, str(statuses))

# ── 3) Tab construction + feature switch ─────────────────────────────────────
settings = QSettings(APP_NAME, 'Main')
KEYS = ('feature_culling', 'feature_iptc', 'feature_ftp', 'feature_flickr')
saved = {k: settings.value(k) for k in KEYS}


def tab_names(w):
    return [w.tabs.tabText(i) for i in range(w.tabs.count())]


try:
    for k in KEYS:
        settings.setValue(k, True)
    settings.sync()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    names = tab_names(w)
    check('merged FTP / Flickr tab present', 'FTP / Flickr' in names,
          str(names))
    check('license combo present', hasattr(w, 'flickr_license_combo'))
    check('license combo default = account default',
          w.flickr_license_combo.currentData() is None)
    check('license combo has CC BY-SA',
          w.flickr_license_combo.findData('5') > 0)
    check('About tab last', names[-1] == 'About', str(names))
    check('flickr mirror in settings', hasattr(w, 'flickr_api_key_mirror'))
    w.flickr_api_key_edit.setText('k123')
    check('flickr key primary->mirror', w.flickr_api_key_mirror.text() == 'k123')
    if hasattr(w, 'cull_flickr_btn'):
        check('culling has Flickr target', True)
    else:
        check('culling has Flickr target', not w._feat_culling,
              'button missing although culling is on')
    # FTP tab now has the shared file list + count label.
    check('ftp list exists', hasattr(w, 'ftp_list'))
    check('ftp count label exists', hasattr(w, 'ftp_count_lbl'))
    check('flickr count label exists', hasattr(w, 'flickr_count_lbl'))
    if hasattr(w, '_cull_wb'):
        w._cull_shutdown()
    w.deleteLater(); app.processEvents()

    settings.setValue('feature_flickr', False)
    settings.sync()
    w = Cammello.MainWindow(logger, emitter, gui_handler, log_path)
    names = tab_names(w)
    check('flickr off: tab is plain FTP', 'FTP' in names
          and 'FTP / Flickr' not in names, str(names))
    check('flickr off: no cull button', not hasattr(w, 'cull_flickr_btn'))
    check('flickr off: no mirror', not hasattr(w, 'flickr_api_key_mirror'))
    if hasattr(w, '_cull_wb'):
        w._cull_shutdown()
    w.deleteLater(); app.processEvents()
finally:
    for k, v in saved.items():
        (settings.remove(k) if v is None else settings.setValue(k, v))
    settings.sync()

print('---')
print('FAILURES:', fails if fails else 'none')
sys.exit(1 if fails else 0)
