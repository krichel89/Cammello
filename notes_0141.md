# Cammello 0.14.1 — Korrekturen aus dem Quelltext-Review (25.07.2026)

## Behoben

* **Zuschnitt bei gedrehten JPEGs schnitt den falschen Bereich.** Die
  Culling-Ansicht zeigt Bilder anhand der EXIF-Orientierung aufrecht; der
  Crop-Rahmen wird gegen dieses aufrechte Bild normalisiert. Der Export
  wendete ihn aber auf die ungedrehten Pixel an — bei Hochformataufnahmen
  (Orientation 6/8) landete ein anderer Bildausschnitt in der `_edit`-Kopie,
  zusätzlich mit stehen gebliebenem Orientierungs-Tag. Der Export dreht jetzt
  zuerst aufrecht (`ImageOps.exif_transpose`) und setzt die Orientierung im
  mitgegebenen EXIF auf 1. (Mit einem Orientation-6-Testbild reproduziert
  und durch `test_fixes_0141.py` abgesichert.)

* **RAW-Edit-Exporte verloren sämtliche Kamera-Metadaten.** Der
  rawpy-Render trägt kein EXIF; die `_edit`-Kopie eines RAW hatte daher
  weder Aufnahmedatum noch Kamera oder GPS. Das EXIF wird jetzt aus dem
  eingebetteten Vorschau-JPEG übernommen (Orientierung ebenfalls auf 1).

* **F2-Umbenennen wies reine Groß-/Kleinschreibungs-Änderungen ab.** Auf
  case-insensitiven Dateisystemen (macOS-Standard) traf die Kollisions-
  prüfung die Quelldatei selbst; `img → IMG` meldete fälschlich „existiert
  bereits". Zusätzlich fängt F2 jetzt unter Windows reservierte Namen
  (`CON`, `NUL`, `COM1`…) und Namen mit Punkt/Leerzeichen am Ende ab.

* **Culling-Ordner-Öffnen crasht nicht mehr, wenn das Culling-Modul
  deaktiviert ist** (fehlendes pyexiv2): defensiver Guard statt
  `AttributeError`.

## Zielnamen-Prüfung (Anlass: Nutzerbericht badfilename)

* **Doppelpunkt, Schrägstrich und Backslash im Commons-Zielnamen werden
  jetzt vor dem Upload abgefangen** — pro Zeile, mit einer Meldung, die das
  Zeichen benennt: MediaWiki verbietet `:` `/` `\` in Dateinamen
  ($wgIllegalFileChars) und ersetzt sie sonst stillschweigend durch „-",
  worauf jede Datei mit einer kryptischen `badfilename`-Warnung scheitert.
  Auf Linux sind solche Namen lokal völlig legal, deshalb fiel es dort
  erst beim Upload auf (realer Fall: 129 Dateien „Sitzungstitel: n.JPG",
  0/129 hochgeladen).

* **Kommt eine `badfilename`-Warnung dennoch vom Server**, erklärt die
  Fehlermeldung jetzt, welche Zeichen MediaWiki beanstandet und unter
  welchem Namen die Datei stattdessen gespeichert würde — statt nur den
  korrigierten Namen zu zitieren.

## Verbessert

* **Belichtung und Weißabgleich in einem Rechendurchgang.** Bisher liefen
  zwei getrennte 8-Bit-LUTs (zweimal sRGB-Dekodierung/Enkodierung =
  doppelte Quantisierung); jetzt eine kombinierte LUT pro Kanal.

* **Edit-Speichern entprellt.** Jeder 1/6-Blendenschritt erzwang bisher
  einen kompletten Settings-Flush auf die Platte; jetzt bündelt ein
  400-ms-Timer die Schreibvorgänge. Ordnerwechsel, Umbenennen und
  Programmende flushen weiterhin sofort.

* **FTPS ist die Voreinstellung für neue FTP-Konfigurationen** (eine
  gespeicherte Wahl bleibt unangetastet). Klartext-FTP bleibt wählbar.

## Aufgeschoben (bewusst)

* FTP-Passwort und Flickr-Secrets in den Schlüsselbund: kollidiert mit dem
  0.14.0-Ziel „nur eine Schlüsselbund-Abfrage" — braucht dasselbe
  Lazy-Muster wie der BotPassword-Weg (0.12.12) und kommt als eigene Runde.

## Neue Testdatei

* `test_fixes_0141.py` (Zielnamen-Prüfung, badfilename-Meldung,
  Orientierungs-Crop end-to-end, EXIF-Aufrecht-Helfer, kombinierte LUT,
  F2-Namensprüfung, Debounce).
