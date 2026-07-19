## Cammello 0.12.3

Culling speed: one file open per image instead of up to six.

### Faster browsing of large folders
Cammello already previews RAW files Photo Mechanic-style — it shows the
camera-rendered JPEG embedded in every RAW instead of decoding the RAW.
What still cost time was that each image was **opened repeatedly**: once for
the embedded preview, and once more per zoom level (filmstrip thumb, screen
view, 100%) just to re-read the orientation.

0.12.3 reads the orientation **in the same open** that extracts the embedded
preview and caches it for the session, so thumb, screen view and 100% zoom
all reuse it. For RAW-heavy festival folders that cuts the file opens per
image from up to six to one — scrolling and zooming get noticeably snappier,
especially from slower disks or network volumes.

The cache is cleared automatically when a folder is (re)loaded, so swapped
cards and re-imports stay correct.

### Native menus — and no more tab bar
Cammello now has a proper menu bar: on macOS in the system menu bar at the
top of the screen, on Windows in the window. **File / Edit / View / Upload /
Help** gather the existing commands with their keyboard shortcuts visible
next to them, so nothing has to be discovered by guesswork any more.
"About Cammello", "Settings…" and "Quit" carry the standard roles, so macOS
files them under the Cammello application menu where they belong.

The **View** menu switches between the sections (Culling, MediaWiki, IPTC,
FTP/Flickr, Settings, Log, About) with Cmd/Ctrl+1…9 — which makes the tab
bar redundant, so it is gone. The sections themselves are unchanged.

### Reload button
The reload symbol next to "Open…" was almost invisible (a hairline glyph
that some system fonts did not render at all). It now uses the platform's
own reload icon.
