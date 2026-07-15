"""Translations, part B: upload run, progress dialog, login, bulk edit and
the structured description editor."""

DATA_B = {
    # ── Upload run / progress ───────────────────────────────────────────────
    'Upload': {'de': 'Upload', 'es': 'Subida', 'fr': 'Import',
               'it': 'Caricamento'},
    'Uploading': {'de': 'Lade hoch', 'es': 'Subiendo', 'fr': 'Import en cours',
                  'it': 'Caricamento in corso'},
    'Uploading…': {'de': 'Lade hoch…', 'es': 'Subiendo…',
                   'fr': 'Import en cours…', 'it': 'Caricamento…'},
    'Uploading {i}/{total}…': {'de': 'Lade hoch {i}/{total}…',
                               'es': 'Subiendo {i}/{total}…',
                               'fr': 'Import {i}/{total}…',
                               'it': 'Caricamento {i}/{total}…'},
    '{verb} {i} of {total} file(s)…': {
        'de': '{verb} {i} von {total} Datei(en)…',
        'es': '{verb} {i} de {total} archivo(s)…',
        'fr': '{verb} {i} sur {total} fichier(s)…',
        'it': '{verb} {i} di {total} file…'},
    'Cancelling: the file currently being uploaded is finished first, then '
    'the run stops.': {
        'de': 'Abbruch: Die gerade hochgeladene Datei wird noch beendet, dann '
              'stoppt der Lauf.',
        'es': 'Cancelando: primero se termina el archivo que se está '
              'subiendo, luego se detiene la ejecución.',
        'fr': "Annulation : le fichier en cours d'import est d'abord terminé, "
              "puis l'exécution s'arrête.",
        'it': 'Annullamento: il file attualmente in caricamento viene prima '
              "completato, poi l'esecuzione si ferma."},
    'Uploaded (SDC failed)': {
        'de': 'Hochgeladen (SDC fehlgeschlagen)',
        'es': 'Subido (fallaron los datos estructurados)',
        'fr': 'Importé (échec des données structurées)',
        'it': 'Caricato (dati strutturati non riusciti)'},
    'Uploaded, but structured data failed: {msg}': {
        'de': 'Hochgeladen, aber strukturierte Daten fehlgeschlagen: {msg}',
        'es': 'Subido, pero fallaron los datos estructurados: {msg}',
        'fr': 'Importé, mais échec des données structurées : {msg}',
        'it': 'Caricato, ma i dati strutturati non sono riusciti: {msg}'},
    'Not logged in.': {'de': 'Nicht angemeldet.', 'es': 'Sin iniciar sesión.',
                       'fr': 'Non connecté.', 'it': 'Non connesso.'},
    'Please log in first.': {'de': 'Bitte zuerst anmelden.',
                             'es': 'Inicie sesión primero.',
                             'fr': "Veuillez d'abord vous connecter.",
                             'it': 'Accedi prima.'},
    'No files': {'de': 'Keine Dateien', 'es': 'Sin archivos',
                 'fr': 'Aucun fichier', 'it': 'Nessun file'},
    'Please add files first.': {'de': 'Bitte zuerst Dateien hinzufügen.',
                                'es': 'Añada archivos primero.',
                                'fr': "Veuillez d'abord ajouter des fichiers.",
                                'it': 'Aggiungi prima dei file.'},
    'Invalid Wikidata IDs': {'de': 'Ungültige Wikidata-IDs',
                             'es': 'Identificadores de Wikidata no válidos',
                             'fr': 'Identifiants Wikidata non valides',
                             'it': 'ID Wikidata non validi'},
    'The following fields must contain Wikidata QIDs (e.g. Q640).\n'
    'Pick an entry from the suggestion list or enter a valid QID:': {
        'de': 'Die folgenden Felder müssen Wikidata-QIDs enthalten (z. B. '
              'Q640).\nEinen Eintrag aus der Vorschlagsliste wählen oder eine '
              'gültige QID eingeben:',
        'es': 'Los siguientes campos deben contener QID de Wikidata (p. ej. '
              'Q640).\nElija una entrada de la lista de sugerencias o '
              'introduzca un QID válido:',
        'fr': 'Les champs suivants doivent contenir des QID Wikidata '
              '(p. ex. Q640).\nChoisissez une entrée dans la liste de '
              'suggestions ou saisissez un QID valide :',
        'it': 'I campi seguenti devono contenere QID di Wikidata (es. '
              "Q640).\nScegli una voce dall'elenco dei suggerimenti o "
              'inserisci un QID valido:'},
    '… (+{n} more)': {'de': '… (+{n} weitere)', 'es': '… (+{n} más)',
                      'fr': '… (+{n} autres)', 'it': '… (+{n} altri)'},

    # ── Login dialog ────────────────────────────────────────────────────────
    'Login – Wikimedia Commons': {
        'de': 'Anmeldung – Wikimedia Commons',
        'es': 'Inicio de sesión – Wikimedia Commons',
        'fr': 'Connexion – Wikimedia Commons',
        'it': 'Accesso – Wikimedia Commons'},
    'Username:': {'de': 'Benutzername:', 'es': 'Usuario:',
                  'fr': "Nom d'utilisateur :", 'it': 'Nome utente:'},
    'Password:': {'de': 'Passwort:', 'es': 'Contraseña:',
                  'fr': 'Mot de passe :', 'it': 'Password:'},
    'Use a <b>BotPassword</b>: create one at '
    '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
    'Special:BotPasswords</a> and log in with the name shown there '
    '(e.g. <i>YourName@Cammello</i>).<br><br>'
    'Required grants:'
    '<ul style="margin-top:2px;">'
    '<li>Edit existing pages</li>'
    '<li>Create, edit, and move pages</li>'
    '<li>Upload new files</li>'
    '<li>Upload, replace, and move files</li>'
    '</ul>': {
        'de': 'Ein <b>BotPassword</b> verwenden: unter '
              '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
              'Special:BotPasswords</a> anlegen und mit dem dort angezeigten '
              'Namen anmelden (z. B. <i>DeinName@Cammello</i>).<br><br>'
              'Benötigte Rechte:'
              '<ul style="margin-top:2px;">'
              '<li>Bestehende Seiten bearbeiten</li>'
              '<li>Seiten anlegen, bearbeiten und verschieben</li>'
              '<li>Neue Dateien hochladen</li>'
              '<li>Dateien hochladen, ersetzen und verschieben</li>'
              '</ul>',
        'es': 'Use una <b>BotPassword</b>: créela en '
              '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
              'Special:BotPasswords</a> e inicie sesión con el nombre que se '
              'muestra allí (p. ej. <i>SuNombre@Cammello</i>).<br><br>'
              'Permisos necesarios:'
              '<ul style="margin-top:2px;">'
              '<li>Editar páginas existentes</li>'
              '<li>Crear, editar y trasladar páginas</li>'
              '<li>Subir archivos nuevos</li>'
              '<li>Subir, reemplazar y trasladar archivos</li>'
              '</ul>',
        'fr': 'Utilisez un <b>BotPassword</b> : créez-en un sur '
              '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
              'Special:BotPasswords</a> et connectez-vous avec le nom qui y '
              'est affiché (p. ex. <i>VotreNom@Cammello</i>).<br><br>'
              'Droits requis :'
              '<ul style="margin-top:2px;">'
              '<li>Modifier des pages existantes</li>'
              '<li>Créer, modifier et renommer des pages</li>'
              '<li>Importer de nouveaux fichiers</li>'
              '<li>Importer, remplacer et renommer des fichiers</li>'
              '</ul>',
        'it': 'Usa una <b>BotPassword</b>: creala su '
              '<a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">'
              'Special:BotPasswords</a> e accedi con il nome lì indicato '
              '(es. <i>TuoNome@Cammello</i>).<br><br>'
              'Permessi necessari:'
              '<ul style="margin-top:2px;">'
              '<li>Modificare pagine esistenti</li>'
              '<li>Creare, modificare e spostare pagine</li>'
              '<li>Caricare nuovi file</li>'
              '<li>Caricare, sostituire e spostare file</li>'
              '</ul>'},

    # ── Bulk edit ───────────────────────────────────────────────────────────
    'Bulk edit selected files': {
        'de': 'Ausgewählte Dateien sammelbearbeiten',
        'es': 'Editar en lote los archivos seleccionados',
        'fr': 'Édition groupée des fichiers sélectionnés',
        'it': 'Modifica in blocco dei file selezionati'},
    'Apply a value to the {n} selected file(s):': {
        'de': 'Einen Wert auf die {n} ausgewählte(n) Datei(en) anwenden:',
        'es': 'Aplicar un valor a los {n} archivo(s) seleccionado(s):',
        'fr': 'Appliquer une valeur aux {n} fichier(s) sélectionné(s) :',
        'it': 'Applicare un valore ai {n} file selezionati:'},
    'Field:': {'de': 'Feld:', 'es': 'Campo:', 'fr': 'Champ :',
               'it': 'Campo:'},
    'Value:': {'de': 'Wert:', 'es': 'Valor:', 'fr': 'Valeur :',
               'it': 'Valore:'},
    'No selection': {'de': 'Keine Auswahl', 'es': 'Sin selección',
                     'fr': 'Aucune sélection', 'it': 'Nessuna selezione'},
    'Please select one or more rows first (Ctrl/Shift-click to select '
    'several).': {
        'de': 'Bitte zuerst eine oder mehrere Zeilen auswählen (Strg/Umschalt '
              '+ Klick für mehrere).',
        'es': 'Seleccione primero una o varias filas (Ctrl/Mayús + clic para '
              'varias).',
        'fr': "Sélectionnez d'abord une ou plusieurs lignes (Ctrl/Maj + clic "
              'pour en choisir plusieurs).',
        'it': 'Seleziona prima una o più righe (Ctrl/Maiusc + clic per '
              'sceglierne diverse).'},
    'Applied "{key}" to {n} file(s).': {
        'de': '"{key}" auf {n} Datei(en) angewendet.',
        'es': 'Se aplicó "{key}" a {n} archivo(s).',
        'fr': '« {key} » appliqué à {n} fichier(s).',
        'it': '"{key}" applicato a {n} file.'},
    # Bulk-edit field labels (translated dynamically via tr(label)).
    'Depicts (P180)': {'de': 'Zeigt (P180)', 'es': 'Representa (P180)',
                       'fr': 'Représente (P180)', 'it': 'Raffigura (P180)'},
    'Categories': {'de': 'Kategorien', 'es': 'Categorías',
                   'fr': 'Catégories', 'it': 'Categorie'},
    'Caption (en)': {'de': 'Bildtext (en)', 'es': 'Leyenda (en)',
                     'fr': 'Légende (en)', 'it': 'Didascalia (en)'},
    'Caption (de)': {'de': 'Bildtext (de)', 'es': 'Leyenda (de)',
                     'fr': 'Légende (de)', 'it': 'Didascalia (de)'},
    'Semicolon-separated QIDs; type a name to search Wikidata.': {
        'de': 'Durch Semikolon getrennte QIDs; einen Namen eingeben, um '
              'Wikidata zu durchsuchen.',
        'es': 'QID separados por punto y coma; escriba un nombre para buscar '
              'en Wikidata.',
        'fr': 'QID séparés par des points-virgules ; saisissez un nom pour '
              'rechercher dans Wikidata.',
        'it': 'QID separati da punto e virgola; digita un nome per cercare in '
              'Wikidata.'},
    'Semicolon-separated, without [[Category:]].': {
        'de': 'Durch Semikolon getrennt, ohne [[Category:]].',
        'es': 'Separadas por punto y coma, sin [[Category:]].',
        'fr': 'Séparées par des points-virgules, sans [[Category:]].',
        'it': 'Separate da punto e virgola, senza [[Category:]].'},
    'Sets the English SDC caption.': {
        'de': 'Setzt den englischen SDC-Bildtext.',
        'es': 'Establece la leyenda SDC en inglés.',
        'fr': 'Définit la légende SDC en anglais.',
        'it': 'Imposta la didascalia SDC in inglese.'},
    'Sets the German SDC caption.': {
        'de': 'Setzt den deutschen SDC-Bildtext.',
        'es': 'Establece la leyenda SDC en alemán.',
        'fr': 'Définit la légende SDC en allemand.',
        'it': 'Imposta la didascalia SDC in tedesco.'},
    'Sets the Date column (e.g. 2026-02-15).': {
        'de': 'Setzt die Spalte Datum (z. B. 2026-02-15).',
        'es': 'Establece la columna Fecha (p. ej. 2026-02-15).',
        'fr': 'Définit la colonne Date (p. ex. 2026-02-15).',
        'it': 'Imposta la colonna Data (es. 2026-02-15).'},

    # ── Structured description editor ───────────────────────────────────────
    'Captions:': {'de': 'Bildtexte:', 'es': 'Leyendas:', 'fr': 'Légendes :',
                  'it': 'Didascalie:'},
    'Add language': {'de': 'Sprache hinzufügen', 'es': 'Añadir idioma',
                     'fr': 'Ajouter une langue', 'it': 'Aggiungi lingua'},
    'Remove this language': {'de': 'Diese Sprache entfernen',
                             'es': 'Quitar este idioma',
                             'fr': 'Supprimer cette langue',
                             'it': 'Rimuovi questa lingua'},
    'Caption, e.g. Harald Krichel at the Berlinale 2026': {
        'de': 'Bildtext, z. B. Harald Krichel auf der Berlinale 2026',
        'es': 'Leyenda, p. ej. Harald Krichel en la Berlinale 2026',
        'fr': 'Légende, p. ex. Harald Krichel à la Berlinale 2026',
        'it': 'Didascalia, es. Harald Krichel alla Berlinale 2026'},
    'Information wikitext for this language (uploaded as {{%s|1=…}})': {
        'de': 'Information-Wikitext für diese Sprache (hochgeladen als '
              '{{%s|1=…}})',
        'es': 'Wikitexto Information para este idioma (se sube como '
              '{{%s|1=…}})',
        'fr': 'Wikitexte Information pour cette langue (importé comme '
              '{{%s|1=…}})',
        'it': 'Wikitesto Information per questa lingua (caricato come '
              '{{%s|1=…}})'},
    'Depicts (P180):': {'de': 'Zeigt (P180):', 'es': 'Representa (P180):',
                        'fr': 'Représente (P180) :',
                        'it': 'Raffigura (P180):'},
    'Created during (P10408):': {
        'de': 'Entstanden während (P10408):',
        'es': 'Creado durante (P10408):',
        'fr': 'Créé lors de (P10408) :',
        'it': 'Creato durante (P10408):'},
    'Categories:': {'de': 'Kategorien:', 'es': 'Categorías:',
                    'fr': 'Catégories :', 'it': 'Categorie:'},
    'Gallery suffix:': {'de': 'Galerie-Suffix:', 'es': 'Sufijo de galería:',
                        'fr': 'Suffixe de galerie :',
                        'it': 'Suffisso galleria:'},
    'Extra wikitext / comments:': {
        'de': 'Zusätzlicher Wikitext / Kommentare:',
        'es': 'Wikitexto adicional / comentarios:',
        'fr': 'Wikitexte supplémentaire / commentaires :',
        'it': 'Wikitesto aggiuntivo / commenti:'},
    '# lines starting with # are comments and are not uploaded': {
        'de': '# Zeilen, die mit # beginnen, sind Kommentare und werden nicht '
              'hochgeladen',
        'es': '# las líneas que empiezan por # son comentarios y no se suben',
        'fr': '# les lignes commençant par # sont des commentaires et ne sont '
              'pas importées',
        'it': '# le righe che iniziano con # sono commenti e non vengono '
              'caricate'},
    'Drag to resize the field': {
        'de': 'Ziehen, um die Feldgröße zu ändern',
        'es': 'Arrastre para cambiar el tamaño del campo',
        'fr': 'Faites glisser pour redimensionner le champ',
        'it': 'Trascina per ridimensionare il campo'},
}
