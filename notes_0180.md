# Cammello 0.18.0

Eine Arbeitsversion (gerade Ziffer hinter dem ersten Punkt) mit einem
Thema: **Audio-Uploads fremder Aufnahmen.** Enthalten ist außerdem die
nie getaggte 0.17.1 — die Behebung des Absturzes beim Stilwechsel.

Maßstab war deine Mendelssohn-Seite (Orgelsonate op. 65
Nr. 5, aufgenommen von Wolfram Syré); der Test hält sie wörtlich und
vergleicht zeichengenau.

## Was du tun musst

1. Im Workflow-Menü **„Music and audio"** wählen. Nur dort erscheint die
   neue Gruppe mit den dreizehn Feldern; in deinen Fotoworkflows ändert
   sich nichts.
2. Deine vorhandene `~/Cammello/workflows.toml` wird **nicht** angefasst.
   Der Musik-Workflow steht nur in der eingebauten Vorgabe. Willst du ihn
   in deiner eigenen Datei haben, brauchst du dort einen Block mit
   `felder_an` — die Datei einmal umbenennen und neu erzeugen lassen
   zeigt die aktuelle Vorlage samt Feldliste.
3. Ausprobieren, ob die erzeugten Kategorien stimmen. Sie werden vor dem
   Einsetzen gegen Commons geprüft; was es nicht gibt, fällt weg und
   steht als Zeile im Log.

## Was neu ist

* **Autorzeile mit Rollen.** `composition: …` und
  `recording (Technik): …`. Eine Rolle ohne Namen entfällt ganz.
* **Zwei Lizenzen.** Werk und Aufnahme getrennt, als Aufzählung. Ist
  „Todesjahr des Komponisten" gefüllt und die Vorlage sagt nichts über
  ein Todesjahr, wird `|deathyear=` ergänzt — genau einmal.
* **Kategorien werden gerechnet, nicht getippt.** Sieben Muster aus
  deinen sieben, gefüllt aus Instrument, Land, Epoche, Werk, Komponist
  und Aufnehmendem. Komponist und Aufnehmender kommen aus dem
  LINKZIEL des Wikitext-Links, nicht aus dem sichtbaren Text — bei dir
  steht „Felix Mendelssohn Bartoldy", die Kategorie heißt „Felix
  Mendelssohn".
* **Quelle bleibt freiwillig**, und die Quellenvorlage hängt ohne
  Leerzeichen am Link, wie auf deiner Seite.

## Was ich beim Bauen gefunden habe

* Meine erste Fassung der `deathyear`-Ergänzung hätte bei
  `{{A}} und {{B}}` das Jahr in die **zweite** Vorlage geschrieben — der
  Text fängt mit `{{` an und hört mit `}}` auf. Jetzt werden die
  Klammerpaare gezählt.
* `is_hidden()` las die rohe Ausschlussliste und antwortete „nicht
  versteckt" für ein Feld, das die Oberfläche gerade versteckt hatte.
  Geht jetzt durch dieselbe Funktion wie alles andere.
* `felder_aus` allein trug die Sache nicht (siehe oben) — daher
  `felder_an`.

## Was offen bleibt

* `{{Template:Organ Repertory Wolfram Syré}}` auf deiner Seite: das
  Präfix ist überflüssig. Cammello schreibt, was du ins Feld tippst —
  wenn es zeichengleich bleiben soll, tippe es mit Präfix.
* Ob der einfache Zeilenumbruch zwischen den beiden Autorrollen als
  Umbruch rendert, ist **ungeprüft**. Sieh dir die erste erzeugte Seite
  an; falls beide Rollen in einer Zeile landen, gehört ein `<br />`
  dazwischen und ich baue es ein.
* Die Kategoriemuster stammen aus **einem** Beispiel. Zwei, drei weitere
  Seiten von dir würden sie absichern.
* Die Felder sind stapelweit (wie Autor und Lizenz), nicht je Datei. Für
  ein Album mit verschiedenen Werken je Datei bräuchte es eine
  Erweiterung.
