## Cammello 0.11.8

Culling-Verbesserungen, ein aufgeräumter „Übernehmen"-Button, ein Hinweis zu
BotPasswords im Einstellungen-Tab und ein passend großes Dock-Icon auf dem Mac.

### Culling
- **Laufende Nummer im Vollbild.** Das Overlay zeigt jetzt neben Farbe und
  Sternen die Position des Bildes (z. B. `300/500`).
- **Ein „Übernehmen"-Knopf statt drei.** Die bisherigen Ziele MediaWiki, FTP
  und Flickr sind zu einem Knopf zusammengefasst: „Übernehmen" reicht die
  Auswahl (oder – ohne Auswahl – alle gefilterten Bilder) in einem Rutsch an
  den MediaWiki-, den IPTC- und den FTP-Tab weiter. Es wird dabei noch nichts
  hochgeladen. „Ordner…" bleibt als eigener Knopf; Flickr erreichst du über
  seinen eigenen Tab.
- **Ordner neu laden.** Ein neuer Knopf liest den aktuellen Ordner erneut von
  der Festplatte ein – praktisch, wenn Bewertungen/Labels in einem anderen
  Programm geändert wurden.
- **Nach Farben filtern, mit Mehrfachauswahl.** Farbige Schaltflächen in der
  Filterleiste; mehrere gleichzeitig wählbar. Die graue Fläche filtert auf
  „kein Label". Nichts aktiv = alle Farben.
- **Alles aus-/abwählen per Tastatur.** `Cmd+A` (Mac) bzw. `Ctrl+A`
  (Windows/Linux) wählt alle sichtbaren Bilder aus, `Cmd/Ctrl+D` hebt die
  Auswahl auf.
- Reject gibt es weiterhin über die Taste `X` (Bewertung -1).

### Einstellungen
- Der MediaWiki-Konto-Bereich verlinkt jetzt direkt auf **Special:BotPasswords**
  und nennt die benötigten Rechte (Seiten bearbeiten; erstellen, bearbeiten und
  verschieben; Dateien hochladen; hochladen, ersetzen und verschieben).

### macOS
- Das Dock-Icon hat jetzt den üblichen transparenten Rand und wirkt nicht mehr
  zu groß neben anderen Icons.
