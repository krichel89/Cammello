# Cammello 0.18.2

Neu: **„Verschieben nach…"** im Sichtungsmodul, neben „Speichern nach…".

## Was du tun musst

Markieren, „Verschieben nach…", Zielordner wählen. Fertig.

## Wie es sich verhält

**Immer die ganze Gruppe.** RAW, JPEG und `.xmp`-Sidecar zusammen — der
Paarselektor (JPEG/RAW/beide) gilt beim Verschieben ausdrücklich NICHT.
Beim Kopieren darf er gelten, weil das Original liegen bleibt; beim
Verschieben nicht: die halbe Paarhälfte zurückzulassen ergibt einen RAW
ohne JPEG und ein Sidecar, das eine Datei beschreibt, die nicht mehr
daneben liegt.

**Es wird nie etwas überschrieben.** Liegt auch nur eine der Dateien schon
im Zielordner, bricht Cammello ab und nennt die Namen — es wird dann gar
nichts verschoben. Grund: ein überschreibendes Verschieben vernichtet
zwei Dateien auf einmal, die im Ziel und die einzige verbliebene Kopie
der Quelle. Eine halb verschobene Gruppe wäre schlimmer als eine, die
gar nicht verschoben wurde.

**Der Zielordner darf nicht der geöffnete sein** — das wird abgefangen.

**Keine gerenderte Kopie.** Bei „Speichern nach…" wird ein Bild mit
Bildbearbeitung als `<name>_edit.jpg` exportiert. Beim Verschieben nicht:
dort wandert das Original. Sonst bliebe der RAW ohne seinen Partner
zurück.

**Vor dem Verschieben** werden ausstehende XMP-Schreibvorgänge geleert,
damit Sterne und Farben von vor drei Sekunden mitreisen. Danach wandern
die pfadgebundenen Aufzeichnungen (Beschnitt, Kanalmarken) an den neuen
Ort, und der Ordner wird neu eingelesen.

## Wo es gebaut ist

`culling.group_paths()` und `culling.move_collisions()` sind reine
Funktionen ohne Qt — die Bündelung und die Kollisionsprüfung sind ohne
Fenster prüfbar. Der Kopierworker verschiebt jetzt auch, statt dass es
einen zweiten fast gleichen Worker gäbe: Fortschritt, Abbrechen und
Zusammenfassung sind identisch und wären sonst auseinandergelaufen.

## Ungeprüft

Der Knopf selbst und der Ordner-Neueinlesen-Weg danach — dafür braucht es
ein Fenster mit echten Dateien. Die Logik darunter ist in
`test_move_0182.py` abgedeckt (16 Zusicherungen).
