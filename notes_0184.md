# Cammello 0.18.4 — Ladeweg im Sichtungsmodul, Doppelklick im Raster

## Doppelklick im Raster

Im Raster öffnet ein Doppelklick auf ein Bild dieses Bild im **Vollbild**.
Der Bildbetrachter kann das seit 0.9; im Raster passierte bisher nichts, was
wie ein Defekt aussieht.

Zwei Feinheiten, damit es sich richtig anfühlt:

* Vollbild zeigt das Bild, auf das du geklickt hast — die Zeile wird vorher
  zur aktuellen gemacht, nicht irgendein vorher ausgewähltes Bild.
* Beim Verlassen des Vollbilds landest du wieder im **Raster**, wenn du von
  dort gekommen bist. `E` und `G` benennen weiter ausdrücklich ihren Modus
  und schlagen diese Rückkehr.

## Einlesen: was gebaut wurde

**Ehrlich vorweg: ich konnte deine Langsamkeit hier nicht nachstellen.** Im
Container brauchte das Öffnen eines Ordners mit 800 Bildern 0,05 s bis die
Oberfläche zurück war. Was auf deiner Karte die Zeit frisst, kann ich von
hier aus nicht sehen — deshalb enthält diese Version zwei strukturelle
Verbesserungen **und** drei Messpunkte im Log.

### 1. Metadaten parallel und gebündelt

Der Hintergrundleser für Bewertungen und Farbmarken (`_MetadataReader`) las
bisher **eine Datei nach der anderen** und meldete **jede einzelne** per
Signal an die Oberfläche.

* Jetzt läuft er in einem kleinen Threadpool (8). Jeder Lesevorgang ist
  Datei-Ein-/Ausgabe, das GIL ist dabei frei, die Threads überlappen also
  wirklich. Gemessen mit geleertem Seitencache auf lokaler SSD: 0,42 s
  seriell gegen 0,23 s mit 16 Threads bei 800 Paaren. Auf einer Karte am
  Leser sollte der Gewinn **größer** ausfallen, weil dort die Wartezeit je
  Datei stärker durchschlägt als die Übertragungsrate — das ist eine
  begründete Erwartung, keine Messung.
* Die Ergebnisse kommen jetzt in **Bündeln** statt einzeln. Gemessen: 800
  Zeilen einzeln zu aktualisieren kostete 0,52 s Zeit im
  Oberflächen-Thread, dieselbe Arbeit in einem Durchgang 0,002 s. Über eine
  Karte mit 3000 Bildern war das sekundenlanges Stocken. Das erste Bündel
  ist absichtlich klein (12), damit die erste Bildschirmseite ihre Sterne
  sofort bekommt; danach 64 oder spätestens nach 150 ms.

### 2. Zeilen werden erst beim Ansehen ausgestattet

Das Öffnen eines Ordners hat bisher **jede** Zeile ausgestattet — Sterne,
Farbbalken, Kanal- und Bearbeitungsmarke, Kurzhilfe — bevor das Fenster
zurückkam. Bei 3000 Bildern ist das 3000-mal Arbeit für Zeilen, die niemand
ansieht.

Jetzt werden nur die Zeilen im Sichtfenster (plus Rand) ausgestattet, der
Rest beim Hineinscrollen. Buchführung dazu (`_cull_decorated`) liegt **in**
`_cull_decorate_row`, nicht bei den Aufrufern — eine zweite handgeführte
Liste wäre genau der `sdc._ASSIGN_RE`-Fehler. Auslöser fürs Nachziehen:
Scrollen (beide Leisten), Rastern, Größenänderung des Streifens, Rückkehr
aus dem Vollbild.

**Diesen Punkt verkaufe ich nicht als die Lösung.** Im Container waren die
800 Zeilen in 0,05 s ausgestattet. Weniger Arbeit ist trotzdem weniger
Arbeit, und die Testreihe sichert ab, dass keine Zeile ungeschmückt bleibt.

### 3. Drei Zahlen im Log

Beim nächsten Öffnen einer Karte stehen im Log:

```
Culling: folder ready in X.XX s (scan + rows).
Culling: ratings/labels for N entry/entries read in X.XX s.
Culling: first screenful of thumbnails complete X.XX s after opening.
```

Das sind die drei Kandidaten: das Auflisten und Aufbauen der Zeilen, das
Lesen der Bewertungen von der Karte, und das Entpacken der
CR3-Vorschaubilder. **Bitte diese drei Zeilen nach dem nächsten Kartenlauf
schicken** — dann weiß ich, wo ich ansetzen muss, statt zu raten. Meine
Vermutung ist die dritte Zeile (LibRaw-Vorschauen), aber das ist eine
Vermutung.

## Was gebaut wurde

`mw_culling.py`: `_MetadataReader` auf Threadpool und `items_ready(list)`
umgebaut; `_cull_visible_range()` herausgelöst; `_cull_decorate_visible()`
neu; `_cull_meta_arrived` nimmt Bündel; `_cull_meta_done` protokolliert;
`_CullStrip.mouseDoubleClickEvent` und `resizeEvent`;
`_cull_fullscreen_from_row`; `_cull_fs_from_grid` in
`_cull_toggle_fullscreen`, mit Ausnahme für `E` und `G`.

Neue Testreihe `test_speed_0184.py` (26 Prüfungen), darunter: das Öffnen
stattet nicht alle Zeilen aus, jede sichtbare Zeile ist ausgestattet,
Scrollen zieht nach, ein zweiter Durchgang macht nichts doppelt, ein
Filterwechsel vergisst den alten Stand, jeder Index kommt genau einmal aus
dem Leser, Doppelklick im Raster zeigt das geklickte Bild im Vollbild,
Rückkehr ins Raster, `E`/`G` behalten Vorrang, und der Doppelklick im
Filmstreifen öffnet **kein** Vollbild.

Keine neuen i18n-Schlüssel — es kommt kein neuer Text hinzu.

## Nicht enthalten

Deine drei `n:`-Punkte (Export-Beschriftung, Kopieren-Option beim
Verschieben, nur RAW+Sidecar) liegen weiter unangetastet. Der
Windows-Backend für den Kamera-Import wartet weiter auf die Ausgabe von
`wpd_probe.py`.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.3 gediffed.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.

**Nicht prüfbar ohne Fenster und Karte:** wie es sich anfühlt. Der
Doppelklick ist offscreen geprüft, aber ein echter Doppelklick geht durch
Qts Klickerkennung, nicht durch einen gebauten Event.
