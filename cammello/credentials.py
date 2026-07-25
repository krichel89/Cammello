"""OS keyring storage for every credential Cammello holds.

One module, one rule: secrets live in the operating system's credential
store (Windows Credential Manager, macOS Keychain, Linux Secret Service /
KWallet) via the `keyring` library; QSettings keeps only non-secret data
(usernames, hosts, flags).

Design decisions
----------------
* Graceful degradation, never a hard dependency: if `keyring` is missing or
  no usable backend exists (headless Linux, stripped-down desktops), every
  function here returns None/False and the callers keep their existing
  QSettings plaintext path.  `backend_available()` tells the Settings tab
  which mode is active so it can show an honest hint.
* One keyring "service" (SERVICE) for the whole app; the credential is
  addressed by a slot string ("mediawiki:User", "ftp:user@host", ...).
  The slot helpers below are the only place slot names are composed -
  callers must not build slot strings by hand.
* Migration is explicit and destructive on success only:
  `migrate_qsettings_value()` moves a plaintext value into the keyring and
  removes the QSettings key afterwards.  If the keyring write fails, the
  QSettings value is left untouched.
* No PyQt imports here except for typing convenience via duck-typing -
  the module works with any object that has value()/setValue()/remove()
  (i.e. QSettings), so it stays unit-testable without a QApplication.

Packaging notes (PyInstaller)
-----------------------------
`keyring` selects its backend at runtime; PyInstaller does not see that.
Add to the spec/CLI:
    --hidden-import keyring.backends.Windows
    --hidden-import keyring.backends.macOS
    --hidden-import keyring.backends.SecretService
    --hidden-import keyring.backends.kwallet
On Linux, `keyring` needs the `secretstorage` + `jeepney` wheels (pulled in
automatically by pip).  requirements.txt: add `keyring>=24`.
"""
import logging

log = logging.getLogger(__name__)

SERVICE = 'Cammello'

try:                                    # soft dependency, see module docstring
    import keyring
    import keyring.errors
except ImportError:                     # pragma: no cover - environment detail
    keyring = None


# ── Slot naming ──────────────────────────────────────────────────────────────
# The slot is the keyring "username" field; SERVICE is constant.  Keep these
# helpers as the single source of slot names so entries stay findable.

def mediawiki_slot(username):
    """BotPassword secret for the given MediaWiki username."""
    return f'mediawiki:{username.strip()}'


def mw_oauth_slot(kind):
    """OAuth access credential, kind in ('token', 'secret', 'tokens').

    'tokens' is the combined slot introduced in 0.14: token and secret live
    in ONE keyring entry, so unlocking costs one prompt instead of two. The
    two single slots are still read once, to migrate old installations.
    """
    return f'mw-oauth:{kind}'


def ftp_slot(user, host):
    """FTP/FTPS/SFTP password for user@host."""
    return f'ftp:{user.strip()}@{host.strip()}'


def flickr_slot(kind):
    """Flickr credential, kind in ('api_secret', 'token_secret')."""
    return f'flickr:{kind}'


# ── Backend probing ──────────────────────────────────────────────────────────

_backend_ok = None      # tri-state cache: None = not probed yet


def backend_available():
    """True if a real keyring backend is usable on this machine.

    Detects the `fail.Keyring` placeholder backend and an empty chainer,
    both of which `keyring` may return instead of raising.
    """
    global _backend_ok
    if _backend_ok is not None:
        return _backend_ok
    if keyring is None:
        _backend_ok = False
        return False
    try:
        backend = keyring.get_keyring()
        name = type(backend).__module__ + '.' + type(backend).__name__
        if '.fail.' in name:
            _backend_ok = False
        elif hasattr(backend, 'backends'):          # ChainerBackend
            _backend_ok = bool(getattr(backend, 'backends'))
        else:
            _backend_ok = True
        log.debug('keyring backend: %s (usable=%s)', name, _backend_ok)
    except Exception as exc:                        # backend probing must not crash
        log.warning('keyring probe failed: %s', exc)
        _backend_ok = False
    return _backend_ok


def backend_name():
    """Human-readable backend name for the Settings tab ('' if none)."""
    if not backend_available():
        return ''
    try:
        return type(keyring.get_keyring()).__name__
    except Exception:
        return ''


# ── Store / load / delete ────────────────────────────────────────────────────
# All three swallow backend exceptions (locked keychains, D-Bus hiccups,
# permission prompts denied by the user) and report via return value + log.

# Session cache (0.14). Every keyring read can raise a system prompt, and
# an unsigned macOS bundle is asked again for every single read. Values
# fetched once are therefore kept for the life of the process - they cannot
# change behind our back, since this process is the only writer.
_cache = {}


def clear_cache():
    """Forget cached secrets (used after a logout)."""
    _cache.clear()


def store(slot, secret):
    """Put `secret` into the keyring under `slot`.  -> bool success."""
    if not backend_available():
        return False
    try:
        keyring.set_password(SERVICE, slot, secret)
        _cache[slot] = secret
        return True
    except Exception as exc:
        log.warning('keyring store failed for %s: %s', slot, exc)
        return False


def load(slot):
    """-> secret string, or None (not stored, no backend, or backend error).

    Cached for the life of the process: on macOS an unsigned bundle is
    prompted for EVERY read, so reading the same slot twice meant two
    password dialogs.
    """
    if slot in _cache:
        return _cache[slot]
    if not backend_available():
        return None
    try:
        value = keyring.get_password(SERVICE, slot)
    except Exception as exc:
        log.warning('keyring load failed for %s: %s', slot, exc)
        return None
    _cache[slot] = value
    return value


def delete(slot):
    """Remove `slot` from the keyring.  Missing entries count as success."""
    _cache.pop(slot, None)
    if not backend_available():
        return False
    try:
        keyring.delete_password(SERVICE, slot)
        return True
    except Exception as exc:
        if keyring is not None and isinstance(
                exc, keyring.errors.PasswordDeleteError):
            return True                             # was not stored - fine
        log.warning('keyring delete failed for %s: %s', slot, exc)
        return False


# ── One-time migration from QSettings plaintext ──────────────────────────────

def migrate_qsettings_value(settings, key, slot):
    """Move a plaintext secret out of QSettings into the keyring.

    settings: a QSettings (or anything with value/setValue/remove/sync).
    Returns the secret that is now authoritative (from keyring if possible,
    else the old plaintext), or '' if nothing is stored anywhere.

    Rules:
    * keyring already has a value  -> it wins; a leftover QSettings copy is
      removed.
    * only QSettings has a value   -> copied to keyring; removed from
      QSettings ONLY if the keyring write succeeded.
    * no backend                   -> plaintext returned unchanged (status
      quo, caller keeps working).
    """
    stored = load(slot)
    plain = settings.value(key, '') or ''
    if stored is not None and stored != '':
        if plain:
            settings.remove(key)
            settings.sync()
            log.info('removed plaintext %r (keyring already holds %s)',
                     key, slot)
        return stored
    if plain:
        if store(slot, plain):
            settings.remove(key)
            settings.sync()
            log.info('migrated %r to keyring slot %s', key, slot)
        return plain
    return ''


# ── MediaWiki BotPassword: keyring with QSettings-plaintext fallback ─────────
# The BotPassword was the last plaintext secret in QSettings. These two
# helpers move it into the OS keyring (keyed by username), while keeping the
# old plaintext path working verbatim when no keyring backend exists.

def load_mediawiki_password(settings, username):
    """Return the MediaWiki BotPassword for `username`.

    keyring (per username) wins; without a backend, or when nothing is stored
    there, the QSettings plaintext value is returned unchanged. Also performs
    the one-time migration of an existing plaintext value into the keyring, so
    a first run after upgrading silently moves the secret out of QSettings.
    """
    username = (username or '').strip()
    if not username:
        return settings.value('password', '') or ''
    return migrate_qsettings_value(settings, 'password',
                                   mediawiki_slot(username))


def save_mediawiki_password(settings, username, password):
    """Persist the MediaWiki BotPassword.

    With a keyring backend: store under mediawiki_slot(username) and drop the
    QSettings plaintext copy (an empty password deletes the entry). Without a
    backend: keep writing QSettings plaintext, exactly as before.
    """
    username = (username or '').strip()
    if backend_available() and username:
        if password:
            if store(mediawiki_slot(username), password):
                settings.remove('password')
                settings.sync()
                return
        else:                               # cleared password -> remove secret
            delete(mediawiki_slot(username))
            settings.remove('password')
            settings.sync()
            return
    # no backend (or no username yet): status-quo plaintext path
    settings.setValue('password', password)
    settings.sync()
