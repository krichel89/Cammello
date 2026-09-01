# Cammello 0.18.5 — deine drei vorgemerkten Punkte

Ich habe „Weiter" als „arbeite die `n:`-Liste ab" gelesen. Alle drei Punkte
sind gebaut; für den Windows-Kamera-Backend und die Kartengeschwindigkeit
fehlen mir weiter deine Ausgaben, da konnte ich nicht weiter.

## 1. „Save to…" heißt wieder „Export…"

Nur die Beschriftung. Der Weg selbst ist unverändert: kopiert, was der
Paarselektor sagt, RAW nimmt sein `.xmp` mit, im Zielordner wird nichts
überschrieben.

## 2. und 3. Ein Dialog statt drei Knöpfe

„Verschieben nach…" öffnet jetzt keinen nackten Ordnerwähler mehr, sondern
einen Dialog mit drei Zeilen:

```
Zielordner:  [ …………………………………… ] [ Durchsuchen… ]

Vorgang      (•) Verschieben (die Dateien verlassen diesen Ordner)
             ( ) Kopieren (die Dateien bleiben auch hier)

Welche       (•) Die ganze Gruppe: RAW, JPEG und .xmp-Sidecar
Dateien      ( ) Nur RAW und .xmp-Sidecar
```

Deine Vorgabe war ausdrücklich „eine Wahl im Dialog, kein dritter Knopf" —
also sitzt beides hier und die Knopfleiste bleibt bei zwei Einträgen.

**Der Dialog öffnet auf „Verschieben" + „ganze Gruppe", also genau dem, was
0.18.2 getan hat.** Das ist Absicht: Punkt 3 hebt die Begründung für die
Zwangsgruppierung auf — halbe Paare sind jetzt möglich, aber nie aus
Versehen. Ein Eintrag ohne RAW wandert unter dem engen Umfang trotzdem mit;
da ist kein Partner, der zurückbleiben könnte.

**Die Kollisionsregel hängt jetzt am Vorgang, nicht am Knopf:**

* **Verschieben** — liegt auch nur ein Name schon im Ziel, bricht der ganze
  Vorgang ab. Überschreiben würde die Zieldatei **und** die letzte Kopie der
  Quelle vernichten.
* **Kopieren** — vorhandene Namen werden übersprungen, der Rest geht durch.
  Die Quelle bleibt ja liegen, genau wie beim Export seit jeher.

Der geöffnete Ordner als Ziel wird bei beidem abgelehnt.

## Was gebaut wurde

`culling.group_paths(item, scope)` bekommt den Umfangsparameter mit den
Konstanten `SCOPE_GROUP` (Vorgabe, altes Verhalten) und `SCOPE_RAW`. Ohne
Argument ist alles wie in 0.18.2 — die vorhandenen Aufrufer und
`test_move_0182.py` bleiben unberührt.

`mw_culling.py`: neue Klasse `_TransferDialog`; `_cull_move_to_folder`
holt Ziel, Vorgang und Umfang von dort, hängt die Kollisionsprüfung an
`move` und verbindet je nach Vorgang `_cull_on_move_finished` oder
`_cull_on_copy_finished` (nur ein Verschieben liest den Ordner neu ein).
Kein zweiter Worker — `_FolderCopyWorker` kann beides seit 0.18.2.

13 neue i18n-Schlüssel in fünf Sprachen, neue Testreihe
`test_transfer_0185.py` (24 Prüfungen).

## Offen geblieben

* **Windows-Kamera-Backend** — wartet auf die Ausgabe von `wpd_probe.py`
  (liegt seit 0.18.3 im Paket).
* **Kartengeschwindigkeit** — wartet auf die drei Zeitzeilen aus dem Log
  nach dem nächsten Kartenlauf.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert: 479 Befundarten, null neue.
* Volle Testreihe zweimal mit frischem HOME, gegen 0.18.4 gediffed.
* Verifikation im frischen Verzeichnis und aus dem entpackten Zip.

**Nicht prüfbar ohne Fenster:** wie sich der Dialog anfühlt. Geprüft ist,
was er zurückmeldet und dass er einen nicht vorhandenen Ordner ablehnt;
nicht geprüft ist die Anordnung auf dem Bildschirm.
