Downloads for macOS, Windows and Linux are attached below.

**Added**
- **Wikimedia OAuth sign-in (opt-in, not yet active).** A one-click login flow is now built in; it stays hidden until a registered OAuth consumer key is configured, so nothing changes for current logins. Until then, the BotPassword login remains the standard way in.
- **MediaWiki password now stored in the OS keyring** (macOS Keychain, Windows Credential Manager, Linux Secret Service) instead of plain text. Any existing plaintext password is migrated automatically on first start. Without a keyring backend, the previous plaintext behaviour is kept unchanged.
- **Show/hide tabs in Settings.** A new "Tabs" section lets you hide any tab except Settings and About (Culling, MediaWiki, IPTC, FTP, Flickr, Log). Applied after a restart.

**Fixed / restored**
- `exifread` is a listed dependency again (it went missing from the 0.11.3 packaging), so the camera name shows in the EXIF overlay for RAW files.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
