# Cammello 0.16.0 — Arbeitsversion (29.07.2026)

**Neue Nummerierung ab jetzt:** Die Ziffer **hinter dem ersten Punkt**
entscheidet. **Ungerade** heißt Testversion, **gerade** heißt
Arbeitsversion. Damit war die ganze Reihe 0.15.x eine Testreihe, und
0.16.x ist die erste Arbeitsreihe. Die Patch-Nummer sagt darüber nichts
mehr aus — eine ganze Reihe bleibt das, was sie ist.

Die Versionsprüfung geht danach: Wer eine Arbeitsversion verwendet, wird
standardmäßig nur über Arbeitsversionen informiert; wer selbst eine
Testversion fährt, hört auch von Testversionen.

## Zur Download-Seite

Meldet die Prüfung eine neuere Fassung, steht die Adresse nicht mehr bloß
im Text. Es gibt einen Knopf **„Download-Seite öffnen"**, der direkt zur
Release-Seite führt — und daneben „Später".

## macOS: das Dock-Icon ist jetzt rund

Der Icon im Bundle war seit 0.14.2 korrekt gerundet, im Finder sah er auch
so aus. Beim Start ersetzte die App das Dock-Icon aber durch die
**ungerundete Quelldatei** — deshalb wirkte er eckig, sobald Cammello
lief. Behoben; das Programm nimmt jetzt dieselbe gerundete Fassung, die
Startbildschirm und Info-Seite schon benutzt haben.

Nebenbei aus dem Build entfernt: eine Größe (64 px), die Apples Iconset
gar nicht kennt und im ungünstigen Fall das ganze Set ungültig macht.

## Umbenennen: Schema statt Platzhalter

Der Dialog sieht jetzt aus wie der in Fotos und Lightroom: Oben wählt man
ein **Benennungsschema**, darunter stehen nur die Felder, die dieses
Schema wirklich braucht — der Rest ist ausgegraut, so wie Fotos die
„Anfangsnummer" ausgraut.

Die Schemata:

* Benutzerdefinierter Name – Originaldateinummer
* Benutzerdefinierter Name – Sequenz
* Benutzerdefinierter Name (x von y)
* Originaldateiname
* Originaldateiname – Sequenz
* Datum – Originaldateiname
* Datum – Benutzerdefinierter Name – Sequenz
* Eigene Vorlage…

Ganz unten steht ein **Beispiel** mit echter Endung, das sich beim Tippen
mitändert — `testI-66330.JPG`.

**Die Originaldateinummer** sind die Ziffern, mit denen der Dateiname aus
der Kamera endet. Wie viele davon übernommen werden, muss niemand mehr
einstellen — Cammello bestimmt es aus der Auswahl selbst: Es nimmt die
**größte gemeinsame Endziffernfolge**, also die Länge, die *jede*
ausgewählte Datei liefern kann, begrenzt auf drei bis sechs Stellen. Eine
Lumix zählt sechsstellig, eine Canon vierstellig; liegt beides zusammen in
der Auswahl, gelten vier. Dateien, deren Name auf gar keine Ziffer endet,
zählen bei dieser Rechnung nicht mit — sie könnten nichts beitragen und
würden eine sechsstellige Reihe sonst grundlos auf drei herunterziehen.
Der Sinn der Nummer bleibt derselbe: Der Commons-Name zeigt weiter auf die
Rohdatei auf der Platte.

Endet ein Dateiname auf gar keine Ziffer, bekommt **diese eine Datei** die
laufende Nummer. Und würden zwei Dateien gleich heißen, werden **alle**
durchnummeriert — identische Namen kollidieren auf Commons.

Wer eine Reihenfolge braucht, die kein Schema anbietet, nimmt **Eigene
Vorlage** mit `{n}` (laufende Nummer), `{c}` (Originaldateinummer),
`{name}` (Originaldateiname), `{text}` (der Text oben) und `{date}`
(Aufnahmedatum).

## Ein ganzes Verzeichnis laden, ohne Culling

Im MediaWiki-Modul steht neben dem Anmeldenamen ein Knopf **„Verzeichnis
öffnen…"**. Er lädt jede hochladbare Datei eines Verzeichnisses direkt in
die Tabelle — der Weg über das Culling-Modul entfällt, wenn nichts
auszusortieren ist.

Was er tut und was nicht:

* **Nicht rekursiv.** Nur die oberste Ebene des gewählten Verzeichnisses,
  keine Unterverzeichnisse.
* **Nur hochladbare Dateitypen**, dieselbe Endungsliste, mit der auch
  „Dateien hinzufügen…" arbeitet. RAW-Dateien sind bewusst nicht dabei:
  Cammello hat keinen RAW-Konverter, sie ließen sich also gar nicht
  hochladen. Angenehmer Nebeneffekt — ein Verzeichnis mit RAW+JPEG-Paaren
  ergibt eine Zeile pro Bild statt zwei.
* **Fortschritt mit Abbrechen.** Wer abbricht, behält die bereits
  gelesenen Zeilen; weggeworfen wird nichts.
* **Ab 1000 Dateien fragt Cammello vorher nach.** Eine harte Grenze gibt
  es nicht, aber jede Vorschau kostet rund 0,21 MB Arbeitsspeicher — bei
  tausend Dateien also etwa 210 MB, dazu die Zeit fürs Dekodieren.

Bereits in der Tabelle stehende Dateien werden wie beim Hinzufügen als
Doppelte erkannt und übersprungen.

## „Sprache hinzufügen" nimmt die nächste freie

Bisher legte der Knopf jedes Mal eine englische Zeile an — beim zweiten
Klick stand Englisch also zweimal da. Jetzt wählt er die erste Sprache
vor, die im Editor noch keine Zeile hat: erst die vier Standardsprachen,
dann die selbst gemerkten ISO-Codes. Sind alle vergeben, legt er trotzdem
eine Zeile an, statt den Dienst zu verweigern.
