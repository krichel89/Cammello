## Cammello 0.13.0

Everything since 0.12.14 in one version: geodata, non-destructive
cropping, the manual in the Help menu, and three fixes to how gallery
pages are written.

### Geodata
Adding a file reads its GPS block along with the capture date - one EXIF
read, nothing to click. The value lands in the per-file description as
`coordinates=48.137154, 11.576124` and is shown in a "Coordinates" field
you can edit or clear. At upload it becomes:

    {{Location dec|48.137154|11.576124}}          in the wikitext
    P1259 "coordinates of the point of view"      in the structured data

P1259 is the CAMERA position, which is exactly what EXIF records - not
P625, which would be the position of the thing pictured.

Decisions: per file, never in the base block (every picture has its own
position); switchable in the upload settings; unparseable values are
skipped and logged rather than written as a broken template. Pillow
generally cannot read EXIF from camera RAW, so a RAW-only shot yields no
position - a RAW+JPEG pair gets it from the JPEG.

### Cropping in the culling view
Press C on an image to start a crop. A rule-of-thirds grid and eight
handles place the box, the area outside dims, and the top-left readout
shows the resulting pixel size as you drag. Number keys pick an aspect
ratio - 1 free, 2 = 3:2, 3 = 4:3, 4 = 1:1, 5 = 16:9, 6 = 5:4 - and
pressing the SAME number again flips that ratio between landscape and
portrait (2:3, 3:4, 9:16, 4:5). Enter applies, Esc cancels, Shift+C
removes. A scissors badge marks edited files in the filmstrip, and while
crop mode is on the toolbar's "[M] numbers = STARS" label turns into a
crop-key legend with the full table in its tooltip.

**Non-destructive by construction.** The source file is never modified. A
crop is stored per file (in QSettings, keyed by path, like the channel
marks) and applied only when the file leaves Cammello. Right now that is
the culling folder export: an edited file is written as a rendered
"<name>_edit.jpg" copy, unedited files are copied verbatim.

**The foundation underneath (edits.py).** A new module holds the per-image
edit record and the renderer. It already does exposure as well as crop, in
linear light with EXIF preserved, and knows how to render RAW originals
via rawpy - but the exposure UI and the wiring into the
Commons/FTP/Flickr upload paths come in a later slice. For now crop is the
visible feature; the rest is tested groundwork.

### The manual, reachable from inside the program
Help > "Cammello manual (on Commons)", or F1, opens

    https://commons.wikimedia.org/wiki/Commons:Cammello/documentation/<lang>

The five manual pages match the five UI languages one to one, so whoever
reads Cammello in French gets the French manual. An unknown language falls
back to /en rather than a red link. The address lives in constants.py
(MANUAL_BASE_URL + manual_url), not in the menu code, so the pages can
move without touching the UI.

### Gallery pages: three fixes
**A failed read no longer looks like a missing page.** get_page_content
returned None both when the page did not exist (404) and when the request
failed for any other reason - a 503, a rate limit. update_gallery reads
None as "create it", so a transient server error could replace a grown
gallery with just the current session's files. Now a failed read raises,
the gallery edit is skipped, and the error is logged and shown. Losing an
update is recoverable; losing a gallery is not.

**A page without a gallery now gets an opening tag.** The branch for "page
exists, but has no <gallery>" appended the file lines plus a closing tag -
no opening one, leaving filenames as plain text after a stray </gallery>.
It now appends a complete, balanced block.

**The page title is assembled cleanly.** It comes from the gallery prefix
(a setting, e.g. `User:Seewolf`) and the per-session suffix (e.g.
`Berlinale 2026`); you type neither slash. gallery_page_name() splits both
halves on slashes, trims every segment and drops empty ones, so a leading
slash on the suffix, a trailing one on the prefix, doubled slashes and
spaces around a slash can never reach Commons as part of the title:

    'User:Seewolf/'  + '/Berlinale 2026'   -> User:Seewolf/Berlinale 2026
    'User:Seewolf//' + '//Cannes//26//'    -> User:Seewolf/Cannes/26

Multi-level prefixes keep their own levels. A suffix without a prefix
skips the gallery and says so in the log.

### New test files
test_geo_01215.py, test_edits.py, test_crop_0130.py, test_manual_0131.py,
test_gallery_0132.py - all run headless alongside the existing suite.
