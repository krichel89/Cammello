"""Translations, part C: culling tab, IPTC tab, FTP tab."""

DATA_C = {
    # ── Culling toolbar ─────────────────────────────────────────────────────
    'Open folder…': {'de': 'Ordner öffnen…', 'es': 'Abrir carpeta…',
                     'fr': 'Ouvrir un dossier…', 'it': 'Apri cartella…'},
    'Number keys 1-5 set stars or colors; M toggles the mode.': {
        'de': 'Die Zifferntasten 1-5 setzen Sterne oder Farben; M schaltet den '
              'Modus um.',
        'es': 'Las teclas 1-5 asignan estrellas o colores; M cambia de modo.',
        'fr': 'Les touches 1-5 attribuent des étoiles ou des couleurs ; M '
              'bascule le mode.',
        'it': 'I tasti 1-5 assegnano stelle o colori; M cambia modalità.'},
    'numbers = STARS': {'de': 'Ziffern = STERNE', 'es': 'números = ESTRELLAS',
                        'fr': 'chiffres = ÉTOILES', 'it': 'numeri = STELLE'},
    'numbers = COLORS': {'de': 'Ziffern = FARBEN', 'es': 'números = COLORES',
                         'fr': 'chiffres = COULEURS', 'it': 'numeri = COLORI'},
    'Zoom:': {'de': 'Zoom:', 'es': 'Zoom:', 'fr': 'Zoom :', 'it': 'Zoom:'},
    'One zoom step out (Cmd/Ctrl -)': {
        'de': 'Eine Zoomstufe heraus (Cmd/Strg -)',
        'es': 'Reducir un paso de zoom (Cmd/Ctrl -)',
        'fr': 'Un cran de zoom arrière (Cmd/Ctrl -)',
        'it': 'Un passo di zoom indietro (Cmd/Ctrl -)'},
    'One zoom step in (Cmd/Ctrl +)': {
        'de': 'Eine Zoomstufe hinein (Cmd/Strg +)',
        'es': 'Aumentar un paso de zoom (Cmd/Ctrl +)',
        'fr': 'Un cran de zoom avant (Cmd/Ctrl +)',
        'it': 'Un passo di zoom avanti (Cmd/Ctrl +)'},
    'Grid': {'de': 'Raster', 'es': 'Cuadrícula', 'fr': 'Grille',
             'it': 'Griglia'},
    'Grid view (G): thumbnails instead of the large image.': {
        'de': 'Rasteransicht (G): Miniaturen statt des großen Bildes.',
        'es': 'Vista de cuadrícula (G): miniaturas en lugar de la imagen '
              'grande.',
        'fr': "Vue en grille (G) : vignettes au lieu de la grande image.",
        'it': "Vista a griglia (G): miniature al posto dell'immagine grande."},
    'Show:': {'de': 'Zeigen:', 'es': 'Mostrar:', 'fr': 'Afficher :',
              'it': 'Mostra:'},
    'all': {'de': 'alle', 'es': 'todas', 'fr': 'toutes', 'it': 'tutte'},
    'incl. rejects': {'de': 'inkl. Ausschuss', 'es': 'incl. descartes',
                      'fr': 'y c. rejets', 'it': 'incl. scarti'},
    'Send to:': {'de': 'Senden an:', 'es': 'Enviar a:', 'fr': 'Envoyer vers :',
                 'it': 'Invia a:'},
    'Adds the selected images to the MediaWiki tab; with no selection, every '
    'image passing the filter. Images can also be dragged onto the MediaWiki '
    'tab directly.': {
        'de': 'Fügt die ausgewählten Bilder dem MediaWiki-Tab hinzu; ohne '
              'Auswahl jedes Bild, das den Filter passiert. Bilder können auch '
              'direkt auf den MediaWiki-Tab gezogen werden.',
        'es': 'Añade las imágenes seleccionadas a la pestaña MediaWiki; sin '
              'selección, todas las imágenes que pasan el filtro. También se '
              'pueden arrastrar directamente a la pestaña MediaWiki.',
        'fr': "Ajoute les images sélectionnées à l'onglet MediaWiki ; sans "
              'sélection, toutes les images qui passent le filtre. Les images '
              "peuvent aussi être glissées directement sur l'onglet MediaWiki.",
        'it': 'Aggiunge le immagini selezionate alla scheda MediaWiki; senza '
              'selezione, ogni immagine che supera il filtro. Le immagini '
              'possono anche essere trascinate direttamente sulla scheda '
              'MediaWiki.'},
    'Uploads the selected images (as they are, no IPTC writing) to the server '
    'configured in the FTP tab / Settings.': {
        'de': 'Lädt die ausgewählten Bilder (unverändert, ohne IPTC-Schreiben) '
              'auf den im FTP-Tab / in den Einstellungen konfigurierten Server '
              'hoch.',
        'es': 'Sube las imágenes seleccionadas (tal cual, sin escribir IPTC) '
              'al servidor configurado en la pestaña FTP / Ajustes.',
        'fr': "Importe les images sélectionnées (telles quelles, sans écriture "
              "IPTC) vers le serveur configuré dans l'onglet FTP / Réglages.",
        'it': 'Carica le immagini selezionate (così come sono, senza scrittura '
              'IPTC) sul server configurato nella scheda FTP / Impostazioni.'},
    'Folder…': {'de': 'Ordner…', 'es': 'Carpeta…', 'fr': 'Dossier…',
                'it': 'Cartella…'},
    'Copies the selected images into a local folder. RAW files bring their '
    '.xmp sidecar along; existing files in the target folder are never '
    'overwritten.': {
        'de': 'Kopiert die ausgewählten Bilder in einen lokalen Ordner. '
              'RAW-Dateien nehmen ihre .xmp-Sidecar-Datei mit; vorhandene '
              'Dateien im Zielordner werden nie überschrieben.',
        'es': 'Copia las imágenes seleccionadas en una carpeta local. Los RAW '
              'llevan consigo su archivo .xmp; nunca se sobrescriben los '
              'archivos existentes en la carpeta de destino.',
        'fr': 'Copie les images sélectionnées dans un dossier local. Les RAW '
              'emportent leur fichier .xmp ; les fichiers existants du dossier '
              'cible ne sont jamais écrasés.',
        'it': 'Copia le immagini selezionate in una cartella locale. I RAW '
              'portano con sé il file .xmp; i file già presenti nella cartella '
              'di destinazione non vengono mai sovrascritti.'},
    'Copy selection to folder': {
        'de': 'Auswahl in Ordner kopieren',
        'es': 'Copiar la selección a una carpeta',
        'fr': 'Copier la sélection dans un dossier',
        'it': 'Copia la selezione in una cartella'},
    'Copy to folder': {'de': 'In Ordner kopieren',
                       'es': 'Copiar a carpeta',
                       'fr': 'Copier dans un dossier',
                       'it': 'Copia nella cartella'},

    # ── Culling status / items ──────────────────────────────────────────────
    'No folder open. Open one to start culling.': {
        'de': 'Kein Ordner geöffnet. Zum Sichten einen Ordner öffnen.',
        'es': 'No hay ninguna carpeta abierta. Abra una para empezar la '
              'selección.',
        'fr': 'Aucun dossier ouvert. Ouvrez-en un pour commencer le tri.',
        'it': 'Nessuna cartella aperta. Aprine una per iniziare la selezione.'},
    '{pos}/{shown} shown ({total} in folder)': {
        'de': '{pos}/{shown} angezeigt ({total} im Ordner)',
        'es': '{pos}/{shown} mostradas ({total} en la carpeta)',
        'fr': '{pos}/{shown} affichées ({total} dans le dossier)',
        'it': '{pos}/{shown} mostrate ({total} nella cartella)'},
    'Nothing passes the current filter.': {
        'de': 'Nichts passiert den aktuellen Filter.',
        'es': 'Nada pasa el filtro actual.',
        'fr': 'Rien ne passe le filtre actuel.',
        'it': 'Nulla supera il filtro attuale.'},
    '[P] RAW+JPEG pair (one picture, two files)': {
        'de': '[P] RAW+JPEG-Paar (ein Bild, zwei Dateien)',
        'es': '[P] par RAW+JPEG (una imagen, dos archivos)',
        'fr': '[P] paire RAW+JPEG (une image, deux fichiers)',
        'it': '[P] coppia RAW+JPEG (una foto, due file)'},
    '[T] already in the file table': {
        'de': '[T] bereits in der Dateitabelle',
        'es': '[T] ya está en la tabla de archivos',
        'fr': '[T] déjà dans le tableau des fichiers',
        'it': '[T] già nella tabella dei file'},
    '{added} file(s) added to the table, {dupes} duplicate(s) skipped, '
    '{failed} failed.': {
        'de': '{added} Datei(en) zur Tabelle hinzugefügt, {dupes} Duplikat(e) '
              'übersprungen, {failed} fehlgeschlagen.',
        'es': '{added} archivo(s) añadidos a la tabla, {dupes} duplicado(s) '
              'omitidos, {failed} con error.',
        'fr': '{added} fichier(s) ajoutés au tableau, {dupes} doublon(s) '
              'ignorés, {failed} en échec.',
        'it': '{added} file aggiunti alla tabella, {dupes} duplicati saltati, '
              '{failed} non riusciti.'},

    # ── Culling settings ────────────────────────────────────────────────────
    'Advance to the next image after rating/labeling': {
        'de': 'Nach Bewertung/Farbmarkierung zum nächsten Bild springen',
        'es': 'Pasar a la imagen siguiente tras valorar o etiquetar',
        'fr': "Passer à l'image suivante après notation ou étiquetage",
        'it': "Passare all'immagine successiva dopo valutazione o etichetta"},
    'Auto-advance:': {'de': 'Automatisch weiter:', 'es': 'Avance automático:',
                      'fr': 'Avance automatique :',
                      'it': 'Avanzamento automatico:'},
    'Color label set:': {'de': 'Farbmarkierungs-Satz:',
                         'es': 'Conjunto de etiquetas de color:',
                         'fr': "Jeu d'étiquettes de couleur :",
                         'it': 'Set di etichette colore:'},
    'Language of the label TEXT written to XMP - must match the color label '
    'set of your Lightroom, or LR shows the label in white.': {
        'de': 'Sprache des in XMP geschriebenen Markierungs-TEXTS - muss zum '
              'Farbmarkierungs-Satz deines Lightroom passen, sonst zeigt LR '
              'die Markierung weiß an.',
        'es': 'Idioma del TEXTO de la etiqueta escrito en XMP: debe coincidir '
              'con el conjunto de etiquetas de color de su Lightroom, o LR '
              'mostrará la etiqueta en blanco.',
        'fr': "Langue du TEXTE d'étiquette écrit dans le XMP - doit "
              "correspondre au jeu d'étiquettes de couleur de votre Lightroom, "
              "sinon LR affiche l'étiquette en blanc.",
        'it': "Lingua del TESTO dell'etichetta scritto nell'XMP: deve "
              'corrispondere al set di etichette colore del tuo Lightroom, '
              "altrimenti LR mostra l'etichetta in bianco."},
    'RAW+JPEG pairs:': {'de': 'RAW+JPEG-Paare:', 'es': 'Pares RAW+JPEG:',
                        'fr': 'Paires RAW+JPEG :', 'it': 'Coppie RAW+JPEG:'},
    'Which file of a RAW+JPEG pair goes to the file table (button and '
    'drag-and-drop).': {
        'de': 'Welche Datei eines RAW+JPEG-Paars in die Dateitabelle geht '
              '(Schaltfläche und Drag-and-drop).',
        'es': 'Qué archivo de un par RAW+JPEG va a la tabla de archivos (botón '
              'y arrastrar y soltar).',
        'fr': "Quel fichier d'une paire RAW+JPEG va dans le tableau des "
              'fichiers (bouton et glisser-déposer).',
        'it': 'Quale file di una coppia RAW+JPEG finisce nella tabella dei '
              'file (pulsante e trascinamento).'},
    'pair: JPEG': {'de': 'Paar: JPEG', 'es': 'par: JPEG', 'fr': 'paire : JPEG',
                   'it': 'coppia: JPEG'},
    'pair: RAW': {'de': 'Paar: RAW', 'es': 'par: RAW', 'fr': 'paire : RAW',
                  'it': 'coppia: RAW'},
    'pair: both': {'de': 'Paar: beide', 'es': 'par: ambos',
                   'fr': 'paire : les deux', 'it': 'coppia: entrambi'},

    # ── Folder copy worker ──────────────────────────────────────────────────
    'Skipped (exists)': {'de': 'Übersprungen (vorhanden)',
                         'es': 'Omitido (ya existe)',
                         'fr': 'Ignoré (existe déjà)',
                         'it': 'Saltato (già presente)'},
    'Done: {ok}/{total} file(s) copied': {
        'de': 'Fertig: {ok}/{total} Datei(en) kopiert',
        'es': 'Listo: {ok}/{total} archivo(s) copiados',
        'fr': 'Terminé : {ok}/{total} fichier(s) copiés',
        'it': 'Fatto: {ok}/{total} file copiati'},
    'Cancelled: {ok}/{total} file(s) copied, {n} not started.': {
        'de': 'Abgebrochen: {ok}/{total} Datei(en) kopiert, {n} nicht '
              'begonnen.',
        'es': 'Cancelado: {ok}/{total} archivo(s) copiados, {n} sin empezar.',
        'fr': 'Annulé : {ok}/{total} fichier(s) copiés, {n} non commencés.',
        'it': 'Annullato: {ok}/{total} file copiati, {n} non avviati.'},
    '{n} skipped (already there)': {
        'de': '{n} übersprungen (bereits vorhanden)',
        'es': '{n} omitidos (ya estaban)',
        'fr': '{n} ignorés (déjà présents)',
        'it': '{n} saltati (già presenti)'},
    '{n} failed': {'de': '{n} fehlgeschlagen', 'es': '{n} con error',
                   'fr': '{n} en échec', 'it': '{n} non riusciti'},

    # ── IPTC tab ────────────────────────────────────────────────────────────
    'Files (shared with the MediaWiki tab):': {
        'de': 'Dateien (gemeinsam mit dem MediaWiki-Tab):',
        'es': 'Archivos (compartidos con la pestaña MediaWiki):',
        'fr': "Fichiers (partagés avec l'onglet MediaWiki) :",
        'it': 'File (condivisi con la scheda MediaWiki):'},
    'Refresh list': {'de': 'Liste aktualisieren', 'es': 'Actualizar lista',
                     'fr': 'Actualiser la liste', 'it': 'Aggiorna elenco'},
    'IPTC fields of the selected file': {
        'de': 'IPTC-Felder der ausgewählten Datei',
        'es': 'Campos IPTC del archivo seleccionado',
        'fr': 'Champs IPTC du fichier sélectionné',
        'it': 'Campi IPTC del file selezionato'},
    'separated by ;': {'de': 'getrennt durch ;', 'es': 'separados por ;',
                       'fr': 'séparés par ;', 'it': 'separati da ;'},
    'Read IPTC from file': {'de': 'IPTC aus Datei lesen',
                            'es': 'Leer IPTC del archivo',
                            'fr': 'Lire les IPTC du fichier',
                            'it': 'Leggi IPTC dal file'},
    'Fill from MediaWiki data': {
        'de': 'Aus MediaWiki-Daten füllen',
        'es': 'Rellenar con datos de MediaWiki',
        'fr': 'Remplir avec les données MediaWiki',
        'it': 'Compila dai dati MediaWiki'},
    'caption -> Caption/Headline, categories -> Keywords, author -> Creator, '
    'date -> Date created, target filename -> Title. QIDs are not resolved to '
    'names (that would need a Wikidata lookup).': {
        'de': 'caption -> Bildtext/Schlagzeile, Kategorien -> Stichwörter, '
              'Autor -> Urheber, Datum -> Erstellungsdatum, Zieldateiname -> '
              'Titel. QIDs werden nicht zu Namen aufgelöst (das bräuchte eine '
              'Wikidata-Abfrage).',
        'es': 'caption -> Leyenda/Titular, categorías -> Palabras clave, autor '
              '-> Creador, fecha -> Fecha de creación, nombre de destino -> '
              'Título. Los QID no se resuelven a nombres (haría falta una '
              'consulta a Wikidata).',
        'fr': 'caption -> Légende/Titre, catégories -> Mots-clés, auteur -> '
              'Créateur, date -> Date de création, nom de fichier cible -> '
              'Titre. Les QID ne sont pas résolus en noms (cela nécessiterait '
              'une requête Wikidata).',
        'it': 'caption -> Didascalia/Titolo, categorie -> Parole chiave, '
              'autore -> Autore, data -> Data di creazione, nome file di '
              'destinazione -> Titolo. I QID non vengono risolti in nomi '
              '(servirebbe una query a Wikidata).'},
    'Caption -> Wikitext as': {'de': 'Bildtext -> Wikitext als',
                               'es': 'Leyenda -> Wikitexto como',
                               'fr': 'Légende -> Wikitexte en',
                               'it': 'Didascalia -> Wikitesto come'},
    "Copies the IPTC caption into the file's description as caption_<language>.": {
        'de': 'Kopiert den IPTC-Bildtext als caption_<Sprache> in die '
              'Beschreibung der Datei.',
        'es': 'Copia la leyenda IPTC en la descripción del archivo como '
              'caption_<idioma>.',
        'fr': 'Copie la légende IPTC dans la description du fichier sous la '
              'forme caption_<langue>.',
        'it': 'Copia la didascalia IPTC nella descrizione del file come '
              'caption_<lingua>.'},
    'IPTC writing': {'de': 'IPTC-Schreiben', 'es': 'Escritura de IPTC',
                     'fr': 'Écriture IPTC', 'it': 'Scrittura IPTC'},
    'Write into the ORIGINAL files (default: copies in the export folder '
    'below)': {
        'de': 'In die ORIGINALDATEIEN schreiben (Standard: Kopien im '
              'Exportordner unten)',
        'es': 'Escribir en los archivos ORIGINALES (por defecto: copias en la '
              'carpeta de exportación de abajo)',
        'fr': 'Écrire dans les fichiers ORIGINAUX (par défaut : copies dans le '
              "dossier d'export ci-dessous)",
        'it': 'Scrivere nei file ORIGINALI (predefinito: copie nella cartella '
              'di esportazione qui sotto)'},
    'Export folder for copies': {
        'de': 'Exportordner für Kopien',
        'es': 'Carpeta de exportación para las copias',
        'fr': "Dossier d'export pour les copies",
        'it': 'Cartella di esportazione per le copie'},
    'Write IPTC (all files with data)': {
        'de': 'IPTC schreiben (alle Dateien mit Daten)',
        'es': 'Escribir IPTC (todos los archivos con datos)',
        'fr': 'Écrire les IPTC (tous les fichiers ayant des données)',
        'it': 'Scrivi IPTC (tutti i file con dati)'},
    'The caption field is empty.': {
        'de': 'Das Bildtext-Feld ist leer.',
        'es': 'El campo de leyenda está vacío.',
        'fr': 'Le champ de légende est vide.',
        'it': 'Il campo della didascalia è vuoto.'},
    'Choose an export folder, or enable writing into the original files.': {
        'de': 'Einen Exportordner wählen oder das Schreiben in die '
              'Originaldateien aktivieren.',
        'es': 'Elija una carpeta de exportación o active la escritura en los '
              'archivos originales.',
        'fr': "Choisissez un dossier d'export ou activez l'écriture dans les "
              'fichiers originaux.',
        'it': 'Scegli una cartella di esportazione oppure attiva la scrittura '
              'nei file originali.'},
    'No file has any IPTC data yet.': {
        'de': 'Noch keine Datei hat IPTC-Daten.',
        'es': 'Ningún archivo tiene todavía datos IPTC.',
        'fr': "Aucun fichier n'a encore de données IPTC.",
        'it': 'Nessun file ha ancora dati IPTC.'},
    'IPTC written: {written} file(s), {failed} failed.': {
        'de': 'IPTC geschrieben: {written} Datei(en), {failed} fehlgeschlagen.',
        'es': 'IPTC escrito: {written} archivo(s), {failed} con error.',
        'fr': 'IPTC écrits : {written} fichier(s), {failed} en échec.',
        'it': 'IPTC scritti: {written} file, {failed} non riusciti.'},
    'Filled {n} field(s) from MediaWiki data for "{name}".': {
        'de': '{n} Feld(er) aus MediaWiki-Daten für "{name}" gefüllt.',
        'es': 'Se rellenaron {n} campo(s) con datos de MediaWiki para "{name}".',
        'fr': '{n} champ(s) remplis avec les données MediaWiki pour « {name} ».',
        'it': 'Compilati {n} campi dai dati MediaWiki per "{name}".'},
    'Caption copied to caption_{lang} for "{name}".': {
        'de': 'Bildtext nach caption_{lang} kopiert für "{name}".',
        'es': 'Leyenda copiada a caption_{lang} para "{name}".',
        'fr': 'Légende copiée vers caption_{lang} pour « {name} ».',
        'it': 'Didascalia copiata in caption_{lang} per "{name}".'},
    'IPTC write failed, file skipped: "{name}": {e}': {
        'de': 'IPTC-Schreiben fehlgeschlagen, Datei übersprungen: "{name}": {e}',
        'es': 'Fallo al escribir IPTC, archivo omitido: "{name}": {e}',
        'fr': "Échec de l'écriture IPTC, fichier ignoré : « {name} » : {e}",
        'it': 'Scrittura IPTC non riuscita, file saltato: "{name}": {e}'},
    # IPTC field labels (translated dynamically via tr(label)).
    'Title / object name': {'de': 'Titel / Objektname',
                            'es': 'Título / nombre del objeto',
                            'fr': "Titre / nom de l'objet",
                            'it': "Titolo / nome dell'oggetto"},
    'Headline': {'de': 'Schlagzeile', 'es': 'Titular', 'fr': 'Titre',
                 'it': 'Titolo'},
    'Caption / description': {'de': 'Bildtext / Beschreibung',
                              'es': 'Leyenda / descripción',
                              'fr': 'Légende / description',
                              'it': 'Didascalia / descrizione'},
    'Keywords': {'de': 'Stichwörter', 'es': 'Palabras clave',
                 'fr': 'Mots-clés', 'it': 'Parole chiave'},
    'Creator (by-line)': {'de': 'Urheber (Byline)',
                          'es': 'Creador (autoría)',
                          'fr': 'Créateur (signature)',
                          'it': 'Autore (firma)'},
    'Copyright notice': {'de': 'Urheberrechtshinweis',
                         'es': 'Aviso de derechos de autor',
                         'fr': "Mention de droit d'auteur",
                         'it': "Avviso di copyright"},
    'Credit': {'de': 'Bildnachweis', 'es': 'Crédito', 'fr': 'Crédit',
               'it': 'Credito'},
    'Source': {'de': 'Quelle', 'es': 'Fuente', 'fr': 'Source', 'it': 'Fonte'},
    'City': {'de': 'Stadt', 'es': 'Ciudad', 'fr': 'Ville', 'it': 'Città'},
    'Province / state': {'de': 'Bundesland / Region',
                         'es': 'Provincia / estado',
                         'fr': 'Province / région',
                         'it': 'Provincia / regione'},
    'Country': {'de': 'Land', 'es': 'País', 'fr': 'Pays', 'it': 'Paese'},
    'Date created (YYYY-MM-DD)': {'de': 'Erstellungsdatum (JJJJ-MM-TT)',
                                  'es': 'Fecha de creación (AAAA-MM-DD)',
                                  'fr': 'Date de création (AAAA-MM-JJ)',
                                  'it': 'Data di creazione (AAAA-MM-GG)'},

    # ── FTP tab ─────────────────────────────────────────────────────────────
    'FTP server': {'de': 'FTP-Server', 'es': 'Servidor FTP',
                   'fr': 'Serveur FTP', 'it': 'Server FTP'},
    'FTP upload': {'de': 'FTP-Upload', 'es': 'Subida por FTP',
                   'fr': 'Import FTP', 'it': 'Caricamento FTP'},
    'Protocol:': {'de': 'Protokoll:', 'es': 'Protocolo:', 'fr': 'Protocole :',
                  'it': 'Protocollo:'},
    'Host:': {'de': 'Host:', 'es': 'Servidor:', 'fr': 'Hôte :',
              'it': 'Host:'},
    'Port:': {'de': 'Port:', 'es': 'Puerto:', 'fr': 'Port :', 'it': 'Porta:'},
    'User:': {'de': 'Benutzer:', 'es': 'Usuario:', 'fr': 'Utilisateur :',
              'it': 'Utente:'},
    'empty = default port': {'de': 'leer = Standardport',
                             'es': 'vacío = puerto predeterminado',
                             'fr': 'vide = port par défaut',
                             'it': 'vuoto = porta predefinita'},
    'Store password in settings (PLAIN TEXT - unsafe)': {
        'de': 'Passwort in den Einstellungen speichern (KLARTEXT - unsicher)',
        'es': 'Guardar la contraseña en los ajustes (TEXTO PLANO - inseguro)',
        'fr': 'Enregistrer le mot de passe dans les réglages (EN CLAIR - non '
              'sécurisé)',
        'it': 'Salvare la password nelle impostazioni (TESTO IN CHIARO - non '
              'sicuro)'},
    'Remote directory:': {'de': 'Zielverzeichnis:',
                          'es': 'Directorio remoto:',
                          'fr': 'Répertoire distant :',
                          'it': 'Directory remota:'},
    'Files and IPTC data come from the IPTC tab. Write settings (export '
    'folder) are in the IPTC tab.': {
        'de': 'Dateien und IPTC-Daten kommen aus dem IPTC-Tab. Die '
              'Schreibeinstellungen (Exportordner) stehen im IPTC-Tab.',
        'es': 'Los archivos y los datos IPTC vienen de la pestaña IPTC. Los '
              'ajustes de escritura (carpeta de exportación) están en la '
              'pestaña IPTC.',
        'fr': "Les fichiers et les données IPTC proviennent de l'onglet IPTC. "
              "Les réglages d'écriture (dossier d'export) s'y trouvent aussi.",
        'it': 'I file e i dati IPTC provengono dalla scheda IPTC. Le '
              'impostazioni di scrittura (cartella di esportazione) sono nella '
              'scheda IPTC.'},
    'Write IPTC + upload all': {'de': 'IPTC schreiben + alle hochladen',
                                'es': 'Escribir IPTC y subir todo',
                                'fr': 'Écrire les IPTC + tout importer',
                                'it': 'Scrivi IPTC + carica tutto'},
    'The IPTC tab is disabled, so the "Write IPTC + upload" workflow is '
    'unavailable. These server settings are used by the Culling tab '
    '("-> FTP").': {
        'de': 'Der IPTC-Tab ist deaktiviert, daher ist der Ablauf "IPTC '
              'schreiben + hochladen" nicht verfügbar. Diese '
              'Servereinstellungen werden vom Sichtungs-Tab ("-> FTP") '
              'verwendet.',
        'es': 'La pestaña IPTC está desactivada, así que el flujo "Escribir '
              'IPTC y subir" no está disponible. Estos ajustes del servidor '
              'los usa la pestaña de selección ("-> FTP").',
        'fr': "L'onglet IPTC est désactivé : le flux « Écrire les IPTC + "
              'importer » est indisponible. Ces réglages de serveur sont '
              "utilisés par l'onglet de tri (« -> FTP »).",
        'it': 'La scheda IPTC è disattivata, quindi il flusso "Scrivi IPTC + '
              'carica" non è disponibile. Queste impostazioni del server sono '
              'usate dalla scheda di selezione ("-> FTP").'},
    'Host is missing.': {'de': 'Der Host fehlt.', 'es': 'Falta el servidor.',
                         'fr': "L'hôte est manquant.", 'it': 'Manca l\'host.'},
    'Host is missing (FTP tab or Settings tab).': {
        'de': 'Der Host fehlt (FTP-Tab oder Einstellungen-Tab).',
        'es': 'Falta el servidor (pestaña FTP o pestaña Ajustes).',
        'fr': "L'hôte est manquant (onglet FTP ou onglet Réglages).",
        'it': "Manca l'host (scheda FTP o scheda Impostazioni)."},
    'Password is missing (it is asked per session unless you chose to store '
    'it).': {
        'de': 'Das Passwort fehlt (es wird pro Sitzung abgefragt, sofern es '
              'nicht gespeichert wurde).',
        'es': 'Falta la contraseña (se pide en cada sesión salvo que haya '
              'elegido guardarla).',
        'fr': 'Le mot de passe est manquant (il est demandé à chaque session '
              "sauf si vous avez choisi de l'enregistrer).",
        'it': 'Manca la password (viene chiesta a ogni sessione, a meno che tu '
              'non abbia scelto di salvarla).'},
    'Password is missing (it is asked per session unless you chose to '
    'store it).': {
        'de': 'Das Passwort fehlt (es wird pro Sitzung abgefragt, sofern es '
              'nicht gespeichert wurde).',
        'es': 'Falta la contraseña (se pide en cada sesión salvo que haya '
              'elegido guardarla).',
        'fr': 'Le mot de passe est manquant (il est demandé à chaque session '
              "sauf si vous avez choisi de l'enregistrer).",
        'it': 'Manca la password (viene chiesta a ogni sessione, a meno che tu '
              'non abbia scelto di salvarla).'},
    'No file could be prepared.': {
        'de': 'Es konnte keine Datei vorbereitet werden.',
        'es': 'No se pudo preparar ningún archivo.',
        'fr': "Aucun fichier n'a pu être préparé.",
        'it': 'Non è stato possibile preparare alcun file.'},
    'Sent': {'de': 'Gesendet', 'es': 'Enviado', 'fr': 'Envoyé',
             'it': 'Inviato'},
    'Connection failed: {e}': {'de': 'Verbindung fehlgeschlagen: {e}',
                               'es': 'Fallo de conexión: {e}',
                               'fr': 'Échec de la connexion : {e}',
                               'it': 'Connessione non riuscita: {e}'},
    'Failed: could not connect to {host}.': {
        'de': 'Fehlgeschlagen: keine Verbindung zu {host}.',
        'es': 'Error: no se pudo conectar a {host}.',
        'fr': 'Échec : impossible de se connecter à {host}.',
        'it': 'Non riuscito: impossibile connettersi a {host}.'},
    'Remote directory: {e}': {'de': 'Zielverzeichnis: {e}',
                              'es': 'Directorio remoto: {e}',
                              'fr': 'Répertoire distant : {e}',
                              'it': 'Directory remota: {e}'},
    'Failed: remote directory "{dir}".': {
        'de': 'Fehlgeschlagen: Zielverzeichnis "{dir}".',
        'es': 'Error: directorio remoto "{dir}".',
        'fr': 'Échec : répertoire distant « {dir} ».',
        'it': 'Non riuscito: directory remota "{dir}".'},
    'Cancelled: {ok}/{total} file(s) sent, {skipped} not started.': {
        'de': 'Abgebrochen: {ok}/{total} Datei(en) gesendet, {skipped} nicht '
              'begonnen.',
        'es': 'Cancelado: {ok}/{total} archivo(s) enviados, {skipped} sin '
              'empezar.',
        'fr': 'Annulé : {ok}/{total} fichier(s) envoyés, {skipped} non '
              'commencés.',
        'it': 'Annullato: {ok}/{total} file inviati, {skipped} non avviati.'},
    'Done: {ok}/{total} file(s) sent.': {
        'de': 'Fertig: {ok}/{total} Datei(en) gesendet.',
        'es': 'Listo: {ok}/{total} archivo(s) enviados.',
        'fr': 'Terminé : {ok}/{total} fichier(s) envoyés.',
        'it': 'Fatto: {ok}/{total} file inviati.'},
}
