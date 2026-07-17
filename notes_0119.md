## Cammello 0.11.9

Build-Reparatur. Der 0.11.8-CI-Build brach im Compile-Check ab, weil in
`mw_oauth.py` ein mehrzeiliger String innerhalb eines f-Strings stand — auf
Python 3.12 erlaubt, auf dem 3.11-Runner ein `SyntaxError`. Die Stelle ist
umgebaut (der Text wird vor dem f-String zusammengesetzt), sodass sie auf jeder
Python-Version übersetzt.

Inhaltlich identisch mit 0.11.8 (Culling-Verbesserungen, „Übernehmen"-Button,
BotPasswords-Link im Einstellungen-Tab, gepolstertes Mac-Dock-Icon).
