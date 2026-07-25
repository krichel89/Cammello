# Cammello 0.14.2 — Vorschau, verschiebbares Editfenster, Startseite, fortsetzbare Uploads (25.07.2026)

**Zwei neue Module: `cammello/splash.py` und `cammello/upload_journal.py`.**
Beim Einspielen mit übernehmen, sonst `ImportError` beim Start.

## Vorschau für Weißabgleich und Belichtung

Die Culling-Ansicht zeigt jetzt, was die Korrektur tatsächlich bewirkt —
nicht mehr nur die Zahl im Editfenster.

* `previews.apply_tone()` rechnet mit **denselben Tabellen wie der Export**
  (`edits._combined_lut`), damit Bildschirm und hochgeladene Datei
  übereinstimmen. Abgesichert durch eine Prüfung, die beide Wege gegen
  denselben Wert vergleicht.
* Zwei Rechenwege, beide in C: `numpy` (kommt mit rawpy) als Schnellpfad,
  sonst `bytes.translate` auf Kanal-Scheiben. Beide liefern identische
  Pixel (geprüft).
* Die Ansicht behält das **unbearbeitete** Bild; jede Änderung rechnet neu,
  ohne die Datei erneut zu lesen. Beim Bildwechsel wird die Korrektur
  gesetzt, **bevor** die Pixel ankommen — kein Aufblitzen des unkorrigierten
  Bildes.
* Bei gehaltener `+`/`−`-Taste wird die Neuberechnung entprellt (90 ms);
  ein einzelner Pipettenklick und der Bildwechsel wirken sofort.

**Dabei behoben (Folgefehler der Vorschau):** Die Pipette maß bisher das
**angezeigte** Bild. Sobald ein Weißabgleich sichtbar ist, hätte eine zweite
Messung auf bereits korrigierten Pixeln stattgefunden und die Korrektur
doppelt angewandt. Sie liest jetzt das Quellbild, samt Umrechnung über einen
aktiven Zuschnitt.

## Editfenster

* **Verschiebbar**: überall dort anfassen, wo kein Knopf ist (Titel, Texte,
  Hintergrund) — nicht nur an der schmalen Titelzeile, die über einem Foto
  ein fummeliges Ziel wäre. Die Knöpfe behalten ihre Klicks.
* Die Position wird als **Anteil der Ansicht** gemerkt: sie übersteht
  Fenstergrößen und den Wechsel in den Vollbildmodus und wird immer in die
  Ansicht geklemmt. Doppelklick auf den Hintergrund setzt zurück nach oben
  rechts. (Gilt für die laufende Sitzung, nicht über Neustarts.)
* Die **Zuschnitt-Legende** steht jetzt auch im Editfenster — sichtbar nur
  während des Zuschneidens, damit das Fenster sonst klein bleibt.

## Startseite

Statt des schwarzen Fensters beim Start erscheint ein gezeichneter
Startbildschirm mit **beiden Logos**: Cammello-Icon und Titel oben, die
WikiPortraits-Wortmarke unten. Gezeichnet statt gebündelt — dadurch scharf
auf Retina-Displays und immer mit der aktuellen Versionsnummer.

Die Wortmarke sitzt auf einem **hellen Band**: ihre Schrift ist nahezu
schwarz und wäre auf dunklem Grund unlesbar. So bleibt ein fremdes Logo
unverändert, statt es umzufärben. Dieselbe Lösung im Über-Dialog, wo das
Logo jetzt ebenfalls steht.

Fehlt eine Grafik, startet Cammello trotzdem — der Startbildschirm ist
Beiwerk und darf den Start nie verhindern.

## Mac-Icon

Ursache der eckigen Darstellung: **macOS rundet Icons nicht selbst ab**, die
Form muss im `.icns` stecken — und unser Quellbild ist ein randvolles
Quadrat. Der Build maskiert jetzt mit einer echten **Superellipse** (n≈5) im
Apple-Raster 824 von 1024 px; ein einfacher Eckenradius liest sich neben
Systemicons subtil falsch. Dasselbe Bild liegt als `icon_rounded.png` bei,
damit Startseite und Über-Dialog dieselbe Form zeigen wie das Dock.

*Offen:* Das Quellbild ist nur 512 px und wird für das Icon auf 1024
hochskaliert — die großen Darstellungen bleiben dadurch leicht weich. Mit
einem größeren Original wäre das behoben.

## Unterbrochene Uploads fortsetzen

Stürzt ein Stapel nach 100 von 200 Bildern ab, lässt er sich nach dem
Neustart genau dort fortsetzen — ohne von Hand zu ermitteln, was schon oben
ist.

* Ein **Journal** (`~/Cammello/upload_journal.json`) hält den Stand. Es wird
  nach **jeder** Datei geschrieben, und zwar **atomar** (Temp-Datei im selben
  Verzeichnis, `fsync`, dann `os.replace`) — ein Absturz mitten im Schreiben
  hinterlässt entweder das alte oder das neue Journal, nie ein halbes.
  Bewusst **nicht** in QSettings: dort ist nicht zugesichert, wann ein Wert
  die Platte erreicht, und genau darauf kommt es hier an.
* Das Journal enthält die **kompletten Zeilendaten**. Die Fortsetzung hängt
  deshalb nicht daran, dass die Tabelle die Zeilen noch hat — nach einem
  Absturz hat sie das nicht.
* **Das Absturzfenster ist abgedeckt:** Eine Datei wird *vor* dem Upload als
  „unterwegs" vermerkt. Stirbt der Prozess, während sie in der Leitung ist,
  weiß die Fortsetzung, dass der Ausgang unbekannt ist, und **fragt Commons**
  (`get_page_id`), statt zu raten. Sonst würde die Datei entweder mit einer
  „exists"-Warnung scheitern oder — bei aktiviertem „Ignore warnings" — sich
  selbst überschreiben.
* **Galerie-Einträge** der ersten Hälfte gehen nicht verloren: Galerien
  werden einmal am Ende geschrieben, die Einträge stehen also im Journal und
  werden in den Fortsetzungslauf übernommen — und danach als geschrieben
  vermerkt, damit sie nicht doppelt landen.
* **Angeboten wird es, nie automatisch gestartet:** Beim Programmstart
  erscheint (400 ms nach dem Fenster) ein Dialog mit *Fortsetzen* /
  *Später* / *Verwerfen*; dazu ein Menüeintrag **Upload → Unterbrochenen
  Upload fortsetzen…**. Die Prüfung beim Start liest nur eine Datei — kein
  Netz, kein Schlüsselbund (0.12.12-Regel).
* Fortgesetzt wird nur, was nie hochgeladen wurde. **Fehlgeschlagene**
  Dateien werden nicht erneut versucht (ein falscher Dateiname bliebe
  falsch), bleiben aber im Bericht. Ist eine Datei inzwischen verschoben,
  wird sie mit Nachfrage übersprungen; stammt das Journal von einem anderen
  Wiki, gibt es eine Warnung.
* Ein Journal-Fehler bricht **nie** einen laufenden Upload ab — er wird
  protokolliert, der Stapel ist dann nur nicht fortsetzbar.

## Neue Testdateien

`test_resume_0142.py` (27 Prüfungen): simulierter **Absturz nach 100 von
200** Dateien durch den echten `UploadWorker` mit einer Test-API, danach
Fortsetzung — alle 200 landen genau einmal oben; das Absturzfenster in
beiden Ausprägungen (Datei kam an / kam nicht an); Galerie-Übernahme ohne
Doppelschreiben; beschädigtes, fremdformatiges und fehlendes Journal werden
ignoriert statt zu scheitern; Lauf ohne Journal unverändert.

`test_features_0142.py` (33 Prüfungen): Tonwert-Vorschau in beide
Rechenwege, Gleichstand mit dem Export, Pipette auf dem Quellbild (auch mit
Zuschnitt), Verschieben/Klemmen/Merken des Editfensters, Entprellung,
Startbildschirm bei 1× und 2× sowie bei fehlenden Grafiken.

## Geändert

`cammello/previews.py`, `culling_view.py`, `edit_panel.py`, `mw_culling.py`,
`main_window.py`, `workers.py`, `mw_upload.py`, `mw_files.py`, `menus.py`,
`i18n.py` (24 neue Schlüssel × 5 Sprachen), `constants.py`,
**neu** `cammello/splash.py` und `cammello/upload_journal.py`,
**neue Grafiken** `cammello/assets/wikiportraits.png` und
`icon_rounded.png`, `.github/workflows/build.yml`, `release.sh`,
`CHANGELOG.md`.
