Downloads for macOS, Windows and Linux are attached below.

**Bug fixes since v0.11.1**
- macOS app: the Culling, IPTC and FTP tabs no longer disappear. The bundled `libexiv2.dylib` needed native libraries (inih, brotli, gettext) that were missing from the build, so pyexiv2 failed to load; the macOS build now installs exiv2 so the app is self-contained even without Homebrew.
- Windows crash when opening a folder in the Culling tab is fixed. Rating and colour-label reading no longer uses the native metadata library on the scan path (it could hard-crash on some files, e.g. Panasonic `.RW2`); ratings/labels are read directly from the XMP of sidecars and JPEGs instead.
- Portrait photos that were shown lying on their side (Windows) are now displayed upright — orientation is read via Pillow (JPEG) and libraw (RAW).

**Added**
- Caption languages: an ISO code added via "Other (ISO code)…" can now be removed again from the dropdown via "Remove saved language…". The four default languages (en, de, es, fr) stay fixed.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
