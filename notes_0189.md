# Cammello 0.18.9 — Rückkehr ins Vollbild

## Was los war

Das Vollbild ist ein **eigenes, rahmenloses Fenster**, und der Bildbetrachter
wird beim Umschalten dorthin umgehängt. Im Hauptfenster bleibt dadurch ein
**Loch** im Teiler, wo eben noch das Bild war.

Holt macOS die Anwendung zurück, hebt es das **Hauptfenster** nach vorn, nicht
das rahmenlose — und dieses Loch ist die komische Ansicht. Der eigentliche
Bildschirminhalt liegt dann irgendwo dahinter.

## Zwei Antworten darauf

**1. Bei jeder Aktivierung kommt das Vollbildfenster wieder nach vorn.**
Cammello hängt sich, solange das Vollbild steht, an das Aktivierungssignal der
Anwendung. Kommst du zurück, wird das Fenster wieder auf Vollbild gesetzt
(falls es als gewöhnliches Fenster zurückkam), nach vorn geholt, aktiviert und
bekommt die Tastatur. Das Ganze **um einen Durchlauf verzögert** — macOS ordnet
in dem Moment noch seine eigenen Fenster, und ein Nach-vorn-Holen mitten
hinein verliert.

Ein eingepasstes Bild wird dabei neu eingepasst. Das ist nicht nur Kosmetik:
wenn du in der Zwischenzeit einen externen Monitor abgezogen hast, ist der
Bildschirm ein anderer geworden.

**2. Das Loch wird gestopft.** An die Stelle des Bildbetrachters tritt, solange
das Vollbild steht, eine Beschriftung: „Das Vollbild liegt in einem eigenen
Fenster. F oder Esc dort holt das Bild hierher zurück." Selbst wenn das
Hauptfenster kurz zu sehen ist, ergibt es dann einen Sinn.

Der Haken wird beim Verlassen wieder gelöst — auch beim Herunterfahren, falls
das Vollbild dabei noch steht.

## Was gebaut wurde

`mw_culling.py`: `_cull_fs_watch()`, `_cull_fs_app_state()`,
`_cull_fs_reassert()`, `_cull_fs_placeholder()`; Ein- und Ausstieg im
`_cull_toggle_fullscreen` angepasst, Freigabe in `_cull_shutdown`.

1 neuer i18n-Schlüssel in fünf Sprachen, neue Testreihe
`test_fsreturn_0189.py` (27 Prüfungen): der Haken wird gesetzt und gelöst,
der Teiler hat kein leeres Fach, das Wiederherstellen macht aus einem
gewöhnlichen Fenster wieder ein Vollbild, Bild und Zoom überstehen die
Runde, eine späte Aktivierung nach dem Verlassen tut nichts, und das
Herunterfahren löst den Haken.

## Wichtig: ich kann das nicht nachstellen

Der Container hat kein macOS und keinen Fensterwechsel zwischen Programmen.
Geprüft ist die **Mechanik** — dass der Haken hängt, dass das Fenster wieder
auf Vollbild geht, dass nichts hängen bleibt. **Nicht** geprüft ist, ob macOS
sich damit zufriedengibt.

Falls es weiter komisch aussieht, hilft mir das hier weiter:

* Ist nach dem Zurückwechseln das **Hauptfenster** vorn (mit der neuen
  Beschriftung statt des Bildes) oder das Vollbild, aber falsch gezeichnet?
* Passiert es auch, wenn du mit Cmd+Tab wechselst statt mit der Maus?
* Steht Cammello dabei auf einem eigenen Space oder auf demselben?

Wenn das Nach-vorn-Holen unter macOS nicht durchkommt, ist die Alternative,
das Vollbild beim Verlassen der Anwendung **automatisch zu beenden** — dann
bist du beim Zurückkommen in der Lupenansicht statt in einem halben Fenster.
Das baue ich, wenn es nötig ist, aber es kostet dich deinen Vollbildzustand,
deshalb erst der behutsame Weg.

## Offen geblieben

* **Windows-Kamera-Backend** — wartet auf die Ausgabe von `wpd_probe.py`.
* **Kartengeschwindigkeit** — wartet auf die drei Zeitzeilen aus dem Log.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.8 gediffed.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.
