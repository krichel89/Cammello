## Cammello 0.12.0

Start of the 0.12 line: a tidier culling toolbar, a roomier MediaWiki editor,
and the OAuth sign-in wired all the way through to the actual uploads.

### Culling tab — less clutter
- **"Open folder…" → "Open…"**, with **Reload** now sitting right next to it as
  a compact **⟳** icon button (it used to live far off on the right; the glyph
  is scaled up so it reads clearly).
- **Zoom toolbar controls removed.** Zoom is mouse-wheel / trackpad and
  **Cmd/Ctrl +/-** only now — the −/read-out/+ buttons were redundant.
- **Filter controls consolidated** into one cluster under a single **Filter:**
  label (the separate "Show:" and "Colours:" labels are gone; tooltips carry
  the meaning).
- **"Send to:" label removed**; the staging button is now **"Add to tabs"**
  (de: "Übernehmen" — the old "Apply" was misleading), and the folder-export
  button is now **"Save to…"**.

### MediaWiki tab — F2 rename, like Lightroom
- **F2 renames the target Commons filename.** One selected row: F2 opens the
  inline editor on the "Target filename" cell (extension stays fixed, as
  before). Several rows: F2 opens a **bulk-rename dialog** with a name
  template — `{n}` becomes a running number (auto-appended if missing),
  zero-padded, with a free start number and a live preview. Only the Commons
  target name changes; source files on disk are never touched. Template and
  start number are remembered.

### MediaWiki tab — more room for categories
- The **"Suggest category"** buttons are now a compact **"Suggest"** sitting
  right behind the Categories field, so the category field itself gets the
  space. Their tooltips still explain exactly what each one adds.

### OAuth sign-in now drives uploads
- The stored OAuth access token is now used for real: every API request is
  signed with an `Authorization` header (RFC 5849 / HMAC-SHA1, reusing the
  verified Flickr signing code); multipart upload bodies are correctly
  excluded from the signature.
- When a consumer is configured **and** you have authorized once, **Login**
  skips the password dialog and signs in via OAuth automatically; BotPassword
  stays the path otherwise. No login handshake and no session cookie — the
  header authenticates every call.
- Dormant until the consumer key/secret are filled in on Meta, so behaviour is
  unchanged for BotPassword users.

### Settings
- The **language dropdown** now carries a permanent gray "(takes effect after
  a restart)" hint next to it (the status-bar message alone was easy to miss).

### Release tooling
- **Wikidata is updated automatically on release.** `release.sh` now calls
  `wd edit-entity ./wikidata_version.js <version>` (wikibase-cli): the new
  version lands on Q140509313 as P348 with publication date (P577) and the
  release-tag URL as reference (P854); it gets rank *preferred* while
  superseded versions are demoted to *normal*. Re-runs are idempotent (the
  new version is excluded from the demotion), and the whole step is
  non-fatal — a Wikidata hiccup never blocks a release. One-time setup:
  `npm install -g wikibase-cli` and `wd config credentials
  https://www.wikidata.org`.

### Internal / code review
- Dead code removed: the culling tab's direct FTP/Flickr send handlers
  (orphaned since their buttons went away in 0.11.8).
- i18n: duplicate dictionary keys deduplicated ('License:', 'Categories').
- Review pass over efficiency/security: every outgoing HTTP request carries a
  timeout; login/CSRF tokens stay redacted in logs; the OAuth Authorization
  header is never logged; API URL remains HTTPS-enforced; OAuth identify JWTs
  are verified (alg pin, constant-time signature check, iss/aud/exp).
- `test_cullview.py` updated for the removed zoom read-out/buttons (it now
  drives the unchanged zoom ladder via the keyboard path).
