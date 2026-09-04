# Cammello 0.18.6 — der Zoomsprung

Reine Fehlerbehebung. Eigene Versionsnummer nur, damit du die Pakete
auseinanderhalten kannst.

## Was los war

Cmd + „+" fordert die **volle** Vorschau an — wer zoomt, will echte Pixel.
Die trifft einen Moment später ein und ist um ein Vielfaches breiter als die
Bildschirmvorschau, die sie ersetzt: **2560 px gegen 8192 px** bei einem
R5-Bild. Beim Tausch wurde die **Transformation** beibehalten. Auf dem
Bildschirm landet aber *Maßstab × Pixelbreite* — derselbe Maßstab über 3,2×
so viele Pixel ließ das Bild also um 3,2× wachsen. Du hast einen Schritt
verlangt und drei bekommen; das sieht aus wie ein Sprung auf 100 %.

Damit erklärt sich auch dein „gerne mal": es passiert nur, wenn die volle
Vorschau noch nicht im Zwischenspeicher lag, und nur um den Faktor, um den
sich die beiden Vorschaustufen unterscheiden. Bei einer JPEG-Datei unter
2560 px passiert gar nichts.

## Was gebaut wurde

Die Transformation zu behalten war die falsche Lesart von `keep_view`.
Stehen bleiben muss, **was der Nutzer sieht**. Beim Tausch wird deshalb der
Maßstab durch die Auflösungsänderung geteilt und der Ausschnitt auf denselben
**relativen** Punkt zurückgesetzt — die Szene hat unter der Ansicht ja
ebenfalls ihre Größe geändert. Neu: `CullImageView._keep_apparent_size()`,
gerufen aus `_apply_crop_display()`.

Ein angenehmer Nebeneffekt: die angezeigte Prozentzahl wird ehrlich. 50 %
einer 2560-px-Vorschau waren nie 50 % des Bildes; nach dem Tausch bedeutet
die Zahl, was sie sagt. Aus deinem einen Schritt von „Einpassen" (hier
gemessen: 40,8 %) wird also 50 % der Vorschau und danach 15,6 % des echten
Bildes — dieselbe Bildgröße auf dem Schirm, nur richtig beschriftet.

Ein Tausch **gleicher** Auflösung rührt die Ansicht überhaupt nicht mehr an.
Das ist der Weg für Weißabgleich und Belichtung, der bei jedem Reglerstopp
läuft; ein Nachzentrieren hätte dort nur Rundungsdrift eingebracht.

Neue Testreihe `test_zoom_0186.py` (16 Prüfungen), darunter: das Bild behält
beim Eintreffen der vollen Vorschau seine Größe auf dem Schirm und seinen
Ausschnitt, die Prozentzahl wird mitskaliert, ein gleich großer Tausch ändert
exakt nichts, `keep_view=False` passt weiter ein, und ein Tausch im
Einpass-Modus passt neu ein.

Keine neuen i18n-Schlüssel.

## Offen geblieben

* **Windows-Kamera-Backend** — wartet auf die Ausgabe von `wpd_probe.py`.
* **Kartengeschwindigkeit** — wartet auf die drei Zeitzeilen aus dem Log.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.5 gediffed;
  `test_cullview.py` und `test_crop_0130.py` laufen unverändert durch.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.

**Nicht prüfbar ohne Fenster:** die Messungen oben stammen aus einem
1200×700-Ansichtsfenster im Container. Bitte einmal an einem echten
R5-Bild gegenprüfen — und falls es weiter springt, sag mir, ob es beim
**ersten** Cmd+ passiert oder erst beim zweiten.
