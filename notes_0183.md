# Cammello 0.18.3 — Import direkt von der Kamera

## Worum es geht

Canon-Bodies (R5, R6 und jede EOS seit den DSLR-Jahren) melden sich über
USB als **PTP-Gerät**, nicht als Massenspeicher. Die Karte wird deshalb nie
gemountet: kein Volume im Finder, kein Laufwerksbuchstabe im Explorer, also
auch kein Pfad, den „Öffnen…" auflisten könnte. Lightroom arbeitet ebenfalls
nicht *auf* der Karte — es spricht PTP und **kopiert beim Import auf die
Platte**. Genau das macht Cammello jetzt auch.

Gedacht als **Notweg bei fehlendem Kartenleser**, nicht als Alltagspfad: die
Übertragung per PTP ist spürbar langsamer als ein CFexpress-Leser.

## Bedienung

Im Sichtungsmodul neben „Öffnen…" und dem Neu-Laden-Knopf: **„Von Kamera…"**

1. Kamera einschalten, USB anstecken.
2. Sind mehrere Kameras angeschlossen, fragt Cammello, welche.
3. Zielordner wählen (der zuletzt benutzte Ordner ist vorgeschlagen).
4. Cammello liest die Karte, kopiert und **öffnet den Zielordner
   anschließend im Sichtungsmodul**.

## Regeln, die dabei gelten

* **Nichts wird überschrieben.** Ein Name, der im Zielordner schon mit
  **gleicher Größe** liegt, gilt als bereits importiert und wird
  übersprungen — das ist es, was einen abgebrochenen Import ohne Journal
  fortsetzbar macht. Ein Name mit **anderer Größe** (zwei Karten mit
  denselben laufenden Nummern) wird als Namenskonflikt gemeldet und in Ruhe
  gelassen, nicht umbenannt und nicht überschrieben.
* **Abweichung von der 0.18.2-Regel, bewusst:** beim Verschieben bricht der
  ganze Vorgang bei einer Kollision ab. Beim Import wäre das falsch — eine
  Karte hat 800 Dateien, und ein einziger Konflikt darf nicht die restlichen
  799 verhindern. Also: überspringen, am Ende berichten.
* **Teilübertragungen können nicht täuschen.** Jede Datei landet zuerst als
  `<name>.part` und wird erst nach vollständigem Empfang umbenannt. Ein
  Abbruch hinterlässt also nie eine kurze Datei, die der nächste Lauf für
  fertig hielte.
* **Abbrechen** wirkt zwischen zwei Dateien, wie beim Upload.
* Aufnahmezeit der Kamera wird auf die kopierte Datei gesetzt.
* Genommen werden RAW, JPEG, Sidecars sowie `.wav`, `.mp4`, `.mov`, `.crm`;
  die Verwaltungsdateien der Karte bleiben liegen.

## Was gebaut wurde

**Neues Modul `cammello/camera.py`** (Qt-frei, wie `edits.py` und
`channels.py`): Backend-Auswahl je Plattform, `wanted()`, `scan_dest()`,
`plan_import()`, `part_path()`, `summary_text()` und der gphoto2-Backend.
Die Endungslisten kommen aus `culling.py` statt ein zweites Mal von Hand —
eine zweite handgeführte Liste derselben Namen war genau der
`sdc._ASSIGN_RE`-Fehler.

**`mw_culling.py`**: Knopf „Von Kamera…", `_CameraImportWorker` (gleiche
Signalform wie `_FolderCopyWorker`, damit der vorhandene Fortschrittsdialog
unverändert weiterläuft) und die Handler `_cull_import_from_camera`,
`_cull_on_camera_listing/_ready/_fatal/_finished`.

**`widgets.py`**: `UploadProgressDialog.set_total()` und `set_detail()` —
beim Import ist die Zahl der Dateien erst bekannt, wenn die Karte gelesen
ist, also öffnet der Dialog mit 0 und lernt sie nach.

**10 neue i18n-Schlüssel** in fünf Sprachen, **`test_camera_0183.py`**
(36 Prüfungen).

## Plattformen

| Plattform | Weg | Stand |
|---|---|---|
| macOS (Apple Silicon) | libgphoto2 über `python-gphoto2` | gebaut |
| Linux | dito | gebaut |
| macOS Intel | — | **absichtlich nicht**, siehe unten |
| Windows | Windows Portable Devices (WPD) | **fehlt noch**, siehe unten |

`requirements.txt` bekommt `gphoto2>=2.6,<2.7 ; sys_platform != "win32"`.
Der Marker ist Pflicht: auf Windows gibt es kein Wheel, pip würde aus dem
Quelltext bauen wollen und den Build umbringen.

`build.yml`: `--collect-all gphoto2` für den arm64-Mac- und den Linux-Build.
Das ist keine Kosmetik — das Paket setzt `CAMLIBS`/`IOLIBS` relativ zum
eigenen Verzeichnis, und ohne das mitgelieferte `camlibs/ptp2.so` findet
libgphoto2 überhaupt keine Kamera.

**Intel-Mac ausgenommen:** das x86_64-Wheel ist `macosx_15_0`. Es würde das
Mindest-macOS des Intel-Builds von 13 (Ventura, diktiert vom pyexiv2-Wheel)
auf 15 anheben. Dieselbe Filterlogik wie bei rawpy. Preis: im Intel-Build
kein Kamera-Import.

**Windows fehlt bewusst.** libgphoto2 ist nie nach Windows portiert worden
(`gphoto/libgphoto2#279`). Der richtige Weg dort ist die WPD-API, die PTP
über USB als Klassentreiber bedient. Ich habe sie **nicht blind
geschrieben**: die WPD-Eigenschaftsschlüssel sind GUID+PID-Paare, und die
aus dem Gedächtnis hinzuschreiben heißt, Code auszuliefern, der nicht
laufen kann. Der Knopf sagt unter Windows in klaren Worten, dass es noch
nicht geht.

## Was ich von dir brauche (Windows, eine Runde)

Bitte auf dem Windows-Rechner mit **angeschlossener, eingeschalteter
Kamera** laufen lassen und die Ausgabe schicken:

```
pip install comtypes
python wpd_probe.py
```

`wpd_probe.py` liegt im Paket in der Wurzel. Es koppelt nichts an, es
listet nur, was Windows sieht. Gegen diese Ausgabe schreibe ich den
Windows-Backend für 0.18.4.

Zusätzlich interessant: erscheint die R5 im Explorer unter „Dieser PC" als
*tragbares Gerät* (ohne Laufwerksbuchstaben)? Normalerweise tut sie das.
Wenn nicht, ist das ein eigenes Problem vor dem Cammello-Feature.

## Nicht enthalten

Deine drei `n:`-Punkte (Export statt „Save to…", Kopieren-Option beim
Verschieben, nur RAW+Sidecar) sind weiter vorgemerkt und liegen in dieser
Version unangetastet.

## Prüfung vor der Lieferung

* `py_compile` über alles, AST-Gate gegen mehrzeilige f-String-Ausdrücke.
* pyflakes normalisiert gediffed: **479 Befundarten, null neue.** (Der
  bundler-sichtbare `gphoto2`-Import in `camera.py` ist an eine Zuweisung
  gebunden, damit er keinen 480. Befund erzeugt.)
* Volle Testreihe zweimal mit frischem HOME, gegen den 0.18.2-Stand
  gediffed: identisch, plus die neue Reihe.
* Verifikation im frischen Verzeichnis (sauberer Klon von `v0.18.0` +
  0.18.2-Paket + dieses Paket) und aus dem entpackten Zip.

**Nicht prüfbar ohne Kamera und ohne Fenster:** der eigentliche
PTP-Durchlauf, die Kameraauswahl bei zwei Bodies, das Neueinlesen des
Zielordners danach. Beim ersten Lauf bitte das Log schicken.
