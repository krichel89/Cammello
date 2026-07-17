Downloads for macOS, Windows and Linux are attached below.

**Added — IPTC "Event" (created during)**
- A new **Event** field in the IPTC tab, read from and written to the standard XMP property `Xmp.iptcExt.Event` (Photo Mechanic's "Event" field).
- **Event → created during:** searches Wikidata for the event and sets it as the "created during" (P10408) statement.
- **Event → category:** adds the event as a category (resolved via Wikidata to the Commons category P373, or the name).

**Changed — constant creator / rights / contact block**
- **Creator, Copyright notice and Credit** moved out of the per-image editor into a new **"Creator / rights / contact"** block that is the same for every processed image and is no longer filled from the MediaWiki data. It lives in the Settings tab and appears collapsed at the top of the IPTC tab. Added contact fields: e-mail, phone, website and postal address (street, city, postal code, country), written to the standard IPTC "Creator's contact info" XMP fields.
- The block is written onto every processed image, even ones without their own per-image IPTC edits.
- The **"Source"** field was removed.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
