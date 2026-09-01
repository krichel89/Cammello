# Cammello 0.18.1

Die Musikfelder sind jetzt zwischen **Gesamtset** und **Auswahl**
aufgeteilt. Dazu ein Fund, der schon länger im Quelltext saß.

## Was du tun musst

Nichts umstellen. Beim nächsten Start stehen fünf Felder woanders:

* **Gesamtset** (Gruppe „Music and audio" rechts) — Aufnehmender,
  Aufnahmetechnik, Quellenvorlage, Lizenz der Aufnahme, Instrument,
  Epoche, Land, Andere Versionen.
* **Auswahl** (Beschreibungseditor, wie „Depicts") — Komponist,
  Todesjahr, Kompositionsjahr, Werk, Lizenz der Komposition.

Der Gedanke: derselbe Organist spielt auf derselben Orgel aus derselben
Quelle, aber die Stücke haben verschiedene Komponisten. Bei einem Album
markierst du alle Sätze eines Werks und trägst den Komponisten einmal
ein — der Auswahl-Editor wirkt auf alles Markierte.

## Wie es sich verhält

Die fünf Auswahl-Felder sind jetzt `SD_KEYS`, also normale
`schlüssel=wert`-Zeilen in der Beschreibungszelle. Damit gilt für sie
alles, was für `depicts` schon galt: Speicherung in der Zelle,
Mehrfachauswahl, und **der Wert der Auswahl schlägt den des Gesamtsets**.
Ein LEERES Auswahlfeld löscht den Gesamtset-Wert nicht.

## Was dabei ans Licht kam

`_ASSIGN_RE` in `sdc.py` — das Muster, das entscheidet, welche Zeilen
KEIN Freitext sind — zählte die Schlüssel von Hand auf und war
auseinandergelaufen: `coordinates` und `object_coordinates` fehlten
darin. Diese Zeilen wurden also als strukturierte Daten gelesen **und**
zusätzlich als Freitext stehen gelassen. Bei jedem Durchlauf durch den
Editor verdoppelten sie sich.

Meine Musikfelder hätten den Fehler in dem Moment geerbt, in dem sie
`SD_KEYS` wurden — genau so ist er aufgefallen. Das Muster wird jetzt
AUS `SD_KEYS` gebaut, kann also nicht mehr abweichen. Der Rundlauf ist
in `test_music_0181.py` festgehalten.

Wenn du alte Beschreibungen mit Koordinaten hast, in denen die Zeile
doppelt steht: die Dopplung verschwindet beim nächsten Speichern von
selbst.
