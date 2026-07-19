## Cammello 0.12.2

A reliability fallback for OAuth sign-in.

### OAuth: out-of-band (manual code) sign-in
The Wikimedia sign-in dialog has a new checkbox, **"Enter the confirmation
code manually"**. With it on, Cammello no longer waits for the loopback
redirect; instead it authorizes with `oauth_callback=oob`:

1. Click **Start authorization** — Cammello opens (or shows) the authorize
   link.
2. In the browser, click **Allow**. The wiki now displays a short
   **confirmation code** instead of redirecting.
3. Paste that code into Cammello and click **Finish**.

Because `oob` is always accepted by the wiki, this path works with **any**
consumer — no matter its callback URL, its "callback is prefix" setting, or
whether it has been approved yet. It's the dependable way in when the
automatic loopback confirmation can't be used.

The normal loopback flow is unchanged and stays the default; the manual
option is only there when you need it.

### Registration note (documentation)
The `mw_oauth` module docstring now states the correct loopback callback to
register: the **bare host** `http://127.0.0.1` (or `http://127.0.0.1:`).
Special:OAuth compares the callback as a plain string prefix, so a
registered `http://127.0.0.1/cammello/` can never match the random-port
callback `http://127.0.0.1:<port>/cammello/`. No code behaviour changed.
