## Cammello 0.12.1

One feature: **channel marks** keep CC-licensed Commons material and
commercial stock material cleanly apart — without hiding anything.

### Channel marks (Commons vs. commercial)
Right-click one or more files — in the MediaWiki table or the FTP/Flickr
list — and choose:

- **Mark for Commons (CC)** — green colour code
- **Mark for commercial use (FTP/Flickr)** — orange colour code
- **Remove channel mark**

A marked file **stays in every list**, but in the *other* channel it is
grayed out and locked: a Commons-marked file appears gray in the FTP/Flickr
list, cannot be selected there and is skipped by FTP and Flickr uploads
(with a log note); a commercially-marked file appears gray in the MediaWiki
table, cannot be selected or edited there and is skipped by the Commons
upload. Tooltips on the grayed entries explain why.

Unmarked files behave exactly as before — marking is the opt-in. Marks
persist across sessions (keyed by file path), so a file you once released
under CC stays protected from the commercial channel the next time you load
the same folder — and vice versa.

The exclusion is enforced twice: grayed entries are unselectable, **and**
every upload path filters marked files out again (also on the
"nothing selected = all files" fallback), so no stale selection can slip
one through.
