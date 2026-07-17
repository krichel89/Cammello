Downloads for macOS, Windows and Linux are attached below.

**Added — IPTC "Person shown"**
- A new **Person shown** field in the IPTC tab, read from and written to the standard XMP property `Xmp.iptcExt.PersonInImage` (the same field Photo Mechanic and Lightroom use). Multiple names are separated by semicolons, like the other multi-value fields.
- **Person shown → categories:** adds each person as a category — either directly by name (`[[Category:Name]]`) or resolved via Wikidata (name → item → Commons category P373), with a picker to choose the right item per person.
- **Person shown → depicts:** searches Wikidata for each person and lets you pick the item to add as a depicts (P180) statement.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
