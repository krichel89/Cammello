"""Translations, part A: shared terms, tabs, MediaWiki tab, upload, login.

Split across three modules purely for file size; i18n.py merges them. The key
is the English source string (see i18n.py). Every {placeholder} of a key must
appear unchanged in each translation - test_i18n.py enforces this.
"""

DATA_A = {
    # ── Shared / generic ────────────────────────────────────────────────────
    'e.g.': {'de': 'z. B.', 'es': 'p. ej.', 'fr': 'p. ex.', 'it': 'es.'},
    'Date': {'de': 'Datum', 'es': 'Fecha', 'fr': 'Date', 'it': 'Data'},
    'Status': {'de': 'Status', 'es': 'Estado', 'fr': 'Statut', 'it': 'Stato'},
    'Error': {'de': 'Fehler', 'es': 'Error', 'fr': 'Erreur', 'it': 'Errore'},
    'Done': {'de': 'Fertig', 'es': 'Listo', 'fr': 'Terminé', 'it': 'Fatto'},
    'Cancel': {'de': 'Abbrechen', 'es': 'Cancelar', 'fr': 'Annuler',
               'it': 'Annulla'},
    'Cancelled': {'de': 'Abgebrochen', 'es': 'Cancelado', 'fr': 'Annulé',
                  'it': 'Annullato'},
    'Cancelling…': {'de': 'Wird abgebrochen…', 'es': 'Cancelando…',
                    'fr': 'Annulation…', 'it': 'Annullamento…'},
    'Preparing…': {'de': 'Vorbereitung…', 'es': 'Preparando…',
                   'fr': 'Préparation…', 'it': 'Preparazione…'},
    'Clear': {'de': 'Leeren', 'es': 'Vaciar', 'fr': 'Effacer',
              'it': 'Svuota'},
    'Copy': {'de': 'Kopieren', 'es': 'Copiar', 'fr': 'Copier',
             'it': 'Copia'},
    'Copying': {'de': 'Kopiere', 'es': 'Copiando', 'fr': 'Copie en cours',
                'it': 'Copia in corso'},
    'Copied': {'de': 'Kopiert', 'es': 'Copiado', 'fr': 'Copié',
               'it': 'Copiato'},
    'Preview': {'de': 'Vorschau', 'es': 'Vista previa', 'fr': 'Aperçu',
                'it': 'Anteprima'},
    'Images': {'de': 'Bilder', 'es': 'Imágenes', 'fr': 'Images',
               'it': 'Immagini'},
    'Text files': {'de': 'Textdateien', 'es': 'Archivos de texto',
                   'fr': 'Fichiers texte', 'it': 'File di testo'},
    'All files': {'de': 'Alle Dateien', 'es': 'Todos los archivos',
                  'fr': 'Tous les fichiers', 'it': 'Tutti i file'},
    'Open folder': {'de': 'Ordner öffnen', 'es': 'Abrir carpeta',
                    'fr': 'Ouvrir le dossier', 'it': 'Apri cartella'},
    'Export folder': {'de': 'Exportordner', 'es': 'Carpeta de exportación',
                      'fr': "Dossier d'export", 'it': 'Cartella di esportazione'},

    # ── Tab names ───────────────────────────────────────────────────────────
    'Culling': {'de': 'Sichtung', 'es': 'Selección', 'fr': 'Tri',
                'it': 'Selezione'},
    'Settings': {'de': 'Einstellungen', 'es': 'Ajustes', 'fr': 'Réglages',
                 'it': 'Impostazioni'},
    'Log': {'de': 'Protokoll', 'es': 'Registro', 'fr': 'Journal',
            'it': 'Registro'},

    # ── Table headers ───────────────────────────────────────────────────────
    'Source file': {'de': 'Quelldatei', 'es': 'Archivo de origen',
                    'fr': 'Fichier source', 'it': 'File di origine'},
    'Target filename (Commons)': {
        'de': 'Zieldateiname (Commons)',
        'es': 'Nombre de destino (Commons)',
        'fr': 'Nom de fichier cible (Commons)',
        'it': 'Nome file di destinazione (Commons)'},
    'Description (file, hidden)': {
        'de': 'Beschreibung (Datei, ausgeblendet)',
        'es': 'Descripción (archivo, oculta)',
        'fr': 'Description (fichier, masquée)',
        'it': 'Descrizione (file, nascosta)'},
    'Wikitext': {'de': 'Wikitext', 'es': 'Wikitexto', 'fr': 'Wikitexte',
                 'it': 'Wikitesto'},
    'Name under which the file is stored on Commons (without "File:"). The '
    'extension is taken from the source file and cannot be changed. Empty = '
    'source filename.': {
        'de': 'Name, unter dem die Datei auf Commons gespeichert wird (ohne '
              '"File:"). Die Endung stammt aus der Quelldatei und ist nicht '
              'änderbar. Leer = Name der Quelldatei.',
        'es': 'Nombre con el que se guarda el archivo en Commons (sin '
              '"File:"). La extensión procede del archivo de origen y no se '
              'puede cambiar. Vacío = nombre del archivo de origen.',
        'fr': 'Nom sous lequel le fichier est enregistré sur Commons (sans '
              '"File:"). L\'extension provient du fichier source et ne peut '
              'pas être modifiée. Vide = nom du fichier source.',
        'it': 'Nome con cui il file viene salvato su Commons (senza "File:"). '
              "L'estensione deriva dal file di origine e non è modificabile. "
              'Vuoto = nome del file di origine.'},
    'Local source file (not modified).': {
        'de': 'Lokale Quelldatei (wird nicht verändert).',
        'es': 'Archivo de origen local (no se modifica).',
        'fr': 'Fichier source local (non modifié).',
        'it': 'File di origine locale (non viene modificato).'},
    'Effective wikitext (upload settings + base description + this file). '
    'Read-only; shown at most {max_lines} lines high - hover a cell for the '
    'full text.': {
        'de': 'Effektiver Wikitext (Upload-Einstellungen + Basisbeschreibung '
              '+ diese Datei). Nur lesbar; höchstens {max_lines} Zeilen hoch '
              '- für den vollen Text die Zelle überfahren.',
        'es': 'Wikitexto efectivo (ajustes de subida + descripción base + '
              'este archivo). Solo lectura; se muestran como máximo '
              '{max_lines} líneas: pase el ratón sobre la celda para ver el '
              'texto completo.',
        'fr': 'Wikitexte effectif (réglages d\'import + description de base + '
              'ce fichier). Lecture seule ; {max_lines} lignes au maximum - '
              'survolez une cellule pour le texte complet.',
        'it': 'Wikitesto effettivo (impostazioni di caricamento + descrizione '
              'di base + questo file). Sola lettura; al massimo {max_lines} '
              'righe: passa sulla cella per il testo completo.'},

    # ── MediaWiki toolbar ───────────────────────────────────────────────────
    'Login': {'de': 'Anmelden', 'es': 'Iniciar sesión', 'fr': 'Connexion',
              'it': 'Accedi'},
    'Test connection': {'de': 'Verbindung testen', 'es': 'Probar conexión',
                        'fr': 'Tester la connexion',
                        'it': 'Prova connessione'},
    'Not logged in': {'de': 'Nicht angemeldet', 'es': 'Sin iniciar sesión',
                      'fr': 'Non connecté', 'it': 'Non connesso'},
    'Add files': {'de': 'Dateien hinzufügen', 'es': 'Añadir archivos',
                  'fr': 'Ajouter des fichiers', 'it': 'Aggiungi file'},
    'Remove selected': {'de': 'Auswahl entfernen', 'es': 'Quitar selección',
                        'fr': 'Retirer la sélection',
                        'it': 'Rimuovi selezione'},
    'Bulk edit selected': {'de': 'Auswahl sammelbearbeiten',
                           'es': 'Editar selección en lote',
                           'fr': 'Édition groupée de la sélection',
                           'it': 'Modifica selezione in blocco'},
    'Clear all': {'de': 'Alles leeren', 'es': 'Vaciar todo',
                  'fr': 'Tout effacer', 'it': 'Svuota tutto'},
    'Upload all': {'de': 'Alle hochladen', 'es': 'Subir todo',
                   'fr': 'Tout importer', 'it': 'Carica tutto'},
    'Upload all ({n})': {'de': 'Alle hochladen ({n})',
                         'es': 'Subir todo ({n})',
                         'fr': 'Tout importer ({n})',
                         'it': 'Carica tutto ({n})'},
    'Upload selected ({n})': {'de': 'Auswahl hochladen ({n})',
                              'es': 'Subir selección ({n})',
                              'fr': 'Importer la sélection ({n})',
                              'it': 'Carica selezione ({n})'},
    'Uploads the selected rows. Deselect everything to upload all files.': {
        'de': 'Lädt die ausgewählten Zeilen hoch. Auswahl aufheben, um alle '
              'Dateien hochzuladen.',
        'es': 'Sube las filas seleccionadas. Deseleccione todo para subir '
              'todos los archivos.',
        'fr': 'Importe les lignes sélectionnées. Désélectionnez tout pour '
              'importer tous les fichiers.',
        'it': 'Carica le righe selezionate. Deseleziona tutto per caricare '
              'tutti i file.'},
    'Nothing is selected, so all files are uploaded. Select rows to upload '
    'only those.': {
        'de': 'Nichts ausgewählt, daher werden alle Dateien hochgeladen. '
              'Zeilen auswählen, um nur diese hochzuladen.',
        'es': 'No hay nada seleccionado, así que se suben todos los archivos. '
              'Seleccione filas para subir solo esas.',
        'fr': 'Rien n\'est sélectionné : tous les fichiers seront importés. '
              'Sélectionnez des lignes pour n\'importer que celles-ci.',
        'it': 'Non è selezionato nulla, quindi vengono caricati tutti i file. '
              'Seleziona delle righe per caricare solo quelle.'},
    'Ignore warnings (overwrite)': {
        'de': 'Warnungen ignorieren (überschreiben)',
        'es': 'Ignorar advertencias (sobrescribir)',
        'fr': 'Ignorer les avertissements (écraser)',
        'it': 'Ignora gli avvisi (sovrascrivi)'},

    # ── Upload settings form ────────────────────────────────────────────────
    'Upload settings': {'de': 'Upload-Einstellungen',
                        'es': 'Ajustes de subida',
                        'fr': "Réglages d'import",
                        'it': 'Impostazioni di caricamento'},
    'MediaWiki upload': {'de': 'MediaWiki-Upload',
                         'es': 'Subida a MediaWiki',
                         'fr': 'Import MediaWiki',
                         'it': 'Caricamento su MediaWiki'},
    'Author:': {'de': 'Autor:', 'es': 'Autor:', 'fr': 'Auteur :',
                'it': 'Autore:'},
    'Creator (P170):': {'de': 'Urheber (P170):', 'es': 'Creador (P170):',
                        'fr': 'Créateur (P170) :', 'it': 'Autore (P170):'},
    'Source:': {'de': 'Quelle:', 'es': 'Fuente:', 'fr': 'Source :',
                'it': 'Fonte:'},
    'Permission:': {'de': 'Genehmigung:', 'es': 'Permiso:',
                    'fr': 'Autorisation :', 'it': 'Autorizzazione:'},
    'License:': {'de': 'Lizenz:', 'es': 'Licencia:', 'fr': 'Licence :',
                 'it': 'Licenza:'},
    'License (P275):': {'de': 'Lizenz (P275):', 'es': 'Licencia (P275):',
                        'fr': 'Licence (P275) :', 'it': 'Licenza (P275):'},
    'Copyright (P6216):': {'de': 'Urheberrecht (P6216):',
                           'es': 'Derechos de autor (P6216):',
                           'fr': "Droit d'auteur (P6216) :",
                           'it': "Diritto d'autore (P6216):"},
    'Other templates:': {'de': 'Weitere Vorlagen:',
                         'es': 'Otras plantillas:',
                         'fr': 'Autres modèles :', 'it': 'Altri template:'},
    'Other fields:': {'de': 'Weitere Felder:', 'es': 'Otros campos:',
                      'fr': 'Autres champs :', 'it': 'Altri campi:'},
    'Gallery prefix:': {'de': 'Galerie-Präfix:', 'es': 'Prefijo de galería:',
                        'fr': 'Préfixe de galerie :',
                        'it': 'Prefisso galleria:'},
    'HTTP timeout (s):': {'de': 'HTTP-Zeitlimit (s):',
                          'es': 'Tiempo de espera HTTP (s):',
                          'fr': 'Délai HTTP (s) :',
                          'it': 'Timeout HTTP (s):'},
    'e.g. (leave empty unless needed)': {
        'de': 'z. B. (leer lassen, falls nicht nötig)',
        'es': 'p. ej. (dejar vacío si no hace falta)',
        'fr': 'p. ex. (laisser vide sauf si nécessaire)',
        'it': 'es. (lasciare vuoto se non serve)'},

    # ── Expert mode / base description ──────────────────────────────────────
    'Expert mode (raw description_all text)': {
        'de': 'Expertenmodus (roher description_all-Text)',
        'es': 'Modo experto (texto description_all sin procesar)',
        'fr': 'Mode expert (texte description_all brut)',
        'it': 'Modalità esperto (testo description_all grezzo)'},
    'Edit the raw description_all text directly instead of using the '
    'structured single-line fields.': {
        'de': 'Den rohen description_all-Text direkt bearbeiten statt der '
              'strukturierten einzeiligen Felder.',
        'es': 'Editar directamente el texto description_all en lugar de usar '
              'los campos estructurados de una línea.',
        'fr': 'Modifier directement le texte description_all brut au lieu des '
              'champs structurés sur une ligne.',
        'it': 'Modificare direttamente il testo description_all grezzo invece '
              'dei campi strutturati a riga singola.'},
    'Base description (for all files)': {
        'de': 'Basisbeschreibung (für alle Dateien)',
        'es': 'Descripción base (para todos los archivos)',
        'fr': 'Description de base (pour tous les fichiers)',
        'it': 'Descrizione di base (per tutti i file)'},
    'Shared lines for every file, e.g.': {
        'de': 'Gemeinsame Zeilen für jede Datei, z. B.',
        'es': 'Líneas comunes para cada archivo, p. ej.',
        'fr': 'Lignes communes à chaque fichier, p. ex.',
        'it': 'Righe comuni a ogni file, es.'},
    'Selected file – description': {
        'de': 'Ausgewählte Datei – Beschreibung',
        'es': 'Archivo seleccionado – descripción',
        'fr': 'Fichier sélectionné – description',
        'it': 'File selezionato – descrizione'},
    'Select a single file to edit its description.': {
        'de': 'Eine einzelne Datei auswählen, um ihre Beschreibung zu '
              'bearbeiten.',
        'es': 'Seleccione un único archivo para editar su descripción.',
        'fr': 'Sélectionnez un seul fichier pour modifier sa description.',
        'it': 'Seleziona un singolo file per modificarne la descrizione.'},

    # ── Settings save/load ──────────────────────────────────────────────────
    'Save settings': {'de': 'Einstellungen speichern',
                      'es': 'Guardar ajustes',
                      'fr': 'Enregistrer les réglages',
                      'it': 'Salva impostazioni'},
    'Save the upload settings and the base description so they are restored '
    'next time.': {
        'de': 'Upload-Einstellungen und Basisbeschreibung speichern, damit '
              'sie beim nächsten Mal wiederhergestellt werden.',
        'es': 'Guarda los ajustes de subida y la descripción base para '
              'restaurarlos la próxima vez.',
        'fr': "Enregistre les réglages d'import et la description de base "
              'pour les restaurer la prochaine fois.',
        'it': 'Salva le impostazioni di caricamento e la descrizione di base '
              'per ripristinarle la prossima volta.'},
    'Save to file…': {'de': 'In Datei speichern…',
                      'es': 'Guardar en archivo…',
                      'fr': 'Enregistrer dans un fichier…',
                      'it': 'Salva su file…'},
    'Write settings + base description to a text file.': {
        'de': 'Einstellungen + Basisbeschreibung in eine Textdatei schreiben.',
        'es': 'Escribe los ajustes y la descripción base en un archivo de '
              'texto.',
        'fr': 'Écrit les réglages et la description de base dans un fichier '
              'texte.',
        'it': 'Scrive impostazioni e descrizione di base in un file di testo.'},
    'Load from file…': {'de': 'Aus Datei laden…',
                        'es': 'Cargar desde archivo…',
                        'fr': "Charger depuis un fichier…",
                        'it': 'Carica da file…'},
    'Read settings back from a text file.': {
        'de': 'Einstellungen aus einer Textdatei zurücklesen.',
        'es': 'Vuelve a leer los ajustes desde un archivo de texto.',
        'fr': 'Relit les réglages depuis un fichier texte.',
        'it': 'Rilegge le impostazioni da un file di testo.'},
    'incl. selected file': {'de': 'inkl. ausgewählter Datei',
                            'es': 'incl. archivo seleccionado',
                            'fr': 'y c. fichier sélectionné',
                            'it': 'incl. file selezionato'},
    "Also write the selected file's description into the settings file.": {
        'de': 'Auch die Beschreibung der ausgewählten Datei in die '
              'Einstellungsdatei schreiben.',
        'es': 'Escribir también la descripción del archivo seleccionado en el '
              'archivo de ajustes.',
        'fr': 'Écrire aussi la description du fichier sélectionné dans le '
              'fichier de réglages.',
        'it': 'Scrivere anche la descrizione del file selezionato nel file '
              'delle impostazioni.'},
    'Save settings to file': {'de': 'Einstellungen in Datei speichern',
                              'es': 'Guardar ajustes en un archivo',
                              'fr': 'Enregistrer les réglages dans un fichier',
                              'it': 'Salva le impostazioni su file'},
    'Load settings from file': {'de': 'Einstellungen aus Datei laden',
                                'es': 'Cargar ajustes desde un archivo',
                                'fr': 'Charger les réglages depuis un fichier',
                                'it': 'Carica le impostazioni da file'},
    'Save error': {'de': 'Speicherfehler', 'es': 'Error al guardar',
                   'fr': "Erreur d'enregistrement", 'it': 'Errore di salvataggio'},
    'Load error': {'de': 'Ladefehler', 'es': 'Error al cargar',
                   'fr': 'Erreur de chargement', 'it': 'Errore di caricamento'},
    'Could not write the file:': {
        'de': 'Die Datei konnte nicht geschrieben werden:',
        'es': 'No se pudo escribir el archivo:',
        'fr': "Impossible d'écrire le fichier :",
        'it': 'Impossibile scrivere il file:'},
    'Could not read the file:': {
        'de': 'Die Datei konnte nicht gelesen werden:',
        'es': 'No se pudo leer el archivo:',
        'fr': 'Impossible de lire le fichier :',
        'it': 'Impossibile leggere il file:'},
    'Settings saved.': {'de': 'Einstellungen gespeichert.',
                        'es': 'Ajustes guardados.',
                        'fr': 'Réglages enregistrés.',
                        'it': 'Impostazioni salvate.'},
    'Settings saved to {path}': {
        'de': 'Einstellungen gespeichert in {path}',
        'es': 'Ajustes guardados en {path}',
        'fr': 'Réglages enregistrés dans {path}',
        'it': 'Impostazioni salvate in {path}'},
    'Settings loaded from {path}.': {
        'de': 'Einstellungen geladen aus {path}.',
        'es': 'Ajustes cargados desde {path}.',
        'fr': 'Réglages chargés depuis {path}.',
        'it': 'Impostazioni caricate da {path}.'},
    'Saved. No single file selected, so no file description was included.': {
        'de': 'Gespeichert. Keine einzelne Datei ausgewählt, daher wurde '
              'keine Dateibeschreibung aufgenommen.',
        'es': 'Guardado. No hay un único archivo seleccionado, así que no se '
              'incluyó ninguna descripción de archivo.',
        'fr': "Enregistré. Aucun fichier unique sélectionné : aucune "
              'description de fichier n\'a été incluse.',
        'it': 'Salvato. Nessun singolo file selezionato, quindi non è stata '
              'inclusa alcuna descrizione di file.'},
    '(file description in the file was ignored: no single file selected)': {
        'de': '(Dateibeschreibung in der Datei wurde ignoriert: keine '
              'einzelne Datei ausgewählt)',
        'es': '(se ignoró la descripción de archivo del archivo: no hay un '
              'único archivo seleccionado)',
        'fr': '(la description de fichier contenue dans le fichier a été '
              'ignorée : aucun fichier unique sélectionné)',
        'it': '(la descrizione di file contenuta nel file è stata ignorata: '
              'nessun singolo file selezionato)'},

    # ── Appearance / language ───────────────────────────────────────────────
    'Appearance': {'de': 'Erscheinungsbild', 'es': 'Apariencia',
                   'fr': 'Apparence', 'it': 'Aspetto'},
    'Color scheme:': {'de': 'Farbschema:', 'es': 'Esquema de color:',
                      'fr': 'Thème de couleurs :', 'it': 'Schema colori:'},
    'system': {'de': 'System', 'es': 'sistema', 'fr': 'système',
               'it': 'sistema'},
    'light': {'de': 'hell', 'es': 'claro', 'fr': 'clair', 'it': 'chiaro'},
    'dark': {'de': 'dunkel', 'es': 'oscuro', 'fr': 'sombre', 'it': 'scuro'},
    'Language:': {'de': 'Sprache:', 'es': 'Idioma:', 'fr': 'Langue :',
                  'it': 'Lingua:'},
    'The language change takes effect after a restart.': {
        'de': 'Die Sprachumstellung wird nach einem Neustart wirksam.',
        'es': 'El cambio de idioma surte efecto tras reiniciar.',
        'fr': 'Le changement de langue prend effet après un redémarrage.',
        'it': 'Il cambio di lingua ha effetto dopo un riavvio.'},
    'Settings are saved when the window is closed.': {
        'de': 'Die Einstellungen werden beim Schließen des Fensters '
              'gespeichert.',
        'es': 'Los ajustes se guardan al cerrar la ventana.',
        'fr': 'Les réglages sont enregistrés à la fermeture de la fenêtre.',
        'it': 'Le impostazioni vengono salvate alla chiusura della finestra.'},

    # ── Log tab ─────────────────────────────────────────────────────────────
    'Verbose logging': {'de': 'Ausführliches Protokoll',
                        'es': 'Registro detallado',
                        'fr': 'Journal détaillé',
                        'it': 'Registro dettagliato'},
    'Open log file': {'de': 'Protokolldatei öffnen',
                      'es': 'Abrir archivo de registro',
                      'fr': 'Ouvrir le fichier journal',
                      'it': 'Apri il file di registro'},
    'Log file: {path}': {'de': 'Protokolldatei: {path}',
                         'es': 'Archivo de registro: {path}',
                         'fr': 'Fichier journal : {path}',
                         'it': 'File di registro: {path}'},
    'Log copied to clipboard.': {
        'de': 'Protokoll in die Zwischenablage kopiert.',
        'es': 'Registro copiado al portapapeles.',
        'fr': 'Journal copié dans le presse-papiers.',
        'it': 'Registro copiato negli appunti.'},

    # ── Status bar / files ──────────────────────────────────────────────────
    'Ready. Please log in first.': {
        'de': 'Bereit. Bitte zuerst anmelden.',
        'es': 'Listo. Inicie sesión primero.',
        'fr': "Prêt. Veuillez d'abord vous connecter.",
        'it': 'Pronto. Accedi prima.'},
    'Testing connection…': {'de': 'Verbindung wird getestet…',
                            'es': 'Probando la conexión…',
                            'fr': 'Test de la connexion…',
                            'it': 'Verifica della connessione…'},
    'Logged in as {username}': {'de': 'Angemeldet als {username}',
                                'es': 'Sesión iniciada como {username}',
                                'fr': 'Connecté en tant que {username}',
                                'it': 'Connesso come {username}'},
    'Connection OK: {info}': {'de': 'Verbindung OK: {info}',
                              'es': 'Conexión correcta: {info}',
                              'fr': 'Connexion OK : {info}',
                              'it': 'Connessione OK: {info}'},
    'Select image files': {'de': 'Bilddateien auswählen',
                           'es': 'Seleccionar archivos de imagen',
                           'fr': 'Sélectionner des fichiers image',
                           'it': 'Seleziona file immagine'},
    '{n} added': {'de': '{n} hinzugefügt', 'es': '{n} añadidos',
                  'fr': '{n} ajoutés', 'it': '{n} aggiunti'},
    '{n} duplicate(s) skipped': {
        'de': '{n} Duplikat(e) übersprungen',
        'es': '{n} duplicado(s) omitidos',
        'fr': '{n} doublon(s) ignoré(s)',
        'it': '{n} duplicato/i saltato/i'},
    '{n} skipped (see log)': {
        'de': '{n} übersprungen (siehe Protokoll)',
        'es': '{n} omitidos (véase el registro)',
        'fr': '{n} ignorés (voir le journal)',
        'it': '{n} saltati (vedi registro)'},
}
