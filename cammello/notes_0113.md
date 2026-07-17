Downloads for macOS, Windows and Linux are attached below.

**Added — Culling tab**
- **Home / End** jump to the first / last image (in both loupe and grid view).
- **Double-click** on the image toggles fullscreen (same as the F key).
- **`i`** toggles an EXIF info overlay: filename, camera, lens, and focal length · aperture · shutter · ISO · capture time. JPEGs are read via Pillow; RAW files via libraw, so the overlay works for RAW-only shots too (the camera name additionally uses the optional `exifread` package when installed).

**Changed**
- RAW thumbnail extraction runs in parallel again, restoring the pre-0.11.1 scan speed. It had been serialized while chasing the 0.11.1 crash; that turned out to be unrelated (it was pyexiv2 on the scan path, removed in 0.11.2).

**Dependencies**
- New optional dependency `exifread` (pure Python), used only to show the camera name for RAW-only files.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
