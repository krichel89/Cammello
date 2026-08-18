# Cammello 0.17.0

Eine Testversion (ungerade Ziffer hinter dem ersten Punkt) mit einem
einzigen Thema: **Anmeldung über OAuth 2.0.**

## Was sich ändert

Beim Anmelden ist jetzt OAuth 2.0 der vorgegebene Weg. Der Ablauf für dich
und andere Nutzer sieht gleich aus wie bisher — Knopf drücken, im Browser
„Zulassen", fertig —, aber unter der Haube ist er deutlich einfacher und
in einem Punkt grundsätzlich besser:

**Es wird kein Geheimnis mehr ausgeliefert.** Der alte Weg (OAuth 1.0a)
brauchte Key *und* Secret im Programm, weil jede Anfrage damit signiert
wird. Der neue Client ist als „nicht vertraulich" registriert: Im
Quelltext steht nur noch die öffentliche Client-ID, und an die Stelle des
Geheimnisses tritt PKCE — ein Einmal-Nachweis, den Cammello für jede
Anmeldung frisch erzeugt.

## Was du wissen solltest

* Zugriffstoken laufen nach **vier Stunden** ab. Cammello erneuert sie
  selbständig über das Refresh-Token; schlägt mitten in einem Upload eine
  Anfrage deswegen fehl, wird einmal erneuert und die Anfrage wiederholt.
  Der Server tauscht dabei auch das Refresh-Token aus; Cammello speichert
  immer das zuletzt erhaltene Paar im Schlüsselbund.
* Die **klassische Autorisierung (OAuth 1.0a) bleibt vollständig
  erhalten** — im Anmeldedialog per Häkchen wählbar, ebenso das
  Bot-Passwort. Bestehende 1.0a-Anmeldungen funktionieren weiter; neu
  angemeldet wird über den neuen Weg.
* Schlägt der automatische Rückweg fehl (Firewall), kannst du wie gehabt
  die Zeile aus der Adressleiste in das Feld im Dialog einfügen — Cammello
  fischt den Code selbst heraus.
* Abmelden entfernt beide Autorisierungen lokal; die serverseitige
  Freigabe verwaltest du wie immer auf Special:OAuthManageMyGrants.

## Zum Testen

1. Einmal frisch anmelden (der Dialog startet automatisch im neuen Weg).
2. Ein Bild hochladen.
3. Ideal wäre ein Test nach über vier Stunden Laufzeit: einfach ein
   weiteres Bild hochladen — die Erneuerung sollte unsichtbar passieren
   und im Log als „Access token expired - refreshed" auftauchen.
