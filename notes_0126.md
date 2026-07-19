## Cammello 0.12.6

The big structure round from the interactive wishlist - visible workflow
tabs, marks on the images, context-aware menus, and the exiv2 crashes
defused for good.

### The workflow is visible again
- **Lightroom-style module strip, top right**: Culling · MediaWiki · IPTC ·
  FTP/Flickr as a flat text row above the pages; the active step is bold.
  Click to switch; Cmd/Ctrl+1…4 still work.
- **Settings, Log and About are windows now** (File > Settings, Help > Show
  log / About Cammello), so the strip shows only real workflow steps.

### Marks on the image
- **Channel mark at the thumbnail**: a small dot in the corner - teal =
  Commons, orange = commercial - in the filmstrip and the grid, and in the
  loupe/fullscreen overlay. Setting a mark (or uploading, which sets it
  automatically) updates the dots immediately.
- **Rejected images** are greyed out and carry a small red ✕ in the corner.
  The filter behaviour is unchanged: rejects stay hidden unless
  "incl. rejects" is on.

### Menus
- **Edit is now Metadata** - and carries the ratings: stars (0-5), Rejected
  (X) and the colour labels (6-9; M toggles the digit keys to colours,
  where 5 is purple). The shortcuts are finally visible next to the entries.
- Entries that belong to another page are **greyed out** instead of firing
  invisibly - the digit keys can no longer rate images while you are on a
  different page.
- **Open folder** works from anywhere and switches to Culling first.
- List commands moved to File: "Remove selected" and **"Clear list"** (the
  old "Clear" name suggested it only cleared the selection - it empties the
  whole list).
- **Bulk edit is gone**: selecting several rows and editing a field already
  propagates the change to all of them, so the extra dialog was a second,
  clumsier path to the same result.

### exiv2 is gone from the culling and sidecar paths
Windows kept crashing exiv2 on files that are demonstrably fine - plain
.xmp sidecars, ordinary JPEGs. Rather than keep guessing, the metadata that
Cammello writes is now handled **without any native library**:

- **Rating and colour label in .xmp sidecars**: written as text (the
  attributes are patched in place, everything Lightroom or Photo Mechanic
  put there survives).
- **Rating and colour label embedded in JPEGs**: written by rewriting the
  APP1 XMP segment directly - so a JPEG-only picture, which has no sidecar,
  keeps its rating too.
- **Person shown / Event in sidecars** (IPTC module): read and written as
  XML text as well.

exiv2 is now only used for IPTC/XMP inside non-RAW image files, and even
there it runs in the isolated helper process.

### exiv2 crashes defused
Two Windows crashes (a Canon DNG with a corrupt maker note, and a sidecar
write) died inside exiv2 with access violations no try/except can catch.
Three defenses, all in this release:
- **All metadata calls run in a helper process.** If exiv2 goes down, the
  helper dies, Cammello reports the file and keeps running; the helper
  restarts on the next call. Queued ratings survive as error entries
  instead of vanishing with the app.
- **exiv2 never opens RAW/DNG files any more** (IPTC module; the culling
  module already had this rule): for RAW, metadata is read from and written
  to the .xmp sidecar - which is where it belongs anyway.
- Errors from unreadable files become log warnings, not crashes.

### MediaWiki page
- Section 1 is called **"Author and license"** - it holds the data that is
  always the same. "Upload settings" said nothing.
- **"Other templates" moved into the base description**: templates like
  {{WikiPortraits at Berlinale 2026}} are event-bound, so they belong with
  the per-event data - and "Clear base description" now clears them too.
- **"Not logged in" is a link**: one click opens the (OAuth) sign-in. When
  signed in, the label simply shows your username.
- **Bot password moved into a small sub-dialog** behind a button under the
  OAuth row in Settings. It stays as the consumer-independent fallback;
  stored passwords are kept.
