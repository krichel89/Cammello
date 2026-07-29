# Cammello 0.15.2 — Alt-Text, Sprachcodes mit Schrift, Versionsprüfung (29.07.2026)

## Sprachcodes mit Schrift- oder Regionsanteil

Ein Nutzer meldete, dass Bildunterschriften auf Malaiisch in **Jawi-Schrift**
nicht möglich sind: Der Code lautet `ms-Arab`, und Cammello antwortete
„Not a valid code". Behoben — aber der Fehler saß tiefer als gemeldet.

Die alte Prüfung war `[a-z]{2,3}` plus ein `.lower()`. Sie scheiterte am
Bindestrich **und** hätte den Großbuchstaben der Schriftkennung zerstört.
Vor allem aber steckte dasselbe Muster an **sechs weiteren Stellen**: Eine
Unterschrift `caption_ms-Arab=…` wäre zwar eingetragen, beim nächsten Lesen
der Beschreibung aber stillschweigend wieder verschwunden. Die Erweiterung
im Eingabedialog allein hätte gar nichts gebracht.

Jetzt gibt es **ein** Muster für alle sieben Stellen, und es deckt
`ms-Arab`, `zh-Hant`, `sr-Latn`, `pt-BR` und ihresgleichen ab.

### Wer entscheidet über die Schreibweise

`ms-Arab` und `ms-arab` sind **beide** im Umlauf: ISO 15924 schreibt
Schriftkennungen groß, MediaWiki-interne Codes klein. Statt zu raten fragt
Cammello **Commons selbst** (`meta=wbcontentlanguages`), vergleicht ohne
Rücksicht auf Groß- und Kleinschreibung und übernimmt die Schreibweise, die
das Wiki verwendet. Ist Commons nicht erreichbar, wird der Code nach
Musterprüfung akzeptiert — eine Netzstörung darf keine gültige Sprache
blockieren.

## Alt-Text

Jede Sprachzeile im **Dateieditor** hat jetzt eine dritte Zeile: den
**Alt-Text** für Screenreader. In der Basisbeschreibung gibt es ihn
bewusst nicht — was zu sehen ist, unterscheidet sich von Bild zu Bild. Er wird als Aussage **P11265** in den strukturierten Daten
hochgeladen, in der Sprache seiner Zeile.

**Nur dort.** Ein Wikitext-Gegenstück gibt es auf Commons nicht. Die
Vorlage `{{Alt}}` ist keine Alt-Text-Vorlage, sondern die Sprachvorlage für
**Süd-Altaisch** (ISO-Code `alt`) — sie zu verwenden würde den Text als
altaisch auszeichnen.

Alt-Text ist nicht dasselbe wie die Bildunterschrift: Die Unterschrift
benennt, *was* das ist, der Alt-Text beschreibt, was zu *sehen* ist.

## Versionsprüfung

Einmal täglich beim Start, außerdem jederzeit über **Hilfe → Nach
Aktualisierungen suchen**. Die Prüfung fragt die GitHub-Releases ab.

**Gerade Endziffer = stabil, ungerade = experimentell.** Diese Fassung ist
0.15.2 und damit stabil. Wichtig zu wissen: Die Regel wirkt nur nach vorn
und bedeutet, dass Nummern übersprungen werden — auf 0.15.2 folgt stabil
die 0.15.4, die 0.15.3 wäre eine experimentelle. Ältere Fassungen wurden
ohne die Regel vergeben und werden deshalb nicht eingeordnet.

Wer selbst eine experimentelle Fassung verwendet, wird auch über
experimentelle informiert; sonst nur über stabile. Beides abschaltbar.

Die automatische Prüfung ist still: Ist alles aktuell oder das Netz nicht
erreichbar, sagt sie nichts.

## Workflow-Wechsel räumt auf

Beim Umschalten des Workflows konnten Felder, die der neue Ablauf
ausblendet, noch gefüllt sein — und **ausgeblendet heißt nicht inaktiv**:
Eine Objektkoordinate wäre trotzdem als `{{Object location dec}}` und P9149
mit hochgegangen.

Cammello fragt jetzt beim Wechsel, ob solche Werte geleert werden sollen,
und nennt dabei, um welche Felder es geht. Gefragt wird nur, wenn wirklich
etwas drinsteht; „Nein" lässt alles unberührt. **Nie stillschweigend** —
das Rückgängig deckt nur die Bildbearbeitung ab.

## Galerie: ein Feld statt zwei

Die getrennte Einstellung „Gallery prefix" ist weg. In der
Basisbeschreibung steht jetzt der **volle Seitenname**, etwa
`User:Seewolf/Berlinale 2026`. Leer heißt: keine Galerie.

Ein Wert aus der Zeit von Präfix und Suffix wird beim Laden **einmal
zusammengesetzt**, damit aus „Berlinale 2026" nicht plötzlich eine
Galerieseite im Hauptnamensraum wird.

## Kleinigkeiten

* Der erste Workflow heißt jetzt **Events/Portraits**.
* Der rote Punkt bei **depicts** bleibt weg, wenn die Auswahl darunter
  ausdrücklich sagt, dass es nichts zu verknüpfen gibt („No Wikidata
  item", „Not applicable", „Unidentified"). Wer ein Feld gerade für
  unzutreffend erklärt hat, soll dafür nicht gemahnt werden.

## Nachtrag aus der Durchsicht

* Der rote Punkt bei **depicts** blieb manchmal aus. Die Ursache war der
  Zeitpunkt, nicht die Bedingung: Die Markierungen hingen nur an
  Textänderungen, und eine Datei mit leerem depicts in einen Editor zu
  laden, dessen depicts schon leer war, ändert keinen Text und löst kein
  Signal aus — die Marken der vorherigen Datei blieben stehen. Sie werden
  jetzt dort neu berechnet, wo der Editor geladen wird.
* **Absturz behoben:** Wurde die Dateiliste ersetzt, während eine Datei im
  Editor lag, brach das Programm beim nächsten Übernehmen mit einem
  RuntimeError ab. Das Editorfeld ist an ein Tabellenelement gebunden, das
  beim Neuladen zerstört wird; das wird jetzt abgefangen.
* Das Feld **HTTP-Timeout** ist aus den Einstellungen verschwunden. Der
  Wert gilt weiter, ein gespeicherter wird weiter beachtet — nur die
  Eingabe ist weg.
