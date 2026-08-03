# Cammello 0.16.1

Eine Arbeitsversion (gerade Ziffer hinter dem ersten Punkt) mit zwei
Themen: **die Workflows sind jetzt eine Textdatei, die du selbst
bearbeitest**, und **das letzte Modul heißt „Uploads" und kann auch nach
Commons hochladen**.

## Die Datei

Sie heißt `workflows.toml` und liegt in deinem Benutzerverzeichnis neben
der Logdatei — auf dem Mac unter `~/Cammello/`, unter Windows in
`C:\Users\<Name>\Cammello\`. Beim ersten Start legt Cammello sie dort an,
danach wird sie nie wieder angefasst: sie überlebt also jedes Update.

Dass sie **nicht** im Programmverzeichnis liegt, ist Absicht. Alles unter
`assets/` steckt im Programm selbst, und ein gebautes Cammello entpackt
das bei jedem Start neu — eine Bearbeitung dort wäre beim nächsten Start
wieder verschwunden.

Zwei neue Menüpunkte unter **Datei**:

* **Workflow-Datei öffnen…** — öffnet sie im Texteditor deines Systems.
* **Workflows neu laden** — liest sie erneut ein, ohne Neustart.

## Was in der Datei steht

Ein Workflow ist ein Block. Ein neuer Workflow ist ein neuer Block:

    [[workflow]]
    schluessel = "presse"
    name       = "Pressekonferenz"
    felder_aus = ["kamerastandort", "objektstandort", "galerieseite"]

      [workflow.vorbelegung]
      vorlagen = "{{Wikiportraits}}"

      [workflow.beispiel]
      autor = "[[User:Seewolf|Harald Krichel]]"

* `schluessel` ist der interne Name. Er wird nie angezeigt und sollte
  später nicht mehr geändert werden — Cammello merkt sich daran, welcher
  Workflow gewählt war.
* `name` steht im Auswahlfeld.
* `felder_aus` sind die Felder, die **verborgen** werden. Es ist eine
  Ausschlussliste: alles, was nicht dasteht, bleibt sichtbar. Kommt in
  einer späteren Version ein Feld dazu, erscheint es von allein, statt
  stillschweigend zu fehlen, weil deine Datei es noch nicht kannte.
* **`vorbelegung`** trägt Text in ein Feld ein — aber nur, solange das Feld
  leer ist. Was du selbst getippt hast, wird nie überschrieben.
* **`beispiel`** setzt nur den grauen Hinweis im leeren Feld. Er wird nie
  gelesen und nie mit hochgeladen.

Die Datei, die Cammello anlegt, führt **alle verfügbaren Feldnamen als
Kommentar** auf, jeweils mit der Beschriftung, die du im Programm siehst.
Du musst also nie im Quelltext nachsehen, und die Liste kann nicht
veralten: sie wird aus dem Programm heraus erzeugt.

## Wenn etwas nicht stimmt

Eine kaputte Datei hält Cammello nie auf. Bei einem Tippfehler gelten die
eingebauten Workflows, und im Log steht der Grund samt Zeile und Spalte —
etwa `Expected ']]' at the end of an array declaration (at line 1, column
11)`. Nach **Workflows neu laden** sagt Cammello es zusätzlich in einem
Fenster, damit eine Änderung, die nicht gewirkt hat, nicht wie ein Fehler
im Programm aussieht. Einzelne unbrauchbare Zeilen — ein Feldname, den es
nicht gibt — werden übergangen und im Log genannt; der Rest der Datei gilt
weiter.

## Was gleich geblieben ist

Die beiden eingebauten Workflows verhalten sich genau wie in 0.16.0:
„Veranstaltungen/Porträts" verbirgt die beiden Standortfelder,
„Gebäude und Landschaften" verbirgt „Entstanden während". Wer die Datei
nicht anfasst, merkt von der Umstellung nichts.

Unverändert gilt außerdem: ein Workflow **belegt vor, er sperrt nicht**.
Jedes Feld bleibt bearbeitbar, und ein verborgenes Feld ist nicht
untätig — steht dort noch ein Wert, würde er hochgeladen. Deshalb fragt
Cammello beim Wechsel wie bisher nach, ob solche Werte gelöscht werden
sollen. Der Expertenmodus zeigt weiterhin alles, unabhängig vom Workflow.
Das IPTC-Modul wird bewusst nicht mitgeschaltet.

Weil jedes Feld einen Namen hat, kannst du jetzt auch Felder verbergen,
die vorher fest sichtbar waren — „Zeigt (P180)", die Kategorien, die
Galerieseite, den zusätzlichen Wikitext. Vorher waren es nur die
Standortfelder und „Entstanden während".

---

# Das Modul „Uploads"

Das letzte Modul hieß bisher „FTP / Flickr" — benannt nach zwei von drei
Zielen, und ausgerechnet das wichtigste fehlte. Es heißt jetzt **Uploads**,
unabhängig davon, welche Dienste eingeschaltet sind, und ganz oben rechts
sitzt eine neue Gruppe **Wikimedia Commons** mit dem Knopf **„Zu Commons
hochladen"**.

Der Knopf im MediaWiki-Modul bleibt, wo er war — das hier ist ein zweiter
Weg, kein Umzug. Und es ist wirklich derselbe Weg: Die links ausgewählten
Dateien werden in die Tabelle des MediaWiki-Moduls übernommen, dann läuft
der ganz normale Upload. Alles, was der gewohnte Knopf prüft, gilt also
auch hier — die Anmeldung, die Wikidata-IDs, das Pflichtfeld „Zeigt", der
Ausschluss kommerziell markierter Dateien, der Fortschrittsdialog. Cammello
wechselt dabei ins MediaWiki-Modul, weil der Upload dort berichtet, was er
tut.

## Filter im Kopf der Bilderspalte

Über der Dateiliste steht jetzt eine Filterleiste: **Sterne, Farben,
Kanäle** — dieselbe Gestik wie im Sichtungsmodul, damit ein Klick überall
dasselbe bedeutet.

Der Unterschied liegt in der Wirkung. Im Sichtungsmodul blendet der Filter
aus, was nicht passt. Hier **steuert er die Auswahl**: Was passt, wird
ausgewählt, was nicht passt, bleibt sichtbar und wird nur leicht ausgegraut.
Da die Upload-Knöpfe ohnehin der Auswahl folgen, braucht es zwischen Filtern
und Hochladen keinen weiteren Begriff.

Verknüpft wird wie in Lightroom:

* **Sterne sind eine Schwelle.** Ein Klick auf den dritten Stern heißt „drei
  Sterne und mehr"; ein zweiter Klick auf denselben Stern schaltet ab. Eine
  Datei hat genau eine Bewertung, deshalb wäre „drei oder fünf" keine
  sinnvolle Frage. Zurückgewiesene Bilder (roter Daumen) passieren einen
  aktiven Sternfilter nie.
* **Farben sind ODER.** Rot und Grün angeklickt heißt: die roten und die
  grünen. Das graue Feld ganz rechts meint „ohne Label" — dort landen auch
  Bilder mit einem Labeltext, den Cammello nicht kennt.
* **Kanäle sind ebenfalls ODER**, mit denselben drei Punkten wie in den
  Listen: für Commons, für kommerziell, ohne Markierung.
* **Die drei Gruppen zusammen sind UND:** drei Sterne UND (rot ODER grün).

Das Kreuz am Ende schaltet alles ab.

Eine Sicherung, die man hoffentlich nie bemerkt: Bisher galt überall
„nichts ausgewählt = alle Dateien". Bei aktivem Filter gilt das **nicht**
mehr — sonst hätte ein Filter, der auf nichts zutrifft, die Auswahl geleert
und damit die ganze Liste zum Upload freigegeben, also genau das Gegenteil
des Gewollten. Trifft der Filter nichts, wird nichts hochgeladen, und
Cammello sagt es.

Die Bewertungen kommen aus den XMP-Daten neben den Bildern, genau wie im
Sichtungsmodul: eine Sidecar-Datei schlägt das eingebettete XMP, RAW-Dateien
werden nie geöffnet. Sie werden je Datei einmal gelesen und gemerkt, damit
die Leiste beim Klicken nicht ins Stocken gerät; nach jedem Neuaufbau der
Liste wird neu gelesen.

---

# Wenn eine Datei nicht lesbar ist

Aus einem Nutzerbericht: Von 501 Dateien gingen 11 hoch, 490 scheiterten —
mit einem rohen Traceback und der Meldung „[Errno 22] Invalid argument".
Der Upload hatte nie begonnen; Windows hatte die Dateien zwar gefunden und
geöffnet, lieferte die Daten aber nicht (typisch für Online-only-Dateien
aus OneDrive, ein getrenntes Netzlaufwerk oder abgezogene Speichermedien).

Zwei Dinge machten das unnötig schwer:

* Die Fehlermeldung nannte den **Commons-Zielnamen** — eine Datei, die es
  auf der eigenen Platte gar nicht gibt. Welches Bild klemmte, war nicht
  herauszufinden.
* Der Lauf endete mit „11/501" und keinem Wort zu den übrigen 490.

Beides ist behoben:

* Cammello liest vor jedem Upload probeweise ein Byte. Klappt das nicht,
  steht im Log **„Cannot read: `<vollständiger lokaler Pfad>`"** mit dem
  Grund im Klartext — kein Traceback mehr, denn der sah aus wie ein Absturz
  in Cammello, obwohl das Problem beim Speicherort lag.
* Die Abschlussmeldung sagt jetzt, wie viele Dateien nicht lesbar waren und
  dass sie in der Warteschlange bleiben.
* Solche Dateien gelten **nicht** als endgültig gescheitert. Bisher wurden
  fehlgeschlagene Dateien bei „Fortsetzen" bewusst übersprungen — richtig
  bei einer Ablehnung durch Commons (schlechter Dateiname, fehlende Lizenz),
  falsch hier: Sobald die Dateien wieder verfügbar sind, gehen genau
  dieselben Bilder anstandslos hoch. Der Wiederaufnahme-Dialog weist eigens
  darauf hin.

Liegt die Datei auf einem **Netz- oder Wechsellaufwerk**, hängt Cammello
einen Satz an: „Kopiere sie in einen lokalen Ordner und versuche es
erneut." Bewusst nur dann — beim Hinzufügen von Dateien wird nicht gewarnt.
Ein Netzlaufwerk funktioniert die meiste Zeit tadellos; eine Warnung auf
Verdacht würde man nach dem dritten Mal überlesen. An dieser Stelle
dagegen, wo das Lesen gerade fehlgeschlagen ist, ist es der nützlichste
Satz, den das Programm sagen kann.

Fällt der Fehler erst mitten im Senden an — weil ein Laufwerk währenddessen
verschwindet —, wird er genauso behandelt.
