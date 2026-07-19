## Cammello 0.12.9

An optimization pass over the source, requested as such. Two findings were
worth acting on; both are guarded by a new test file.

### Faster card scans
The rating/label scan read up to 4 MB from the head of EVERY JPEG to find
the XMP packet. Cameras write EXIF and XMP within the first ~100 KiB, so the
read is now a ladder: 192 KiB first, 4 MB only if the packet was not found,
the whole file as the last resort. On typical files that is ~20x less I/O -
across a 3000-image card, roughly 0.6 GB from the reader instead of 12 GB.
Correctness is unchanged and tested at every rung, including behind the
last one.

### exiv2 really is out of the main process now
Since 0.12.6 every exiv2 call runs in the crash-isolated helper process -
but three module-level imports still loaded the native library into the GUI
process at startup, which is precisely what that architecture is for
preventing. The feature check now asks whether the module is installed
without importing it; the helper imports it on first use; a completely
unused import in the preview module is deleted. Startup is about 0.2 s
faster. One trade-off, stated plainly: a BROKEN pyexiv2 installation is now
noticed at the first metadata access (with a message naming the module)
rather than at startup.

### Not changed on purpose
The broad legacy star-imports in the mixin modules light up every linter,
but stripping them is churn with real regression risk and no runtime win -
they stay, as previously agreed. The i18n table and the per-item metadata
signals were measured and are not bottlenecks.
