# Cammello 0.18.7 — versteckte Dateien, Unterordner, Karten von selbst öffnen

## 1. Punktdateien fliegen raus

Namen mit Punkt am Anfang werden beim Einlesen übersprungen — Dateien **und**
Ordner.

Das waren die AppleDouble-Begleiter von macOS: eine Karte, die einmal in
einem Mac steckte, trägt neben jeder `IMG_0001.CR3` eine `._IMG_0001.CR3`.
Die haben eine Bildendung, und `._IMG_0001` ist ein **anderer** Stamm als
`IMG_0001` — sie wurden also nicht zum Paar gefaltet, sondern kamen als
eigene Einträge durch. Ein unlesbarer Doppelgänger je Bild. Dazu `.Trashes`,
`.Spotlight-V100` und `.DS_Store`.

Geprüft wird der **Name**, nicht das Dateisystem-Merkmal: unter Windows
tragen Punktdateien kein Versteckt-Kennzeichen, und genau um die geht es.

Die Protokollzeile zählt sie jetzt mit:

```
… name(s) listed, 7 hidden (leading dot), 6 picture file(s), …
```

Wenn also nach dem Einspielen plötzlich halb so viele Bilder dastehen, sagt
die Zeile, dass es an den Doppelgängern lag.

## 2. Unterordner

Neues Kästchen **„Unterordner"** in der Sichtungsleiste, wird gemerkt. Aus
ist die Vorgabe — dein Arbeitsordner braucht es nicht.

Die Paarbildung geht dabei über **Ordner und Stamm**, nicht über den Stamm
allein. Innerhalb eines DCIM-Ordners vergibt die Kamera keine Nummer zweimal,
über zwei Ordner hinweg gibt es `IMG_0001` aber doppelt — die zusammenzufalten
hätte vier Dateien zu einem Eintrag gemacht und stillschweigend ein Bild
verschluckt.

Das Neu-Einlesen behält den Umfang, mit dem der Ordner geöffnet wurde, und
folgt nicht dem Kästchen von jetzt.

## 3. Karte von selbst öffnen

Neues Kästchen **„Karten öffnen"**, **an** als Vorgabe. Steckst du eine Karte
ein, öffnet Cammello sie sofort — **immer mit Unterordnern**, denn `DCIM` ist
nur ein Behälter, die Bilder liegen eine Ebene tiefer in `100EOSR5`.

* Als Karte gilt ein Datenträger mit einem **DCIM-Ordner**. Ein USB-Stick
  löst also nichts aus.
* Geöffnet wird der DCIM-Ordner, nicht die Wurzel — so bleiben `MISC` und
  die Verwaltungsordner der Karte draußen.
* Was vorher offen war, **wird ersetzt**. Das ist der Preis für „sofort".
  Beim Arbeiten von einer Karte also besser ausschalten; die Kurzhilfe am
  Kästchen sagt das auch.
* Was beim Start schon steckte, gilt nicht als neu — sonst würde Cammello
  beim Hochfahren die Platte im Leser aufreißen. Dasselbe beim
  Wiedereinschalten des Kästchens.

Umgesetzt als **Abfrage alle 2,5 Sekunden** statt als Dateisystem-Wächter:
`QFileSystemWatcher` täte es auf dem Mac (`/Volumes` ist ein Verzeichnis),
unter Windows gibt es aber kein solches Verzeichnis, dort sind Datenträger
Laufwerksbuchstaben. Ein Auflisten von `/Volumes` alle paar Sekunden kostet
nichts und ist auf allen drei Systemen derselbe Code.

## Was gebaut wurde

`culling.py`: `is_hidden_name()`; `scan_folder(folder, report, recursive)`
mit Ordner+Stamm-Schlüssel und `os.walk`, das versteckte Ordner vorher
abschneidet; `scan_report_text()` zählt die Versteckten.

`camera.py`: `volume_roots()`, `list_volumes()`, `card_folder()`,
`new_cards()` — Qt-frei, deshalb prüfbar.

`mw_culling.py`: die zwei Kästchen (beide gemerkt), `_cull_start_card_watch`,
`_cull_poll_cards`, `_cull_autocard_toggled`; der Zeitgeber wird beim
Herunterfahren **zuerst** gestoppt, ein Auslösen mitten im Abbau würde in
halb abgebaute Fenster hinein öffnen.

4 neue i18n-Schlüssel in fünf Sprachen, neue Testreihe `test_cards_0187.py`
(26 Prüfungen).

## Offen geblieben

* **Windows-Kamera-Backend** — wartet auf die Ausgabe von `wpd_probe.py`.
* **Kartengeschwindigkeit** — wartet auf die drei Zeitzeilen aus dem Log.
  Ein Teil davon könnte sich hiermit übrigens erledigt haben: wenn deine
  Karte aus einem Mac kam, hat Cammello bisher **doppelt so viele Einträge**
  aufgebaut wie es Bilder gibt, und für jeden Doppelgänger eine Vorschau
  angefordert, die nur scheitern konnte. Das ist eine Vermutung, aber eine
  gut begründete — die Zeitzeilen werden es zeigen.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.6 gediffed.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.

**Nicht prüfbar hier:** ein echtes Einstecken. Der Container hat keine
Wechseldatenträger, geprüft ist deshalb die Erkennungslogik gegen
nachgebaute Ordner, nicht das Ereignis selbst. Beim ersten Versuch bitte
schauen, ob im Log `Culling: card detected, opening "…"` steht.
