"""FTP / FTPS / SFTP upload worker for the IPTC tab.

paramiko (SFTP) is an OPTIONAL dependency; plain FTP and FTPS use ftplib from
the standard library. The worker mirrors the Commons UploadWorker: progress
per file, cancel between files, a summary at the end.

For testability the network client is built by a factory that can be replaced
in tests (FtpUploadWorker(..., client_factory=...)); the default factory picks
ftplib or paramiko based on the protocol.
"""
import os

from PyQt5.QtCore import QThread, pyqtSignal

from .i18n import tr

try:
    import paramiko
    _PARAMIKO_ERROR = None
except Exception as e:
    paramiko = None
    _PARAMIKO_ERROR = str(e)

PROTOCOLS = ['ftp', 'ftps', 'sftp']
DEFAULT_PORTS = {'ftp': 21, 'ftps': 21, 'sftp': 22}


def sftp_available():
    return paramiko is not None


def sftp_unavailable_reason():
    return _PARAMIKO_ERROR or 'paramiko is not installed'


class _FtpClient:
    """Thin uniform wrapper around ftplib.FTP / FTP_TLS."""

    def __init__(self, host, port, user, password, timeout, use_tls):
        import ftplib
        import ssl
        if use_tls:
            # SECURITY: ftplib's default TLS context does NOT verify server
            # certificates. create_default_context() enables certificate
            # verification and hostname checking.
            self._ftp = ftplib.FTP_TLS(context=ssl.create_default_context())
        else:
            self._ftp = ftplib.FTP()
        self._ftp.connect(host, port, timeout=timeout)
        self._ftp.login(user, password)
        if use_tls:
            self._ftp.prot_p()          # encrypt the data channel too

    def chdir(self, remote_dir):
        if remote_dir:
            self._ftp.cwd(remote_dir)

    def put(self, local_path, remote_name):
        with open(local_path, 'rb') as f:
            self._ftp.storbinary(f'STOR {remote_name}', f)

    def close(self):
        try:
            self._ftp.quit()
        except Exception:
            self._ftp.close()


class _SftpClient:
    def __init__(self, host, port, user, password, timeout):
        if paramiko is None:
            raise RuntimeError(sftp_unavailable_reason())
        self._transport = paramiko.Transport((host, port))
        # Password auth only for now; key files would be a separate feature.
        self._transport.banner_timeout = timeout
        self._transport.start_client(timeout=timeout)
        # SECURITY: verify the server's host key against ~/.ssh/known_hosts
        # instead of blindly trusting whatever answers (MITM protection).
        # A host that is not in known_hosts is REJECTED with an instructive
        # message - connect once with the ssh/sftp command line to add it.
        self._verify_host_key(host, port)
        self._transport.auth_password(username=user, password=password)
        self._sftp = paramiko.SFTPClient.from_transport(self._transport)

    def _verify_host_key(self, host, port):
        server_key = self._transport.get_remote_server_key()
        known = paramiko.HostKeys()
        path = os.path.expanduser('~/.ssh/known_hosts')
        try:
            known.load(path)
        except IOError:
            pass
        lookup_names = [host if port in (22, None, '') else f'[{host}]:{port}']
        for name in lookup_names:
            entry = known.lookup(name)
            if entry is not None:
                stored = entry.get(server_key.get_name())
                if stored is not None and stored == server_key:
                    return
                if stored is not None:
                    self._transport.close()
                    raise RuntimeError(
                        f'HOST KEY MISMATCH for {name}: the server key does '
                        f'not match ~/.ssh/known_hosts. This can indicate a '
                        f'man-in-the-middle attack - not connecting.')
        self._transport.close()
        raise RuntimeError(
            f'Unknown host key for {lookup_names[0]}: not found in '
            f'~/.ssh/known_hosts. Connect once with "sftp {host}" on the '
            f'command line to review and store the key, then retry.')

    def chdir(self, remote_dir):
        if remote_dir:
            self._sftp.chdir(remote_dir)

    def put(self, local_path, remote_name):
        self._sftp.put(local_path, remote_name)

    def close(self):
        try:
            self._sftp.close()
        finally:
            self._transport.close()


def default_client_factory(protocol, host, port, user, password, timeout):
    if protocol == 'sftp':
        return _SftpClient(host, port, user, password, timeout)
    return _FtpClient(host, port, user, password, timeout,
                      use_tls=(protocol == 'ftps'))


class FtpUploadWorker(QThread):
    progress = pyqtSignal(int, str)        # index, status text
    file_started = pyqtSignal(int, str)    # index, filename
    error = pyqtSignal(int, str)           # index (-1 = global), message
    finished = pyqtSignal(str)             # summary

    def __init__(self, protocol, host, port, user, password, remote_dir,
                 files, logger, timeout=30, client_factory=None):
        """files: list of (local_path, remote_name)."""
        super().__init__()
        self.protocol = protocol
        self.host = host
        self.port = int(port or DEFAULT_PORTS.get(protocol, 21))
        self.user = user
        self.password = password
        self.remote_dir = remote_dir
        self.files = files
        self.log = logger
        self.timeout = timeout
        self.client_factory = client_factory or default_client_factory
        self._cancelled = False

    def cancel(self):
        self._cancelled = True
        self.log.info('FTP cancel requested: stopping after the current file.')

    def run(self):
        total = len(self.files)
        self.log.info('=== %s upload to %s:%s started: %d file(s) ===',
                      self.protocol.upper(), self.host, self.port, total)
        try:
            client = self.client_factory(self.protocol, self.host, self.port,
                                         self.user, self.password, self.timeout)
        except Exception as e:
            self.log.error('Connection to %s failed: %s', self.host, e,
                           exc_info=True)
            self.error.emit(-1, tr('Connection failed: {e}').format(e=e))
            self.finished.emit(
                tr('Failed: could not connect to {host}.').format(host=self.host))
            return

        ok = 0
        cancelled_at = None
        try:
            try:
                client.chdir(self.remote_dir)
            except Exception as e:
                self.log.error('Remote directory "%s": %s', self.remote_dir, e,
                               exc_info=True)
                self.error.emit(-1, tr('Remote directory: {e}').format(e=e))
                self.finished.emit(
                    tr('Failed: remote directory "{dir}".').format(
                        dir=self.remote_dir))
                return

            for i, (local, remote) in enumerate(self.files):
                if self._cancelled:
                    cancelled_at = i
                    self.progress.emit(i, tr('Cancelled'))
                    break
                self.file_started.emit(i, remote)
                self.progress.emit(i, tr('Uploading…'))
                try:
                    client.put(local, remote)
                except Exception as e:
                    self.log.error('✗ FTP error for "%s": %s', remote, e,
                                   exc_info=True)
                    self.error.emit(i, str(e) or type(e).__name__)
                    self.progress.emit(i, '✗ ' + tr('Error'))
                    continue
                self.log.info('✓ Sent: "%s"', remote)
                self.progress.emit(i, '✓ ' + tr('Sent'))
                ok += 1
        finally:
            client.close()

        if cancelled_at is not None:
            skipped = total - cancelled_at
            self.log.info('=== FTP upload cancelled: %d/%d sent, %d not '
                          'started ===', ok, total, skipped)
            self.finished.emit(
                tr('Cancelled: {ok}/{total} file(s) sent, '
                   '{skipped} not started.').format(
                    ok=ok, total=total, skipped=skipped))
        else:
            self.log.info('=== FTP upload finished: %d/%d sent ===', ok, total)
            self.finished.emit(
                tr('Done: {ok}/{total} file(s) sent.').format(ok=ok, total=total))
