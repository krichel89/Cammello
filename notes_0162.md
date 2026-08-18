# Cammello 0.16.2

Eine kleine Pflegeversion auf der 0.16.1.

# Kleinere Verbesserungen

* **Passwörter im Schlüsselbund.** Das FTP-Passwort und die
  Flickr-Geheimnisse (API-Secret und die beiden OAuth-Token) liegen jetzt
  im Schlüsselbund des Betriebssystems — dort, wo der MediaWiki-Login
  seine Zugangsdaten seit jeher ablegt. Vorhandene Klartextwerte ziehen
  beim ersten Laden automatisch um; auf Rechnern ohne Schlüsselbund
  bleibt alles wie bisher, und der Hinweistext der Checkbox erklärt die
  Regel. Beim Fensteraufbau fragt Cammello den Schlüsselbund bewusst
  nie — unter macOS würde sonst bei jedem Start ein Dialog erscheinen;
  Passwörter werden erst im Moment des Gebrauchs gelesen.
* **Das Bearbeiten-Panel merkt sich seinen Platz** über Neustarts —
  als Anteil der Ansicht, sodass es bei anderer Fenstergröße an derselben
  relativen Stelle sitzt. Doppelklick auf den Titel bringt es weiterhin
  in die Standardecke zurück und vergisst den gemerkten Platz.
* Die „Features"-Zeile im Log nennt jetzt auch den rawpy-Zustand — bisher
  fiel ein fehlendes rawpy erst auf, wenn ein RAW-Verzeichnis geöffnet
  wurde.
* Der Update-Dialog öffnet nur noch https-Adressen; alles andere führt
  zur Releases-Seite.
* Vier verwaiste Übersetzungseinträge entfernt, Verzeichnis-Scan über
  scandir, und das Log sagt „directory" wie die Oberfläche.
