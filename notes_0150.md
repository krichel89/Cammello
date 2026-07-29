# Cammello 0.15.0 — Zweiter Workflow, Standortdaten, Aufnahmedaten (28.07.2026)

Die größte Runde seit Langem. Kern ist ein **zweiter Workflow** neben dem
bisherigen Veranstaltungs- und Porträtbetrieb: „Buildings and Landscapes",
mit allem, was Standortdaten dafür brauchen.

## Der Workflow-Umschalter

Oben im MediaWiki-Modul, neben „Ignore warnings", sitzt ein Auswahlfeld mit
zwei Arbeitsabläufen. Es belegt Vorlagen, Kategorievorschläge und
strukturierte Daten vor und zeigt **nur die Felder, die der jeweilige
Ablauf braucht**: alles zum Standort erscheint bei Gebäuden, „Created
during" und die Ereignis-Übernahme im IPTC-Modul bei Veranstaltungen. Wer
alles gleichzeitig sehen will, schaltet den Expertenmodus ein — dort ist
grundsätzlich alles bedienbar.

Die Abläufe stehen als Tabelle im Quelltext (`cammello/workflows.py`), ein
dritter ist deshalb ein Eintrag und kein Umbau.

## Zwei Standorte statt einem

Beim Porträt ist es dasselbe, beim Gebäude nicht: Die Kamera steht auf der
anderen Straßenseite. Commons trennt das, und Cammello jetzt auch.

* **Kamerastandort** → `{{Location dec}}` und P1259
* **Objektstandort** → `{{Object location dec}}` und P9149

Beide Felder stehen untereinander in der Gruppe „Selected file(s)", und die
Beschriftung sagt jeweils, dass der Wert **sowohl in den Wikitext als auch
in die strukturierten Daten** geht. Den Objektstandort kann „from Wikidata"
aus dem Item holen, das unter „depicts" eingetragen ist.

Neu ist außerdem eine **Standortspalte** in der Dateiliste, die beide
Koordinaten untereinander zeigt.

## Das Standort-Menü

Drei Aktionen, alle auf der Dateiliste:

* **Standort aus Datei lesen.** Zuerst die `.xmp`-Begleitdatei, dann die
  EXIF-Daten — die Begleitdatei gewinnt, weil ihr Inhalt durch einen
  bewussten Eingriff entstanden ist, während EXIF-GPS einfach anfällt.
  Selbst eingetragene Werte werden nie überschrieben.
* **GPX-Track zuordnen.** Ein Dialog: Track wählen, Zeitversatz und
  maximalen Abstand prüfen, **Vorschau ansehen**, dann anwenden. Erst dann
  wird geschrieben.
* **Alle Standortdaten löschen.** Räumt beide Koordinaten aus Cammello und
  aus den Bilddateien.

### Zum Zeitversatz

Kameras schreiben Ortszeit ohne Zeitzone, GPX-Tracks laufen in UTC. Der
Versatz ist aus der Zeitzone dieses Rechners **vorbelegt** und bleibt
**änderbar** — die Vorbelegung stimmt genau dann, wenn die Kamerauhr in
dieser Zone stand. Eine Reise ins Ausland oder eine nachgehende Kamerauhr
braucht eine Korrektur, und dafür ist das Feld da.

Zwischen zwei Trackpunkten wird **nicht** interpoliert. Ein erfundener
Zwischenwert läge auf einer Geraden, die niemand gegangen ist; lieber der
nächste echte Punkt — oder gar keiner, wenn er weiter weg ist als erlaubt.

## Koordinaten in der Datei

Die Zuordnung landet **in den JPEG- und TIFF-Dateien**, und das Löschen
holt sie dort auch wieder heraus: alle GPS-Felder, EXIF und XMP, samt
Referenzbuchstaben, Höhe, Zeitstempel und Aufnahmerichtung. Nur die Breite
zu entfernen und das „N" stehen zu lassen wäre keine Löschung.

**Ortsnamen bleiben.** Stadt, Region und Land werden von Hand eingetragen
und sind damit gewollt. **RAW-Dateien werden nie verändert** — das Negativ
bleibt unangetastet.

## IPTC

Das Feld **Sublocation** ist dazugekommen: der Ort innerhalb der Stadt, bei
einem Gebäude das eigentlich Interessante.

## Aufnahmedaten in den strukturierten Daten

Beim Hochladen wandern Angaben, die ohnehin in der Datei stehen,
automatisch in die strukturierten Daten — nichts auszufüllen:

* Belichtungszeit (P6757), Blendenzahl (P6790), ISO (P6789),
  Brennweite (P2151)
* Aufnahmedatum (P571, tagesgenau) und Medientyp (P1163)
* **Kamera** (P4082) und **Objektiv** (P11385) — aber nur, wenn der
  EXIF-Text auf **genau ein** Wikidata-Item passt
* Bei Eigenwerk zusätzlich die Quellenangabe (P7482)

Die Kameratabelle stammt aus Wikidata selbst: Items tragen ihren
EXIF-Modelltext als P2009, und `make_camera_map.py` erzeugt daraus
`cammello/assets/camera_map.json` — derzeit **8180 eindeutige Modelle**.
Mehrdeutige Bezeichnungen stehen gar nicht erst drin, ein Treffer ist also
immer eindeutig. Für Objektive gibt es auf Wikidata keine entsprechende
Eigenschaft; diese Liste wird von Hand gepflegt und ist noch leer.

Abschaltbar in den Einstellungen.

## Rückgängig

**Strg-Z beziehungsweise Cmd-Z** nimmt die letzte Bildbearbeitung zurück —
Zuschnitt, Belichtung, Weißabgleich, 50 Schritte weit. Bewertungen,
Umbenennungen und Koordinaten sind bewusst nicht dabei. Der Kurzbefehl
hängt nur am Culling-Modul, damit er den Textfeldern der anderen Module
ihr eigenes Rückgängig nicht wegnimmt.

## Bearbeitungen kommen jetzt beim Upload an

Ein alter Fehler: Zuschnitt, Belichtung und Weißabgleich wirkten nur beim
Export aus dem Culling-Ordner — hochgeladen wurde trotzdem das Original.
Jetzt wird die bearbeitete Fassung gerendert und **die** hochgeladen. Die
Metadaten kommen weiter aus der Originaldatei, und wenn das Rendern
scheitert, geht das Original hoch statt gar nichts.

## Vorschaubilder

Bilder erschienen manchmal verzögert oder gar nicht. Vier Ursachen, alle
behoben:

* Ein bereits eingereihtes Bild ließ sich **nicht höher priorisieren** — es
  wartete hinter bis zu acht Vorablade-Aufträgen, obwohl es gerade
  angesehen wurde.
* Ein Dekodierfehler landete **nur im Log**, die Ansicht blieb leer.
* Fiel ein Bild zwischen Meldung und Anzeige aus dem Zwischenspeicher,
  passierte **stillschweigend nichts**.
* Beim Ordnerwechsel brach ein Auftrag **ohne jedes Signal** ab.

Darüber liegt jetzt ein Wachhund: Ist nach 1,2 Sekunden kein Bild da, wird
bis zu dreimal nachgefragt.

## Kleinigkeiten

* Der Hintergrund im Culling ist **neutrales Grau** statt Schwarz und folgt
  dem Farbschema (im Dunkelmodus dunkler, im Hellmodus heller).
* Beim Weißabgleich wird der Mauszeiger zur **Pipette**.
* Der **Startbildschirm** bleibt vier Sekunden und richtet sich am
  Hauptfenster aus.
* Ein **roter Punkt** markiert dringend empfohlene Felder, die noch leer
  sind; „Author and license" startet zugeklappt.
* Ausgeblendete Felder nehmen ihre **Beschriftung** mit.
* Wikidata-Abfragen frieren das Fenster nicht mehr ein.
* Begleitdateien werden mit **Größenbegrenzung** gelesen.

## Für Entwickler

Neue Module: `workflows.py`, `geo.py`, `gpx.py`, `gpx_dialog.py`,
`camera_map.py` sowie `assets/camera_map.json` und `make_camera_map.py`.

Neue Testdateien: `test_workflow_0150.py`, `test_preview_0150.py`,
`test_location_0150.py`, `test_undo_0150.py`, `test_gpx_0150.py`,
`test_sdc_exif_0150.py`, `test_gpswrite_0150.py`.
