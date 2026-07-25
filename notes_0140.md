## Cammello 0.14.0

The ad-hoc edits get a home, and four password prompts become one.

### The edit panel
A small panel sits in the top-right corner of the culling view and holds
what you reach for while going through a shoot: crop, white balance,
exposure. It shows the current state - a tick next to Crop and White
balance, the exposure as "EV +4/6" - so you can see what a picture already
carries instead of remembering it. It is a CHILD of the view, not a
separate window: it follows into fullscreen and can never end up behind
the main window.

The keyboard stays the fast path. C crops, W picks a white balance, + and
- move the exposure, and the panel simply reflects it.

### White balance (W)
Press W, then click a spot that should be neutral grey or white. The gains
are computed in LINEAR light - deriving them from the encoded values
leaves a visible part of the cast behind, which is what a first attempt
here did. Green is the reference and stays at 1.0, so only red and blue
move. A spot too dark to judge is refused rather than amplified into
noise.

### Exposure in sixths (+ / -)
Finer than the third-stop steps a camera dial offers, which is rather the
point of correcting on screen. Ctrl/Cmd with + and - remain the zoom
shortcuts they have always been.

### The crop is finally visible
Applying a crop with Enter now shows the picture cropped. Pressing C puts
the full frame back so the box can be pulled outwards again, and Esc
restores whatever was stored. The legend spells the ratios out instead of
hiding them in a tooltip.

### F2 renames on disk
You name the picture, not its parts: a RAW+JPEG pair and any .xmp sidecar
are renamed together, so the item stays one item. Ratings live in the
files' own XMP and travel with them; crop, white balance, exposure and
channel marks are keyed by path, so they are moved across explicitly -
otherwise a renamed picture would lose its stars and its crop. An existing
name is refused, and if a rename fails halfway the files already moved are
put back.

### One keyring prompt instead of four
The stored OAuth authorization used to live in two keyring entries, and
each was read twice per login - four prompts on an unsigned macOS bundle.
Both halves now live in ONE entry, and anything read once is kept for the
life of the process. Old installations are migrated the first time they
are read. The last prompt disappears only with a Developer ID signature;
the build workflow is already prepared for it.

### Dialogs remember where you were
File and folder dialogs open in the folder you last used. With nothing
remembered yet they start in the system's Pictures folder - checked for
existence first, since the system names one whether or not it was ever
created.
