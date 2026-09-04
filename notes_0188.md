# Cammello 0.18.8 — Vollbild bearbeitet nicht, Zoom wandert mit

## 1. Keine Bearbeitung im Vollbild

Im Vollbild sind aus:

* **C** — Zuschnitt
* **W** — Weißabgleich-Pipette
* **+ / −** (ohne Cmd) — Belichtung
* **Cmd+Z** — Rücknahme
* Alles zurücksetzen

An bleiben: **Sterne, Farbmarken, X**, Blättern, Zoom, **I**, **M**, **F2**
und der Wechsel der Ansicht. Das Vollbild ist zum Sichten da, und genau die
Bearbeitungstasten liegen direkt neben den Bewertungstasten.

Der Grund: das Bearbeitungsfeld ist im Vollbild nicht auf dem Schirm.
Zuschnitt, Weißabgleich und Belichtung wären dort **blind** verstellt worden —
man sieht die Änderung, aber keinen Wert und keinen Weg zurück.

Zwei Feinheiten:

* Die Sperre sitzt in den **Aktionen**, nicht in der Tastenbehandlung. So
  kommt auch das schwebende Feld nicht daran vorbei.
* Eine gedrückte Bearbeitungstaste sagt kurz im Bild, warum nichts passiert
  („Im Vollbild wird nicht bearbeitet — F oder Esc zum Verlassen"). Eine
  tote Taste ohne Erklärung ist schlimmer als keine Taste.
* Ein **laufender Zuschnitt** wird beim Wechsel ins Vollbild **abgebrochen**,
  nicht stillschweigend übernommen. Die Pipette wird ebenfalls abgelegt.

## 2. Der Zoom wandert mit

**Beim Blättern:** bist du hineingezoomt, öffnet das nächste Bild in
derselben **Bildgröße auf dem Schirm** und an derselben Stelle im Bild. Das
ist der Zweck des Zooms beim Sichten — eine Serie bei 100 % durchgehen und
sehen, welche Aufnahme sitzt. Bist du eingepasst, bleibt es beim Einpassen;
es wird nichts „klebrig", was du nicht selbst gesetzt hast.

**Beim Ansichtswechsel:** ein hineingezoomtes Bild bleibt beim Sprung ins
Vollbild und zurück auf seiner Größe. Nur ein **eingepasstes** Bild wird neu
eingepasst — das Fenster ist ja ein anderes.

Getragen wird der Zoom als **Bildbreite auf dem Schirm**, nicht als
Maßstabszahl. Aus demselben Grund wie in 0.18.6: eine Maßstabszahl bedeutet
nur etwas im Verhältnis zu dem Pixelbild, für das sie gilt, und die beiden
Vorschaustufen eines Bildes unterscheiden sich um etwa das Dreifache. Ein
Bild, dessen Vorschau eine andere Größe hat, landet trotzdem in derselben
Größe.

## Was gebaut wurde

`culling_view.py`: `apparent_width()`, `relative_center()`,
`set_apparent_width()`.

`mw_culling.py`: `_cull_edits_locked()` und `_cull_say_locked()`, Wachen in
`_cull_toggle_crop`, `_cull_set_pipette`, `_cull_step_ev`, `_cull_undo_edit`,
`_cull_reset_edits`; `_cull_update_edit_panel` blendet im Vollbild aus;
`_cull_keep_zoom_across_resize()`; `_cull_show_index` merkt sich den Zoom,
`_cull_restore_zoom()` setzt ihn einmalig wieder.

Ein Nebenfund dabei behoben: kam die Bildschirmvorschau erst **nach** dem
Blättern an, wurde sie nur eingesetzt, wenn die Ansicht eingepasst war. Beim
Blättern im Zoom blieb der Bildschirm sonst leer.

1 neuer i18n-Schlüssel in fünf Sprachen, neue Testreihe
`test_fsedit_0188.py` (32 Prüfungen).

## Offen geblieben

* **Windows-Kamera-Backend** — wartet auf die Ausgabe von `wpd_probe.py`.
* **Kartengeschwindigkeit** — wartet auf die drei Zeitzeilen aus dem Log.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.7 gediffed;
  `test_cullview.py`, `test_crop_0130.py` und `test_zoom_0186.py` laufen
  unverändert durch.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.

**Zwei Auslegungen, die du korrigieren solltest, wenn ich falsch liege:**

1. „no edit" habe ich als *Pixel verändern* gelesen — Bewertungen und
   Farbmarken bleiben also an. Sollen die im Vollbild auch aus, sag Bescheid.
2. „while switching" habe ich als **beides** gebaut: Bildwechsel **und**
   Ansichtswechsel. Der Bildwechsel ist der auffälligere von beiden (bisher
   sprang jedes Bild auf „Einpassen" zurück); falls du nur den
   Ansichtswechsel meintest, nehme ich das Klebrige beim Blättern wieder
   heraus.
