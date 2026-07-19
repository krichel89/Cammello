## Cammello 0.12.7

The first round of fixes from testing 0.12.6 on Mac and Windows: the
culling view shows what it discards, the interface stops looking like two
different programs, and the sign-in finally leaves a trail.

### Culling
- **Rejects stay on screen.** A rejected image is no longer filtered out of
  the strip; it stays where it is, greyed out with a red ✕, so you can see
  what you discarded and take it back. The checkbox is inverted
  accordingly: it now reads *hide rejects* and starts unchecked. One
  exception on purpose - as soon as a star filter is active, rejects drop
  out. "Three stars and up" is a question about your selects, not about the
  bin.
- **Stars can no longer run away.** A file was drawn with an endless row of
  stars. Ratings read from XMP are now clamped to the valid range, an
  out-of-range value is written to the log together with the raw string
  from the file, and every place that paints stars goes through one helper
  that cannot produce more than five.

### Look
- **Module strip:** all four titles are bold permanently, and only their
  colour says which one is active. The 0.12.6 attempt measured the bold
  text and added a margin - a guess that was still too small on Windows.
  With a constant weight the width simply never changes.
- **One kind of button.** Culling and MediaWiki looked like different
  programs because their bars were built from different widget classes.
  The button chrome now lives in one stylesheet and covers both, in the
  MediaWiki look. The green Upload button keeps its accent.
- **Quieter section headings.** The blue badge with white bold text was
  competing with the fields underneath; the heading is now accent-coloured
  text on a thin rule.
- **Slightly larger UI font** - one point, applied to the application, so
  menus and dialogs grow along with everything else.
- **Windows dark mode:** greyed-out menu entries are actually grey now. The
  native Windows style paints menu items itself and ignores the stylesheet
  colour, which is why macOS was fixed in 0.12.6 and Windows was not.
  Windows now uses the Fusion painter in every colour scheme, with the
  system palette kept.

### Sign-in
- **The manual path takes the address from the browser.** After "Allow",
  Meta redirects to the local callback even when the manual mode was
  requested - and if nothing is listening there, the browser shows a
  connection error. The confirmation was in the address bar the whole time.
  That entire address can now be pasted into the field; Cammello reads the
  confirmation out of it. A plain code still works.
- **The manual path is no longer a dead end.** It used to ask the wiki for
  an "oob" confirmation and start no local server. But this consumer has its
  callback registered as a required prefix, so Special:OAuth redirects the
  browser to that callback anyway - onto a port where nothing was listening.
  Manual mode now starts the same loopback server as the automatic flow: if
  the redirect arrives, you are signed in without touching anything, and
  pasting is only the fallback. A real "oob" request is used just for the
  one case it fits, a port that cannot be bound.
- **The wait is 600 seconds** instead of 300, and running out is written to
  the log instead of failing silently. Taking your time must never be the
  reason a sign-in fails.
- **The authorization flow writes to the log.** Start, mode, the link, the
  arriving token, success, failure, cancel. A failed sign-in used to leave
  no trace at all, which made it impossible to tell from the log what went
  wrong. No secrets are logged.
