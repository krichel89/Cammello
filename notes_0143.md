# Cammello 0.14.3 — Startbildschirm sichtbar machen, Icon-Werkzeug (25.07.2026)

Nachbesserung zu 0.14.2: der Startbildschirm war auf dem Mac nicht zu
sehen, und das Icon blieb eckig.

## Startbildschirm

Zwei Fehler in 0.14.2, beide behoben:

* **Durchsichtiges Fenster.** Der Startbildschirm zeichnete abgerundete
  Ecken auf eine transparente Grafik und forderte dafür ein transluzentes
  Fenster an (`WA_TranslucentBackground`) — auf macOS kann diese Kombination
  dazu führen, dass gar nichts erscheint. Zusätzlich wurden die Fensterflags
  nach dem Erzeugen neu gesetzt, was das Fenster dort hinter andere rutschen
  lassen kann. Beides ist weg: Die Karte ist jetzt **deckend und rechteckig**
  (mit dezentem Rahmen). Ein Startbildschirm, der zuverlässig da ist, ist
  mehr wert als schönere Ecken.

* **Zu kurz sichtbar.** Er wurde geschlossen, sobald das Hauptfenster stand
  — auf einer schnellen Maschine sind das ein paar hundert Millisekunden.
  Er bleibt jetzt **mindestens 1,5 Sekunden** stehen, auch wenn der Start
  schneller fertig ist.

Außerdem: Er wird auf dem Bildschirm zentriert, auf dem gearbeitet wird, und
**das Log sagt jetzt, ob er erschienen ist** (`Start screen shown.` bzw. eine
Warnung mit dem Grund) — ohne das lässt sich ein fehlender Startbildschirm
aus der Ferne nicht beurteilen.

## Icon

Die Rundung aus 0.14.2 steckt in `.github/workflows/build.yml` und entsteht
deshalb **nur bei einem neuen GitHub-Actions-Build**. Wird das `.app` woanders
gebaut — lokal mit py2app oder PyInstaller —, greift sie nie. Das war in der
Lieferung nicht deutlich gesagt.

Neu daher: **`make_icns.py`** im Wurzelverzeichnis. Einmal ausführen, und das
gerundete Icon liegt fertig für jeden Packvorgang bereit:

```
python3 make_icns.py
```

Es schreibt `cammello/assets/icon.icns` (alle Größen von 16 bis 1024 px — die
Finder-Seitenleiste braucht das vollständige Set) und `icon_rounded.png` für
Startbildschirm und Über-Dialog. Auf Nicht-macOS wird nur das PNG erzeugt.

**Wenn das alte Icon nach dem Neubau kleben bleibt**, cached macOS es:

```
touch <Pfad>/Cammello.app && killall Dock
```

Das Bundle in einen anderen Ordner zu verschieben wirkt ebenfalls.

*Weiter offen:* Das Quellbild ist 512 px und wird auf 824 hochskaliert — die
großen Darstellungen bleiben dadurch leicht weich. Mit einem größeren
Original wäre das behoben.

## Geändert

`cammello/splash.py`, `cammello/main_window.py`, `cammello/constants.py`,
**neu** `make_icns.py`, ergänzte Prüfungen in `test_features_0142.py`,
`release.sh`, `CHANGELOG.md`.
