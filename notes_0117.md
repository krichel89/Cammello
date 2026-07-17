Downloads for macOS, Windows and Linux are attached below.

**Improved — Wikidata lookup is now fuzzy**
- The person/event Wikidata lookup no longer relies on prefix matching alone. When the label search comes up short, it falls back to a full-text (CirrusSearch) search that is tolerant of word order, ordinals and stray spaces — so entries like "78th Cannes Film Festival" are found. The query is also whitespace-normalised.

**Changed — combined IPTC transfer actions**
- "Person shown → depicts" and "Person shown → categories" are now one action: **Person shown → depicts + category**. Pick each person's Wikidata item once; it adds both the depicts (P180) statement and the category.
- "Event → created during" and "Event → category" are now one action: **Event → created during + category**.

**Fixed — IPTC layout**
- A long file list no longer pushes the field editor off-screen: file names are elided, the list width is capped, and the action buttons wrap onto multiple lines when space is tight.

Full details: [CHANGELOG.md](https://github.com/krichel89/Cammello/blob/main/CHANGELOG.md)
