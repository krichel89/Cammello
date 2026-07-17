## Cammello 0.12.0

Start of the 0.12 line: a tidier culling toolbar, a roomier MediaWiki editor,
and the OAuth sign-in wired all the way through to the actual uploads.

### Culling tab — less clutter
- **"Open folder…" → "Open…"**, with **Reload** now sitting right next to it as
  a compact **⟳** icon button (it used to live far off on the right).
- **Zoom toolbar controls removed.** Zoom is mouse-wheel / trackpad and
  **Cmd/Ctrl +/-** only now — the −/read-out/+ buttons were redundant.
- **Filter controls consolidated** into one cluster under a single **Filter:**
  label (the separate "Show:" and "Colours:" labels are gone; tooltips carry
  the meaning).
- **"Send to:" label removed**; the folder-export button is now **"Save to…"**.

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

### Internal
- `test_cullview.py` updated for the removed zoom read-out/buttons (it now
  drives the unchanged zoom ladder via the keyboard path).
