# Cammello 0.15.1 — Rote Punkte für die Pflichtfelder pro Datei (28.07.2026)

Nachtrag zu 0.15.0: Der rote Punkt markierte bisher nur Autor, Quelle und
Lizenz. Jetzt markiert er auch, was **pro Datei** fehlt.

## Was jetzt einen Punkt bekommt

* **Kategorien** — und zwar nur, wenn keine *inhaltliche* dabei ist.
* **Depicts** (P180)
* **Bildunterschrift** (die strukturierte Hälfte)
* **Information** (die Wikitext-Hälfte)

Die ersten beiden bekommen den Punkt vor ihrer Feldbeschriftung. Die
Captions-Zeilen haben keine Beschriftung, an der ein Punkt sitzen könnte —
dort erscheint stattdessen eine kleine rote Zeile, die benennt, was noch
leer ist. Die Gruppe „Selected file(s)" trägt den Punkt in der Überschrift,
sobald irgendetwas davon fehlt.

## Inhaltliche und Meta-Kategorien

Eine Datei, die nur in „Photographs by …" und „Uploaded with Cammello"
steht, ist praktisch unkategorisiert: Keine dieser Kategorien sagt, was auf
dem Bild zu sehen ist. Solche Kategorien zählen deshalb nicht mit.

Als Meta gelten unter anderem:

* Urheberkategorien wie `Photographs by *`
* Projektkategorien wie `WikiPortraits*`
* Wartungskategorien wie `Uploaded with *` oder `Media needing categories*`
* Lizenz-Ablagen wie `CC-BY-SA-*`

**Die Liste ist eine einfache Textdatei:**
`cammello/assets/meta_categories.txt`. Eine Zeile pro Muster, `#` leitet
einen Kommentar ein, `*` steht am Anfang oder Ende für „irgendetwas".
Änderungen daran brauchen keinen Eingriff in den Quelltext.

Fehlt die Datei, gilt nichts als Meta — im Zweifel wird also **nicht**
gemahnt statt zu Unrecht.

## Hinweise

Die Punkte pro Datei erscheinen nur, solange eine Zeile ausgewählt ist;
ohne Auswahl sind die Felder aus gutem Grund leer.
