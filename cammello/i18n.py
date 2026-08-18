"""Lightweight UI translation (0.10.0).

Design decisions (agreed 2026-07-14):
  * Five UI languages: en, de, es, fr, it. English is the SOURCE language;
    the translation key IS the English string, so an untranslated string
    falls back to English automatically and the code stays readable.
  * tr() returns the template UNFORMATTED - call sites with runtime values
    use tr('... {n} ...').format(n=...). Translations must keep every
    {placeholder} of their key (enforced by test_i18n.py).
  * The language is chosen in the Settings tab, persisted as 'ui_language'
    in QSettings, and applied at STARTUP in main() before the window is
    built (a change takes effect after a restart - live retranslation of
    every widget was deliberately not built, it would touch the MediaWiki
    core for cosmetics).
  * First start: the system locale picks the language if it is one of the
    five, otherwise English.
  * Log messages stay English on purpose (diagnostic channel).

No Qt imports in here: the module is usable from plain logic tests.
"""

# (code, native name) - the order of the Settings dropdown.
UI_LANGUAGES = [
    ('en', 'English'),
    ('de', 'Deutsch'),
    ('es', 'Español'),
    ('fr', 'Français'),
    ('it', 'Italiano'),
]

_current = ['en']


def set_language(code):
    """Select the UI language ('en'|'de'|'es'|'fr'|'it'); unknown codes fall
    back to English."""
    _current[0] = code if code in dict(UI_LANGUAGES) else 'en'


def current_language():
    return _current[0]


def default_language_from_locale(locale_name):
    """Map a locale name like 'de_DE' to one of the five UI languages
    ('en' if none matches). The caller passes QLocale().name()."""
    prefix = (locale_name or '').split('_')[0].lower()
    return prefix if prefix in dict(UI_LANGUAGES) else 'en'


def tr(text):
    """Translate an English UI string into the current language.

    Unknown keys and missing per-language entries return the English text
    unchanged (fallback), so a forgotten entry can never crash the app.
    """
    lang = _current[0]
    if lang == 'en':
        return text
    entry = TRANSLATIONS.get(text)
    if not entry:
        return text
    return entry.get(lang, text)


def missing_keys():
    """[(key, lang)] for every key lacking a translation - used by tests."""
    out = []
    for key, entry in TRANSLATIONS.items():
        for lang, _name in UI_LANGUAGES:
            if lang != 'en' and lang not in entry:
                out.append((key, lang))
    return out


# key (English) -> {'de': ..., 'es': ..., 'fr': ..., 'it': ...}
# Grouped by UI area. Every {placeholder} of a key MUST survive
# translation (enforced by test_i18n.py).
TRANSLATIONS = {
    'Rename file': {
        'de': 'Datei umbenennen',
        'es': 'Renombrar archivo',
        'fr': 'Renommer le fichier',
        'it': 'Rinomina file',
    },
    'New name (without extension):': {
        'de': 'Neuer Name (ohne Endung):',
        'es': 'Nombre nuevo (sin extensión):',
        'fr': 'Nouveau nom (sans extension) :',
        'it': 'Nuovo nome (senza estensione):',
    },
    # 0.14.2: resuming an interrupted upload batch.
    'Interrupted upload': {
        'de': 'Unterbrochener Upload',
        'es': 'Subida interrumpida',
        'fr': 'Téléversement interrompu',
        'it': 'Caricamento interrotto',
    },
    '&Resume interrupted upload\u2026': {
        'de': 'Unterbrochenen Upload &fortsetzen\u2026',
        'es': '&Reanudar la subida interrumpida\u2026',
        'fr': '&Reprendre le téléversement interrompu\u2026',
        'it': '&Riprendi il caricamento interrotto\u2026',
    },
    'Continue a batch that was cancelled or interrupted by a crash.': {
        'de': 'Einen abgebrochenen oder durch einen Absturz unterbrochenen '
              'Stapel fortsetzen.',
        'es': 'Continuar un lote cancelado o interrumpido por un fallo.',
        'fr': 'Poursuivre un lot annulé ou interrompu par un plantage.',
        'it': 'Continuare un lotto annullato o interrotto da un arresto '
              'anomalo.',
    },
    'An upload from {when} was interrupted.': {
        'de': 'Ein Upload vom {when} wurde unterbrochen.',
        'es': 'Una subida del {when} quedó interrumpida.',
        'fr': 'Un téléversement du {when} a été interrompu.',
        'it': 'Un caricamento del {when} è stato interrotto.',
    },
    '{done} of {total} file(s) were uploaded; {open} still to go.': {
        'de': '{done} von {total} Datei(en) sind hochgeladen; {open} fehlen '
              'noch.',
        'es': 'Se subieron {done} de {total} archivo(s); faltan {open}.',
        'fr': '{done} fichier(s) sur {total} ont été téléversés ; il en '
              'reste {open}.',
        'it': 'Caricati {done} di {total} file; ne restano {open}.',
    },
    '{n} file(s) failed and will not be retried.': {
        'de': '{n} Datei(en) sind fehlgeschlagen und werden nicht erneut '
              'versucht.',
        'es': '{n} archivo(s) fallaron y no se reintentarán.',
        'fr': '{n} fichier(s) ont échoué et ne seront pas réessayés.',
        'it': '{n} file non sono riusciti e non verranno ritentati.',
    },
    'Resume it now?': {
        'de': 'Jetzt fortsetzen?',
        'es': '¿Reanudarla ahora?',
        'fr': 'Le reprendre maintenant ?',
        'it': 'Riprenderlo ora?',
    },
    'Resume': {
        'de': 'Fortsetzen',
        'es': 'Reanudar',
        'fr': 'Reprendre',
        'it': 'Riprendi',
    },
    'Later': {
        'de': 'Später',
        'es': 'Más tarde',
        'fr': 'Plus tard',
        'it': 'Più tardi',
    },
    'Discard': {
        'de': 'Verwerfen',
        'es': 'Descartar',
        'fr': 'Abandonner',
        'it': 'Scarta',
    },
    'The interrupted upload is kept - resume it from the Upload menu.': {
        'de': 'Der unterbrochene Upload bleibt erhalten \u2014 fortsetzen '
              'lässt er sich über das Upload-Menü.',
        'es': 'La subida interrumpida se conserva: puedes reanudarla desde '
              'el menú Subir.',
        'fr': 'Le téléversement interrompu est conservé \u2014 reprenez-le '
              'depuis le menu Téléversement.',
        'it': 'Il caricamento interrotto viene conservato: riprendilo dal '
              'menu Caricamento.',
    },
    'There is no interrupted upload to resume.': {
        'de': 'Es gibt keinen unterbrochenen Upload zum Fortsetzen.',
        'es': 'No hay ninguna subida interrumpida que reanudar.',
        'fr': 'Il n\u2019y a aucun téléversement interrompu à reprendre.',
        'it': 'Non c\u2019è alcun caricamento interrotto da riprendere.',
    },
    'Every file of that batch is already on Commons.': {
        'de': 'Alle Dateien dieses Stapels sind bereits auf Commons.',
        'es': 'Todos los archivos de ese lote ya están en Commons.',
        'fr': 'Tous les fichiers de ce lot sont déjà sur Commons.',
        'it': 'Tutti i file di quel lotto sono già su Commons.',
    },
    'That upload was started against a different wiki ({url}). Resume it '
    'here anyway?': {
        'de': 'Dieser Upload wurde gegen ein anderes Wiki gestartet '
              '({url}). Trotzdem hier fortsetzen?',
        'es': 'Esa subida se inició contra otro wiki ({url}). ¿Reanudarla '
              'aquí de todos modos?',
        'fr': 'Ce téléversement a été lancé sur un autre wiki ({url}). Le '
              'reprendre ici malgré tout ?',
        'it': 'Quel caricamento è stato avviato su un altro wiki ({url}). '
              'Riprenderlo comunque qui?',
    },
    '{n} file(s) are no longer where they were. They will be skipped:': {
        'de': '{n} Datei(en) liegen nicht mehr an ihrem alten Ort. Sie '
              'werden übersprungen:',
        'es': '{n} archivo(s) ya no están donde estaban. Se omitirán:',
        'fr': '{n} fichier(s) ne sont plus à leur emplacement. Ils seront '
              'ignorés :',
        'it': '{n} file non sono più dove si trovavano. Verranno saltati:',
    },
    'Continue?': {
        'de': 'Fortfahren?',
        'es': '¿Continuar?',
        'fr': 'Continuer ?',
        'it': 'Continuare?',
    },
    # 0.14.2: the edit panel's drag handle and its crop legend. The four
    # one-word keys are legend cells, deliberately lower case and short -
    # they sit in a narrow panel next to a key symbol.
    'Drag to move this panel': {
        'de': 'Zum Verschieben ziehen',
        'es': 'Arrastra para mover este panel',
        'fr': 'Faites glisser pour déplacer ce panneau',
        'it': 'Trascina per spostare questo pannello',
    },
    'Crop keys': {
        'de': 'Zuschnitt-Tasten',
        'es': 'Teclas de recorte',
        'fr': 'Touches de recadrage',
        'it': 'Tasti di ritaglio',
    },
    'Same number again = rotate': {
        'de': 'Gleiche Ziffer nochmal = drehen',
        'es': 'Mismo número otra vez = girar',
        'fr': 'Même chiffre à nouveau = pivoter',
        'it': 'Stesso numero di nuovo = ruota',
    },
    'free': {
        'de': 'frei',
        'es': 'libre',
        'fr': 'libre',
        'it': 'libero',
    },
    'apply': {
        'de': 'anwenden',
        'es': 'aplicar',
        'fr': 'appliquer',
        'it': 'applica',
    },
    'cancel': {
        'de': 'abbrechen',
        'es': 'cancelar',
        'fr': 'annuler',
        'it': 'annulla',
    },
    'remove': {
        'de': 'entfernen',
        'es': 'quitar',
        'fr': 'supprimer',
        'it': 'rimuovi',
    },
    'Starting\u2026': {
        'de': 'Startet\u2026',
        'es': 'Iniciando\u2026',
        'fr': 'Démarrage\u2026',
        'it': 'Avvio\u2026',
    },
    'That name is reserved on Windows or ends with a dot or space.': {
        'de': 'Dieser Name ist unter Windows reserviert oder endet mit '
              'Punkt oder Leerzeichen.',
        'es': 'Ese nombre está reservado en Windows o termina en punto '
              'o espacio.',
        'fr': 'Ce nom est réservé sous Windows ou se termine par un point '
              'ou une espace.',
        'it': 'Quel nome è riservato in Windows o termina con un punto '
              'o uno spazio.',
    },
    'That name contains characters a file name cannot hold.': {
        'de': 'Dieser Name enthält Zeichen, die ein Dateiname nicht tragen kann.',
        'es': 'Ese nombre contiene caracteres que un nombre de archivo no admite.',
        'fr': "Ce nom contient des caractères qu'un nom de fichier ne peut pas porter.",
        'it': 'Quel nome contiene caratteri che un nome di file non può avere.',
    },
    'Click a neutral grey or white spot — W ends it': {
        'de': 'Auf eine neutralgraue oder weiße Stelle klicken — W beendet',
        'es': 'Haz clic en un punto gris neutro o blanco: W termina',
        'fr': 'Cliquez sur un gris neutre ou un blanc — W termine',
        'it': 'Clicca su un punto grigio neutro o bianco — W termina',
    },
    'That spot is too dark to balance on.': {
        'de': 'Diese Stelle ist zu dunkel für einen Weißabgleich.',
        'es': 'Ese punto es demasiado oscuro para equilibrar.',
        'fr': 'Cet endroit est trop sombre pour la balance des blancs.',
        'it': 'Quel punto è troppo scuro per il bilanciamento.',
    },
    '[crop] 1 free · 2 3:2 · 3 4:3 · 4 1:1 · 5 16:9 · 6 5:4  (same key again = rotate)  ·  Enter apply · Esc cancel · ⇧C remove': {
        'de': '[Zuschnitt] 1 frei · 2 3:2 · 3 4:3 · 4 1:1 · 5 16:9 · 6 5:4  (gleiche Taste nochmal = drehen)  ·  Enter übernehmen · Esc abbrechen · ⇧C entfernen',
        'es': '[recorte] 1 libre · 2 3:2 · 3 4:3 · 4 1:1 · 5 16:9 · 6 5:4  (misma tecla otra vez = girar)  ·  Intro aplicar · Esc cancelar · ⇧C quitar',
        'fr': '[recadrage] 1 libre · 2 3:2 · 3 4:3 · 4 1:1 · 5 16:9 · 6 5:4  (même touche = pivoter)  ·  Entrée appliquer · Échap annuler · ⇧C retirer',
        'it': '[ritaglio] 1 libero · 2 3:2 · 3 4:3 · 4 1:1 · 5 16:9 · 6 5:4  (stesso tasto = ruota)  ·  Invio applica · Esc annulla · ⇧C rimuovi',
    },
    'A file called "{name}" already exists.': {
        'de': 'Eine Datei namens „{name}" gibt es schon.',
        'es': 'Ya existe un archivo llamado «{name}».',
        'fr': 'Un fichier nommé « {name} » existe déjà.',
        'it': 'Esiste già un file chiamato «{name}».',
    },
    'Renaming failed: {error}': {
        'de': 'Umbenennen fehlgeschlagen: {error}',
        'es': 'Error al renombrar: {error}',
        'fr': 'Échec du renommage : {error}',
        'it': 'Rinomina fallita: {error}',
    },
    'Edit': {
        'de': 'Bearbeiten',
        'es': 'Editar',
        'fr': 'Retouche',
        'it': 'Modifica',
    },
    'Crop (C)': {
        'de': 'Zuschnitt (C)',
        'es': 'Recorte (C)',
        'fr': 'Recadrage (C)',
        'it': 'Ritaglio (C)',
    },
    'Draw a crop on this image. Enter applies it, Esc cancels.': {
        'de': 'Einen Zuschnitt auf diesem Bild aufziehen. Enter übernimmt, Esc bricht ab.',
        'es': 'Dibuja un recorte en esta imagen. Intro aplica, Esc cancela.',
        'fr': 'Tracez un recadrage sur cette image. Entrée applique, Échap annule.',
        'it': 'Traccia un ritaglio su questa immagine. Invio applica, Esc annulla.',
    },
    'White balance (W)': {
        'de': 'Weißabgleich (W)',
        'es': 'Balance de blancos (W)',
        'fr': 'Balance des blancs (W)',
        'it': 'Bilanciamento del bianco (W)',
    },
    'Pick a spot that should be neutral grey or white.\nClick the picture with the pipette; press W again to stop.': {
        'de': 'Eine Stelle wählen, die neutralgrau oder weiß sein soll.\nMit der Pipette ins Bild klicken; W beendet den Modus.',
        'es': 'Elige un punto que deba ser gris neutro o blanco.\nHaz clic en la imagen con el cuentagotas; pulsa W para terminar.',
        'fr': "Choisissez un endroit qui devrait être gris neutre ou blanc.\nCliquez dans l'image avec la pipette ; W met fin au mode.",
        'it': "Scegli un punto che dovrebbe essere grigio neutro o bianco.\nClicca sull'immagine con il contagocce; premi W per terminare.",
    },
    'Reset all': {
        'de': 'Alles zurücksetzen',
        'es': 'Restablecer todo',
        'fr': 'Tout réinitialiser',
        'it': 'Reimposta tutto',
    },
    'Remove crop, white balance and exposure from this image.': {
        'de': 'Zuschnitt, Weißabgleich und Belichtung von diesem Bild entfernen.',
        'es': 'Quitar recorte, balance de blancos y exposición de esta imagen.',
        'fr': 'Retirer recadrage, balance des blancs et exposition de cette image.',
        'it': 'Rimuovi ritaglio, bilanciamento del bianco ed esposizione da questa immagine.',
    },
    'Exposure in sixths of a stop': {
        'de': 'Belichtung in Sechstel-Blendenstufen',
        'es': 'Exposición en sextos de paso',
        'fr': 'Exposition par sixièmes de diaphragme',
        'it': 'Esposizione in sesti di stop',
    },
    'Cammello &manual (on Commons)': {
        'de': 'Cammello-&Handbuch (auf Commons)',
        'es': '&Manual de Cammello (en Commons)',
        'fr': '&Manuel de Cammello (sur Commons)',
        'it': '&Manuale di Cammello (su Commons)',
    },
    '[crop] 1-6 ratio (again = rotate) · Enter apply · Esc cancel · ⇧C remove': {
        'de': '[Zuschnitt] 1–6 Verhältnis (nochmal = drehen) · Enter übernehmen · Esc abbrechen · ⇧C entfernen',
        'es': '[recorte] 1–6 proporción (otra vez = girar) · Intro aplicar · Esc cancelar · ⇧C quitar',
        'fr': '[recadrage] 1–6 ratio (à nouveau = pivoter) · Entrée appliquer · Échap annuler · ⇧C retirer',
        'it': '[ritaglio] 1–6 proporzione (di nuovo = ruota) · Invio applica · Esc annulla · ⇧C rimuovi',
    },
    'Crop keys:\n  1  free    2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\nPress the same number again to switch that ratio between landscape\nand portrait (2:3, 3:4, 9:16, 4:5). Drag the box or its handles to\nplace it. Enter applies, Esc cancels, Shift+C removes the crop.': {
        'de': 'Zuschnitt-Tasten:\n  1  frei    2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\nDieselbe Zahl noch einmal drücken kippt das Verhältnis zwischen Quer-\nund Hochformat (2:3, 3:4, 9:16, 4:5). Rahmen oder Griffe ziehen, um ihn\nzu platzieren. Enter übernimmt, Esc bricht ab, Shift+C entfernt den Zuschnitt.',
        'es': 'Teclas de recorte:\n  1  libre   2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\nPulsa el mismo número otra vez para cambiar esa proporción entre\nhorizontal y vertical (2:3, 3:4, 9:16, 4:5). Arrastra el marco o sus\ntiradores para colocarlo. Intro aplica, Esc cancela, Mayús+C lo quita.',
        'fr': 'Touches de recadrage :\n  1  libre   2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\nAppuyez de nouveau sur le même chiffre pour basculer ce ratio entre\npaysage et portrait (2:3, 3:4, 9:16, 4:5). Faites glisser le cadre ou ses\npoignées pour le placer. Entrée applique, Échap annule, Maj+C retire.',
        'it': 'Tasti di ritaglio:\n  1  libero  2  3:2    3  4:3    4  1:1    5  16:9    6  5:4\nPremi di nuovo lo stesso numero per alternare la proporzione tra\norizzontale e verticale (2:3, 3:4, 9:16, 4:5). Trascina il riquadro o le\nmaniglie per posizionarlo. Invio applica, Esc annulla, Maiusc+C rimuove.',
    },
    'Crop: {w}×{h} px  —  Enter: apply, Esc: cancel, Shift+C: remove': {
        'de': 'Zuschnitt: {w}×{h} px  —  Enter: übernehmen, Esc: abbrechen, Shift+C: entfernen',
        'es': 'Recorte: {w}×{h} px  —  Intro: aplicar, Esc: cancelar, Mayús+C: quitar',
        'fr': 'Recadrage : {w}×{h} px  —  Entrée : appliquer, Échap : annuler, Maj+C : retirer',
        'it': 'Ritaglio: {w}×{h} px  —  Invio: applica, Esc: annulla, Maiusc+C: rimuovi',
    },
    'Read camera position from EXIF when adding files': {
        'de': 'Kameraposition beim Hinzufügen aus EXIF lesen',
        'es': 'Leer la posición de la cámara del EXIF al añadir archivos',
        'fr': "Lire la position de l'appareil depuis l'EXIF à l'ajout",
        'it': "Leggere la posizione della fotocamera dall'EXIF all'aggiunta",
    },
    'Fills the coordinates field of each newly added file from its EXIF data.\nTurn this off to publish no positions; already filled fields stay as\nthey are, and "from EXIF" in the file section keeps working either way.': {
        'de': 'Füllt das Koordinatenfeld jeder neu hinzugefügten Datei aus deren\nEXIF-Daten. Ausschalten, um keine Positionen zu veröffentlichen; bereits\ngefüllte Felder bleiben, und „aus EXIF" im Dateiabschnitt funktioniert\nso oder so weiter.',
        'es': 'Rellena el campo de coordenadas de cada archivo recién añadido a partir\nde sus datos EXIF. Desactívalo para no publicar posiciones; los campos ya\nrellenados se conservan, y «desde EXIF» en la sección del archivo sigue\nfuncionando igualmente.',
        'fr': 'Remplit le champ de coordonnées de chaque fichier ajouté à partir de ses\ndonnées EXIF. Désactivez-le pour ne publier aucune position ; les champs\ndéjà remplis restent, et « depuis EXIF » dans la section du fichier\ncontinue de fonctionner.',
        'it': 'Riempie il campo delle coordinate di ogni file appena aggiunto dai suoi\ndati EXIF. Disattivalo per non pubblicare posizioni; i campi già compilati\nrestano, e «da EXIF» nella sezione del file continua a funzionare.',
    },
    'Coordinates': {
        'de': 'Koordinaten',
        'es': 'Coordenadas',
        'fr': 'Coordonnées',
        'it': 'Coordinate',
    },
    'Coordinates:': {
        'de': 'Koordinaten:',
        'es': 'Coordenadas:',
        'fr': 'Coordonnées :',
        'it': 'Coordinate:',
    },
    'No GPS position in the EXIF data of the selected file(s).': {
        'de': 'Keine GPS-Position in den EXIF-Daten der ausgewählten Datei(en).',
        'es': 'No hay posición GPS en los datos EXIF del archivo o archivos seleccionados.',
        'fr': 'Aucune position GPS dans les données EXIF du ou des fichiers sélectionnés.',
        'it': 'Nessuna posizione GPS nei dati EXIF del file o dei file selezionati.',
    },
    '{n} coordinate(s) read from EXIF.': {
        'de': '{n} Koordinate(n) aus EXIF gelesen.',
        'es': '{n} coordenada(s) leída(s) del EXIF.',
        'fr': "{n} coordonnée(s) lue(s) depuis l'EXIF.",
        'it': "{n} coordinata/e letta/e dall'EXIF.",
    },
    'Where the CAMERA stood, in decimal degrees: latitude, longitude.\n\nFilled from the EXIF data of the file when it is added, if the camera\nrecorded a position - "from EXIF" reads it again, e.g. after you\ncleared the field. Leave it empty to publish no position at all.\n\nBecomes {{Location dec}} in the wikitext and the "coordinates of the\npoint of view" statement (P1259) in the structured data - the camera\nposition, not the position of what is pictured.': {
        'de': 'Wo die KAMERA stand, in Dezimalgrad: Breite, Länge.\n\nWird beim Hinzufügen der Datei aus deren EXIF-Daten gefüllt, sofern die\nKamera eine Position aufgezeichnet hat – „aus EXIF" liest sie erneut,\nz. B. nachdem du das Feld geleert hast. Leer lassen, um gar keine\nPosition zu veröffentlichen.\n\nWird zu {{Location dec}} im Wikitext und zur Aussage „Koordinaten des\nAufnahmestandpunkts" (P1259) in den strukturierten Daten – der\nKamerastandort, nicht der Standort des Abgebildeten.',
        'es': 'Dónde estaba la CÁMARA, en grados decimales: latitud, longitud.\n\nSe rellena al añadir el archivo a partir de sus datos EXIF, si la cámara\nregistró una posición; «desde EXIF» vuelve a leerla, p. ej. después de\nvaciar el campo. Déjalo vacío para no publicar ninguna posición.\n\nSe convierte en {{Location dec}} en el wikitexto y en la declaración\n«coordenadas del punto de vista» (P1259) en los datos estructurados: la\nposición de la cámara, no la de lo retratado.',
        'fr': "Où se trouvait l'APPAREIL, en degrés décimaux : latitude, longitude.\n\nRempli à l'ajout du fichier depuis ses données EXIF, si l'appareil a\nenregistré une position – « depuis EXIF » la relit, p. ex. après avoir\nvidé le champ. Laissez vide pour ne publier aucune position.\n\nDevient {{Location dec}} dans le wikitexte et la déclaration\n« coordonnées du point de vue » (P1259) dans les données structurées : la\nposition de l'appareil, pas celle du sujet.",
        'it': "Dove si trovava la FOTOCAMERA, in gradi decimali: latitudine, longitudine.\n\nViene riempito all'aggiunta del file dai suoi dati EXIF, se la fotocamera\nha registrato una posizione; «da EXIF» la rilegge, ad es. dopo aver\nsvuotato il campo. Lascialo vuoto per non pubblicare alcuna posizione.\n\nDiventa {{Location dec}} nel wikitesto e la dichiarazione «coordinate del\npunto di vista» (P1259) nei dati strutturati: la posizione della\nfotocamera, non quella del soggetto.",
    },
    'from EXIF': {
        'de': 'aus EXIF',
        'es': 'desde EXIF',
        'fr': 'depuis EXIF',
        'it': 'da EXIF',
    },
    'Read the position from the EXIF data of the selected file(s) again.': {
        'de': 'Die Position erneut aus den EXIF-Daten der ausgewählten Datei(en) lesen.',
        'es': 'Volver a leer la posición de los datos EXIF del archivo o archivos seleccionados.',
        'fr': 'Relire la position depuis les données EXIF du ou des fichiers sélectionnés.',
        'it': 'Rileggere la posizione dai dati EXIF del file o dei file selezionati.',
    },
    'P6216 "copyright status": how the work stands in copyright terms.\n\nQ73566113 - available under a Creative Commons license: the right one\nfor own photographs published here (the default).\nQ50423863 - copyrighted, without such a release.\nQ19652 - public domain.\n\nThis has no wikitext counterpart of its own; it exists only as structured\ndata. Pick from the dropdown or enter another Q-number.': {
        'de': 'P6216 „Urheberrechtsstatus": Wie das Werk urheberrechtlich dasteht.\n\nQ73566113 – unter einer Creative-Commons-Lizenz verfügbar: das Richtige\nfür eigene, hier veröffentlichte Fotos (der Vorgabewert).\nQ50423863 – urheberrechtlich geschützt, ohne eine solche Freigabe.\nQ19652 – gemeinfrei.\n\nDazu gibt es keine eigene Wikitext-Entsprechung; das existiert nur als\nstrukturierte Daten. Aus dem Dropdown wählen oder eine andere Q-Nummer\neintragen.',
        'es': 'P6216 «estado de los derechos de autor»: cómo está la obra en términos de\nderechos de autor.\n\nQ73566113: disponible bajo una licencia Creative Commons, lo correcto para\nfotos propias publicadas aquí (el valor por defecto).\nQ50423863: con derechos de autor, sin esa liberación.\nQ19652: dominio público.\n\nNo tiene contrapartida propia en wikitexto; existe solo como datos\nestructurados. Elige del desplegable o introduce otro número Q.',
        'fr': "P6216 « statut du droit d'auteur » : la situation de l'œuvre au regard du\ndroit d'auteur.\n\nQ73566113 – disponible sous licence Creative Commons : ce qu'il faut pour\nvos propres photos publiées ici (valeur par défaut).\nQ50423863 – protégé, sans une telle libération.\nQ19652 – domaine public.\n\nIl n'y a pas d'équivalent wikitexte ; cela n'existe qu'en données\nstructurées. Choisissez dans le menu ou saisissez un autre numéro Q.",
        'it': "P6216 «stato del diritto d'autore»: come si colloca l'opera dal punto di\nvista del diritto d'autore.\n\nQ73566113 – disponibile con licenza Creative Commons: quello giusto per\nfoto proprie pubblicate qui (il valore predefinito).\nQ50423863 – protetto da copyright, senza tale liberatoria.\nQ19652 – pubblico dominio.\n\nNon ha una controparte propria in wikitesto; esiste solo come dati\nstrutturati. Scegli dal menu o inserisci un altro numero Q.",
    },
    'work available with a Creative Commons license': {
        'de': 'unter Creative-Commons-Lizenz verfügbar',
        'es': 'disponible con licencia Creative Commons',
        'fr': 'disponible sous licence Creative Commons',
        'it': 'disponibile con licenza Creative Commons',
    },
    'public domain': {
        'de': 'gemeinfrei',
        'es': 'dominio público',
        'fr': 'domaine public',
        'it': 'pubblico dominio',
    },
    'P275 "copyright license": the SAME license as the template above, as a\nWikidata item - Q18199165 is CC BY-SA 4.0 and matches {{Cc-by-sa-4.0}}.\n\nAgain the same fact twice: the template is the wikitext half, P275 the\nstructured half. Picking a license in EITHER dropdown sets the other\none too, so the two cannot contradict each other.': {
        'de': 'P275 „Lizenz": DIESELBE Lizenz wie die Vorlage oben, als Wikidata-Objekt –\nQ18199165 ist CC BY-SA 4.0 und passt zu {{Cc-by-sa-4.0}}.\n\nWieder derselbe Sachverhalt zweimal: die Vorlage ist die Wikitext-Hälfte,\nP275 die strukturierte. Eine Lizenz in EINEM der beiden Dropdowns zu wählen\nsetzt das andere gleich mit, damit sich beide nicht widersprechen können.',
        'es': 'P275 «licencia»: la MISMA licencia que la plantilla de arriba, como elemento\nde Wikidata: Q18199165 es CC BY-SA 4.0 y corresponde a {{Cc-by-sa-4.0}}.\n\nDe nuevo el mismo hecho dos veces: la plantilla es la mitad wikitexto, P275\nla estructurada. Elegir una licencia en CUALQUIERA de los dos desplegables\nfija también el otro, para que no puedan contradecirse.',
        'fr': "P275 « licence » : la MÊME licence que le modèle ci-dessus, comme élément\nWikidata – Q18199165 est CC BY-SA 4.0 et correspond à {{Cc-by-sa-4.0}}.\n\nÀ nouveau le même fait deux fois : le modèle est la moitié wikitexte, P275\nla moitié structurée. Choisir une licence dans L'UN des deux menus règle\naussi l'autre, afin qu'ils ne puissent pas se contredire.",
        'it': "P275 «licenza»: la STESSA licenza del template qui sopra, come elemento\nWikidata: Q18199165 è CC BY-SA 4.0 e corrisponde a {{Cc-by-sa-4.0}}.\n\nDi nuovo lo stesso fatto due volte: il template è la metà wikitesto, P275\nquella strutturata. Scegliere una licenza in UNO dei due menu imposta anche\nl'altro, così non possono contraddirsi.",
    },
    'copyrighted': {
        'de': 'urheberrechtlich geschützt',
        'es': 'con derechos de autor',
        'fr': "protégé par le droit d'auteur",
        'it': 'protetto da copyright',
    },
    'What probably stays the same for a photographer forever.': {
        'de': 'Das, was für einen Fotografen vermutlich immer gleich bleibt.',
        'es': 'Lo que para un fotógrafo probablemente permanece siempre igual.',
        'fr': 'Ce qui, pour un photographe, reste probablement toujours identique.',
        'it': 'Ciò che per un fotografo probabilmente resta sempre uguale.',
    },
    'For one upload session, e.g. all pictures of one event.': {
        'de': 'Für eine Upload-Sitzung, z. B. alle Bilder einer Veranstaltung.',
        'es': 'Para una sesión de subida, p. ej. todas las imágenes de un evento.',
        'fr': "Pour une session de téléversement, p. ex. toutes les images d'un événement.",
        'it': 'Per una sessione di caricamento, ad es. tutte le immagini di un evento.',
    },
    'The subject of one picture, possibly of several.': {
        'de': 'Das Motiv auf einem, evtl. mehreren Bildern.',
        'es': 'El motivo de una imagen, posiblemente de varias.',
        'fr': "Le sujet d'une image, éventuellement de plusieurs.",
        'it': "Il soggetto di un'immagine, eventualmente di più.",
    },
    'Searches Wikidata for the event and sets it as the "created during" (P10408) statement.': {
        'de': 'Sucht das Event in Wikidata und setzt es als „Entstanden während"-Aussage (P10408).',
        'es': 'Busca el evento en Wikidata y lo establece como declaración «creado durante» (P10408).',
        'fr': 'Recherche l’événement dans Wikidata et le définit comme déclaration « créé lors de » (P10408).',
        'it': 'Cerca l’evento in Wikidata e lo imposta come dichiarazione "creato durante" (P10408).',
    },
    'Adds the event as a category (resolved via Wikidata to the Commons category P373, or the name).': {
        'de': 'Fügt das Event als Kategorie hinzu (via Wikidata zur Commons-Kategorie P373 aufgelöst, sonst der Name).',
        'es': 'Añade el evento como categoría (resuelto vía Wikidata a la categoría de Commons P373, o el nombre).',
        'fr': 'Ajoute l’événement comme catégorie (résolu via Wikidata en catégorie Commons P373, sinon le nom).',
        'it': 'Aggiunge l’evento come categoria (risolto tramite Wikidata alla categoria Commons P373, altrimenti il nome).',
    },
    'Adds each person shown as a category - directly by name, or resolved via Wikidata (name -> item -> Commons category P373).': {
        'de': 'Fügt jede abgebildete Person als Kategorie hinzu – direkt über den Namen oder via Wikidata aufgelöst (Name -> Objekt -> Commons-Kategorie P373).',
        'es': 'Añade cada persona mostrada como categoría, directamente por el nombre o resuelta vía Wikidata (nombre -> elemento -> categoría de Commons P373).',
        'fr': 'Ajoute chaque personne représentée comme catégorie, directement par le nom ou via Wikidata (nom -> élément -> catégorie Commons P373).',
        'it': 'Aggiunge ogni persona ritratta come categoria, direttamente dal nome o risolta tramite Wikidata (nome -> elemento -> categoria Commons P373).',
    },
    'Searches Wikidata for each person shown and lets you pick the item to add as a depicts (P180) statement.': {
        'de': 'Sucht für jede abgebildete Person in Wikidata und lässt dich das Objekt für eine Depicts-Aussage (P180) auswählen.',
        'es': 'Busca en Wikidata cada persona mostrada y te permite elegir el elemento para añadir como declaración depicts (P180).',
        'fr': 'Recherche dans Wikidata chaque personne représentée et vous laisse choisir l’élément à ajouter comme déclaration depicts (P180).',
        'it': 'Cerca in Wikidata ogni persona ritratta e ti fa scegliere l’elemento da aggiungere come dichiarazione depicts (P180).',
    },
    'BotPassword recommended (Special:BotPasswords). The password is stored in your system keyring - leave it empty to be asked at login instead.': {
        'de': 'BotPasswort empfohlen (Special:BotPasswords). Das Passwort wird im System-Schlüsselbund gespeichert – leer lassen, um stattdessen beim Login gefragt zu werden.',
        'es': 'Se recomienda BotPassword (Special:BotPasswords). La contraseña se guarda en el llavero del sistema; déjala vacía para que se pregunte al iniciar sesión.',
        'fr': "BotPassword recommandé (Special:BotPasswords). Le mot de passe est stocké dans le trousseau du système ; laissez-le vide pour qu'il soit demandé à la connexion.",
        'it': "BotPassword consigliata (Special:BotPasswords). La password è salvata nel portachiavi di sistema; lasciala vuota per essere richiesta all'accesso.",
    },
    'BotPassword recommended (Special:BotPasswords). No system keyring available, so the password is stored in plain text - leave it empty to be asked at login instead.': {
        'de': 'BotPasswort empfohlen (Special:BotPasswords). Kein System-Schlüsselbund verfügbar, daher wird das Passwort im Klartext gespeichert – leer lassen, um stattdessen beim Login gefragt zu werden.',
        'es': 'Se recomienda BotPassword (Special:BotPasswords). No hay llavero del sistema disponible, así que la contraseña se guarda en texto plano; déjala vacía para que se pregunte al iniciar sesión.',
        'fr': "BotPassword recommandé (Special:BotPasswords). Aucun trousseau système disponible ; le mot de passe est donc stocké en clair. Laissez-le vide pour qu'il soit demandé à la connexion.",
        'it': "BotPassword consigliata (Special:BotPasswords). Nessun portachiavi di sistema disponibile, quindi la password è salvata in chiaro; lasciala vuota per essere richiesta all'accesso.",
    },
    'Enter the confirmation code manually (use if the automatic confirmation does not work)': {
        'de': 'Bestätigungscode manuell eingeben (falls die automatische Bestätigung nicht klappt)',
        'es': 'Introducir el código de confirmación manualmente (si la confirmación automática no funciona)',
        'fr': 'Saisir le code de confirmation manuellement (si la confirmation automatique ne fonctionne pas)',
        'it': 'Inserisci manualmente il codice di conferma (se la conferma automatica non funziona)',
    },
    'Open the link, click "Allow", then paste the confirmation code here and press Finish.': {
        'de': 'Öffne den Link, klicke auf „Zulassen", füge dann den Bestätigungscode hier ein und klicke auf Fertigstellen.',
        'es': 'Abre el enlace, haz clic en «Permitir», luego pega aquí el código de confirmación y pulsa Finalizar.',
        'fr': 'Ouvrez le lien, cliquez sur « Autoriser », puis collez ici le code de confirmation et cliquez sur Terminer.',
        'it': 'Apri il link, fai clic su «Consenti», poi incolla qui il codice di conferma e premi Completa.',
    },
    'Files and IPTC data come from the IPTC tab. Write settings (export folder) are in the IPTC tab.': {
        'de': 'Dateien und IPTC-Daten stammen aus dem IPTC-Tab. Die Schreib-Einstellungen (Exportordner) stehen ebenfalls dort.',
        'es': 'Los archivos y los datos IPTC vienen de la pestaña IPTC. Los ajustes de escritura (carpeta de exportación) están allí.',
        'fr': 'Les fichiers et les données IPTC proviennent de l’onglet IPTC. Les réglages d’écriture (dossier d’export) s’y trouvent aussi.',
        'it': 'I file e i dati IPTC provengono dalla scheda IPTC. Le impostazioni di scrittura (cartella di esportazione) sono lì.',
    },
    'The IPTC tab is disabled, so the "Write IPTC + upload" workflow is unavailable. These server settings are used by the Culling tab ("-> FTP").': {
        'de': 'Der IPTC-Tab ist abgeschaltet, daher steht der Ablauf „IPTC schreiben + hochladen“ nicht zur Verfügung. Diese Servereinstellungen nutzt der Sichtungs-Tab („-> FTP“).',
        'es': 'La pestaña IPTC está desactivada, así que el flujo «Escribir IPTC + subir» no está disponible. La pestaña de selección usa estos ajustes del servidor («-> FTP»).',
        'fr': 'L’onglet IPTC est désactivé : le flux « Écrire l’IPTC + envoyer » n’est pas disponible. Ces réglages de serveur sont utilisés par l’onglet de tri (« -> FTP »).',
        'it': 'La scheda IPTC è disattivata, quindi il flusso "Scrivi IPTC + carica" non è disponibile. Queste impostazioni del server sono usate dalla scheda di selezione ("-> FTP").',
    },
    'Adds the selected images to the MediaWiki tab; with no selection, every image passing the filter. Images can also be dragged onto the MediaWiki tab directly.': {
        'de': 'Fügt die ausgewählten Bilder dem MediaWiki-Tab hinzu; ohne Auswahl alle Bilder, die den Filter passieren. Bilder lassen sich auch direkt auf den MediaWiki-Tab ziehen.',
        'es': 'Añade las imágenes seleccionadas a la pestaña MediaWiki; sin selección, todas las que pasen el filtro. También se pueden arrastrar directamente a la pestaña MediaWiki.',
        'fr': 'Ajoute les images sélectionnées à l’onglet MediaWiki ; sans sélection, toutes celles qui passent le filtre. Les images peuvent aussi être glissées directement sur l’onglet MediaWiki.',
        'it': 'Aggiunge le immagini selezionate alla scheda MediaWiki; senza selezione, tutte quelle che passano il filtro. Le immagini si possono anche trascinare direttamente sulla scheda MediaWiki.',
    },
    'Uploads the selected images (as they are, no IPTC writing) to the server configured in the FTP tab / Settings.': {
        'de': 'Lädt die ausgewählten Bilder unverändert (ohne IPTC-Schreiben) auf den im FTP-Tab bzw. in den Einstellungen konfigurierten Server.',
        'es': 'Sube las imágenes seleccionadas tal cual (sin escribir IPTC) al servidor configurado en la pestaña FTP / Ajustes.',
        'fr': 'Envoie les images sélectionnées telles quelles (sans écriture IPTC) vers le serveur configuré dans l’onglet FTP / Réglages.',
        'it': 'Carica le immagini selezionate così come sono (senza scrittura IPTC) sul server configurato nella scheda FTP / Impostazioni.',
    },
    'Uploads the selected images (as they are) to the Flickr account authorized in the Flickr tab.': {
        'de': 'Lädt die ausgewählten Bilder unverändert auf das im Flickr-Tab autorisierte Konto hoch.',
        'es': 'Sube las imágenes seleccionadas tal cual a la cuenta de Flickr autorizada en la pestaña Flickr.',
        'fr': 'Envoie les images sélectionnées telles quelles vers le compte Flickr autorisé dans l’onglet Flickr.',
        'it': 'Carica le immagini selezionate così come sono sull’account Flickr autorizzato nella scheda Flickr.',
    },
    'Suggests categories from the depicts entries and the "created during" event (Commons category P373, or the label; a missing year is taken from the Date column).': {
        'de': 'Schlägt Kategorien aus den Depicts-Einträgen und dem „Entstanden während“-Ereignis vor (Commons-Kategorie P373, sonst das Label; ein fehlendes Jahr kommt aus der Datumsspalte).',
        'es': 'Sugiere categorías a partir de las entradas de depicts y del evento «creado durante» (categoría de Commons P373, o la etiqueta; un año que falte se toma de la columna Fecha).',
        'fr': 'Suggère des catégories à partir des entrées depicts et de l’événement « créé lors de » (catégorie Commons P373, sinon le libellé ; une année manquante est reprise de la colonne Date).',
        'it': 'Suggerisce categorie dalle voci depicts e dall’evento "creato durante" (categoria Commons P373, altrimenti l’etichetta; un anno mancante viene preso dalla colonna Data).',
    },
    'BotPassword recommended (Special:BotPasswords). The password is stored in PLAIN TEXT - leave it empty to be asked at login instead.': {
        'de': 'BotPassword empfohlen (Special:BotPasswords). Das Passwort wird im KLARTEXT gespeichert – leer lassen, um stattdessen beim Anmelden gefragt zu werden.',
        'es': 'Se recomienda una BotPassword (Special:BotPasswords). La contraseña se guarda en TEXTO PLANO: déjela vacía para que se pida al iniciar sesión.',
        'fr': 'BotPassword recommandé (Special:BotPasswords). Le mot de passe est enregistré en TEXTE CLAIR – laissez-le vide pour qu’il soit demandé à la connexion.',
        'it': 'BotPassword consigliata (Special:BotPasswords). La password è salvata in TESTO IN CHIARO: lasciala vuota per farla chiedere all’accesso.',
    },
    'The short caption of the file, in the language on the left - ONE sentence,\nno wiki markup: "Harald Krichel at the Berlinale 2026".\n\nThis is the STRUCTURED caption (Wikibase label). Commons stores every\nfile TWICE: as wikitext (the Information template - the field below)\nand as structured data (machine-readable statements - this field).\nThey say the same thing in two forms; that is why Cammello asks for\nboth. "Information from caption" copies this text down.': {
        'de': 'Die kurze Bildunterschrift in der links gewählten Sprache – EIN Satz,\nkein Wiki-Markup: „Harald Krichel bei der Berlinale 2026".\n\nDies ist die STRUKTURIERTE Bildunterschrift (Wikibase-Label). Commons\nspeichert jede Datei ZWEIMAL: als Wikitext (die Information-Vorlage –\ndas Feld darunter) und als strukturierte Daten (maschinenlesbare\nAussagen – dieses Feld). Beide sagen dasselbe in zwei Formen; deshalb\nfragt Cammello nach beidem. „Information aus Bildunterschrift"\nübernimmt diesen Text nach unten.',
        'es': 'El pie de foto breve en el idioma elegido a la izquierda: UNA frase, sin\nmarcado wiki: «Harald Krichel en la Berlinale 2026».\n\nEste es el pie ESTRUCTURADO (etiqueta de Wikibase). Commons guarda cada\narchivo DOS VECES: como wikitexto (la plantilla Information, el campo de\nabajo) y como datos estructurados (declaraciones legibles por máquina,\neste campo). Ambos dicen lo mismo en dos formas; por eso Cammello pide\nlos dos. «Information desde el pie» copia este texto abajo.',
        'fr': "La légende courte dans la langue choisie à gauche – UNE phrase, sans\nbalisage wiki : « Harald Krichel à la Berlinale 2026 ».\n\nC'est la légende STRUCTURÉE (libellé Wikibase). Commons enregistre chaque\nfichier DEUX FOIS : en wikitexte (le modèle Information – le champ\nci-dessous) et en données structurées (déclarations lisibles par machine –\nce champ). Les deux disent la même chose sous deux formes ; c'est\npourquoi Cammello demande les deux. « Information depuis la légende »\nrecopie ce texte en dessous.",
        'it': 'La didascalia breve nella lingua scelta a sinistra: UNA frase, senza\nmarcatura wiki: «Harald Krichel alla Berlinale 2026».\n\nQuesta è la didascalia STRUTTURATA (etichetta Wikibase). Commons salva\nogni file DUE VOLTE: come wikitesto (il template Information, il campo\nqui sotto) e come dati strutturati (dichiarazioni leggibili dalle\nmacchine, questo campo). Dicono la stessa cosa in due forme; perciò\nCammello chiede entrambi. «Information dalla didascalia» copia questo\ntesto in basso.',
    },
    'The description in the Information template - the WIKITEXT half of the\npair (the caption above is the structured half). May be longer than the\ncaption and may contain links and templates.\n\nUploaded as {{<language>|1=your text}}. Empty is allowed: then the file\npage shows no description text in this language.': {
        'de': 'Die Beschreibung in der Information-Vorlage – die WIKITEXT-Hälfte des\nPaares (die Bildunterschrift darüber ist die strukturierte Hälfte). Darf\nlänger sein als die Unterschrift und Links sowie Vorlagen enthalten.\n\nWird als {{<Sprache>|1=dein Text}} hochgeladen. Leer ist erlaubt: dann\nzeigt die Dateiseite in dieser Sprache keinen Beschreibungstext.',
        'es': 'La descripción en la plantilla Information: la mitad WIKITEXTO del par (el\npie de foto de arriba es la mitad estructurada). Puede ser más larga que\nel pie y contener enlaces y plantillas.\n\nSe sube como {{<idioma>|1=tu texto}}. Se permite vacío: entonces la página\ndel archivo no muestra texto de descripción en ese idioma.',
        'fr': "La description dans le modèle Information – la moitié WIKITEXTE de la paire\n(la légende ci-dessus est la moitié structurée). Elle peut être plus longue\nque la légende et contenir des liens et des modèles.\n\nTéléversée sous la forme {{<langue>|1=votre texte}}. Vide est permis : la\npage du fichier n'affiche alors aucune description dans cette langue.",
        'it': 'La descrizione nel template Information: la metà WIKITESTO della coppia (la\ndidascalia qui sopra è la metà strutturata). Può essere più lunga della\ndidascalia e contenere link e template.\n\nCaricata come {{<lingua>|1=il tuo testo}}. Vuoto è ammesso: in tal caso la\npagina del file non mostra testo descrittivo in quella lingua.',
    },
    'P180 "depicts": what the picture SHOWS, as Wikidata items - for\nportraits the person in the picture, e.g. Q42 for Douglas Adams.\nSeveral items separated by ;\n\nEnter Q-numbers directly, or type a name and pick from the live\nsuggestions - the field then inserts the Q-number for you.\n\nBecomes the structured "depicts" statement (P180) of the file on Commons.\nRequired for the upload; if the picture has no suitable item, choose a\nreason in the field below instead.': {
        'de': 'P180 „zeigt": Was das Bild ZEIGT, als Wikidata-Objekte – bei Porträts die\nabgebildete Person, z. B. Q42 für Douglas Adams. Mehrere Objekte mit ;\ngetrennt\n\nQ-Nummern direkt eintragen, oder einen Namen tippen und aus den\nLive-Vorschlägen wählen – das Feld setzt dann die Q-Nummer ein.\n\nWird zur strukturierten „zeigt"-Aussage (P180) der Datei auf Commons.\nFür den Upload erforderlich; hat das Bild kein passendes Objekt,\nstattdessen im Feld darunter einen Grund wählen.',
        'es': 'P180 «representa»: lo que MUESTRA la imagen, como elementos de Wikidata: en\nretratos, la persona retratada, p. ej. Q42 para Douglas Adams. Varios\nelementos separados por ;\n\nIntroduce números Q directamente, o escribe un nombre y elige entre las\nsugerencias en vivo: el campo insertará el número Q por ti.\n\nSe convierte en la declaración estructurada «representa» (P180) del archivo\nen Commons. Obligatorio para la subida; si la imagen no tiene un elemento\nadecuado, elige un motivo en el campo de abajo.',
        'fr': "P180 « représente » : ce que MONTRE l'image, comme éléments Wikidata – pour\nles portraits, la personne représentée, p. ex. Q42 pour Douglas Adams.\nPlusieurs éléments séparés par ;\n\nSaisissez des numéros Q directement, ou tapez un nom et choisissez parmi\nles suggestions en direct – le champ insère alors le numéro Q pour vous.\n\nDevient la déclaration structurée « représente » (P180) du fichier sur\nCommons. Requis pour le téléversement ; si l'image n'a pas d'élément\nadapté, choisissez plutôt une raison dans le champ ci-dessous.",
        'it': "P180 «raffigura»: ciò che l'immagine MOSTRA, come elementi Wikidata: nei\nritratti la persona raffigurata, ad es. Q42 per Douglas Adams. Più elementi\nseparati da ;\n\nInserisci direttamente i numeri Q, oppure digita un nome e scegli tra i\nsuggerimenti in tempo reale: il campo inserirà il numero Q per te.\n\nDiventa la dichiarazione strutturata «raffigura» (P180) del file su\nCommons. Obbligatorio per il caricamento; se l'immagine non ha un elemento\nadatto, scegli invece un motivo nel campo sottostante.",
    },
    'P10408 "created during": the event ALL these pictures were taken at,\nas ONE Wikidata item.\n\nIf the edition has its own item, take that one: "Berlinale 2026",\nnot "Berlinale". Smaller festivals often have only one item for the\nwhole series - then that one is right. Type the name and pick from\nthe suggestions, or enter the Q-number directly.\n\nBecomes the "created during" statement (P10408) of every file, and\n"Suggest" derives the base category from it.': {
        'de': 'P10408 „entstanden während": Die Veranstaltung, bei der ALLE diese Bilder\nentstanden sind, als EIN Wikidata-Objekt.\n\nHat die Ausgabe ein eigenes Objekt, nimm dieses: „Berlinale 2026",\nnicht „Berlinale". Kleinere Festivals wie das Rudolstadt-Festival haben\noft nur ein Objekt für die ganze Reihe – dann ist dieses das richtige.\nNamen tippen und aus den Vorschlägen wählen, oder die Q-Nummer direkt\neintragen.\n\nWird zur „entstanden während"-Aussage (P10408) jeder Datei, und\n„Vorschlagen" leitet daraus die Basiskategorie ab.',
        'es': 'P10408 «creado durante»: el evento en el que se tomaron TODAS estas\nimágenes, como UN elemento de Wikidata.\n\nSi la edición tiene su propio elemento, toma ese: «Berlinale 2026», no\n«Berlinale». Los festivales pequeños a menudo solo tienen un elemento para\ntoda la serie: entonces ese es el correcto. Escribe el nombre y elige entre\nlas sugerencias, o introduce el número Q directamente.\n\nSe convierte en la declaración «creado durante» (P10408) de cada archivo,\ny «Sugerir» deriva de ella la categoría base.',
        'fr': "P10408 « créé pendant » : l'événement où TOUTES ces images ont été prises,\ncomme UN SEUL élément Wikidata.\n\nSi l'édition a son propre élément, prenez celui-là : « Berlinale 2026 »,\npas « Berlinale ». Les petits festivals n'ont souvent qu'un seul élément\npour toute la série – c'est alors le bon. Tapez le nom et choisissez parmi\nles suggestions, ou saisissez directement le numéro Q.\n\nDevient la déclaration « créé pendant » (P10408) de chaque fichier, et\n« Suggérer » en déduit la catégorie de base.",
        'it': "P10408 «creato durante»: l'evento in cui sono state scattate TUTTE queste\nimmagini, come UN SOLO elemento Wikidata.\n\nSe l'edizione ha un proprio elemento, prendi quello: «Berlinale 2026»,\nnon «Berlinale». I festival più piccoli spesso hanno un solo elemento per\ntutta la serie: allora è quello giusto. Digita il nome e scegli tra i\nsuggerimenti, oppure inserisci direttamente il numero Q.\n\nDiventa la dichiarazione «creato durante» (P10408) di ogni file, e\n«Suggerisci» ne ricava la categoria di base.",
    },
    'P170 "creator": the photographer as a Wikidata item, IF there is one\nabout you - e.g. Q1583452 (Harald Krichel). Type your name and pick\nfrom the suggestions, or enter the Q-number.\n\nSAME FACT AS "Author" ABOVE, in the second form: the author line is\nthe wikitext half, P170 the structured half. Commons stores both.\nWithout an own item leave this empty - the author line alone is fine.': {
        'de': 'P170 „Urheber": Der Fotograf als Wikidata-Objekt, FALLS es eines über dich\ngibt – z. B. Q1583452 (Harald Krichel). Namen tippen und aus den\nVorschlägen wählen, oder die Q-Nummer eintragen.\n\nDERSELBE SACHVERHALT WIE „Autor" OBEN, nur in der zweiten Form: die\nAutor-Zeile ist die Wikitext-Hälfte, P170 die strukturierte Hälfte.\nCommons speichert beides. Ohne eigenes Objekt leer lassen – die\nAutor-Zeile allein genügt.',
        'es': 'P170 «creador»: el fotógrafo como elemento de Wikidata, SI existe uno sobre\nti, p. ej. Q1583452 (Harald Krichel). Escribe tu nombre y elige entre las\nsugerencias, o introduce el número Q.\n\nEL MISMO HECHO QUE «Autor» ARRIBA, en la segunda forma: la línea de autor\nes la mitad wikitexto, P170 la mitad estructurada. Commons guarda ambas.\nSin elemento propio déjalo vacío: la línea de autor basta.',
        'fr': "P170 « créateur » : le photographe comme élément Wikidata, S'IL en existe un\nsur vous – p. ex. Q1583452 (Harald Krichel). Tapez votre nom et choisissez\nparmi les suggestions, ou saisissez le numéro Q.\n\nLE MÊME FAIT QUE « Auteur » CI-DESSUS, sous la seconde forme : la ligne\nauteur est la moitié wikitexte, P170 la moitié structurée. Commons conserve\nles deux. Sans élément propre, laissez vide – la ligne auteur suffit.",
        'it': 'P170 «creatore»: il fotografo come elemento Wikidata, SE ne esiste uno su di\nte, ad es. Q1583452 (Harald Krichel). Digita il tuo nome e scegli tra i\nsuggerimenti, oppure inserisci il numero Q.\n\nLO STESSO FATTO DI «Autore» QUI SOPRA, nella seconda forma: la riga autore\nè la metà wikitesto, P170 la metà strutturata. Commons conserva entrambe.\nSenza un proprio elemento lascialo vuoto: la riga autore basta.',
    },
    'Who took the pictures, as wikitext - typically a link to your Commons\nuser page with your real name as the visible text:\n\n  [[User:Seewolf|Harald Krichel]]\n\nGoes word for word into the author= field of every upload. This is the\nWIKITEXT half; "Creator (P170)" below is the same fact as structured\ndata. Commons keeps both, so both fields exist here.': {
        'de': 'Wer die Bilder gemacht hat, als Wikitext – üblicherweise ein Link auf\ndeine Commons-Benutzerseite mit deinem Klarnamen als sichtbarem Text:\n\n  [[User:Seewolf|Harald Krichel]]\n\nLandet wortgleich im author=-Feld jedes Uploads. Das ist die\nWIKITEXT-Hälfte; „Urheber (P170)" darunter ist derselbe Sachverhalt als\nstrukturierte Daten. Commons führt beides, deshalb gibt es hier beide\nFelder.',
        'es': 'Quién tomó las imágenes, como wikitexto: normalmente un enlace a tu página\nde usuario de Commons con tu nombre real como texto visible:\n\n  [[User:Seewolf|Harald Krichel]]\n\nVa literalmente al campo author= de cada subida. Esta es la mitad\nWIKITEXTO; «Creador (P170)» más abajo es el mismo hecho como datos\nestructurados. Commons mantiene ambos, por eso existen los dos campos.',
        'fr': "Qui a pris les photos, en wikitexte – généralement un lien vers votre page\nutilisateur Commons avec votre vrai nom comme texte visible :\n\n  [[User:Seewolf|Harald Krichel]]\n\nVa mot pour mot dans le champ author= de chaque téléversement. C'est la\nmoitié WIKITEXTE ; « Créateur (P170) » ci-dessous est le même fait en\ndonnées structurées. Commons conserve les deux, d'où les deux champs.",
        'it': 'Chi ha scattato le foto, come wikitesto: di solito un link alla tua pagina\nutente di Commons con il tuo vero nome come testo visibile:\n\n  [[User:Seewolf|Harald Krichel]]\n\nFinisce parola per parola nel campo author= di ogni caricamento. Questa è\nla metà WIKITESTO; «Creatore (P170)» qui sotto è lo stesso fatto come dati\nstrutturati. Commons conserva entrambi, perciò esistono entrambi i campi.',
    },
    'The license template under which every file in this batch is published,\ne.g. {{Cc-by-sa-4.0}} for Creative Commons Attribution-ShareAlike 4.0.\n\nMust be one of the free licenses Commons accepts. The WIKITEXT half -\n"License (P275)" below says the same as structured data, and the two\nmust not disagree.': {
        'de': 'Die Lizenzvorlage, unter der jede Datei dieser Serie veröffentlicht wird,\nz. B. {{Cc-by-sa-4.0}} für Creative Commons Attribution-ShareAlike 4.0.\n\nMuss eine der auf Commons zulässigen freien Lizenzen sein. Die\nWIKITEXT-Hälfte – „Lizenz (P275)" darunter sagt dasselbe als\nstrukturierte Daten, und beide dürfen sich nicht widersprechen.',
        'es': 'La plantilla de licencia bajo la que se publica cada archivo de esta serie,\np. ej. {{Cc-by-sa-4.0}} para Creative Commons Attribution-ShareAlike 4.0.\n\nDebe ser una de las licencias libres que acepta Commons. La mitad\nWIKITEXTO: «Licencia (P275)» más abajo dice lo mismo como datos\nestructurados, y ambas no deben contradecirse.',
        'fr': 'Le modèle de licence sous lequel chaque fichier de cette série est publié,\np. ex. {{Cc-by-sa-4.0}} pour Creative Commons Attribution-ShareAlike 4.0.\n\nDoit être une des licences libres acceptées par Commons. La moitié\nWIKITEXTE – « Licence (P275) » ci-dessous dit la même chose en données\nstructurées, et les deux ne doivent pas se contredire.',
        'it': 'Il template di licenza sotto cui viene pubblicato ogni file di questa serie,\nad es. {{Cc-by-sa-4.0}} per Creative Commons Attribution-ShareAlike 4.0.\n\nDeve essere una delle licenze libere accettate da Commons. La metà\nWIKITESTO: «Licenza (P275)» qui sotto dice lo stesso come dati strutturati,\ne le due non devono contraddirsi.',
    },
    'The Commons categories this file belongs in - category NAMES only,\nwithout "Category:" and without brackets, several separated by ;\n\ne.g.:  Berlinale 2026; Harald Krichel\n\nEach name becomes a [[Category:...]] line in the wikitext. The category\nshould already exist on Commons - a red category leaves the file\npoorly findable. "Suggest" fills this from the depicts entries.': {
        'de': 'Die Commons-Kategorien, in die diese Datei gehört – nur die NAMEN,\nohne „Category:" und ohne Klammern, mehrere mit ; getrennt\n\nz. B.:  Berlinale 2026; Harald Krichel\n\nJeder Name wird im Wikitext zu einer [[Category:…]]-Zeile. Die Kategorie\nsollte auf Commons schon existieren – eine rote Kategorie macht die\nDatei schlecht auffindbar. „Vorschlagen" füllt das Feld aus den\ndepicts-Einträgen.',
        'es': 'Las categorías de Commons a las que pertenece este archivo: solo los NOMBRES,\nsin «Category:» y sin corchetes, varias separadas por ;\n\np. ej.:  Berlinale 2026; Harald Krichel\n\nCada nombre se convierte en una línea [[Category:…]] en el wikitexto. La\ncategoría debería existir ya en Commons: una categoría roja deja el archivo\nmal localizable. «Sugerir» rellena el campo desde las entradas de depicts.',
        'fr': 'Les catégories Commons auxquelles ce fichier appartient – uniquement les NOMS,\nsans « Category: » et sans crochets, plusieurs séparées par ;\n\np. ex. :  Berlinale 2026; Harald Krichel\n\nChaque nom devient une ligne [[Category:…]] dans le wikitexte. La catégorie\ndevrait déjà exister sur Commons – une catégorie rouge rend le fichier\ndifficile à trouver. « Suggérer » remplit le champ depuis les entrées depicts.',
        'it': 'Le categorie di Commons a cui appartiene questo file: solo i NOMI,\nsenza «Category:» e senza parentesi, più voci separate da ;\n\nad es.:  Berlinale 2026; Harald Krichel\n\nOgni nome diventa una riga [[Category:…]] nel wikitesto. La categoria\ndovrebbe già esistere su Commons: una categoria rossa rende il file\ndifficile da trovare. «Suggerisci» riempie il campo dalle voci depicts.',
    },
    'Only used when the depicts field above stays empty - pick WHY:\n\n"No Wikidata item": the person or subject shown has no item (yet).\n"Not applicable": the picture shows no identifiable subject.\n"Unidentified": there is a subject, but you do not know who or what it is.\n\nStored as depicts_override= in the description; the upload then\nproceeds without a depicts statement.': {
        'de': 'Nur relevant, wenn das depicts-Feld darüber leer bleibt – wähle, WARUM:\n\n„Kein Wikidata-Objekt": die gezeigte Person oder das Motiv hat (noch)\nkein Objekt.\n„Nicht anwendbar": das Bild zeigt kein identifizierbares Motiv.\n„Unidentifiziert": es gibt ein Motiv, aber du weißt nicht, wer oder was\nes ist.\n\nWird als depicts_override= in der Beschreibung gespeichert; der Upload\nläuft dann ohne depicts-Aussage.',
        'es': 'Solo relevante cuando el campo depicts de arriba queda vacío: elige POR QUÉ:\n\n«Sin elemento de Wikidata»: la persona o el motivo mostrado no tiene\nelemento (todavía).\n«No aplicable»: la imagen no muestra ningún motivo identificable.\n«Sin identificar»: hay un motivo, pero no sabes quién o qué es.\n\nSe guarda como depicts_override= en la descripción; la subida procede\nentonces sin declaración de depicts.',
        'fr': "Uniquement pertinent quand le champ depicts ci-dessus reste vide – choisissez\nPOURQUOI :\n\n« Pas d'élément Wikidata » : la personne ou le sujet montré n'a pas (encore)\nd'élément.\n« Non applicable » : l'image ne montre aucun sujet identifiable.\n« Non identifié » : il y a un sujet, mais vous ne savez pas qui ou quoi.\n\nEnregistré comme depicts_override= dans la description ; le téléversement\nse fait alors sans déclaration depicts.",
        'it': "Rilevante solo quando il campo depicts qui sopra resta vuoto: scegli PERCHÉ:\n\n«Nessun elemento Wikidata»: la persona o il soggetto mostrato non ha\n(ancora) un elemento.\n«Non applicabile»: l'immagine non mostra alcun soggetto identificabile.\n«Non identificato»: c'è un soggetto, ma non sai chi o cosa sia.\n\nSalvato come depicts_override= nella descrizione; il caricamento procede\nquindi senza dichiarazione depicts.",
    },
    'The part of the gallery page name that is specific to this batch,\ne.g. the event name: with suffix "Berlinale 2026" the uploads are\nlisted on <gallery prefix>/Berlinale 2026. Plain text, no brackets.': {
        'de': 'Der Teil des Galerieseiten-Namens, der zu dieser Serie gehört – z. B. der\nVeranstaltungsname: mit Suffix „Berlinale 2026" werden die Uploads auf\n<Galerie-Präfix>/Berlinale 2026 gelistet. Reiner Text, keine Klammern.',
        'es': 'La parte del nombre de la página de galería propia de esta serie, p. ej. el\nnombre del evento: con el sufijo «Berlinale 2026» las subidas se listan en\n<prefijo de galería>/Berlinale 2026. Texto simple, sin corchetes.',
        'fr': "La partie du nom de la page de galerie propre à cette série – p. ex. le nom\nde l'événement : avec le suffixe « Berlinale 2026 », les téléversements sont\nlistés sur <préfixe de galerie>/Berlinale 2026. Texte brut, sans crochets.",
        'it': "La parte del nome della pagina di galleria propria di questa serie, ad es.\nil nome dell'evento: con il suffisso «Berlinale 2026» i caricamenti sono\nelencati su <prefisso galleria>/Berlinale 2026. Testo semplice, senza\nparentesi.",
    },
    'Where the file comes from. For your own photographs enter {{own}} -\nthe template that renders as "Own work".\n\nOnly for third-party material would a description or web address of the\norigin go here instead.': {
        'de': 'Woher die Datei stammt. Für eigene Fotografien {{own}} eintragen – die\nVorlage, die als „Eigenes Werk" angezeigt wird.\n\nNur bei fremdem Material stünde hier stattdessen eine Beschreibung oder\nWebadresse der Herkunft.',
        'es': 'De dónde procede el archivo. Para fotografías propias introduce {{own}}:\nla plantilla que se muestra como «Trabajo propio».\n\nSolo con material ajeno iría aquí en su lugar una descripción o dirección\nweb del origen.',
        'fr': "D'où vient le fichier. Pour vos propres photographies, saisissez {{own}} –\nle modèle affiché comme « Travail personnel ».\n\nSeul du matériel tiers appellerait ici une description ou une adresse web\nde l'origine.",
        'it': "Da dove proviene il file. Per fotografie proprie inserisci {{own}}: il\ntemplate mostrato come «Opera propria».\n\nSolo per materiale altrui andrebbe qui invece una descrizione o un\nindirizzo web dell'origine.",
    },
    'Evidence of permission, ONLY for the special case that a rights holder\nhas filed a release with the volunteer team - then the VRT ticket\ntemplate goes here.\n\nFor your own pictures under a free license this stays EMPTY; the\nlicense below is the permission.': {
        'de': 'Nachweis der Erlaubnis, NUR für den Sonderfall, dass ein Rechteinhaber\neine Freigabe beim Support-Team hinterlegt hat – dann gehört die\nVRT-Ticket-Vorlage hierher.\n\nFür eigene Bilder unter freier Lizenz bleibt das Feld LEER; die Lizenz\ndarunter ist die Erlaubnis.',
        'es': 'Prueba del permiso, SOLO para el caso especial de que un titular de derechos\nhaya presentado una autorización al equipo de voluntarios: entonces va aquí\nla plantilla del tique VRT.\n\nPara imágenes propias bajo licencia libre este campo queda VACÍO; la\nlicencia de abajo es el permiso.',
        'fr': "Preuve d'autorisation, UNIQUEMENT pour le cas particulier où un ayant droit\na déposé une autorisation auprès de l'équipe bénévole – le modèle du ticket\nVRT va alors ici.\n\nPour vos propres images sous licence libre, ce champ reste VIDE ; la licence\nci-dessous est l'autorisation.",
        'it': "Prova dell'autorizzazione, SOLO per il caso particolare in cui un titolare\ndei diritti abbia depositato una liberatoria presso il team di volontari:\nallora qui va il template del ticket VRT.\n\nPer immagini proprie sotto licenza libera questo campo resta VUOTO; la\nlicenza qui sotto è l'autorizzazione.",
    },
    'Colours:': {
        'de': 'Farben:', 'es': 'Colores:', 'fr': 'Couleurs :', 'it': 'Colori:',
    },
    'no label': {
        'de': 'kein Label', 'es': 'sin etiqueta', 'fr': 'sans label',
        'it': 'senza etichetta',
    },
    'colour {n}': {
        'de': 'Farbe {n}', 'es': 'color {n}', 'fr': 'couleur {n}',
        'it': 'colore {n}',
    },
    'Reload folder': {
        'de': 'Ordner neu laden', 'es': 'Recargar carpeta',
        'fr': 'Recharger le dossier', 'it': 'Ricarica cartella',
    },
    'Open…': {
        'de': 'Öffnen…', 'es': 'Abrir…', 'fr': 'Ouvrir…', 'it': 'Apri…',
    },
    'Open a folder of images for culling.': {
        'de': 'Einen Ordner mit Bildern zum Sichten öffnen.',
        'es': 'Abre una carpeta de imágenes para la selección.',
        'fr': 'Ouvre un dossier d’images pour le tri.',
        'it': 'Apre una cartella di immagini per la selezione.',
    },
    'Filter:': {
        'de': 'Filter:', 'es': 'Filtro:', 'fr': 'Filtre :', 'it': 'Filtro:',
    },
    'Show only images at or above this star rating.': {
        'de': 'Nur Bilder mit mindestens dieser Sternebewertung anzeigen.',
        'es': 'Mostrar solo imágenes con esta valoración de estrellas o superior.',
        'fr': 'N’afficher que les images ayant au moins cette note en étoiles.',
        'it': 'Mostra solo le immagini con questa valutazione a stelle o superiore.',
    },
    'Save to…': {
        'de': 'Speichern unter…', 'es': 'Guardar en…',
        'fr': 'Enregistrer dans…', 'it': 'Salva in…',
    },
    'Add to tabs': {
        'de': 'Übernehmen', 'es': 'Pasar a las pestañas',
        'fr': 'Vers les onglets', 'it': 'Passa alle schede',
    },
    '(takes effect after a restart)': {
        'de': '(wirksam nach Neustart)',
        'es': '(surte efecto tras reiniciar)',
        'fr': '(prend effet après un redémarrage)',
        'it': '(ha effetto dopo un riavvio)',
    },
    'Rename {count} files': {
        'de': '{count} Dateien umbenennen',
        'es': 'Renombrar {count} archivos',
        'fr': 'Renommer {count} fichiers',
        'it': 'Rinomina {count} file',
    },
    'Start number:': {
        'de': 'Startnummer:', 'es': 'Número inicial:',
        'fr': 'Numéro de départ :', 'it': 'Numero iniziale:',
    },
    'F2 renames; with several rows selected F2 opens the bulk rename.': {
        'de': 'F2 benennt um; bei mehreren markierten Zeilen öffnet F2 die '
              'Massenumbenennung.',
        'es': 'F2 renombra; con varias filas seleccionadas F2 abre el '
              'renombrado en masa.',
        'fr': 'F2 renomme ; avec plusieurs lignes sélectionnées, F2 ouvre le '
              'renommage en masse.',
        'it': 'F2 rinomina; con più righe selezionate F2 apre la '
              'rinomina in blocco.',
    },
    'Mark for Commons (CC)': {
        'de': 'Für Commons (CC) markieren',
        'es': 'Marcar para Commons (CC)',
        'fr': 'Marquer pour Commons (CC)',
        'it': 'Contrassegna per Commons (CC)',
    },
    'Mark for commercial use (FTP/Flickr)': {
        'de': 'Für kommerzielle Nutzung markieren (FTP/Flickr)',
        'es': 'Marcar para uso comercial (FTP/Flickr)',
        'fr': 'Marquer pour usage commercial (FTP/Flickr)',
        'it': 'Contrassegna per uso commerciale (FTP/Flickr)',
    },
    'Remove channel mark': {
        'de': 'Kanal-Markierung entfernen',
        'es': 'Quitar la marca de canal',
        'fr': 'Retirer le marquage de canal',
        'it': 'Rimuovi il contrassegno di canale',
    },
    'Marked for commercial use - excluded from the Commons upload.': {
        'de': 'Für kommerzielle Nutzung markiert – vom Commons-Upload '
              'ausgeschlossen.',
        'es': 'Marcado para uso comercial: excluido de la subida a Commons.',
        'fr': 'Marqué pour usage commercial – exclu de l’envoi vers Commons.',
        'it': 'Contrassegnato per uso commerciale: escluso dal caricamento '
              'su Commons.',
    },
    'Marked for Commons (CC).': {
        'de': 'Für Commons (CC) markiert.',
        'es': 'Marcado para Commons (CC).',
        'fr': 'Marqué pour Commons (CC).',
        'it': 'Contrassegnato per Commons (CC).',
    },
    'Marked for Commons (CC) - excluded from commercial uploads (FTP/Flickr).': {
        'de': 'Für Commons (CC) markiert – von kommerziellen Uploads '
              '(FTP/Flickr) ausgeschlossen.',
        'es': 'Marcado para Commons (CC): excluido de las subidas '
              'comerciales (FTP/Flickr).',
        'fr': 'Marqué pour Commons (CC) – exclu des envois commerciaux '
              '(FTP/Flickr).',
        'it': 'Contrassegnato per Commons (CC): escluso dai caricamenti '
              'commerciali (FTP/Flickr).',
    },
    'Marked for commercial use.': {
        'de': 'Für kommerzielle Nutzung markiert.',
        'es': 'Marcado para uso comercial.',
        'fr': 'Marqué pour usage commercial.',
        'it': 'Contrassegnato per uso commerciale.',
    },
    '{n} file(s) excluded (marked for Commons).': {
        'de': '{n} Datei(en) ausgeschlossen (für Commons markiert).',
        'es': '{n} archivo(s) excluido(s) (marcados para Commons).',
        'fr': '{n} fichier(s) exclu(s) (marqués pour Commons).',
        'it': '{n} file esclusi (contrassegnati per Commons).',
    },
    'Read the current folder again from disk.': {
        'de': 'Den aktuellen Ordner erneut von der Festplatte einlesen.',
        'es': 'Vuelve a leer la carpeta actual desde el disco.',
        'fr': 'Relit le dossier actuel depuis le disque.',
        'it': 'Rilegge la cartella corrente dal disco.',
    },
    'No folder is open yet.': {
        'de': 'Es ist noch kein Ordner geöffnet.',
        'es': 'Aún no hay ninguna carpeta abierta.',
        'fr': 'Aucun dossier n’est encore ouvert.',
        'it': 'Nessuna cartella ancora aperta.',
    },
    'Apply': {
        'de': 'Übernehmen', 'es': 'Aplicar', 'fr': 'Appliquer',
        'it': 'Applica',
    },
    'Adds the selected images (or all filtered images when nothing is selected) to the MediaWiki, IPTC and FTP tabs. Nothing is uploaded yet.': {
        'de': 'Fügt die ausgewählten Bilder (oder alle gefilterten Bilder, wenn nichts ausgewählt ist) den Tabs MediaWiki, IPTC und FTP hinzu. Es wird noch nichts hochgeladen.',
        'es': 'Añade las imágenes seleccionadas (o todas las filtradas si no hay selección) a las pestañas MediaWiki, IPTC y FTP. Aún no se sube nada.',
        'fr': 'Ajoute les images sélectionnées (ou toutes les images filtrées si aucune sélection) aux onglets MediaWiki, IPTC et FTP. Rien n’est encore envoyé.',
        'it': 'Aggiunge le immagini selezionate (o tutte quelle filtrate se non c’è selezione) alle schede MediaWiki, IPTC e FTP. Non viene ancora caricato nulla.',
    },
    'Create one at Special:BotPasswords and log in with the name shown there (e.g. YourName@Cammello). Required grants: edit existing pages; create, edit and move pages; upload new files; upload, replace and move files.': {
        'de': 'Erstelle eines unter Special:BotPasswords und melde dich mit dem dort angezeigten Namen an (z. B. DeinName@Cammello). Nötige Rechte: bestehende Seiten bearbeiten; Seiten erstellen, bearbeiten und verschieben; neue Dateien hochladen; Dateien hochladen, ersetzen und verschieben.',
        'es': 'Crea una en Special:BotPasswords e inicia sesión con el nombre que se muestra allí (p. ej. TuNombre@Cammello). Permisos necesarios: editar páginas existentes; crear, editar y mover páginas; subir archivos nuevos; subir, reemplazar y mover archivos.',
        'fr': 'Créez-en un sur Special:BotPasswords et connectez-vous avec le nom qui y est indiqué (par ex. VotreNom@Cammello). Droits requis : modifier des pages existantes ; créer, modifier et déplacer des pages ; importer de nouveaux fichiers ; importer, remplacer et déplacer des fichiers.',
        'it': 'Creane una su Special:BotPasswords e accedi con il nome mostrato lì (es. TuoNome@Cammello). Permessi necessari: modificare pagine esistenti; creare, modificare e spostare pagine; caricare nuovi file; caricare, sostituire e spostare file.',
    },
    'The password is stored in your system keyring - leave it empty to be asked at login instead.': {
        'de': 'Das Passwort wird im Schlüsselbund deines Systems gespeichert – leer lassen, um stattdessen beim Login danach gefragt zu werden.',
        'es': 'La contraseña se guarda en el llavero del sistema; déjala vacía para que se pida al iniciar sesión.',
        'fr': 'Le mot de passe est stocké dans le trousseau du système ; laissez-le vide pour qu’il soit demandé à la connexion.',
        'it': 'La password viene salvata nel portachiavi di sistema; lasciala vuota per farla chiedere all’accesso.',
    },
    'No system keyring available, so the password is stored in plain text - leave it empty to be asked at login instead.': {
        'de': 'Kein System-Schlüsselbund verfügbar, daher wird das Passwort im Klartext gespeichert – leer lassen, um stattdessen beim Login danach gefragt zu werden.',
        'es': 'No hay llavero del sistema disponible, por lo que la contraseña se guarda en texto plano; déjala vacía para que se pida al iniciar sesión.',
        'fr': 'Aucun trousseau système disponible, le mot de passe est donc stocké en clair ; laissez-le vide pour qu’il soit demandé à la connexion.',
        'it': 'Nessun portachiavi di sistema disponibile, quindi la password viene salvata in chiaro; lasciala vuota per farla chiedere all’accesso.',
    },
    'Person shown -> depicts + category': {
        'de': 'Abgebildete Person -> Depicts + Kategorie',
        'es': 'Persona mostrada -> depicts + categoría',
        'fr': 'Personne représentée -> depicts + catégorie',
        'it': 'Persona ritratta -> depicts + categoria',
    },
    'For each person shown: pick the Wikidata item, then add both a depicts (P180) statement and a category (Commons category P373, or the name).': {
        'de': 'Für jede abgebildete Person das Wikidata-Objekt wählen; fügt dann sowohl eine Depicts-Aussage (P180) als auch eine Kategorie hinzu (Commons-Kategorie P373, sonst der Name).',
        'es': 'Para cada persona mostrada, elige el elemento de Wikidata; añade tanto una declaración depicts (P180) como una categoría (categoría de Commons P373, o el nombre).',
        'fr': 'Pour chaque personne représentée, choisissez l’élément Wikidata ; ajoute à la fois une déclaration depicts (P180) et une catégorie (catégorie Commons P373, sinon le nom).',
        'it': 'Per ogni persona ritratta, scegli l’elemento Wikidata; aggiunge sia una dichiarazione depicts (P180) sia una categoria (categoria Commons P373, altrimenti il nome).',
    },
    'Event -> created during + category': {
        'de': 'Event -> Entstanden während + Kategorie',
        'es': 'Evento -> creado durante + categoría',
        'fr': 'Événement -> créé lors de + catégorie',
        'it': 'Evento -> creato durante + categoria',
    },
    'Pick the Wikidata item for the event, then set "created during" (P10408) and add a category (Commons category P373, or the name).': {
        'de': 'Wikidata-Objekt für das Event wählen; setzt dann „Entstanden während" (P10408) und fügt eine Kategorie hinzu (Commons-Kategorie P373, sonst der Name).',
        'es': 'Elige el elemento de Wikidata para el evento; establece «creado durante» (P10408) y añade una categoría (categoría de Commons P373, o el nombre).',
        'fr': 'Choisissez l’élément Wikidata pour l’événement ; définit « créé lors de » (P10408) et ajoute une catégorie (catégorie Commons P373, sinon le nom).',
        'it': 'Scegli l’elemento Wikidata per l’evento; imposta "creato durante" (P10408) e aggiunge una categoria (categoria Commons P373, altrimenti il nome).',
    },
    '{n} depicts': {
        'de': '{n} Depicts', 'es': '{n} depicts', 'fr': '{n} depicts',
        'it': '{n} depicts',
    },
    '{n} categories': {
        'de': '{n} Kategorien', 'es': '{n} categorías',
        'fr': '{n} catégories', 'it': '{n} categorie',
    },
    'created during {qid}': {
        'de': 'Entstanden während {qid}', 'es': 'creado durante {qid}',
        'fr': 'créé lors de {qid}', 'it': 'creato durante {qid}',
    },
    'Person shown: added {what}.': {
        'de': 'Abgebildete Person: {what} hinzugefügt.',
        'es': 'Persona mostrada: se añadió {what}.',
        'fr': 'Personne représentée : {what} ajouté(s).',
        'it': 'Persona ritratta: aggiunti {what}.',
    },
    'Event: added {what}.': {
        'de': 'Event: {what} hinzugefügt.',
        'es': 'Evento: se añadió {what}.',
        'fr': 'Événement : {what} ajouté(s).',
        'it': 'Evento: aggiunti {what}.',
    },
    'Creator / rights / contact (same for all images)': {
        'de': 'Urheber / Rechte / Kontakt (für alle Bilder gleich)',
        'es': 'Autor / derechos / contacto (igual para todas las imágenes)',
        'fr': 'Créateur / droits / contact (identique pour toutes les images)',
        'it': 'Autore / diritti / contatto (uguale per tutte le immagini)',
    },
    'Event -> created during': {
        'de': 'Event -> Entstanden während',
        'es': 'Evento -> creado durante',
        'fr': 'Événement -> créé lors de',
        'it': 'Evento -> creato durante',
    },
    'Event -> category': {
        'de': 'Event -> Kategorie', 'es': 'Evento -> categoría',
        'fr': 'Événement -> catégorie', 'it': 'Evento -> categoria',
    },
    'No event in this file.': {
        'de': 'Kein Event in dieser Datei.',
        'es': 'No hay ningún evento en este archivo.',
        'fr': 'Aucun événement dans ce fichier.',
        'it': 'Nessun evento in questo file.',
    },
    'Set "created during" (P10408) to {qid} from the event.': {
        'de': '„Entstanden während" (P10408) aus dem Event auf {qid} gesetzt.',
        'es': 'Se estableció «creado durante» (P10408) en {qid} a partir del evento.',
        'fr': '« Créé lors de » (P10408) défini sur {qid} à partir de l’événement.',
        'it': '"Creato durante" (P10408) impostato su {qid} dall’evento.',
    },
    'Added {n} categor(y/ies) from the event.': {
        'de': '{n} Kategorie(n) aus dem Event hinzugefügt.',
        'es': 'Se añadieron {n} categoría(s) del evento.',
        'fr': '{n} catégorie(s) ajoutée(s) depuis l’événement.',
        'it': 'Aggiunte {n} categoria/e dall’evento.',
    },
    'Event': {
        'de': 'Event', 'es': 'Evento', 'fr': 'Événement', 'it': 'Evento',
    },
    'E-mail': {
        'de': 'E-Mail', 'es': 'Correo electrónico', 'fr': 'E-mail',
        'it': 'E-mail',
    },
    'Phone': {
        'de': 'Telefon', 'es': 'Teléfono', 'fr': 'Téléphone',
        'it': 'Telefono',
    },
    'Website': {
        'de': 'Website', 'es': 'Sitio web', 'fr': 'Site web',
        'it': 'Sito web',
    },
    'Street': {
        'de': 'Straße', 'es': 'Calle', 'fr': 'Rue', 'it': 'Via',
    },
    'Postal code': {
        'de': 'PLZ', 'es': 'Código postal', 'fr': 'Code postal',
        'it': 'CAP',
    },
    'Person shown': {
        'de': 'Abgebildete Person', 'es': 'Persona mostrada',
        'fr': 'Personne représentée', 'it': 'Persona ritratta',
    },
    'Person shown -> categories': {
        'de': 'Abgebildete Person -> Kategorien',
        'es': 'Persona mostrada -> categorías',
        'fr': 'Personne représentée -> catégories',
        'it': 'Persona ritratta -> categorie',
    },
    'Person shown -> depicts': {
        'de': 'Abgebildete Person -> Depicts',
        'es': 'Persona mostrada -> depicts',
        'fr': 'Personne représentée -> depicts',
        'it': 'Persona ritratta -> depicts',
    },
    'No person shown in this file.': {
        'de': 'Keine abgebildete Person in dieser Datei.',
        'es': 'No hay ninguna persona mostrada en este archivo.',
        'fr': 'Aucune personne représentée dans ce fichier.',
        'it': 'Nessuna persona ritratta in questo file.',
    },
    'Add {n} person(s) as categories.': {
        'de': '{n} Person(en) als Kategorien hinzufügen.',
        'es': 'Añadir {n} persona(s) como categorías.',
        'fr': 'Ajouter {n} personne(s) comme catégories.',
        'it': 'Aggiungere {n} persona/e come categorie.',
    },
    'Directly by name': {
        'de': 'Direkt über den Namen', 'es': 'Directamente por el nombre',
        'fr': 'Directement par le nom', 'it': 'Direttamente dal nome',
    },
    'Look up on Wikidata': {
        'de': 'In Wikidata nachschlagen', 'es': 'Buscar en Wikidata',
        'fr': 'Rechercher dans Wikidata', 'it': 'Cerca in Wikidata',
    },
    'Added {n} categor(y/ies) from person shown.': {
        'de': '{n} Kategorie(n) aus abgebildeter Person hinzugefügt.',
        'es': 'Se añadieron {n} categoría(s) de la persona mostrada.',
        'fr': '{n} catégorie(s) ajoutée(s) depuis la personne représentée.',
        'it': 'Aggiunte {n} categoria/e dalla persona ritratta.',
    },
    'Added {n} depicts (P180) statement(s) from person shown.': {
        'de': '{n} Depicts-Aussage(n) (P180) aus abgebildeter Person hinzugefügt.',
        'es': 'Se añadieron {n} declaración(es) depicts (P180) de la persona mostrada.',
        'fr': '{n} déclaration(s) depicts (P180) ajoutée(s) depuis la personne représentée.',
        'it': 'Aggiunte {n} dichiarazione/i depicts (P180) dalla persona ritratta.',
    },
    'Pick the matching Wikidata item for each person:': {
        'de': 'Wähle für jede Person das passende Wikidata-Objekt:',
        'es': 'Elige el elemento de Wikidata correspondiente para cada persona:',
        'fr': 'Choisissez l’élément Wikidata correspondant pour chaque personne :',
        'it': 'Scegli l’elemento Wikidata corrispondente per ogni persona:',
    },
    'Use the name as the category': {
        'de': 'Den Namen als Kategorie verwenden',
        'es': 'Usar el nombre como categoría',
        'fr': 'Utiliser le nom comme catégorie',
        'it': 'Usa il nome come categoria',
    },
    'Searching…': {
        'de': 'Suche läuft…', 'es': 'Buscando…', 'fr': 'Recherche…',
        'it': 'Ricerca…',
    },
    '(skip)': {
        'de': '(überspringen)', 'es': '(omitir)', 'fr': '(ignorer)',
        'it': '(salta)',
    },
    'Wikimedia sign-in (OAuth)': {
        'de': 'Wikimedia-Anmeldung (OAuth)',
        'es': 'Inicio de sesión en Wikimedia (OAuth)',
        'fr': 'Connexion Wikimedia (OAuth)',
        'it': 'Accesso Wikimedia (OAuth)',
    },
    'Sign in with Wikimedia (OAuth)…': {
        'de': 'Mit Wikimedia anmelden (OAuth)…',
        'es': 'Iniciar sesión con Wikimedia (OAuth)…',
        'fr': 'Se connecter avec Wikimedia (OAuth)…',
        'it': 'Accedi con Wikimedia (OAuth)…',
    },
    'Cammello asks Wikimedia for permission to upload and edit on Commons in your name. No password is entered in Cammello. Open the link in any browser on this computer where you are signed in to Wikimedia - a second browser works too; Cammello receives the confirmation automatically.': {
        'de': 'Cammello bittet Wikimedia um die Erlaubnis, in deinem Namen auf Commons hochzuladen und zu bearbeiten. In Cammello wird kein Passwort eingegeben. Öffne den Link in einem beliebigen Browser auf diesem Rechner, in dem du bei Wikimedia angemeldet bist – auch ein Zweitbrowser funktioniert; Cammello erhält die Bestätigung automatisch.',
        'es': 'Cammello pide a Wikimedia permiso para subir y editar en Commons en tu nombre. En Cammello no se introduce ninguna contraseña. Abre el enlace en cualquier navegador de este equipo en el que hayas iniciado sesión en Wikimedia; también sirve un segundo navegador. Cammello recibe la confirmación automáticamente.',
        'fr': 'Cammello demande à Wikimedia la permission de téléverser et de modifier sur Commons en votre nom. Aucun mot de passe n’est saisi dans Cammello. Ouvrez le lien dans n’importe quel navigateur de cet ordinateur où vous êtes connecté à Wikimedia – un second navigateur convient aussi ; Cammello reçoit la confirmation automatiquement.',
        'it': 'Cammello chiede a Wikimedia il permesso di caricare e modificare su Commons a tuo nome. In Cammello non si inserisce alcuna password. Apri il link in un qualsiasi browser di questo computer in cui hai effettuato l’accesso a Wikimedia – va bene anche un secondo browser; Cammello riceve la conferma automaticamente.',
    },
    'Show the link only - do not open the default browser': {
        'de': 'Link nur anzeigen – Standardbrowser nicht öffnen',
        'es': 'Mostrar solo el enlace: no abrir el navegador predeterminado',
        'fr': 'Afficher seulement le lien – ne pas ouvrir le navigateur par défaut',
        'it': 'Mostra solo il link – non aprire il browser predefinito',
    },
    'Start authorization': {
        'de': 'Autorisierung starten',
        'es': 'Iniciar autorización',
        'fr': 'Démarrer l’autorisation',
        'it': 'Avvia autorizzazione',
    },
    '&File': {
        'de': '&Datei', 'es': '&Archivo', 'fr': '&Fichier', 'it': '&File',
    },
    '&Edit': {
        'de': '&Bearbeiten', 'es': '&Editar', 'fr': '&Édition',
        'it': '&Modifica',
    },
    '&View': {
        'de': '&Ansicht', 'es': '&Ver', 'fr': '&Affichage',
        'it': '&Visualizza',
    },
    '&Upload': {
        'de': '&Hochladen', 'es': '&Subir', 'fr': '&Envoi',
        'it': '&Caricamento',
    },
    '&Help': {
        'de': '&Hilfe', 'es': 'A&yuda', 'fr': '&Aide', 'it': '&Aiuto',
    },
    '&Open folder…': {
        'de': 'Ordner &öffnen…', 'es': 'Abrir &carpeta…',
        'fr': 'Ouvrir un &dossier…', 'it': 'Apri &cartella…',
    },
    '&Reload folder': {
        'de': 'Ordner &neu laden', 'es': '&Recargar carpeta',
        'fr': '&Recharger le dossier', 'it': '&Ricarica cartella',
    },
    'Reload': {
        'de': 'Neu laden', 'es': 'Recargar', 'fr': 'Recharger',
        'it': 'Ricarica',
    },
    '&Add files…': {
        'de': 'Dateien &hinzufügen…', 'es': '&Añadir archivos…',
        'fr': '&Ajouter des fichiers…', 'it': '&Aggiungi file…',
    },
    '&Save selection to folder…': {
        'de': 'Auswahl in Ordner &speichern…',
        'es': '&Guardar la selección en una carpeta…',
        'fr': '&Enregistrer la sélection dans un dossier…',
        'it': '&Salva la selezione in una cartella…',
    },
    'Settings…': {
        'de': 'Einstellungen…', 'es': 'Configuración…',
        'fr': 'Préférences…', 'it': 'Impostazioni…',
    },
    '&Quit': {
        'de': '&Beenden', 'es': '&Salir', 'fr': '&Quitter', 'it': '&Esci',
    },
    '&Rename…': {
        'de': '&Umbenennen…', 'es': '&Renombrar…', 'fr': '&Renommer…',
        'it': '&Rinomina…',
    },
    'Remove &selected': {
        'de': 'Aus&wahl entfernen', 'es': 'Eliminar lo &seleccionado',
        'fr': 'Supprimer la &sélection', 'it': 'Rimuovi &selezionati',
    },
    '&Clear all': {
        'de': '&Alle entfernen', 'es': '&Vaciar todo', 'fr': '&Tout effacer',
        'it': '&Rimuovi tutto',
    },
    'Clear &base description': {
        'de': '&Basisbeschreibung leeren',
        'es': 'Vaciar la descripción &base',
        'fr': 'Effacer la description de &base',
        'it': 'Svuota la descrizione di &base',
    },
    'Channel &mark': {
        'de': '&Kanal-Markierung', 'es': '&Marca de canal',
        'fr': '&Marquage de canal', 'it': '&Contrassegno di canale',
    },
    'About Cammello': {
        'de': 'Über Cammello', 'es': 'Acerca de Cammello',
        'fr': 'À propos de Cammello', 'it': 'Informazioni su Cammello',
    },
    'Yellow': {
        'de': 'Gelb', 'es': 'Amarillo', 'fr': 'Jaune', 'it': 'Giallo',
    },
    'Rejected': {
        'de': 'Aussortiert', 'es': 'Rechazada',
        'fr': 'Rejetée', 'it': 'Scartata',
    },
    'Red': {
        'de': 'Rot', 'es': 'Rojo', 'fr': 'Rouge', 'it': 'Rosso',
    },
    'Purple': {
        'de': 'Violett', 'es': 'Violeta', 'fr': 'Violet', 'it': 'Viola',
    },
    'No stars': {
        'de': 'Keine Sterne', 'es': 'Sin estrellas',
        'fr': 'Aucune étoile', 'it': 'Nessuna stella',
    },
    'Green': {
        'de': 'Grün', 'es': 'Verde', 'fr': 'Vert', 'it': 'Verde',
    },
    'No label': {
        'de': 'Keine Markierung', 'es': 'Sin etiqueta',
        'fr': 'Aucun libellé', 'it': 'Nessuna etichetta',
    },
    'M toggles the digit keys between stars and colors; in color mode 5 is purple.': {
        'de': 'M schaltet die Zifferntasten zwischen Sternen und Farben um; '
              'im Farbmodus ist 5 Violett.',
        'es': 'M alterna las teclas numéricas entre estrellas y colores; en '
              'modo color, 5 es violeta.',
        'fr': 'M bascule les touches numériques entre étoiles et couleurs ; '
              'en mode couleur, 5 correspond au violet.',
        'it': 'M alterna i tasti numerici tra stelle e colori; in modalità '
              'colore 5 è viola.',
    },
    'Blue': {
        'de': 'Blau', 'es': 'Azul', 'fr': 'Bleu', 'it': 'Blu',
    },
    'C&lear list': {
        'de': '&Liste leeren', 'es': '&Vaciar la lista',
        'fr': 'Vider la &liste', 'it': 'Svuota l&’elenco',
    },
    'Not logged in – sign in': {
        'de': 'Nicht angemeldet – jetzt anmelden',
        'es': 'Sin sesión: iniciar sesión',
        'fr': 'Non connecté – se connecter',
        'it': 'Non connesso – accedi',
    },
    'Logging in…': {
        'de': 'Anmeldung läuft…', 'es': 'Iniciando sesión…',
        'fr': 'Connexion…', 'it': 'Accesso in corso…',
    },
    'Modules': {
        'de': 'Module', 'es': 'Módulos', 'fr': 'Modules', 'it': 'Moduli',
    },
    'Show these modules (applies after restart):': {
        'de': 'Diese Module anzeigen (gilt nach Neustart):',
        'es': 'Mostrar estos módulos (se aplica tras reiniciar):',
        'fr': 'Afficher ces modules (au redémarrage) :',
        'it': 'Mostra questi moduli (si applica al riavvio):',
    },
    'Author and license': {
        'de': 'Urheber und Lizenz', 'es': 'Autoría y licencia',
        'fr': 'Auteur et licence', 'it': 'Autore e licenza',
    },
    'Bot password…': {
        'de': 'Bot-Passwort…', 'es': 'Contraseña de bot…',
        'fr': 'Mot de passe bot…', 'it': 'Password bot…',
    },
    'Bot password': {
        'de': 'Bot-Passwort', 'es': 'Contraseña de bot',
        'fr': 'Mot de passe bot', 'it': 'Password bot',
    },
    'Fallback sign-in with a bot password - independent of the OAuth consumer.': {
        'de': 'Ersatz-Anmeldung mit Bot-Passwort – unabhängig vom '
              'OAuth-Consumer.',
        'es': 'Inicio de sesión alternativo con contraseña de bot, '
              'independiente del consumidor OAuth.',
        'fr': 'Connexion de secours par mot de passe bot – indépendante du '
              'consommateur OAuth.',
        'it': 'Accesso di riserva con password bot – indipendente dal '
              'consumer OAuth.',
    },
    '&Metadata': {
        'de': '&Metadaten', 'es': '&Metadatos',
        'fr': '&Métadonnées', 'it': '&Metadati',
    },
    '&Rating': {
        'de': '&Bewertung', 'es': '&Valoración',
        'fr': '&Note', 'it': '&Valutazione',
    },
    '&Color label': {
        'de': '&Farbmarkierung', 'es': 'Etiqueta de &color',
        'fr': 'Libellé de &couleur', 'it': 'Etichetta &colore',
    },
    '&Settings…': {
        'de': '&Einstellungen…', 'es': '&Configuración…',
        'fr': '&Préférences…', 'it': '&Impostazioni…',
    },
    '&Bulk edit selected': {
        'de': 'Auswahl &massenbearbeiten',
        'es': 'Edición en &lote de la selección',
        'fr': 'Édition en &lot de la sélection',
        'it': 'Modifica in &blocco della selezione',
    },
    '&Clear': {
        'de': '&Leeren', 'es': '&Vaciar', 'fr': '&Effacer', 'it': '&Svuota',
    },
    'Show only images with {n} stars or more (click again for all).': {
        'de': 'Nur Bilder mit {n} Sternen oder mehr zeigen (nochmal klicken '
              'für alle).',
        'es': 'Mostrar solo imágenes con {n} estrellas o más (haz clic de '
              'nuevo para todas).',
        'fr': 'N’afficher que les images avec {n} étoiles ou plus (cliquez à '
              'nouveau pour tout afficher).',
        'it': 'Mostra solo immagini con {n} stelle o più (clicca di nuovo '
              'per tutte).',
    },
    '&Fullscreen': {
        'de': '&Vollbild', 'es': 'Pantalla &completa',
        'fr': 'Plein &écran', 'it': 'Schermo &intero',
    },
    '&Loupe view': {
        'de': '&Lupenansicht', 'es': 'Vista de &lupa',
        'fr': 'Vue &loupe', 'it': 'Vista &lente',
    },
    'Single image, fitted to the window (E).': {
        'de': 'Einzelbild, ins Fenster eingepasst (E).',
        'es': 'Imagen única, ajustada a la ventana (E).',
        'fr': 'Image seule, ajustée à la fenêtre (E).',
        'it': 'Immagine singola, adattata alla finestra (E).',
    },
    '&Grid view': {
        'de': '&Rasteransicht', 'es': 'Vista de &cuadrícula',
        'fr': 'Vue en &grille', 'it': 'Vista a &griglia',
    },
    'Grid view: thumbnails instead of the large image (G).': {
        'de': 'Rasteransicht: Miniaturen statt des großen Bildes (G).',
        'es': 'Vista de cuadrícula: miniaturas en vez de la imagen grande (G).',
        'fr': 'Vue en grille : vignettes au lieu de la grande image (G).',
        'it': 'Vista a griglia: miniature invece dell’immagine grande (G).',
    },
    '&Test connection': {
        'de': 'Verbindung &testen', 'es': '&Probar la conexión',
        'fr': '&Tester la connexion', 'it': '&Prova la connessione',
    },
    'Show &log': {
        'de': '&Log anzeigen', 'es': 'Mostrar el &registro',
        'fr': 'Afficher le &journal', 'it': 'Mostra il &log',
    },
    'Remove every file from the list.': {
        'de': 'Entfernt alle Dateien aus der Liste.',
        'es': 'Quita todos los archivos de la lista.',
        'fr': 'Retire tous les fichiers de la liste.',
        'it': 'Rimuove tutti i file dall’elenco.',
    },
    'Zoom &in': {
        'de': '&Vergrößern', 'es': '&Acercar', 'fr': '&Zoom avant',
        'it': '&Ingrandisci',
    },
    'Zoom &out': {
        'de': 'Ver&kleinern', 'es': 'A&lejar', 'fr': 'Zoom a&rrière',
        'it': '&Riduci',
    },
    '&Log in…': {
        'de': '&Anmelden…', 'es': '&Iniciar sesión…', 'fr': '&Se connecter…',
        'it': '&Accedi…',
    },
    '&Upload to Commons': {
        'de': 'Zu Commons &hochladen', 'es': '&Subir a Commons',
        'fr': '&Envoyer vers Commons', 'it': '&Carica su Commons',
    },
    'Add culling selection to &tabs': {
        'de': 'Culling-Auswahl in die &Bereiche übernehmen',
        'es': 'Añadir la selección de culling a las &secciones',
        'fr': 'Ajouter la sélection du tri aux &sections',
        'it': 'Aggiungi la selezione del culling alle &sezioni',
    },
    '&About Cammello': {
        'de': '&Über Cammello', 'es': '&Acerca de Cammello',
        'fr': 'À &propos de Cammello', 'it': '&Informazioni su Cammello',
    },
    'Open &log file': {
        'de': '&Logdatei öffnen', 'es': 'Abrir el archivo de &registro',
        'fr': 'Ouvrir le fichier &journal', 'it': 'Apri il file di &log',
    },
    'Open log &folder': {
        'de': 'Log-&Ordner öffnen', 'es': 'Abrir la &carpeta de registros',
        'fr': 'Ouvrir le &dossier des journaux',
        'it': 'Apri la &cartella dei log',
    },
    '&Copy log': {
        'de': 'Log &kopieren', 'es': '&Copiar el registro',
        'fr': '&Copier le journal', 'it': '&Copia il log',
    },
    'Sign in to Wikimedia Commons.': {
        'de': 'Bei Wikimedia Commons anmelden.',
        'es': 'Iniciar sesión en Wikimedia Commons.',
        'fr': 'Se connecter à Wikimedia Commons.',
        'it': 'Accedi a Wikimedia Commons.',
    },
    'Add image files to the upload list.': {
        'de': 'Bilddateien zur Upload-Liste hinzufügen.',
        'es': 'Añadir archivos de imagen a la lista de subida.',
        'fr': 'Ajouter des fichiers image à la liste d’envoi.',
        'it': 'Aggiungi file immagine all’elenco di caricamento.',
    },
    'Copy the selected images to a folder.': {
        'de': 'Die ausgewählten Bilder in einen Ordner kopieren.',
        'es': 'Copiar las imágenes seleccionadas a una carpeta.',
        'fr': 'Copier les images sélectionnées dans un dossier.',
        'it': 'Copia le immagini selezionate in una cartella.',
    },
    'Rename the selected files for Commons.': {
        'de': 'Die ausgewählten Dateien für Commons umbenennen.',
        'es': 'Renombrar los archivos seleccionados para Commons.',
        'fr': 'Renommer les fichiers sélectionnés pour Commons.',
        'it': 'Rinomina i file selezionati per Commons.',
    },
    'The local port {port} needed for sign-in is already in use. Close the program using it, or tick "Enter the confirmation code manually" to sign in without it.': {
        'de': 'Der lokale Port {port} für die Anmeldung ist bereits belegt. '
              'Beende das Programm, das ihn nutzt, oder hake „Bestätigungscode '
              'manuell eingeben" an, um dich ohne ihn anzumelden.',
        'es': 'El puerto local {port} necesario para iniciar sesión ya está '
              'en uso. Cierra el programa que lo usa, o marca «Introducir el '
              'código de confirmación manualmente» para iniciar sesión sin él.',
        'fr': 'Le port local {port} nécessaire à la connexion est déjà '
              'utilisé. Fermez le programme qui l’utilise, ou cochez « Saisir '
              'le code de confirmation manuellement » pour vous connecter '
              'sans lui.',
        'it': 'La porta locale {port} necessaria per l’accesso è già in uso. '
              'Chiudi il programma che la usa, oppure seleziona «Inserisci '
              'manualmente il codice di conferma» per accedere senza di essa.',
    },
    'Confirmation code:': {
        'de': 'Bestätigungscode:',
        'es': 'Código de confirmación:',
        'fr': 'Code de confirmation :',
        'it': 'Codice di conferma:',
    },
    'paste the code shown after "Allow"': {
        'de': 'den nach „Zulassen" angezeigten Code einfügen',
        'es': 'pega el código mostrado tras «Permitir»',
        'fr': 'collez le code affiché après « Autoriser »',
        'it': 'incolla il codice mostrato dopo «Consenti»',
    },
    'Finish': {
        'de': 'Fertigstellen',
        'es': 'Finalizar',
        'fr': 'Terminer',
        'it': 'Completa',
    },
    'Requesting an authorization link…': {
        'de': 'Fordere einen Autorisierungslink an…',
        'es': 'Solicitando un enlace de autorización…',
        'fr': 'Demande d’un lien d’autorisation…',
        'it': 'Richiesta di un link di autorizzazione…',
    },
    'Completing sign-in…': {
        'de': 'Schließe die Anmeldung ab…',
        'es': 'Completando el inicio de sesión…',
        'fr': 'Finalisation de la connexion…',
        'it': 'Completamento dell’accesso…',
    },
    'Please paste the confirmation code first.': {
        'de': 'Bitte zuerst den Bestätigungscode einfügen.',
        'es': 'Primero pega el código de confirmación.',
        'fr': 'Veuillez d’abord coller le code de confirmation.',
        'it': 'Incolla prima il codice di conferma.',
    },
    'Authorization link:': {
        'de': 'Autorisierungslink:',
        'es': 'Enlace de autorización:',
        'fr': 'Lien d’autorisation :',
        'it': 'Link di autorizzazione:',
    },
    'Open in default browser': {
        'de': 'Im Standardbrowser öffnen',
        'es': 'Abrir en el navegador predeterminado',
        'fr': 'Ouvrir dans le navigateur par défaut',
        'it': 'Apri nel browser predefinito',
    },
    'Waiting for authorization in the browser…': {
        'de': 'Warte auf Autorisierung im Browser…',
        'es': 'Esperando la autorización en el navegador…',
        'fr': 'En attente de l’autorisation dans le navigateur…',
        'it': 'In attesa dell’autorizzazione nel browser…',
    },
    'Link copied.': {
        'de': 'Link kopiert.',
        'es': 'Enlace copiado.',
        'fr': 'Lien copié.',
        'it': 'Link copiato.',
    },
    'Remove authorization': {
        'de': 'Autorisierung entfernen',
        'es': 'Eliminar autorización',
        'fr': 'Supprimer l’autorisation',
        'it': 'Rimuovi autorizzazione',
    },
    'Authorization removed. To revoke it on the server side, visit Special:OAuthManageMyGrants.': {
        'de': 'Autorisierung entfernt. Zum serverseitigen Widerruf Special:OAuthManageMyGrants besuchen.',
        'es': 'Autorización eliminada. Para revocarla en el servidor, visita Special:OAuthManageMyGrants.',
        'fr': 'Autorisation supprimée. Pour la révoquer côté serveur, visitez Special:OAuthManageMyGrants.',
        'it': 'Autorizzazione rimossa. Per revocarla lato server, visita Special:OAuthManageMyGrants.',
    },
    'Authorization received. You can close this window and return to Cammello.': {
        'de': 'Autorisierung erhalten. Du kannst dieses Fenster schließen und zu Cammello zurückkehren.',
        'es': 'Autorización recibida. Puedes cerrar esta ventana y volver a Cammello.',
        'fr': 'Autorisation reçue. Vous pouvez fermer cette fenêtre et revenir à Cammello.',
        'it': 'Autorizzazione ricevuta. Puoi chiudere questa finestra e tornare a Cammello.',
    },
    'Authorization cancelled.': {
        'de': 'Autorisierung abgebrochen.',
        'es': 'Autorización cancelada.',
        'fr': 'Autorisation annulée.',
        'it': 'Autorizzazione annullata.',
    },
    'Authorization timed out.': {
        'de': 'Zeitüberschreitung bei der Autorisierung.',
        'es': 'Tiempo de espera de la autorización agotado.',
        'fr': 'Délai d’autorisation dépassé.',
        'it': 'Autorizzazione scaduta.',
    },
    'Tabs': {
        'de': 'Tabs',
        'es': 'Pestañas',
        'fr': 'Onglets',
        'it': 'Schede',
    },
    'Show these tabs (applies after restart):': {
        'de': 'Diese Tabs anzeigen (wirkt nach Neustart):',
        'es': 'Mostrar estas pestañas (se aplica al reiniciar):',
        'fr': 'Afficher ces onglets (prend effet au redémarrage) :',
        'it': 'Mostra queste schede (attivo dopo il riavvio):',
    },
    'Requires pyexiv2, which is not available.': {
        'de': 'Benötigt pyexiv2, das nicht verfügbar ist.',
        'es': 'Requiere pyexiv2, que no está disponible.',
        'fr': 'Nécessite pyexiv2, qui n’est pas disponible.',
        'it': 'Richiede pyexiv2, che non è disponibile.',
    },
    'Culling': {
        'de': 'Sichtung',
        'es': 'Selección',
        'fr': 'Tri',
        'it': 'Selezione',
    },
    'Settings': {
        'de': 'Einstellungen',
        'es': 'Ajustes',
        'fr': 'Réglages',
        'it': 'Impostazioni',
    },
    'Log': {
        'de': 'Protokoll',
        'es': 'Registro',
        'fr': 'Journal',
        'it': 'Registro',
    },
    'Appearance': {
        'de': 'Darstellung',
        'es': 'Apariencia',
        'fr': 'Apparence',
        'it': 'Aspetto',
    },
    'Language:': {
        'de': 'Sprache:',
        'es': 'Idioma:',
        'fr': 'Langue :',
        'it': 'Lingua:',
    },
    'Color scheme:': {
        'de': 'Farbschema:',
        'es': 'Esquema de color:',
        'fr': 'Thème de couleurs :',
        'it': 'Schema colori:',
    },
    'system': {
        'de': 'System',
        'es': 'sistema',
        'fr': 'système',
        'it': 'sistema',
    },
    'light': {
        'de': 'hell',
        'es': 'claro',
        'fr': 'clair',
        'it': 'chiaro',
    },
    'dark': {
        'de': 'dunkel',
        'es': 'oscuro',
        'fr': 'sombre',
        'it': 'scuro',
    },
    'The language change takes effect after a restart.': {
        'de': 'Die Sprachumstellung wirkt nach einem Neustart.',
        'es': 'El cambio de idioma se aplica tras reiniciar.',
        'fr': 'Le changement de langue prend effet après un redémarrage.',
        'it': 'Il cambio di lingua ha effetto dopo il riavvio.',
    },
    'Settings are saved when the window is closed.': {
        'de': 'Die Einstellungen werden beim Schließen des Fensters gespeichert.',
        'es': 'Los ajustes se guardan al cerrar la ventana.',
        'fr': 'Les réglages sont enregistrés à la fermeture de la fenêtre.',
        'it': 'Le impostazioni vengono salvate alla chiusura della finestra.',
    },
    'e.g.': {
        'de': 'z. B.',
        'es': 'p. ej.',
        'fr': 'p. ex.',
        'it': 'ad es.',
    },
    'Cancel': {
        'de': 'Abbrechen',
        'es': 'Cancelar',
        'fr': 'Annuler',
        'it': 'Annulla',
    },
    'Cancelled': {
        'de': 'Abgebrochen',
        'es': 'Cancelado',
        'fr': 'Annulé',
        'it': 'Annullato',
    },
    'Cancelling…': {
        'de': 'Wird abgebrochen…',
        'es': 'Cancelando…',
        'fr': 'Annulation…',
        'it': 'Annullamento…',
    },
    'Error': {
        'de': 'Fehler',
        'es': 'Error',
        'fr': 'Erreur',
        'it': 'Errore',
    },
    'Done': {
        'de': 'Fertig',
        'es': 'Listo',
        'fr': 'Terminé',
        'it': 'Fatto',
    },
    'Preparing…': {
        'de': 'Wird vorbereitet…',
        'es': 'Preparando…',
        'fr': 'Préparation…',
        'it': 'Preparazione…',
    },
    'Preview': {
        'de': 'Vorschau',
        'es': 'Vista previa',
        'fr': 'Aperçu',
        'it': 'Anteprima',
    },
    'Images': {
        'de': 'Bilder',
        'es': 'Imágenes',
        'fr': 'Images',
        'it': 'Immagini',
    },
    'Text files': {
        'de': 'Textdateien',
        'es': 'Archivos de texto',
        'fr': 'Fichiers texte',
        'it': 'File di testo',
    },
    'All files': {
        'de': 'Alle Dateien',
        'es': 'Todos los archivos',
        'fr': 'Tous les fichiers',
        'it': 'Tutti i file',
    },
    'Drag to resize the field': {
        'de': 'Ziehen, um die Feldhöhe zu ändern',
        'es': 'Arrastre para cambiar el tamaño del campo',
        'fr': 'Faites glisser pour redimensionner le champ',
        'it': 'Trascina per ridimensionare il campo',
    },
    'Source file': {
        'de': 'Quelldatei',
        'es': 'Archivo de origen',
        'fr': 'Fichier source',
        'it': 'File sorgente',
    },
    'Target filename (Commons)': {
        'de': 'Zieldateiname (Commons)',
        'es': 'Nombre de destino (Commons)',
        'fr': 'Nom de fichier cible (Commons)',
        'it': 'Nome file di destinazione (Commons)',
    },
    'Date': {
        'de': 'Datum',
        'es': 'Fecha',
        'fr': 'Date',
        'it': 'Data',
    },
    'Description (file, hidden)': {
        'de': 'Beschreibung (Datei, verborgen)',
        'es': 'Descripción (archivo, oculta)',
        'fr': 'Description (fichier, masquée)',
        'it': 'Descrizione (file, nascosta)',
    },
    'Wikitext': {
        'de': 'Wikitext',
        'es': 'Wikitexto',
        'fr': 'Wikitexte',
        'it': 'Wikitesto',
    },
    'Status': {
        'de': 'Status',
        'es': 'Estado',
        'fr': 'État',
        'it': 'Stato',
    },
    'Local source file (not modified).': {
        'de': 'Lokale Quelldatei (wird nicht verändert).',
        'es': 'Archivo de origen local (no se modifica).',
        'fr': 'Fichier source local (non modifié).',
        'it': 'File sorgente locale (non modificato).',
    },
    'Name under which the file is stored on Commons (without "File:"). The extension is taken from the source file and cannot be changed. Empty = source filename.': {
        'de': 'Name, unter dem die Datei auf Commons gespeichert wird (ohne „File:“). Die Endung stammt aus der Quelldatei und kann nicht geändert werden. Leer = Quelldateiname.',
        'es': 'Nombre con el que el archivo se guarda en Commons (sin «File:»). La extensión procede del archivo de origen y no se puede cambiar. Vacío = nombre del archivo de origen.',
        'fr': 'Nom sous lequel le fichier est enregistré sur Commons (sans « File: »). L’extension provient du fichier source et ne peut pas être modifiée. Vide = nom du fichier source.',
        'it': 'Nome con cui il file viene salvato su Commons (senza "File:"). L’estensione proviene dal file sorgente e non può essere modificata. Vuoto = nome del file sorgente.',
    },
    'Effective wikitext (upload settings + base description + this file). Read-only; shown at most {max_lines} lines high - hover a cell for the full text.': {
        'de': 'Effektiver Wikitext (Upload-Einstellungen + Basisbeschreibung + diese Datei). Nur lesbar; höchstens {max_lines} Zeilen hoch dargestellt – der vollständige Text erscheint im Tooltip.',
        'es': 'Wikitexto efectivo (ajustes de subida + descripción base + este archivo). Solo lectura; se muestran como máximo {max_lines} líneas: pase el ratón para ver el texto completo.',
        'fr': 'Wikitexte effectif (réglages d’envoi + description de base + ce fichier). En lecture seule ; affiché sur {max_lines} lignes au maximum – survolez la cellule pour le texte complet.',
        'it': 'Wikitesto effettivo (impostazioni di caricamento + descrizione base + questo file). Sola lettura; mostrato al massimo su {max_lines} righe: passa sopra la cella per il testo completo.',
    },
    'Login': {
        'de': 'Anmelden',
        'es': 'Iniciar sesión',
        'fr': 'Connexion',
        'it': 'Accedi',
    },
    'Login – Wikimedia Commons': {
        'de': 'Anmeldung – Wikimedia Commons',
        'es': 'Iniciar sesión – Wikimedia Commons',
        'fr': 'Connexion – Wikimedia Commons',
        'it': 'Accesso – Wikimedia Commons',
    },
    'Test connection': {
        'de': 'Verbindung testen',
        'es': 'Probar conexión',
        'fr': 'Tester la connexion',
        'it': 'Prova connessione',
    },
    'Not logged in': {
        'de': 'Nicht angemeldet',
        'es': 'Sin sesión iniciada',
        'fr': 'Non connecté',
        'it': 'Non connesso',
    },
    'Add files': {
        'de': 'Dateien hinzufügen',
        'es': 'Añadir archivos',
        'fr': 'Ajouter des fichiers',
        'it': 'Aggiungi file',
    },
    'Remove selected': {
        'de': 'Auswahl entfernen',
        'es': 'Quitar seleccionados',
        'fr': 'Retirer la sélection',
        'it': 'Rimuovi selezionati',
    },
    'Bulk edit selected': {
        'de': 'Auswahl gesammelt bearbeiten',
        'es': 'Editar en lote la selección',
        'fr': 'Édition groupée de la sélection',
        'it': 'Modifica in blocco la selezione',
    },
    'Clear all': {
        'de': 'Alles leeren',
        'es': 'Vaciar todo',
        'fr': 'Tout effacer',
        'it': 'Svuota tutto',
    },
    'Upload all': {
        'de': 'Alle hochladen',
        'es': 'Subir todo',
        'fr': 'Tout envoyer',
        'it': 'Carica tutto',
    },
    'Upload all ({n})': {
        'de': 'Alle hochladen ({n})',
        'es': 'Subir todo ({n})',
        'fr': 'Tout envoyer ({n})',
        'it': 'Carica tutto ({n})',
    },
    'Upload selected ({n})': {
        'de': 'Ausgewählte hochladen ({n})',
        'es': 'Subir selección ({n})',
        'fr': 'Envoyer la sélection ({n})',
        'it': 'Carica selezione ({n})',
    },
    'Ignore warnings (overwrite)': {
        'de': 'Warnungen ignorieren (überschreiben)',
        'es': 'Ignorar avisos (sobrescribir)',
        'fr': 'Ignorer les avertissements (écraser)',
        'it': 'Ignora avvisi (sovrascrivi)',
    },
    'Uploads the selected rows. Deselect everything to upload all files.': {
        'de': 'Lädt die ausgewählten Zeilen hoch. Auswahl aufheben, um alle Dateien hochzuladen.',
        'es': 'Sube las filas seleccionadas. Deseleccione todo para subir todos los archivos.',
        'fr': 'Envoie les lignes sélectionnées. Désélectionnez tout pour envoyer tous les fichiers.',
        'it': 'Carica le righe selezionate. Deseleziona tutto per caricare tutti i file.',
    },
    'Nothing is selected, so all files are uploaded. Select rows to upload only those.': {
        'de': 'Nichts ausgewählt – es werden alle Dateien hochgeladen. Zeilen auswählen, um nur diese hochzuladen.',
        'es': 'No hay selección: se suben todos los archivos. Seleccione filas para subir solo esas.',
        'fr': 'Rien n’est sélectionné : tous les fichiers sont envoyés. Sélectionnez des lignes pour n’envoyer que celles-ci.',
        'it': 'Nessuna selezione: vengono caricati tutti i file. Seleziona righe per caricare solo quelle.',
    },
    'Ready. Please log in first.': {
        'de': 'Bereit. Bitte zuerst anmelden.',
        'es': 'Listo. Inicie sesión primero.',
        'fr': 'Prêt. Veuillez d’abord vous connecter.',
        'it': 'Pronto. Accedi prima.',
    },
    'Please log in first.': {
        'de': 'Bitte zuerst anmelden.',
        'es': 'Inicie sesión primero.',
        'fr': 'Veuillez d’abord vous connecter.',
        'it': 'Accedi prima.',
    },
    'No files': {
        'de': 'Keine Dateien',
        'es': 'Sin archivos',
        'fr': 'Aucun fichier',
        'it': 'Nessun file',
    },
    'Please add files first.': {
        'de': 'Bitte zuerst Dateien hinzufügen.',
        'es': 'Añada archivos primero.',
        'fr': 'Veuillez d’abord ajouter des fichiers.',
        'it': 'Aggiungi prima dei file.',
    },
    'Select image files': {
        'de': 'Bilddateien auswählen',
        'es': 'Seleccionar archivos de imagen',
        'fr': 'Sélectionner des fichiers image',
        'it': 'Seleziona file immagine',
    },
    'Logged in as {username}': {
        'de': 'Angemeldet als {username}',
        'es': 'Sesión iniciada como {username}',
        'fr': 'Connecté en tant que {username}',
        'it': 'Connesso come {username}',
    },
    'Testing connection…': {
        'de': 'Verbindung wird getestet…',
        'es': 'Probando conexión…',
        'fr': 'Test de la connexion…',
        'it': 'Test della connessione…',
    },
    'Connection OK: {info}': {
        'de': 'Verbindung OK: {info}',
        'es': 'Conexión correcta: {info}',
        'fr': 'Connexion OK : {info}',
        'it': 'Connessione OK: {info}',
    },
    '{n} added': {
        'de': '{n} hinzugefügt',
        'es': '{n} añadidos',
        'fr': '{n} ajouté(s)',
        'it': '{n} aggiunti',
    },
    '{n} duplicate(s) skipped': {
        'de': '{n} Duplikat(e) übersprungen',
        'es': '{n} duplicado(s) omitido(s)',
        'fr': '{n} doublon(s) ignoré(s)',
        'it': '{n} duplicato/i ignorato/i',
    },
    '{n} skipped (see log)': {
        'de': '{n} übersprungen (siehe Protokoll)',
        'es': '{n} omitido(s) (ver registro)',
        'fr': '{n} ignoré(s) (voir le journal)',
        'it': '{n} ignorato/i (vedi registro)',
    },
    'Upload settings': {
        'de': 'Upload-Einstellungen',
        'es': 'Ajustes de subida',
        'fr': 'Réglages d’envoi',
        'it': 'Impostazioni di caricamento',
    },
    'MediaWiki upload': {
        'de': 'MediaWiki-Upload',
        'es': 'Subida a MediaWiki',
        'fr': 'Envoi MediaWiki',
        'it': 'Caricamento MediaWiki',
    },
    'Author:': {
        'de': 'Autor:',
        'es': 'Autor:',
        'fr': 'Auteur :',
        'it': 'Autore:',
    },
    'Creator (P170):': {
        'de': 'Urheber (P170):',
        'es': 'Creador (P170):',
        'fr': 'Créateur (P170) :',
        'it': 'Autore (P170):',
    },
    'Source:': {
        'de': 'Quelle:',
        'es': 'Fuente:',
        'fr': 'Source :',
        'it': 'Fonte:',
    },
    'Permission:': {
        'de': 'Genehmigung:',
        'es': 'Permiso:',
        'fr': 'Autorisation :',
        'it': 'Autorizzazione:',
    },
    'License (P275):': {
        'de': 'Lizenz (P275):',
        'es': 'Licencia (P275):',
        'fr': 'Licence (P275) :',
        'it': 'Licenza (P275):',
    },
    'Copyright (P6216):': {
        'de': 'Urheberrechtsstatus (P6216):',
        'es': 'Copyright (P6216):',
        'fr': 'Droit d’auteur (P6216) :',
        'it': 'Copyright (P6216):',
    },
    'Other templates:': {
        'de': 'Weitere Vorlagen:',
        'es': 'Otras plantillas:',
        'fr': 'Autres modèles :',
        'it': 'Altri template:',
    },
    'Other fields:': {
        'de': 'Weitere Felder:',
        'es': 'Otros campos:',
        'fr': 'Autres champs :',
        'it': 'Altri campi:',
    },
    'Gallery prefix:': {
        'de': 'Galerie-Präfix:',
        'es': 'Prefijo de galería:',
        'fr': 'Préfixe de galerie :',
        'it': 'Prefisso galleria:',
    },
    'HTTP timeout (s):': {
        'de': 'HTTP-Zeitlimit (s):',
        'es': 'Tiempo de espera HTTP (s):',
        'fr': 'Délai HTTP (s) :',
        'it': 'Timeout HTTP (s):',
    },
    'e.g. (leave empty unless needed)': {
        'de': 'z. B. (leer lassen, falls nicht nötig)',
        'es': 'p. ej. (dejar vacío si no hace falta)',
        'fr': 'p. ex. (laisser vide sauf si nécessaire)',
        'it': 'ad es. (lasciare vuoto se non serve)',
    },
    'Save settings': {
        'de': 'Einstellungen speichern',
        'es': 'Guardar ajustes',
        'fr': 'Enregistrer les réglages',
        'it': 'Salva impostazioni',
    },
    'Save the upload settings and the base description so they are restored next time.': {
        'de': 'Speichert die Upload-Einstellungen und die Basisbeschreibung, damit sie beim nächsten Start wieder da sind.',
        'es': 'Guarda los ajustes de subida y la descripción base para restaurarlos la próxima vez.',
        'fr': 'Enregistre les réglages d’envoi et la description de base pour les restaurer au prochain démarrage.',
        'it': 'Salva le impostazioni di caricamento e la descrizione base per ripristinarle al prossimo avvio.',
    },
    'Save to file…': {
        'de': 'In Datei speichern…',
        'es': 'Guardar en archivo…',
        'fr': 'Enregistrer dans un fichier…',
        'it': 'Salva su file…',
    },
    'Load from file…': {
        'de': 'Aus Datei laden…',
        'es': 'Cargar desde archivo…',
        'fr': 'Charger depuis un fichier…',
        'it': 'Carica da file…',
    },
    'Write settings + base description to a text file.': {
        'de': 'Schreibt Einstellungen und Basisbeschreibung in eine Textdatei.',
        'es': 'Escribe los ajustes y la descripción base en un archivo de texto.',
        'fr': 'Écrit les réglages et la description de base dans un fichier texte.',
        'it': 'Scrive impostazioni e descrizione base in un file di testo.',
    },
    'Read settings back from a text file.': {
        'de': 'Liest die Einstellungen aus einer Textdatei zurück.',
        'es': 'Lee de nuevo los ajustes desde un archivo de texto.',
        'fr': 'Relit les réglages depuis un fichier texte.',
        'it': 'Rilegge le impostazioni da un file di testo.',
    },
    'incl. selected file': {
        'de': 'inkl. ausgewählter Datei',
        'es': 'incl. archivo seleccionado',
        'fr': 'y compris le fichier sélectionné',
        'it': 'incl. file selezionato',
    },
    "Also write the selected file's description into the settings file.": {
        'de': 'Schreibt auch die Beschreibung der ausgewählten Datei in die Einstellungsdatei.',
        'es': 'Escribe también la descripción del archivo seleccionado en el archivo de ajustes.',
        'fr': 'Écrit aussi la description du fichier sélectionné dans le fichier de réglages.',
        'it': 'Scrive anche la descrizione del file selezionato nel file delle impostazioni.',
    },
    'Save settings to file': {
        'de': 'Einstellungen in Datei speichern',
        'es': 'Guardar ajustes en archivo',
        'fr': 'Enregistrer les réglages dans un fichier',
        'it': 'Salva le impostazioni su file',
    },
    'Load settings from file': {
        'de': 'Einstellungen aus Datei laden',
        'es': 'Cargar ajustes desde archivo',
        'fr': 'Charger les réglages depuis un fichier',
        'it': 'Carica le impostazioni da file',
    },
    'Save error': {
        'de': 'Fehler beim Speichern',
        'es': 'Error al guardar',
        'fr': 'Erreur d’enregistrement',
        'it': 'Errore di salvataggio',
    },
    'Load error': {
        'de': 'Fehler beim Laden',
        'es': 'Error al cargar',
        'fr': 'Erreur de chargement',
        'it': 'Errore di caricamento',
    },
    'Could not write the file:': {
        'de': 'Die Datei konnte nicht geschrieben werden:',
        'es': 'No se pudo escribir el archivo:',
        'fr': 'Impossible d’écrire le fichier :',
        'it': 'Impossibile scrivere il file:',
    },
    'Could not read the file:': {
        'de': 'Die Datei konnte nicht gelesen werden:',
        'es': 'No se pudo leer el archivo:',
        'fr': 'Impossible de lire le fichier :',
        'it': 'Impossibile leggere il file:',
    },
    'Settings saved.': {
        'de': 'Einstellungen gespeichert.',
        'es': 'Ajustes guardados.',
        'fr': 'Réglages enregistrés.',
        'it': 'Impostazioni salvate.',
    },
    'Settings saved to {path}': {
        'de': 'Einstellungen gespeichert unter {path}',
        'es': 'Ajustes guardados en {path}',
        'fr': 'Réglages enregistrés dans {path}',
        'it': 'Impostazioni salvate in {path}',
    },
    'Settings loaded from {path}.': {
        'de': 'Einstellungen geladen aus {path}.',
        'es': 'Ajustes cargados desde {path}.',
        'fr': 'Réglages chargés depuis {path}.',
        'it': 'Impostazioni caricate da {path}.',
    },
    'Saved. No single file selected, so no file description was included.': {
        'de': 'Gespeichert. Keine einzelne Datei ausgewählt, daher wurde keine Dateibeschreibung aufgenommen.',
        'es': 'Guardado. No hay un único archivo seleccionado, así que no se incluyó ninguna descripción de archivo.',
        'fr': 'Enregistré. Aucun fichier unique sélectionné : aucune description de fichier n’a été incluse.',
        'it': 'Salvato. Nessun singolo file selezionato, quindi non è stata inclusa alcuna descrizione del file.',
    },
    '(file description in the file was ignored: no single file selected)': {
        'de': '(die Dateibeschreibung in der Datei wurde ignoriert: keine einzelne Datei ausgewählt)',
        'es': '(se ignoró la descripción del archivo: no hay un único archivo seleccionado)',
        'fr': '(la description de fichier a été ignorée : aucun fichier unique sélectionné)',
        'it': '(la descrizione del file è stata ignorata: nessun singolo file selezionato)',
    },
    'Base description (for all files)': {
        'de': 'Basisbeschreibung (für alle Dateien)',
        'es': 'Descripción base (para todos los archivos)',
        'fr': 'Description de base (pour tous les fichiers)',
        'it': 'Descrizione base (per tutti i file)',
    },
    'Selected file(s) - description': {
        'de': 'Ausgewählte Datei(en) – Beschreibung',
        'es': 'Archivo(s) seleccionado(s) – descripción',
        'fr': 'Fichier(s) sélectionné(s) – description',
        'it': 'File selezionato/i – descrizione',
    },
    'Shared lines for every file, e.g.': {
        'de': 'Gemeinsame Zeilen für jede Datei, z. B.',
        'es': 'Líneas comunes para cada archivo, p. ej.',
        'fr': 'Lignes communes à chaque fichier, p. ex.',
        'it': 'Righe comuni per ogni file, ad es.',
    },
    'Expert mode (raw description_all text)': {
        'de': 'Expertenmodus (roher description_all-Text)',
        'es': 'Modo experto (texto description_all sin procesar)',
        'fr': 'Mode expert (texte description_all brut)',
        'it': 'Modalità esperto (testo description_all grezzo)',
    },
    'Edit the raw description_all text directly instead of using the structured single-line fields.': {
        'de': 'Den rohen description_all-Text direkt bearbeiten, statt die strukturierten Einzelfelder zu benutzen.',
        'es': 'Editar directamente el texto description_all en lugar de usar los campos estructurados.',
        'fr': 'Modifier directement le texte description_all au lieu d’utiliser les champs structurés.',
        'it': 'Modificare direttamente il testo description_all invece di usare i campi strutturati.',
    },
    'Select a single file to edit its description.': {
        'de': 'Eine einzelne Datei auswählen, um ihre Beschreibung zu bearbeiten.',
        'es': 'Seleccione un único archivo para editar su descripción.',
        'fr': 'Sélectionnez un seul fichier pour modifier sa description.',
        'it': 'Seleziona un singolo file per modificarne la descrizione.',
    },
    'Captions:': {
        'de': 'Bildunterschriften:',
        'es': 'Leyendas:',
        'fr': 'Légendes :',
        'it': 'Didascalie:',
    },
    'Add language': {
        'de': 'Sprache hinzufügen',
        'es': 'Añadir idioma',
        'fr': 'Ajouter une langue',
        'it': 'Aggiungi lingua',
    },
    'Remove this language': {
        'de': 'Diese Sprache entfernen',
        'es': 'Quitar este idioma',
        'fr': 'Supprimer cette langue',
        'it': 'Rimuovi questa lingua',
    },
    'Caption, e.g. Harald Krichel at the Berlinale 2026': {
        'de': 'Bildunterschrift, z. B. Harald Krichel auf der Berlinale 2026',
        'es': 'Leyenda, p. ej. Harald Krichel en la Berlinale 2026',
        'fr': 'Légende, p. ex. Harald Krichel à la Berlinale 2026',
        'it': 'Didascalia, ad es. Harald Krichel alla Berlinale 2026',
    },
    'Information wikitext for this language (uploaded as {{%s|1=…}})': {
        'de': 'Information-Wikitext für diese Sprache (wird als {{%s|1=…}} hochgeladen)',
        'es': 'Wikitexto Information para este idioma (se sube como {{%s|1=…}})',
        'fr': 'Wikitexte Information pour cette langue (envoyé comme {{%s|1=…}})',
        'it': 'Wikitesto Information per questa lingua (caricato come {{%s|1=…}})',
    },
    'Depicts (P180):': {
        'de': 'Zeigt (P180):',
        'es': 'Representa (P180):',
        'fr': 'Représente (P180) :',
        'it': 'Raffigura (P180):',
    },
    'Created during (P10408):': {
        'de': 'Entstanden während (P10408):',
        'es': 'Creado durante (P10408):',
        'fr': 'Créé lors de (P10408) :',
        'it': 'Creato durante (P10408):',
    },
    'Categories:': {
        'de': 'Kategorien:',
        'es': 'Categorías:',
        'fr': 'Catégories :',
        'it': 'Categorie:',
    },
    'Gallery suffix:': {
        'de': 'Galerie-Suffix:',
        'es': 'Sufijo de galería:',
        'fr': 'Suffixe de galerie :',
        'it': 'Suffisso galleria:',
    },
    'Extra wikitext / comments:': {
        'de': 'Zusätzlicher Wikitext / Kommentare:',
        'es': 'Wikitexto adicional / comentarios:',
        'fr': 'Wikitexte supplémentaire / commentaires :',
        'it': 'Wikitesto aggiuntivo / commenti:',
    },
    '# lines starting with # are comments and are not uploaded': {
        'de': '# Zeilen, die mit # beginnen, sind Kommentare und werden nicht hochgeladen',
        'es': '# las líneas que empiezan por # son comentarios y no se suben',
        'fr': '# les lignes commençant par # sont des commentaires et ne sont pas envoyées',
        'it': '# le righe che iniziano con # sono commenti e non vengono caricate',
    },
    'Bulk edit selected files': {
        'de': 'Ausgewählte Dateien gesammelt bearbeiten',
        'es': 'Editar en lote los archivos seleccionados',
        'fr': 'Édition groupée des fichiers sélectionnés',
        'it': 'Modifica in blocco dei file selezionati',
    },
    'Apply a value to the {n} selected file(s):': {
        'de': 'Einen Wert auf die {n} ausgewählte(n) Datei(en) anwenden:',
        'es': 'Aplicar un valor a los {n} archivo(s) seleccionado(s):',
        'fr': 'Appliquer une valeur aux {n} fichier(s) sélectionné(s) :',
        'it': 'Applica un valore ai {n} file selezionati:',
    },
    'Field:': {
        'de': 'Feld:',
        'es': 'Campo:',
        'fr': 'Champ :',
        'it': 'Campo:',
    },
    'Value:': {
        'de': 'Wert:',
        'es': 'Valor:',
        'fr': 'Valeur :',
        'it': 'Valore:',
    },
    'Depicts (P180)': {
        'de': 'Zeigt (P180)',
        'es': 'Representa (P180)',
        'fr': 'Représente (P180)',
        'it': 'Raffigura (P180)',
    },
    'Caption (en)': {
        'de': 'Bildunterschrift (en)',
        'es': 'Leyenda (en)',
        'fr': 'Légende (en)',
        'it': 'Didascalia (en)',
    },
    'Caption (de)': {
        'de': 'Bildunterschrift (de)',
        'es': 'Leyenda (de)',
        'fr': 'Légende (de)',
        'it': 'Didascalia (de)',
    },
    'Semicolon-separated QIDs; type a name to search Wikidata.': {
        'de': 'Durch Semikolon getrennte QIDs; einen Namen eingeben, um Wikidata zu durchsuchen.',
        'es': 'QID separados por punto y coma; escriba un nombre para buscar en Wikidata.',
        'fr': 'QID séparés par des points-virgules ; saisissez un nom pour chercher dans Wikidata.',
        'it': 'QID separati da punto e virgola; digita un nome per cercare in Wikidata.',
    },
    'Semicolon-separated, without [[Category:]].': {
        'de': 'Durch Semikolon getrennt, ohne [[Category:]].',
        'es': 'Separadas por punto y coma, sin [[Category:]].',
        'fr': 'Séparées par des points-virgules, sans [[Category:]].',
        'it': 'Separate da punto e virgola, senza [[Category:]].',
    },
    'Sets the English SDC caption.': {
        'de': 'Setzt die englische SDC-Bildunterschrift.',
        'es': 'Establece la leyenda SDC en inglés.',
        'fr': 'Définit la légende SDC anglaise.',
        'it': 'Imposta la didascalia SDC inglese.',
    },
    'Sets the German SDC caption.': {
        'de': 'Setzt die deutsche SDC-Bildunterschrift.',
        'es': 'Establece la leyenda SDC en alemán.',
        'fr': 'Définit la légende SDC allemande.',
        'it': 'Imposta la didascalia SDC tedesca.',
    },
    'Sets the Date column (e.g. 2026-02-15).': {
        'de': 'Setzt die Spalte „Datum“ (z. B. 2026-02-15).',
        'es': 'Establece la columna Fecha (p. ej. 2026-02-15).',
        'fr': 'Définit la colonne Date (p. ex. 2026-02-15).',
        'it': 'Imposta la colonna Data (ad es. 2026-02-15).',
    },
    'No selection': {
        'de': 'Keine Auswahl',
        'es': 'Sin selección',
        'fr': 'Aucune sélection',
        'it': 'Nessuna selezione',
    },
    'Please select one or more rows first (Ctrl/Shift-click to select several).': {
        'de': 'Bitte zuerst eine oder mehrere Zeilen auswählen (Strg-/Umschalt-Klick für mehrere).',
        'es': 'Seleccione primero una o varias filas (Ctrl/Mayús-clic para varias).',
        'fr': 'Sélectionnez d’abord une ou plusieurs lignes (Ctrl/Maj-clic pour en choisir plusieurs).',
        'it': 'Seleziona prima una o più righe (Ctrl/Maiusc-clic per selezionarne diverse).',
    },
    'Applied "{key}" to {n} file(s).': {
        'de': '„{key}“ auf {n} Datei(en) angewendet.',
        'es': '«{key}» aplicado a {n} archivo(s).',
        'fr': '« {key} » appliqué à {n} fichier(s).',
        'it': '"{key}" applicato a {n} file.',
    },
    'Invalid Wikidata IDs': {
        'de': 'Ungültige Wikidata-IDs',
        'es': 'ID de Wikidata no válidos',
        'fr': 'Identifiants Wikidata invalides',
        'it': 'ID Wikidata non validi',
    },
    'The following fields must contain Wikidata QIDs (e.g. Q640).\nPick an entry from the suggestion list or enter a valid QID:': {
        'de': 'Die folgenden Felder müssen Wikidata-QIDs enthalten (z. B. Q640).\nWähle einen Eintrag aus der Vorschlagsliste oder gib eine gültige QID ein:',
        'es': 'Los siguientes campos deben contener QID de Wikidata (p. ej. Q640).\nElija una entrada de la lista de sugerencias o escriba un QID válido:',
        'fr': 'Les champs suivants doivent contenir des QID Wikidata (p. ex. Q640).\nChoisissez une entrée dans la liste de suggestions ou saisissez un QID valide :',
        'it': 'I campi seguenti devono contenere QID di Wikidata (ad es. Q640).\nScegli una voce dall’elenco dei suggerimenti o inserisci un QID valido:',
    },
    '… (+{n} more)': {
        'de': '… (+{n} weitere)',
        'es': '… (+{n} más)',
        'fr': '… (+{n} de plus)',
        'it': '… (+{n} altri)',
    },
    'Upload': {
        'de': 'Upload',
        'es': 'Subida',
        'fr': 'Envoi',
        'it': 'Caricamento',
    },
    'Uploading': {
        'de': 'Hochladen',
        'es': 'Subiendo',
        'fr': 'Envoi',
        'it': 'Caricamento',
    },
    'Copying': {
        'de': 'Kopieren',
        'es': 'Copiando',
        'fr': 'Copie',
        'it': 'Copia',
    },
    'Copy': {
        'de': 'Kopieren',
        'es': 'Copiar',
        'fr': 'Copier',
        'it': 'Copia',
    },
    '{verb} {i} of {total} file(s)…': {
        'de': '{verb}: {i} von {total} Datei(en)…',
        'es': '{verb}: {i} de {total} archivo(s)…',
        'fr': '{verb} : {i} sur {total} fichier(s)…',
        'it': '{verb}: {i} di {total} file…',
    },
    'Uploading {i}/{total}…': {
        'de': 'Hochladen {i}/{total}…',
        'es': 'Subiendo {i}/{total}…',
        'fr': 'Envoi {i}/{total}…',
        'it': 'Caricamento {i}/{total}…',
    },
    'Uploading…': {
        'de': 'Wird hochgeladen…',
        'es': 'Subiendo…',
        'fr': 'Envoi…',
        'it': 'Caricamento…',
    },
    'Uploaded (SDC failed)': {
        'de': 'Hochgeladen (SDC fehlgeschlagen)',
        'es': 'Subido (SDC falló)',
        'fr': 'Envoyé (SDC en échec)',
        'it': 'Caricato (SDC fallito)',
    },
    'Uploaded, but structured data failed: {msg}': {
        'de': 'Hochgeladen, aber die strukturierten Daten schlugen fehl: {msg}',
        'es': 'Subido, pero los datos estructurados fallaron: {msg}',
        'fr': 'Envoyé, mais les données structurées ont échoué : {msg}',
        'it': 'Caricato, ma i dati strutturati non sono riusciti: {msg}',
    },
    'Cancelling: the file currently being uploaded is finished first, then the run stops.': {
        'de': 'Wird abgebrochen: Die gerade laufende Datei wird noch fertig hochgeladen, danach stoppt der Lauf.',
        'es': 'Cancelando: primero se termina el archivo que se está subiendo y luego se detiene la ejecución.',
        'fr': 'Annulation : le fichier en cours d’envoi est d’abord terminé, puis l’exécution s’arrête.',
        'it': 'Annullamento: il file in corso di caricamento viene prima completato, poi l’esecuzione si ferma.',
    },
    'Use a <b>BotPassword</b>: create one at <a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">Special:BotPasswords</a> and log in with the name shown there (e.g. <i>YourName@Cammello</i>).<br><br>Required grants:<ul style="margin-top:2px;"><li>Edit existing pages</li><li>Create, edit, and move pages</li><li>Upload new files</li><li>Upload, replace, and move files</li></ul>': {
        'de': 'Verwende ein <b>BotPassword</b>: unter <a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">Special:BotPasswords</a> anlegen und mit dem dort angezeigten Namen anmelden (z. B. <i>DeinName@Cammello</i>).<br><br>Erforderliche Rechte:<ul style="margin-top:2px;"><li>Bestehende Seiten bearbeiten</li><li>Seiten erstellen, bearbeiten und verschieben</li><li>Neue Dateien hochladen</li><li>Dateien hochladen, ersetzen und verschieben</li></ul>',
        'es': 'Use una <b>BotPassword</b>: créela en <a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">Special:BotPasswords</a> e inicie sesión con el nombre que aparece allí (p. ej. <i>SuNombre@Cammello</i>).<br><br>Permisos necesarios:<ul style="margin-top:2px;"><li>Editar páginas existentes</li><li>Crear, editar y trasladar páginas</li><li>Subir archivos nuevos</li><li>Subir, reemplazar y trasladar archivos</li></ul>',
        'fr': 'Utilisez un <b>BotPassword</b> : créez-en un sur <a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">Special:BotPasswords</a> et connectez-vous avec le nom qui y est affiché (p. ex. <i>VotreNom@Cammello</i>).<br><br>Droits requis :<ul style="margin-top:2px;"><li>Modifier des pages existantes</li><li>Créer, modifier et renommer des pages</li><li>Importer de nouveaux fichiers</li><li>Importer, remplacer et renommer des fichiers</li></ul>',
        'it': 'Usa una <b>BotPassword</b>: creane una su <a href="https://commons.wikimedia.org/wiki/Special:BotPasswords">Special:BotPasswords</a> e accedi con il nome mostrato lì (ad es. <i>TuoNome@Cammello</i>).<br><br>Permessi necessari:<ul style="margin-top:2px;"><li>Modificare pagine esistenti</li><li>Creare, modificare e spostare pagine</li><li>Caricare nuovi file</li><li>Caricare, sostituire e spostare file</li></ul>',
    },
    'Username:': {
        'de': 'Benutzername:',
        'es': 'Nombre de usuario:',
        'fr': 'Nom d’utilisateur :',
        'it': 'Nome utente:',
    },
    'Password:': {
        'de': 'Passwort:',
        'es': 'Contraseña:',
        'fr': 'Mot de passe :',
        'it': 'Password:',
    },
    'Verbose logging': {
        'de': 'Ausführliches Protokoll',
        'es': 'Registro detallado',
        'fr': 'Journalisation détaillée',
        'it': 'Registro dettagliato',
    },
    'Clear': {
        'de': 'Leeren',
        'es': 'Vaciar',
        'fr': 'Effacer',
        'it': 'Svuota',
    },
    'Open log file': {
        'de': 'Protokolldatei öffnen',
        'es': 'Abrir archivo de registro',
        'fr': 'Ouvrir le fichier journal',
        'it': 'Apri file di registro',
    },
    'Open folder': {
        'de': 'Ordner öffnen',
        'es': 'Abrir carpeta',
        'fr': 'Ouvrir le dossier',
        'it': 'Apri cartella',
    },
    'Log file: {path}': {
        'de': 'Protokolldatei: {path}',
        'es': 'Archivo de registro: {path}',
        'fr': 'Fichier journal : {path}',
        'it': 'File di registro: {path}',
    },
    'Log copied to clipboard.': {
        'de': 'Protokoll in die Zwischenablage kopiert.',
        'es': 'Registro copiado al portapapeles.',
        'fr': 'Journal copié dans le presse-papiers.',
        'it': 'Registro copiato negli appunti.',
    },
    'Files (shared with the MediaWiki tab):': {
        'de': 'Dateien (gemeinsam mit dem MediaWiki-Tab):',
        'es': 'Archivos (compartidos con la pestaña MediaWiki):',
        'fr': 'Fichiers (partagés avec l’onglet MediaWiki) :',
        'it': 'File (condivisi con la scheda MediaWiki):',
    },
    'Refresh list': {
        'de': 'Liste aktualisieren',
        'es': 'Actualizar lista',
        'fr': 'Actualiser la liste',
        'it': 'Aggiorna elenco',
    },
    'IPTC fields of the selected file': {
        'de': 'IPTC-Felder der ausgewählten Datei',
        'es': 'Campos IPTC del archivo seleccionado',
        'fr': 'Champs IPTC du fichier sélectionné',
        'it': 'Campi IPTC del file selezionato',
    },
    'separated by ;': {
        'de': 'durch ; getrennt',
        'es': 'separado por ;',
        'fr': 'séparé par ;',
        'it': 'separati da ;',
    },
    'Read IPTC from file': {
        'de': 'IPTC aus Datei lesen',
        'es': 'Leer IPTC del archivo',
        'fr': 'Lire l’IPTC du fichier',
        'it': 'Leggi IPTC dal file',
    },
    'Fill from MediaWiki data': {
        'de': 'Aus MediaWiki-Daten füllen',
        'es': 'Rellenar con datos de MediaWiki',
        'fr': 'Remplir depuis les données MediaWiki',
        'it': 'Compila dai dati MediaWiki',
    },
    'caption -> Caption/Headline, categories -> Keywords, author -> Creator, date -> Date created, target filename -> Title. QIDs are not resolved to names (that would need a Wikidata lookup).': {
        'de': 'caption -> Caption/Headline, Kategorien -> Keywords, Autor -> Creator, Datum -> Date created, Zieldateiname -> Title. QIDs werden nicht in Namen aufgelöst (das bräuchte eine Wikidata-Abfrage).',
        'es': 'caption -> Caption/Headline, categorías -> Keywords, autor -> Creator, fecha -> Date created, nombre de destino -> Title. Los QID no se resuelven a nombres (haría falta una consulta a Wikidata).',
        'fr': 'caption -> Caption/Headline, catégories -> Keywords, auteur -> Creator, date -> Date created, nom de fichier cible -> Title. Les QID ne sont pas résolus en noms (cela nécessiterait une requête Wikidata).',
        'it': 'caption -> Caption/Headline, categorie -> Keywords, autore -> Creator, data -> Date created, nome file di destinazione -> Title. I QID non vengono risolti in nomi (servirebbe una query a Wikidata).',
    },
    'Caption -> Wikitext as': {
        'de': 'Caption -> Wikitext als',
        'es': 'Caption -> Wikitexto como',
        'fr': 'Caption -> Wikitexte comme',
        'it': 'Caption -> Wikitesto come',
    },
    "Copies the IPTC caption into the file's description as caption_<language>.": {
        'de': 'Kopiert die IPTC-Caption als caption_<Sprache> in die Beschreibung der Datei.',
        'es': 'Copia la leyenda IPTC en la descripción del archivo como caption_<idioma>.',
        'fr': 'Copie la légende IPTC dans la description du fichier sous la forme caption_<langue>.',
        'it': 'Copia la didascalia IPTC nella descrizione del file come caption_<lingua>.',
    },
    'IPTC writing': {
        'de': 'IPTC-Schreiben',
        'es': 'Escritura IPTC',
        'fr': 'Écriture IPTC',
        'it': 'Scrittura IPTC',
    },
    'Write into the ORIGINAL files (default: copies in the export folder below)': {
        'de': 'In die ORIGINALDATEIEN schreiben (Vorgabe: Kopien im Exportordner unten)',
        'es': 'Escribir en los archivos ORIGINALES (por defecto: copias en la carpeta de exportación de abajo)',
        'fr': 'Écrire dans les fichiers ORIGINAUX (par défaut : copies dans le dossier d’export ci-dessous)',
        'it': 'Scrivere nei file ORIGINALI (predefinito: copie nella cartella di esportazione qui sotto)',
    },
    'Export folder for copies': {
        'de': 'Exportordner für Kopien',
        'es': 'Carpeta de exportación para las copias',
        'fr': 'Dossier d’export pour les copies',
        'it': 'Cartella di esportazione per le copie',
    },
    'Export folder': {
        'de': 'Exportordner',
        'es': 'Carpeta de exportación',
        'fr': 'Dossier d’export',
        'it': 'Cartella di esportazione',
    },
    'Write IPTC (all files with data)': {
        'de': 'IPTC schreiben (alle Dateien mit Daten)',
        'es': 'Escribir IPTC (todos los archivos con datos)',
        'fr': 'Écrire l’IPTC (tous les fichiers avec des données)',
        'it': 'Scrivi IPTC (tutti i file con dati)',
    },
    'The caption field is empty.': {
        'de': 'Das Caption-Feld ist leer.',
        'es': 'El campo de leyenda está vacío.',
        'fr': 'Le champ de légende est vide.',
        'it': 'Il campo didascalia è vuoto.',
    },
    'Choose an export folder, or enable writing into the original files.': {
        'de': 'Wähle einen Exportordner, oder aktiviere das Schreiben in die Originaldateien.',
        'es': 'Elija una carpeta de exportación o active la escritura en los archivos originales.',
        'fr': 'Choisissez un dossier d’export, ou activez l’écriture dans les fichiers originaux.',
        'it': 'Scegli una cartella di esportazione oppure attiva la scrittura nei file originali.',
    },
    'No file has any IPTC data yet.': {
        'de': 'Noch keine Datei hat IPTC-Daten.',
        'es': 'Ningún archivo tiene todavía datos IPTC.',
        'fr': 'Aucun fichier n’a encore de données IPTC.',
        'it': 'Nessun file ha ancora dati IPTC.',
    },
    'IPTC written: {written} file(s), {failed} failed.': {
        'de': 'IPTC geschrieben: {written} Datei(en), {failed} fehlgeschlagen.',
        'es': 'IPTC escrito: {written} archivo(s), {failed} fallidos.',
        'fr': 'IPTC écrit : {written} fichier(s), {failed} en échec.',
        'it': 'IPTC scritto: {written} file, {failed} non riusciti.',
    },
    'Filled {n} field(s) from MediaWiki data for "{name}".': {
        'de': '{n} Feld(er) aus MediaWiki-Daten für „{name}“ gefüllt.',
        'es': '{n} campo(s) rellenados con datos de MediaWiki para «{name}».',
        'fr': '{n} champ(s) remplis depuis les données MediaWiki pour « {name} ».',
        'it': '{n} campo/i compilati dai dati MediaWiki per "{name}".',
    },
    'Caption copied to caption_{lang} for "{name}".': {
        'de': 'Caption nach caption_{lang} kopiert für „{name}“.',
        'es': 'Leyenda copiada a caption_{lang} para «{name}».',
        'fr': 'Légende copiée dans caption_{lang} pour « {name} ».',
        'it': 'Didascalia copiata in caption_{lang} per "{name}".',
    },
    'IPTC write failed, file skipped: "{name}": {e}': {
        'de': 'IPTC-Schreiben fehlgeschlagen, Datei übersprungen: „{name}“: {e}',
        'es': 'Fallo al escribir IPTC, archivo omitido: «{name}»: {e}',
        'fr': 'Échec de l’écriture IPTC, fichier ignoré : « {name} » : {e}',
        'it': 'Scrittura IPTC non riuscita, file ignorato: "{name}": {e}',
    },
    'Title / object name': {
        'de': 'Titel / Objektname',
        'es': 'Título / nombre del objeto',
        'fr': 'Titre / nom de l’objet',
        'it': 'Titolo / nome oggetto',
    },
    'Headline': {
        'de': 'Schlagzeile',
        'es': 'Titular',
        'fr': 'Titre',
        'it': 'Titolo',
    },
    'Caption / description': {
        'de': 'Bildunterschrift / Beschreibung',
        'es': 'Leyenda / descripción',
        'fr': 'Légende / description',
        'it': 'Didascalia / descrizione',
    },
    'Keywords': {
        'de': 'Schlagwörter',
        'es': 'Palabras clave',
        'fr': 'Mots-clés',
        'it': 'Parole chiave',
    },
    'Creator (by-line)': {
        'de': 'Urheber (By-line)',
        'es': 'Creador (by-line)',
        'fr': 'Créateur (by-line)',
        'it': 'Autore (by-line)',
    },
    'Copyright notice': {
        'de': 'Urheberrechtshinweis',
        'es': 'Aviso de copyright',
        'fr': 'Mention de droit d’auteur',
        'it': 'Nota di copyright',
    },
    'Credit': {
        'de': 'Credit',
        'es': 'Crédito',
        'fr': 'Crédit',
        'it': 'Credito',
    },
    'Source': {
        'de': 'Quelle',
        'es': 'Fuente',
        'fr': 'Source',
        'it': 'Fonte',
    },
    'City': {
        'de': 'Stadt',
        'es': 'Ciudad',
        'fr': 'Ville',
        'it': 'Città',
    },
    'Province / state': {
        'de': 'Bundesland / Provinz',
        'es': 'Provincia / estado',
        'fr': 'Province / état',
        'it': 'Provincia / stato',
    },
    'Country': {
        'de': 'Land',
        'es': 'País',
        'fr': 'Pays',
        'it': 'Paese',
    },
    'Date created (YYYY-MM-DD)': {
        'de': 'Aufnahmedatum (JJJJ-MM-TT)',
        'es': 'Fecha de creación (AAAA-MM-DD)',
        'fr': 'Date de création (AAAA-MM-JJ)',
        'it': 'Data di creazione (AAAA-MM-GG)',
    },
    'FTP server': {
        'de': 'FTP-Server',
        'es': 'Servidor FTP',
        'fr': 'Serveur FTP',
        'it': 'Server FTP',
    },
    'FTP upload': {
        'de': 'FTP-Upload',
        'es': 'Subida FTP',
        'fr': 'Envoi FTP',
        'it': 'Caricamento FTP',
    },
    'Protocol:': {
        'de': 'Protokoll:',
        'es': 'Protocolo:',
        'fr': 'Protocole :',
        'it': 'Protocollo:',
    },
    'Host:': {
        'de': 'Host:',
        'es': 'Servidor:',
        'fr': 'Hôte :',
        'it': 'Host:',
    },
    'Port:': {
        'de': 'Port:',
        'es': 'Puerto:',
        'fr': 'Port :',
        'it': 'Porta:',
    },
    'User:': {
        'de': 'Benutzer:',
        'es': 'Usuario:',
        'fr': 'Utilisateur :',
        'it': 'Utente:',
    },
    'empty = default port': {
        'de': 'leer = Standardport',
        'es': 'vacío = puerto predeterminado',
        'fr': 'vide = port par défaut',
        'it': 'vuoto = porta predefinita',
    },
    'Store password in settings (PLAIN TEXT - unsafe)': {
        'de': 'Passwort in den Einstellungen speichern (KLARTEXT – unsicher)',
        'es': 'Guardar la contraseña en los ajustes (TEXTO PLANO: inseguro)',
        'fr': 'Enregistrer le mot de passe dans les réglages (TEXTE EN CLAIR – non sécurisé)',
        'it': 'Salvare la password nelle impostazioni (TESTO IN CHIARO – non sicuro)',
    },
    'Remote directory:': {
        'de': 'Zielverzeichnis:',
        'es': 'Directorio remoto:',
        'fr': 'Répertoire distant :',
        'it': 'Directory remota:',
    },
    'Write IPTC + upload all': {
        'de': 'IPTC schreiben + alle hochladen',
        'es': 'Escribir IPTC + subir todo',
        'fr': 'Écrire l’IPTC + tout envoyer',
        'it': 'Scrivi IPTC + carica tutto',
    },
    'Host is missing.': {
        'de': 'Der Host fehlt.',
        'es': 'Falta el servidor.',
        'fr': 'L’hôte est manquant.',
        'it': 'Manca l’host.',
    },
    'Host is missing (FTP tab or Settings tab).': {
        'de': 'Der Host fehlt (FTP-Tab oder Einstellungen).',
        'es': 'Falta el servidor (pestaña FTP o Ajustes).',
        'fr': 'L’hôte est manquant (onglet FTP ou Réglages).',
        'it': 'Manca l’host (scheda FTP o Impostazioni).',
    },
    'Password is missing (it is asked per session unless you chose to store it).': {
        'de': 'Das Passwort fehlt (es wird pro Sitzung abgefragt, sofern es nicht gespeichert wird).',
        'es': 'Falta la contraseña (se pide por sesión salvo que elija guardarla).',
        'fr': 'Le mot de passe est manquant (il est demandé à chaque session, sauf si vous l’enregistrez).',
        'it': 'Manca la password (viene richiesta a ogni sessione, a meno che tu non scelga di salvarla).',
    },
    'No file could be prepared.': {
        'de': 'Keine Datei konnte vorbereitet werden.',
        'es': 'No se pudo preparar ningún archivo.',
        'fr': 'Aucun fichier n’a pu être préparé.',
        'it': 'Non è stato possibile preparare alcun file.',
    },
    'Connection failed: {e}': {
        'de': 'Verbindung fehlgeschlagen: {e}',
        'es': 'Fallo de conexión: {e}',
        'fr': 'Échec de la connexion : {e}',
        'it': 'Connessione non riuscita: {e}',
    },
    'Failed: could not connect to {host}.': {
        'de': 'Fehlgeschlagen: keine Verbindung zu {host}.',
        'es': 'Fallo: no se pudo conectar con {host}.',
        'fr': 'Échec : impossible de se connecter à {host}.',
        'it': 'Non riuscito: impossibile connettersi a {host}.',
    },
    'Remote directory: {e}': {
        'de': 'Zielverzeichnis: {e}',
        'es': 'Directorio remoto: {e}',
        'fr': 'Répertoire distant : {e}',
        'it': 'Directory remota: {e}',
    },
    'Failed: remote directory "{dir}".': {
        'de': 'Fehlgeschlagen: Zielverzeichnis „{dir}“.',
        'es': 'Fallo: directorio remoto «{dir}».',
        'fr': 'Échec : répertoire distant « {dir} ».',
        'it': 'Non riuscito: directory remota "{dir}".',
    },
    'Sent': {
        'de': 'Gesendet',
        'es': 'Enviado',
        'fr': 'Envoyé',
        'it': 'Inviato',
    },
    'Done: {ok}/{total} file(s) sent.': {
        'de': 'Fertig: {ok}/{total} Datei(en) gesendet.',
        'es': 'Listo: {ok}/{total} archivo(s) enviados.',
        'fr': 'Terminé : {ok}/{total} fichier(s) envoyés.',
        'it': 'Fatto: {ok}/{total} file inviati.',
    },
    'Cancelled: {ok}/{total} file(s) sent, {skipped} not started.': {
        'de': 'Abgebrochen: {ok}/{total} Datei(en) gesendet, {skipped} nicht begonnen.',
        'es': 'Cancelado: {ok}/{total} archivo(s) enviados, {skipped} sin iniciar.',
        'fr': 'Annulé : {ok}/{total} fichier(s) envoyés, {skipped} non commencés.',
        'it': 'Annullato: {ok}/{total} file inviati, {skipped} non avviati.',
    },
    'Open folder…': {
        'de': 'Ordner öffnen…',
        'es': 'Abrir carpeta…',
        'fr': 'Ouvrir un dossier…',
        'it': 'Apri cartella…',
    },
    'Number keys 1-5 set stars or colors; M toggles the mode.': {
        'de': 'Zifferntasten 1–5 setzen Sterne oder Farben; M schaltet den Modus um.',
        'es': 'Las teclas 1-5 asignan estrellas o colores; M cambia el modo.',
        'fr': 'Les touches 1-5 attribuent des étoiles ou des couleurs ; M bascule le mode.',
        'it': 'I tasti 1-5 assegnano stelle o colori; M cambia modalità.',
    },
    'numbers = STARS': {
        'de': 'Zahlen = STERNE',
        'es': 'números = ESTRELLAS',
        'fr': 'chiffres = ÉTOILES',
        'it': 'numeri = STELLE',
    },
    'numbers = COLORS': {
        'de': 'Zahlen = FARBEN',
        'es': 'números = COLORES',
        'fr': 'chiffres = COULEURS',
        'it': 'numeri = COLORI',
    },
    'Zoom:': {
        'de': 'Zoom:',
        'es': 'Zoom:',
        'fr': 'Zoom :',
        'it': 'Zoom:',
    },
    'One zoom step out (Cmd/Ctrl -)': {
        'de': 'Eine Zoomstufe heraus (Cmd/Strg -)',
        'es': 'Un paso de zoom hacia fuera (Cmd/Ctrl -)',
        'fr': 'Un cran de zoom arrière (Cmd/Ctrl -)',
        'it': 'Uno scatto di zoom indietro (Cmd/Ctrl -)',
    },
    'One zoom step in (Cmd/Ctrl +)': {
        'de': 'Eine Zoomstufe hinein (Cmd/Strg +)',
        'es': 'Un paso de zoom hacia dentro (Cmd/Ctrl +)',
        'fr': 'Un cran de zoom avant (Cmd/Ctrl +)',
        'it': 'Uno scatto di zoom avanti (Cmd/Ctrl +)',
    },
    'Grid': {
        'de': 'Raster',
        'es': 'Cuadrícula',
        'fr': 'Grille',
        'it': 'Griglia',
    },
    'Grid view (G): thumbnails instead of the large image.': {
        'de': 'Rasteransicht (G): Miniaturen statt des großen Bildes.',
        'es': 'Vista de cuadrícula (G): miniaturas en lugar de la imagen grande.',
        'fr': 'Vue en grille (G) : vignettes au lieu de la grande image.',
        'it': 'Vista a griglia (G): miniature invece dell’immagine grande.',
    },
    'Show:': {
        'de': 'Zeigen:',
        'es': 'Mostrar:',
        'fr': 'Afficher :',
        'it': 'Mostra:',
    },
    'incl. rejects': {
        'de': 'inkl. Ausschuss',
        'es': 'incl. rechazadas',
        'fr': 'y compris les rejets',
        'it': 'incl. scarti',
    },
    'Send to:': {
        'de': 'Senden an:',
        'es': 'Enviar a:',
        'fr': 'Envoyer vers :',
        'it': 'Invia a:',
    },
    'Folder…': {
        'de': 'Ordner…',
        'es': 'Carpeta…',
        'fr': 'Dossier…',
        'it': 'Cartella…',
    },
    'Copies the selected images into a local folder. RAW files bring their .xmp sidecar along; existing files in the target folder are never overwritten.': {
        'de': 'Kopiert die ausgewählten Bilder in einen lokalen Ordner. RAW-Dateien bringen ihre .xmp-Sidecar-Datei mit; vorhandene Dateien im Zielordner werden nie überschrieben.',
        'es': 'Copia las imágenes seleccionadas a una carpeta local. Los RAW llevan consigo su sidecar .xmp; los archivos existentes en la carpeta de destino nunca se sobrescriben.',
        'fr': 'Copie les images sélectionnées dans un dossier local. Les RAW emportent leur fichier annexe .xmp ; les fichiers existants dans le dossier cible ne sont jamais écrasés.',
        'it': 'Copia le immagini selezionate in una cartella locale. I RAW portano con sé il sidecar .xmp; i file già presenti nella cartella di destinazione non vengono mai sovrascritti.',
    },
    'No folder open. Open one to start culling.': {
        'de': 'Kein Ordner geöffnet. Öffne einen, um mit der Sichtung zu beginnen.',
        'es': 'No hay ninguna carpeta abierta. Abra una para empezar la selección.',
        'fr': 'Aucun dossier ouvert. Ouvrez-en un pour commencer le tri.',
        'it': 'Nessuna cartella aperta. Aprine una per iniziare la selezione.',
    },
    '{pos}/{shown} shown ({total} in folder)': {
        'de': '{pos}/{shown} angezeigt ({total} im Ordner)',
        'es': '{pos}/{shown} mostradas ({total} en la carpeta)',
        'fr': '{pos}/{shown} affichées ({total} dans le dossier)',
        'it': '{pos}/{shown} mostrate ({total} nella cartella)',
    },
    'Nothing passes the current filter.': {
        'de': 'Nichts passiert den aktuellen Filter.',
        'es': 'Nada pasa el filtro actual.',
        'fr': 'Rien ne passe le filtre actuel.',
        'it': 'Niente supera il filtro attuale.',
    },
    '{added} file(s) added to the table, {dupes} duplicate(s) skipped, {failed} failed.': {
        'de': '{added} Datei(en) zur Tabelle hinzugefügt, {dupes} Duplikat(e) übersprungen, {failed} fehlgeschlagen.',
        'es': '{added} archivo(s) añadidos a la tabla, {dupes} duplicado(s) omitido(s), {failed} fallidos.',
        'fr': '{added} fichier(s) ajoutés au tableau, {dupes} doublon(s) ignoré(s), {failed} en échec.',
        'it': '{added} file aggiunti alla tabella, {dupes} duplicato/i ignorato/i, {failed} non riusciti.',
    },
    '[P] RAW+JPEG pair (one picture, two files)': {
        'de': '[P] RAW+JPEG-Paar (ein Bild, zwei Dateien)',
        'es': '[P] Par RAW+JPEG (una imagen, dos archivos)',
        'fr': '[P] Paire RAW+JPEG (une image, deux fichiers)',
        'it': '[P] Coppia RAW+JPEG (un’immagine, due file)',
    },
    '[T] already in the file table': {
        'de': '[T] bereits in der Dateitabelle',
        'es': '[T] ya está en la tabla de archivos',
        'fr': '[T] déjà dans le tableau des fichiers',
        'it': '[T] già nella tabella dei file',
    },
    'Auto-advance:': {
        'de': 'Automatisch weiter:',
        'es': 'Avance automático:',
        'fr': 'Avance automatique :',
        'it': 'Avanzamento automatico:',
    },
    'Advance to the next image after rating/labeling': {
        'de': 'Nach Bewertung/Farbmarkierung zum nächsten Bild springen',
        'es': 'Pasar a la siguiente imagen tras valorar/etiquetar',
        'fr': 'Passer à l’image suivante après notation/étiquetage',
        'it': 'Passare all’immagine successiva dopo valutazione/etichetta',
    },
    'Color label set:': {
        'de': 'Farbmarkierungs-Satz:',
        'es': 'Conjunto de etiquetas de color:',
        'fr': 'Jeu d’étiquettes de couleur :',
        'it': 'Set di etichette colore:',
    },
    'Language of the label TEXT written to XMP - must match the color label set of your Lightroom, or LR shows the label in white.': {
        'de': 'Sprache des in XMP geschriebenen Farbmarkierungs-TEXTES – muss zum Farbmarkierungssatz deines Lightroom passen, sonst zeigt LR die Markierung weiß an.',
        'es': 'Idioma del TEXTO de la etiqueta escrito en XMP: debe coincidir con el conjunto de etiquetas de color de su Lightroom, o LR mostrará la etiqueta en blanco.',
        'fr': 'Langue du TEXTE d’étiquette écrit dans le XMP – doit correspondre au jeu d’étiquettes de couleur de votre Lightroom, sinon LR affiche l’étiquette en blanc.',
        'it': 'Lingua del TESTO dell’etichetta scritto nell’XMP: deve corrispondere al set di etichette colore del tuo Lightroom, altrimenti LR mostra l’etichetta in bianco.',
    },
    'RAW+JPEG pairs:': {
        'de': 'RAW+JPEG-Paare:',
        'es': 'Pares RAW+JPEG:',
        'fr': 'Paires RAW+JPEG :',
        'it': 'Coppie RAW+JPEG:',
    },
    'pair: JPEG': {
        'de': 'Paar: JPEG',
        'es': 'par: JPEG',
        'fr': 'paire : JPEG',
        'it': 'coppia: JPEG',
    },
    'pair: RAW': {
        'de': 'Paar: RAW',
        'es': 'par: RAW',
        'fr': 'paire : RAW',
        'it': 'coppia: RAW',
    },
    'pair: both': {
        'de': 'Paar: beide',
        'es': 'par: ambos',
        'fr': 'paire : les deux',
        'it': 'coppia: entrambi',
    },
    'Which file of a RAW+JPEG pair goes to the file table (button and drag-and-drop).': {
        'de': 'Welche Datei eines RAW+JPEG-Paares in die Dateitabelle wandert (Schaltfläche und Drag-and-drop).',
        'es': 'Qué archivo de un par RAW+JPEG va a la tabla de archivos (botón y arrastrar y soltar).',
        'fr': 'Quel fichier d’une paire RAW+JPEG va dans le tableau des fichiers (bouton et glisser-déposer).',
        'it': 'Quale file di una coppia RAW+JPEG finisce nella tabella dei file (pulsante e trascinamento).',
    },
    'Copy selection to folder': {
        'de': 'Auswahl in Ordner kopieren',
        'es': 'Copiar la selección a una carpeta',
        'fr': 'Copier la sélection dans un dossier',
        'it': 'Copia la selezione in una cartella',
    },
    'Copy to folder': {
        'de': 'In Ordner kopieren',
        'es': 'Copiar a carpeta',
        'fr': 'Copier dans le dossier',
        'it': 'Copia nella cartella',
    },
    'Copied': {
        'de': 'Kopiert',
        'es': 'Copiado',
        'fr': 'Copié',
        'it': 'Copiato',
    },
    'Skipped (exists)': {
        'de': 'Übersprungen (vorhanden)',
        'es': 'Omitido (ya existe)',
        'fr': 'Ignoré (existe déjà)',
        'it': 'Ignorato (già presente)',
    },
    'Done: {ok}/{total} file(s) copied': {
        'de': 'Fertig: {ok}/{total} Datei(en) kopiert',
        'es': 'Listo: {ok}/{total} archivo(s) copiados',
        'fr': 'Terminé : {ok}/{total} fichier(s) copiés',
        'it': 'Fatto: {ok}/{total} file copiati',
    },
    '{n} skipped (already there)': {
        'de': '{n} übersprungen (schon vorhanden)',
        'es': '{n} omitido(s) (ya estaban)',
        'fr': '{n} ignoré(s) (déjà présents)',
        'it': '{n} ignorato/i (già presenti)',
    },
    '{n} failed': {
        'de': '{n} fehlgeschlagen',
        'es': '{n} fallidos',
        'fr': '{n} en échec',
        'it': '{n} non riusciti',
    },
    'Cancelled: {ok}/{total} file(s) copied, {n} not started.': {
        'de': 'Abgebrochen: {ok}/{total} Datei(en) kopiert, {n} nicht begonnen.',
        'es': 'Cancelado: {ok}/{total} archivo(s) copiados, {n} sin iniciar.',
        'fr': 'Annulé : {ok}/{total} fichier(s) copiés, {n} non commencés.',
        'it': 'Annullato: {ok}/{total} file copiati, {n} non avviati.',
    },
    'About': {
        'de': 'Über',
        'es': 'Acerca de',
        'fr': 'À propos',
        'it': 'Informazioni',
    },
    'A WikiPortraits tool by Harald Krichel': {
        'de': 'Ein WikiPortraits-Tool von Harald Krichel',
        'es': 'Una herramienta de WikiPortraits de Harald Krichel',
        'fr': 'Un outil WikiPortraits de Harald Krichel',
        'it': 'Uno strumento WikiPortraits di Harald Krichel',
    },
    'Version {version}': {
        'de': 'Version {version}',
        'es': 'Versión {version}',
        'fr': 'Version {version}',
        'it': 'Versione {version}',
    },
    'License:': {
        'de': 'Lizenz:',
        'es': 'Licencia:',
        'fr': 'Licence :',
        'it': 'Licenza:',
    },
    'Built with:': {
        'de': 'Erstellt mit:',
        'es': 'Creado con:',
        'fr': 'Créé avec :',
        'it': 'Creato con:',
    },
    '{n} file(s)': {
        'de': '{n} Datei(en)',
        'es': '{n} archivo(s)',
        'fr': '{n} fichier(s)',
        'it': '{n} file',
    },
    '{n} selected': {
        'de': '{n} ausgewählt',
        'es': '{n} seleccionados',
        'fr': '{n} sélectionné(s)',
        'it': '{n} selezionati',
    },
    '{sel} of {total} selected': {
        'de': '{sel} von {total} ausgewählt',
        'es': '{sel} de {total} seleccionados',
        'fr': '{sel} sur {total} sélectionnés',
        'it': '{sel} di {total} selezionati',
    },
    'Flickr account': {
        'de': 'Flickr-Konto',
        'es': 'Cuenta de Flickr',
        'fr': 'Compte Flickr',
        'it': 'Account Flickr',
    },
    'Flickr upload': {
        'de': 'Flickr-Upload',
        'es': 'Subida a Flickr',
        'fr': 'Envoi Flickr',
        'it': 'Caricamento su Flickr',
    },
    'API key:': {
        'de': 'API-Schlüssel:',
        'es': 'Clave de API:',
        'fr': 'Clé API :',
        'it': 'Chiave API:',
    },
    'API secret:': {
        'de': 'API-Secret:',
        'es': 'Secreto de API:',
        'fr': 'Secret API :',
        'it': 'Segreto API:',
    },
    'Create a key/secret pair at flickr.com/services/apps/create. Both are stored in the settings.': {
        'de': 'Schlüssel/Secret unter flickr.com/services/apps/create anlegen. Beide werden in den Einstellungen gespeichert.',
        'es': 'Cree el par clave/secreto en flickr.com/services/apps/create. Ambos se guardan en los ajustes.',
        'fr': 'Créez la paire clé/secret sur flickr.com/services/apps/create. Les deux sont enregistrés dans les réglages.',
        'it': 'Crea la coppia chiave/segreto su flickr.com/services/apps/create. Entrambi vengono salvati nelle impostazioni.',
    },
    '1. Open authorization page': {
        'de': '1. Autorisierungsseite öffnen',
        'es': '1. Abrir la página de autorización',
        'fr': '1. Ouvrir la page d’autorisation',
        'it': '1. Apri la pagina di autorizzazione',
    },
    '2. Complete authorization': {
        'de': '2. Autorisierung abschließen',
        'es': '2. Completar la autorización',
        'fr': '2. Terminer l’autorisation',
        'it': '2. Completa l’autorizzazione',
    },
    'Verification code from the browser (nnn-nnn-nnn)': {
        'de': 'Bestätigungscode aus dem Browser (nnn-nnn-nnn)',
        'es': 'Código de verificación del navegador (nnn-nnn-nnn)',
        'fr': 'Code de vérification du navigateur (nnn-nnn-nnn)',
        'it': 'Codice di verifica dal browser (nnn-nnn-nnn)',
    },
    'Authorization page opened in the browser. Grant access, then paste the code below.': {
        'de': 'Autorisierungsseite im Browser geöffnet. Zugriff gewähren, dann den Code unten einfügen.',
        'es': 'Página de autorización abierta en el navegador. Conceda el acceso y pegue el código abajo.',
        'fr': 'Page d’autorisation ouverte dans le navigateur. Accordez l’accès, puis collez le code ci-dessous.',
        'it': 'Pagina di autorizzazione aperta nel browser. Concedi l’accesso, poi incolla il codice qui sotto.',
    },
    'Authorized as {username}.': {
        'de': 'Autorisiert als {username}.',
        'es': 'Autorizado como {username}.',
        'fr': 'Autorisé en tant que {username}.',
        'it': 'Autorizzato come {username}.',
    },
    'Not authorized.': {
        'de': 'Nicht autorisiert.',
        'es': 'No autorizado.',
        'fr': 'Non autorisé.',
        'it': 'Non autorizzato.',
    },
    'Not authorized yet - run the two authorization steps first.': {
        'de': 'Noch nicht autorisiert – zuerst die beiden Autorisierungsschritte ausführen.',
        'es': 'Aún no autorizado: ejecute primero los dos pasos de autorización.',
        'fr': 'Pas encore autorisé – effectuez d’abord les deux étapes d’autorisation.',
        'it': 'Non ancora autorizzato: esegui prima i due passaggi di autorizzazione.',
    },
    'Run step 1 first (the code belongs to that request).': {
        'de': 'Zuerst Schritt 1 ausführen (der Code gehört zu dieser Anfrage).',
        'es': 'Ejecute primero el paso 1 (el código pertenece a esa solicitud).',
        'fr': 'Effectuez d’abord l’étape 1 (le code appartient à cette demande).',
        'it': 'Esegui prima il passaggio 1 (il codice appartiene a quella richiesta).',
    },
    'The verification code is missing.': {
        'de': 'Der Bestätigungscode fehlt.',
        'es': 'Falta el código de verificación.',
        'fr': 'Le code de vérification est manquant.',
        'it': 'Manca il codice di verifica.',
    },
    'API key and secret are missing (create them at flickr.com/services/apps/create).': {
        'de': 'API-Schlüssel und -Secret fehlen (unter flickr.com/services/apps/create anlegen).',
        'es': 'Faltan la clave y el secreto de API (créelos en flickr.com/services/apps/create).',
        'fr': 'La clé et le secret API sont manquants (créez-les sur flickr.com/services/apps/create).',
        'it': 'Mancano chiave e segreto API (creali su flickr.com/services/apps/create).',
    },
    'Files are uploaded as they are; the Flickr title is the target filename. Privacy follows your account upload defaults.': {
        'de': 'Die Dateien werden unverändert hochgeladen; der Flickr-Titel ist der Zieldateiname. Die Sichtbarkeit folgt den Upload-Voreinstellungen deines Kontos.',
        'es': 'Los archivos se suben tal cual; el título en Flickr es el nombre de destino. La privacidad sigue los ajustes predeterminados de subida de su cuenta.',
        'fr': 'Les fichiers sont envoyés tels quels ; le titre Flickr est le nom de fichier cible. La confidentialité suit les réglages d’envoi par défaut de votre compte.',
        'it': 'I file vengono caricati così come sono; il titolo su Flickr è il nome file di destinazione. La privacy segue le impostazioni di caricamento predefinite del tuo account.',
    },
    'Upload to Flickr': {
        'de': 'Zu Flickr hochladen',
        'es': 'Subir a Flickr',
        'fr': 'Envoyer vers Flickr',
        'it': 'Carica su Flickr',
    },
    'Write IPTC + upload': {
        'de': 'IPTC schreiben + hochladen',
        'es': 'Escribir IPTC + subir',
        'fr': 'Écrire l’IPTC + envoyer',
        'it': 'Scrivi IPTC + carica',
    },
    'Uploads the SELECTED files (or all, when nothing is selected). IPTC data is written first; files without IPTC data are skipped. Write settings (export folder) are in the IPTC tab.': {
        'de': 'Lädt die AUSGEWÄHLTEN Dateien hoch (oder alle, wenn nichts ausgewählt ist). Zuerst wird IPTC geschrieben; Dateien ohne IPTC-Daten werden übersprungen. Die Schreib-Einstellungen (Exportordner) stehen im IPTC-Tab.',
        'es': 'Sube los archivos SELECCIONADOS (o todos, si no hay selección). Primero se escribe el IPTC; los archivos sin datos IPTC se omiten. Los ajustes de escritura (carpeta de exportación) están en la pestaña IPTC.',
        'fr': 'Envoie les fichiers SÉLECTIONNÉS (ou tous, si rien n’est sélectionné). L’IPTC est écrit d’abord ; les fichiers sans données IPTC sont ignorés. Les réglages d’écriture (dossier d’export) sont dans l’onglet IPTC.',
        'it': 'Carica i file SELEZIONATI (o tutti, se non c’è selezione). Prima viene scritto l’IPTC; i file senza dati IPTC vengono ignorati. Le impostazioni di scrittura (cartella di esportazione) sono nella scheda IPTC.',
    },
    'The IPTC tab is disabled: the selected files (or all, when nothing is selected) are uploaded AS THEY ARE, without IPTC writing.': {
        'de': 'Der IPTC-Tab ist abgeschaltet: Die ausgewählten Dateien (oder alle, wenn nichts ausgewählt ist) werden UNVERÄNDERT hochgeladen, ohne IPTC-Schreiben.',
        'es': 'La pestaña IPTC está desactivada: los archivos seleccionados (o todos, si no hay selección) se suben TAL CUAL, sin escribir IPTC.',
        'fr': 'L’onglet IPTC est désactivé : les fichiers sélectionnés (ou tous, si rien n’est sélectionné) sont envoyés TELS QUELS, sans écriture IPTC.',
        'it': 'La scheda IPTC è disattivata: i file selezionati (o tutti, se non c’è selezione) vengono caricati COSÌ COME SONO, senza scrittura IPTC.',
    },
    'The authorization steps are on the Flickr tab.': {
        'de': 'Die Autorisierungsschritte stehen im Flickr-Tab.',
        'es': 'Los pasos de autorización están en la pestaña Flickr.',
        'fr': 'Les étapes d’autorisation se trouvent dans l’onglet Flickr.',
        'it': 'I passaggi di autorizzazione sono nella scheda Flickr.',
    },
    'Account default': {
        'de': 'Konto-Voreinstellung',
        'es': 'Predeterminado de la cuenta',
        'fr': 'Réglage par défaut du compte',
        'it': 'Predefinito dell’account',
    },
    'All rights reserved': {
        'de': 'Alle Rechte vorbehalten',
        'es': 'Todos los derechos reservados',
        'fr': 'Tous droits réservés',
        'it': 'Tutti i diritti riservati',
    },
    'No Wikidata item': {
        'de': 'Kein Wikidata-Objekt',
        'es': 'Sin elemento de Wikidata',
        'fr': 'Pas d’élément Wikidata',
        'it': 'Nessun elemento Wikidata',
    },
    'Not applicable': {
        'de': 'Nicht anwendbar',
        'es': 'No aplicable',
        'fr': 'Non applicable',
        'it': 'Non applicabile',
    },
    'Unidentified': {
        'de': 'Unidentifiziert',
        'es': 'Sin identificar',
        'fr': 'Non identifié',
        'it': 'Non identificato',
    },
    'Depicts is missing': {
        'de': 'Depicts fehlt',
        'es': 'Falta depicts',
        'fr': 'Depicts manquant',
        'it': 'Depicts mancante',
    },
    'depicts (P180) is mandatory. Enter a QID, or check one of the overrides ("No Wikidata item", "Not applicable", "Unidentified") for these files:': {
        'de': 'depicts (P180) ist Pflicht. Gib eine QID ein oder setze für diese Dateien eine der Ausnahmen („Kein Wikidata-Objekt“, „Nicht anwendbar“, „Unidentifiziert“):',
        'es': 'depicts (P180) es obligatorio. Escriba un QID o marque una de las excepciones («Sin elemento de Wikidata», «No aplicable», «Sin identificar») para estos archivos:',
        'fr': 'depicts (P180) est obligatoire. Saisissez un QID ou cochez l’une des exceptions (« Pas d’élément Wikidata », « Non applicable », « Non identifié ») pour ces fichiers :',
        'it': 'depicts (P180) è obbligatorio. Inserisci un QID oppure spunta una delle eccezioni ("Nessun elemento Wikidata", "Non applicabile", "Non identificato") per questi file:',
    },
    'Suggest': {
        'de': 'Vorschlagen',
        'es': 'Sugerir',
        'fr': 'Suggérer',
        'it': 'Suggerisci',
    },
    'Categories': {
        'de': 'Kategorien',
        'es': 'Categorías',
        'fr': 'Catégories',
        'it': 'Categorie',
    },
    'No QIDs found - fill depicts or "created during" first.': {
        'de': 'Keine QIDs gefunden – zuerst Depicts oder „Entstanden während“ ausfüllen.',
        'es': 'No se encontraron QID: rellene primero depicts o «creado durante».',
        'fr': 'Aucun QID trouvé – remplissez d’abord depicts ou « créé lors de ».',
        'it': 'Nessun QID trovato: compila prima depicts o "creato durante".',
    },
    'Wikidata request failed: {e}': {
        'de': 'Wikidata-Anfrage fehlgeschlagen: {e}',
        'es': 'La solicitud a Wikidata falló: {e}',
        'fr': 'La requête Wikidata a échoué : {e}',
        'it': 'Richiesta a Wikidata non riuscita: {e}',
    },
    'No new category suggestions found.': {
        'de': 'Keine neuen Kategorievorschläge gefunden.',
        'es': 'No se encontraron nuevas sugerencias de categorías.',
        'fr': 'Aucune nouvelle suggestion de catégorie trouvée.',
        'it': 'Nessun nuovo suggerimento di categoria trovato.',
    },
    '{n} category suggestion(s) added.': {
        'de': '{n} Kategorievorschlag/-vorschläge hinzugefügt.',
        'es': '{n} sugerencia(s) de categoría añadida(s).',
        'fr': '{n} suggestion(s) de catégorie ajoutée(s).',
        'it': '{n} suggerimento/i di categoria aggiunti.',
    },
    'depicts is set (required)': {
        'de': 'depicts ist gesetzt (Pflicht)',
        'es': 'depicts está definido (obligatorio)',
        'fr': 'depicts est renseigné (obligatoire)',
        'it': 'depicts è impostato (obbligatorio)',
    },
    'If no depicts:': {
        'de': 'Falls kein depicts:',
        'es': 'Si no hay depicts:',
        'fr': 'Si pas de depicts :',
        'it': 'Se manca depicts:',
    },
    'Suggest category': {
        'de': 'Kategorie vorschlagen',
        'es': 'Sugerir categoría',
        'fr': 'Suggérer une catégorie',
        'it': 'Suggerisci categoria',
    },
    'Adds a base category from the "created during" event (Commons category P373, or the label; a missing year is taken from the Date column).': {
        'de': 'Fügt eine Basiskategorie aus dem „Entstanden während“-Ereignis hinzu (Commons-Kategorie P373, sonst das Label; ein fehlendes Jahr kommt aus der Datumsspalte).',
        'es': 'Añade una categoría base a partir del evento «creado durante» (categoría de Commons P373, o la etiqueta; un año que falte se toma de la columna Fecha).',
        'fr': 'Ajoute une catégorie de base à partir de l’événement « créé lors de » (catégorie Commons P373, sinon le libellé ; une année manquante est reprise de la colonne Date).',
        'it': 'Aggiunge una categoria base dall’evento "creato durante" (categoria Commons P373, altrimenti l’etichetta; un anno mancante viene preso dalla colonna Data).',
    },
    'No depicts QIDs found - fill depicts first.': {
        'de': 'Keine depicts-QIDs gefunden – zuerst depicts ausfüllen.',
        'es': 'No se encontraron QID de depicts: rellene depicts primero.',
        'fr': 'Aucun QID depicts trouvé – remplissez d’abord depicts.',
        'it': 'Nessun QID depicts trovato: compila prima depicts.',
    },
    'Enter a "created during" QID first.': {
        'de': 'Zuerst eine „Entstanden während“-QID eingeben.',
        'es': 'Introduzca primero un QID de «creado durante».',
        'fr': 'Saisissez d’abord un QID « créé lors de ».',
        'it': 'Inserisci prima un QID "creato durante".',
    },
    'Information from caption': {
        'de': 'Information aus Bildunterschrift',
        'es': 'Information desde la leyenda',
        'fr': 'Information depuis la légende',
        'it': 'Information dalla didascalia',
    },
    'Fills the Information wikitext of each language with its caption text, where the Information field is still empty.': {
        'de': 'Füllt den Information-Wikitext jeder Sprache mit deren Bildunterschrift, sofern das Information-Feld noch leer ist.',
        'es': 'Rellena el wikitexto Information de cada idioma con su leyenda, cuando el campo Information aún está vacío.',
        'fr': 'Remplit le wikitexte Information de chaque langue avec sa légende, lorsque le champ Information est encore vide.',
        'it': 'Riempie il wikitesto Information di ogni lingua con la sua didascalia, quando il campo Information è ancora vuoto.',
    },
    'Adds categories from the depicts entries (Commons category P373, or the label).': {
        'de': 'Fügt Kategorien aus den Depicts-Einträgen hinzu (Commons-Kategorie P373, sonst das Label).',
        'es': 'Añade categorías a partir de las entradas de depicts (categoría de Commons P373, o la etiqueta).',
        'fr': 'Ajoute des catégories à partir des entrées depicts (catégorie Commons P373, sinon le libellé).',
        'it': 'Aggiunge categorie dalle voci depicts (categoria Commons P373, altrimenti l’etichetta).',
    },
    'Clear base description': {
        'de': 'Basisbeschreibung leeren',
        'es': 'Vaciar la descripción base',
        'fr': 'Effacer la description de base',
        'it': 'Svuota la descrizione base',
    },
    'Really clear the whole base description? This updates the wikitext of every file.': {
        'de': 'Wirklich die gesamte Basisbeschreibung leeren? Das aktualisiert den Wikitext aller Dateien.',
        'es': '¿Vaciar realmente toda la descripción base? Esto actualiza el wikitexto de todos los archivos.',
        'fr': 'Vraiment effacer toute la description de base ? Cela met à jour le wikitexte de tous les fichiers.',
        'it': 'Svuotare davvero l’intera descrizione base? Questo aggiorna il wikitesto di tutti i file.',
    },
    'MediaWiki account': {
        'de': 'MediaWiki-Konto',
        'es': 'Cuenta de MediaWiki',
        'fr': 'Compte MediaWiki',
        'it': 'Account MediaWiki',
    },
    'Other (ISO code)…': {
        'de': 'Weitere (ISO-Code)…',
        'es': 'Otro (código ISO)…',
        'fr': 'Autre (code ISO)…',
        'it': 'Altro (codice ISO)…',
    },
    'No EXIF data': {
        'de': 'Keine EXIF-Daten',
        'es': 'Sin datos EXIF',
        'fr': 'Pas de données EXIF',
        'it': 'Nessun dato EXIF',
    },
    'Remove saved language…': {
        'de': 'Gespeicherte Sprache entfernen…',
        'es': 'Eliminar idioma guardado…',
        'fr': 'Supprimer une langue enregistrée…',
        'it': 'Rimuovi lingua salvata…',
    },
    'Remove saved language': {
        'de': 'Gespeicherte Sprache entfernen',
        'es': 'Eliminar idioma guardado',
        'fr': 'Supprimer une langue enregistrée',
        'it': 'Rimuovi lingua salvata',
    },
    'Remove which saved language from the dropdown?': {
        'de': 'Welche gespeicherte Sprache soll aus der Auswahlliste entfernt werden?',
        'es': '¿Qué idioma guardado quieres eliminar de la lista desplegable?',
        'fr': 'Quelle langue enregistrée supprimer de la liste déroulante ?',
        'it': 'Quale lingua salvata rimuovere dal menu a discesa?',
    },
    'No saved languages to remove. The four default languages cannot be removed.': {
        'de': 'Keine gespeicherten Sprachen zum Entfernen. Die vier Standardsprachen können nicht entfernt werden.',
        'es': 'No hay idiomas guardados para eliminar. Los cuatro idiomas predeterminados no se pueden eliminar.',
        'fr': 'Aucune langue enregistrée à supprimer. Les quatre langues par défaut ne peuvent pas être supprimées.',
        'it': 'Nessuna lingua salvata da rimuovere. Le quattro lingue predefinite non possono essere rimosse.',
    },
    'Caption language': {
        'de': 'Bildunterschriften-Sprache',
        'es': 'Idioma de la leyenda',
        'fr': 'Langue de la légende',
        'it': 'Lingua della didascalia',
    },
    'ISO language code (e.g. nl, pt, ja):': {
        'de': 'ISO-Sprachcode (z. B. nl, pt, ja):',
        'es': 'Código de idioma ISO (p. ej. nl, pt, ja):',
        'fr': 'Code de langue ISO (p. ex. nl, pt, ja) :',
        'it': 'Codice lingua ISO (ad es. nl, pt, ja):',
    },
    'Not a valid ISO code: {code}': {
        'de': 'Kein gültiger ISO-Code: {code}',
        'es': 'Código ISO no válido: {code}',
        'fr': 'Code ISO non valide : {code}',
        'it': 'Codice ISO non valido: {code}',
    },
    '{n} files selected - a changed field is applied to all of them.': {
        'de': '{n} Dateien ausgewählt – ein geändertes Feld wird auf alle angewendet.',
        'es': '{n} archivos seleccionados: un campo modificado se aplica a todos.',
        'fr': '{n} fichiers sélectionnés – un champ modifié est appliqué à tous.',
        'it': '{n} file selezionati: un campo modificato viene applicato a tutti.',
    },
    # ── 0.12.7 ───────────────────────────────────────────────────────────
    'hide rejects': {
        'de': 'Aussortierte ausblenden',
        'es': 'ocultar descartadas',
        'fr': 'masquer les rejetées',
        'it': 'nascondi gli scarti',
    },
    'Rejected images are shown greyed out with a red X. Check this to hide them completely.': {
        'de': 'Aussortierte Bilder werden grau mit rotem ✕ angezeigt. Hier ankreuzen, um sie ganz auszublenden.',
        'es': 'Las imágenes descartadas se muestran en gris con una ✕ roja. Marque esta casilla para ocultarlas por completo.',
        'fr': 'Les images rejetées sont affichées en gris avec une ✕ rouge. Cochez cette case pour les masquer complètement.',
        'it': 'Le immagini scartate vengono mostrate in grigio con una ✕ rossa. Selezionare questa casella per nasconderle del tutto.',
    },
    'Confirmation code or URL:': {
        'de': 'Bestätigungscode oder URL:',
        'es': 'Código de confirmación o URL:',
        'fr': 'Code de confirmation ou URL :',
        'it': 'Codice di conferma o URL:',
    },
    'paste the code - or the whole address from the browser': {
        'de': 'Code einfügen – oder die komplette Adresse aus dem Browser',
        'es': 'pegue el código o la dirección completa del navegador',
        'fr': 'collez le code – ou l’adresse complète du navigateur',
        'it': 'incollare il codice oppure l’indirizzo completo dal browser',
    },
    'If the browser shows a code after "Allow", paste it here. If it instead jumps to a 127.0.0.1 address - even one that fails to load - copy that entire address from the address bar and paste it here; Cammello reads the confirmation out of it.': {
        'de': 'Zeigt der Browser nach „Zulassen“ einen Code, diesen hier einfügen. Springt er stattdessen auf eine 127.0.0.1-Adresse – auch auf eine, die nicht lädt –, die ganze Adresse aus der Adresszeile kopieren und hier einfügen; Cammello liest die Bestätigung daraus.',
        'es': 'Si el navegador muestra un código tras «Permitir», péguelo aquí. Si en su lugar salta a una dirección 127.0.0.1 —aunque no se cargue—, copie esa dirección completa de la barra de direcciones y péguela aquí; Cammello extrae de ella la confirmación.',
        'fr': 'Si le navigateur affiche un code après « Autoriser », collez-le ici. S’il bascule à la place vers une adresse 127.0.0.1 – même si elle ne se charge pas –, copiez cette adresse entière depuis la barre d’adresse et collez-la ici ; Cammello en extrait la confirmation.',
        'it': 'Se dopo «Consenti» il browser mostra un codice, incollarlo qui. Se invece passa a un indirizzo 127.0.0.1 – anche se non si carica –, copiare l’intero indirizzo dalla barra degli indirizzi e incollarlo qui; Cammello ne ricava la conferma.',
    },
    'Confirm manually (use if the automatic confirmation does not work - a code or the address from the browser)': {
        'de': 'Manuell bestätigen (falls die automatische Bestätigung nicht klappt – Code oder Adresse aus dem Browser)',
        'es': 'Confirmar manualmente (si la confirmación automática no funciona: un código o la dirección del navegador)',
        'fr': 'Confirmer manuellement (si la confirmation automatique échoue – un code ou l’adresse du navigateur)',
        'it': 'Conferma manuale (se la conferma automatica non funziona: un codice o l’indirizzo dal browser)',
    },
    'Open the link and click "Allow". Then paste either the code shown, or - if the browser jumps to a 127.0.0.1 address, even a failing one - that whole address, and press Finish.': {
        'de': 'Den Link öffnen und auf „Zulassen“ klicken. Dann entweder den angezeigten Code einfügen oder – falls der Browser auf eine 127.0.0.1-Adresse springt, auch auf eine fehlschlagende – diese ganze Adresse, und auf „Fertigstellen“ klicken.',
        'es': 'Abra el enlace y haga clic en «Permitir». Después pegue el código mostrado o —si el navegador salta a una dirección 127.0.0.1, aunque falle— esa dirección completa, y pulse «Finalizar».',
        'fr': 'Ouvrez le lien et cliquez sur « Autoriser ». Collez ensuite le code affiché ou – si le navigateur bascule vers une adresse 127.0.0.1, même en échec – cette adresse entière, puis cliquez sur « Terminer ».',
        'it': 'Aprire il collegamento e fare clic su «Consenti». Quindi incollare il codice mostrato oppure – se il browser passa a un indirizzo 127.0.0.1, anche non funzionante – l’intero indirizzo, e premere «Fine».',
    },
    'No confirmation found in what was pasted. Paste either the code or the complete 127.0.0.1 address from the browser.': {
        'de': 'In der Einfügung war keine Bestätigung zu finden. Bitte entweder den Code oder die komplette 127.0.0.1-Adresse aus dem Browser einfügen.',
        'es': 'No se encontró ninguna confirmación en lo pegado. Pegue el código o la dirección 127.0.0.1 completa del navegador.',
        'fr': 'Aucune confirmation trouvée dans le texte collé. Collez soit le code, soit l’adresse 127.0.0.1 complète du navigateur.',
        'it': 'Nessuna conferma trovata nel testo incollato. Incollare il codice oppure l’indirizzo 127.0.0.1 completo dal browser.',
    },
    'Open the link and click "Allow". If the browser returns on its own you are done. Otherwise paste the code shown - or the whole 127.0.0.1 address from the browser, even if the page failed to load.': {
        'de': 'Den Link öffnen und auf „Zulassen“ klicken. Kehrt der Browser von selbst zurück, ist alles erledigt. Andernfalls den angezeigten Code einfügen – oder die komplette 127.0.0.1-Adresse aus dem Browser, auch wenn die Seite nicht geladen hat.',
        'es': 'Abra el enlace y haga clic en «Permitir». Si el navegador vuelve por sí solo, ya está. Si no, pegue el código mostrado o la dirección 127.0.0.1 completa del navegador, aunque la página no se haya cargado.',
        'fr': 'Ouvrez le lien et cliquez sur « Autoriser ». Si le navigateur revient de lui-même, c’est terminé. Sinon, collez le code affiché – ou l’adresse 127.0.0.1 complète du navigateur, même si la page n’a pas chargé.',
        'it': 'Aprire il collegamento e fare clic su «Consenti». Se il browser torna da solo, è tutto fatto. Altrimenti incollare il codice mostrato oppure l’intero indirizzo 127.0.0.1 dal browser, anche se la pagina non si è caricata.',
    },
    'Sign in with a bot password…': {
        'de': 'Mit Botpasswort anmelden…',
        'es': 'Iniciar sesión con una contraseña de bot…',
        'fr': 'Se connecter avec un mot de passe de bot…',
        'it': 'Accedi con una password bot…',
    },
    'Fallback: sign in with a bot password instead of the browser authorization.': {
        'de': 'Rückfallweg: Anmeldung mit einem Botpasswort statt über die Browser-Autorisierung.',
        'es': 'Alternativa: iniciar sesión con una contraseña de bot en lugar de la autorización por navegador.',
        'fr': 'Solution de repli : connexion avec un mot de passe de bot au lieu de l’autorisation par navigateur.',
        'it': 'Ripiego: accesso con una password bot invece dell’autorizzazione tramite browser.',
    },
    'Edit bot password…': {
        'de': 'Botpasswort bearbeiten…',
        'es': 'Editar la contraseña de bot…',
        'fr': 'Modifier le mot de passe de bot…',
        'it': 'Modifica la password bot…',
    },
    'Stores the bot password used by the fallback sign-in.': {
        'de': 'Speichert das Botpasswort, das der Rückfall-Anmeldung dient.',
        'es': 'Guarda la contraseña de bot que utiliza el inicio de sesión alternativo.',
        'fr': 'Enregistre le mot de passe de bot utilisé par la connexion de repli.',
        'it': 'Salva la password bot usata dall’accesso di ripiego.',
    },
    'Workflow': {
        'de': 'Arbeitsablauf',
        'es': 'Flujo de trabajo',
        'fr': 'Flux de travail',
        'it': 'Flusso di lavoro',
    },
    'Events/Portraits': {
        'de': 'Veranstaltungen/Porträts',
        'es': 'Eventos/Retratos',
        'fr': 'Événements/Portraits',
        'it': 'Eventi/Ritratti',
    },
    'Buildings and Landscapes': {
        'de': 'Gebäude und Landschaften',
        'es': 'Edificios y paisajes',
        'fr': 'Bâtiments et paysages',
        'it': 'Edifici e paesaggi',
    },
    'Presets templates, category suggestions and structured data for '
    'this tab.\nIt fills fields, it never locks them: everything '
    'stays editable, and\nswitching does not overwrite what you have '
    'already entered.\n\nThe IPTC tab is not affected by this.': {
        'de': 'Belegt Vorlagen, Kategorievorschläge und strukturierte Daten '
              'für diesen Tab vor.\nEs füllt Felder, es sperrt sie nicht: '
              'alles bleibt änderbar, und das\nUmschalten überschreibt nicht, '
              'was du bereits eingetragen hast.\n\nDer IPTC-Tab ist davon nicht '
              'betroffen.',
        'es': 'Predefine plantillas, sugerencias de categoría y datos '
              'estructurados para esta pestaña.\nRellena campos, no los '
              'bloquea: todo sigue siendo editable y\ncambiar de flujo no '
              'sobrescribe lo que ya has introducido.\n\nLa pestaña IPTC no '
              'se ve afectada.',
        'fr': 'Préremplit modèles, suggestions de catégories et données '
              'structurées pour cet onglet.\nIl remplit les champs sans les '
              'verrouiller : tout reste modifiable, et\nchanger de flux '
              'n’écrase pas ce que vous avez déjà saisi.\n\nL’onglet IPTC '
              'n’est pas concerné.',
        'it': 'Preimposta modelli, suggerimenti di categoria e dati '
              'strutturati per questa scheda.\nCompila i campi senza '
              'bloccarli: tutto resta modificabile e\ncambiare flusso non '
              'sovrascrive quanto hai già inserito.\n\nLa scheda IPTC non '
              'è interessata.',
    },
    'Preview could not be read: {name}': {
        'de': 'Vorschau konnte nicht gelesen werden: {name}',
        'es': 'No se pudo leer la vista previa: {name}',
        'fr': 'Impossible de lire l’aperçu : {name}',
        'it': 'Impossibile leggere l’anteprima: {name}',
    },
    'Location': {
        'de': 'Standort',
        'es': 'Ubicación',
        'fr': 'Lieu',
        'it': 'Luogo',
    },
    'Location (in selected files)': {
        'de': 'Standort (in ausgewählten Dateien)',
        'es': 'Ubicación (en los archivos seleccionados)',
        'fr': 'Lieu (dans les fichiers sélectionnés)',
        'it': 'Luogo (nei file selezionati)',
    },
    'Where the camera stood, and where the depicted thing stands. For a portrait the two are the same; for a building they are not, and Commons keeps them in separate templates.': {
        'de': 'Wo die Kamera stand und wo das Abgebildete steht. Beim Porträt ist das dasselbe, beim Gebäude nicht — und Commons führt beides in getrennten Vorlagen.',
        'es': 'Dónde estaba la cámara y dónde está lo representado. En un retrato coinciden; en un edificio no, y Commons los guarda en plantillas distintas.',
        'fr': 'Où se trouvait l’appareil et où se trouve le sujet. Pour un portrait c’est identique ; pour un bâtiment non, et Commons les conserve dans des modèles distincts.',
        'it': 'Dove si trovava la fotocamera e dove si trova il soggetto. In un ritratto coincidono, in un edificio no, e Commons li tiene in modelli separati.',
    },
    'Camera position': {
        'de': 'Kamerastandort',
        'es': 'Posición de la cámara',
        'fr': 'Position de l’appareil',
        'it': 'Posizione della fotocamera',
    },
    'Object position': {
        'de': 'Objektstandort',
        'es': 'Posición del objeto',
        'fr': 'Position de l’objet',
        'it': 'Posizione dell’oggetto',
    },
    'Camera position -> {{Location dec}} and P1259 (point of view). Decimal degrees, latitude first, separated by a comma.': {
        'de': 'Kamerastandort → {{Location dec}} und P1259 (Aufnahmestandort). Dezimalgrad, Breite zuerst, mit Komma getrennt.',
        'es': 'Posición de la cámara → {{Location dec}} y P1259 (punto de vista). Grados decimales, primero la latitud, separados por coma.',
        'fr': 'Position de l’appareil → {{Location dec}} et P1259 (point de vue). Degrés décimaux, latitude d’abord, séparés par une virgule.',
        'it': 'Posizione della fotocamera → {{Location dec}} e P1259 (punto di ripresa). Gradi decimali, prima la latitudine, separati da virgola.',
    },
    'Position of the depicted object -> {{Object location dec}} and P9149 (depicted place). This is the building, not the spot you stood on.': {
        'de': 'Standort des abgebildeten Objekts → {{Object location dec}} und P9149 (abgebildeter Ort). Das ist das Gebäude, nicht die Stelle, auf der du standest.',
        'es': 'Posición del objeto representado → {{Object location dec}} y P9149 (lugar representado). Es el edificio, no el punto donde estabas.',
        'fr': 'Position de l’objet représenté → {{Object location dec}} et P9149 (lieu représenté). C’est le bâtiment, pas l’endroit où vous vous teniez.',
        'it': 'Posizione dell’oggetto raffigurato → {{Object location dec}} e P9149 (luogo raffigurato). È l’edificio, non il punto in cui eri.',
    },
    'Read from file': {
        'de': 'Aus Datei lesen',
        'es': 'Leer del archivo',
        'fr': 'Lire depuis le fichier',
        'it': 'Leggi dal file',
    },
    'Reads the camera position of every selected file from its .xmp sidecar, and from the EXIF when the sidecar has none. A value you entered yourself is not overwritten.': {
        'de': 'Liest den Kamerastandort jeder ausgewählten Datei aus ihrer .xmp-Begleitdatei, und aus den EXIF-Daten, wenn die Begleitdatei keinen hat. Selbst eingetragene Werte werden nicht überschrieben.',
        'es': 'Lee la posición de la cámara de cada archivo seleccionado desde su archivo .xmp asociado, y del EXIF si aquel no la tiene. No se sobrescribe un valor introducido por ti.',
        'fr': 'Lit la position de l’appareil de chaque fichier sélectionné dans son fichier .xmp associé, et dans l’EXIF si celui-ci n’en contient pas. Une valeur saisie par vous n’est pas écrasée.',
        'it': 'Legge la posizione della fotocamera di ogni file selezionato dal file .xmp associato, e dall’EXIF se quello non ne ha. Un valore inserito da te non viene sovrascritto.',
    },
    'Apply to selection': {
        'de': 'Auf Auswahl anwenden',
        'es': 'Aplicar a la selección',
        'fr': 'Appliquer à la sélection',
        'it': 'Applica alla selezione',
    },
    'Writes the two fields above into every selected file of the list. An empty field clears that position.': {
        'de': 'Schreibt die beiden Felder oben in jede ausgewählte Datei der Liste. Ein leeres Feld löscht den jeweiligen Standort.',
        'es': 'Escribe los dos campos anteriores en cada archivo seleccionado de la lista. Un campo vacío borra esa posición.',
        'fr': 'Écrit les deux champs ci-dessus dans chaque fichier sélectionné de la liste. Un champ vide efface la position correspondante.',
        'it': 'Scrive i due campi sopra in ogni file selezionato dell’elenco. Un campo vuoto cancella quella posizione.',
    },
    'Location read: {found} of {total}.': {
        'de': 'Standort gelesen: {found} von {total}.',
        'es': 'Ubicación leída: {found} de {total}.',
        'fr': 'Lieu lu : {found} sur {total}.',
        'it': 'Luogo letto: {found} su {total}.',
    },
    'Not a usable coordinate: {text}': {
        'de': 'Keine brauchbare Koordinate: {text}',
        'es': 'No es una coordenada utilizable: {text}',
        'fr': 'Coordonnée inutilisable : {text}',
        'it': 'Coordinata non utilizzabile: {text}',
    },
    'Camera position (wikitext + SDC):': {
        'de': 'Kamerastandort (Wikitext + SDC):',
        'es': 'Posición de la cámara (wikitexto + SDC):',
        'fr': 'Position de l’appareil (wikitexte + SDC) :',
        'it': 'Posizione della fotocamera (wikitesto + SDC):',
    },
    'Object position (wikitext + SDC):': {
        'de': 'Objektstandort (Wikitext + SDC):',
        'es': 'Posición del objeto (wikitexto + SDC):',
        'fr': 'Position de l’objet (wikitexte + SDC) :',
        'it': 'Posizione dell’oggetto (wikitesto + SDC):',
    },
    'Where the DEPICTED thing stands - the building, not the spot you\nstood on. Decimal degrees: latitude, longitude.\n\nBecomes {{Object location dec}} in the wikitext and the "coordinates\nof depicted place" statement (P9149) in the structured data.\n\nOptional: "from Wikidata" fetches it from the item of the building\nif that item carries a coordinate.': {
        'de': 'Wo das ABGEBILDETE steht — das Gebäude, nicht die Stelle,\nauf der du standest. Dezimalgrad: Breite, Länge.\n\nWird {{Object location dec}} im Wikitext und die Aussage\n„Koordinaten des abgebildeten Ortes“ (P9149) in den strukturierten Daten.\n\nOptional: „aus Wikidata“ holt sie aus dem Item des Gebäudes,\nwenn dieses eine Koordinate trägt.',
        'es': 'Dónde está lo REPRESENTADO — el edificio, no el punto\ndonde estabas. Grados decimales: latitud, longitud.\n\nSe convierte en {{Object location dec}} en el wikitexto y en la declaración\n«coordenadas del lugar representado» (P9149) en los datos estructurados.\n\nOpcional: «desde Wikidata» la toma del elemento del edificio\nsi este tiene una coordenada.',
        'fr': 'Où se trouve le SUJET — le bâtiment, pas l’endroit\noù vous vous teniez. Degrés décimaux : latitude, longitude.\n\nDevient {{Object location dec}} dans le wikitexte et la déclaration\n« coordonnées du lieu représenté » (P9149) dans les données structurées.\n\nOptionnel : « depuis Wikidata » la récupère de l’élément du bâtiment\nsi celui-ci porte une coordonnée.',
        'it': 'Dove si trova il SOGGETTO — l’edificio, non il punto\nin cui eri. Gradi decimali: latitudine, longitudine.\n\nDiventa {{Object location dec}} nel wikitesto e la dichiarazione\n«coordinate del luogo raffigurato» (P9149) nei dati strutturati.\n\nOpzionale: «da Wikidata» la recupera dall’elemento dell’edificio\nse questo ha una coordinata.',
    },
    'from Wikidata': {
        'de': 'aus Wikidata',
        'es': 'desde Wikidata',
        'fr': 'depuis Wikidata',
        'it': 'da Wikidata',
    },
    'Take the coordinate from the Wikidata item entered under depicts.': {
        'de': 'Nimmt die Koordinate aus dem Wikidata-Item, das unter „Bildet ab“ eingetragen ist.',
        'es': 'Toma la coordenada del elemento de Wikidata indicado en «representa».',
        'fr': 'Reprend la coordonnée de l’élément Wikidata indiqué sous « représente ».',
        'it': 'Prende la coordinata dall’elemento Wikidata indicato in «raffigura».',
    },
    'Read location from file': {
        'de': 'Standort aus Datei lesen',
        'es': 'Leer ubicación del archivo',
        'fr': 'Lire le lieu depuis le fichier',
        'it': 'Leggi il luogo dal file',
    },
    'Clear all location data': {
        'de': 'Alle Standortdaten löschen',
        'es': 'Borrar todos los datos de ubicación',
        'fr': 'Effacer toutes les données de lieu',
        'it': 'Cancella tutti i dati di luogo',
    },
    'Removes both coordinates from EVERY file in the list. This is the way back when the camera recorded a wrong position: clear it, then enter or read the right one.': {
        'de': 'Entfernt beide Koordinaten aus JEDER Datei der Liste. Das ist der Weg zurück, wenn die Kamera eine falsche Position aufgezeichnet hat: löschen, dann die richtige eintragen oder einlesen.',
        'es': 'Elimina ambas coordenadas de TODOS los archivos de la lista. Es el camino de vuelta cuando la cámara registró una posición errónea: borrar y luego introducir o leer la correcta.',
        'fr': 'Supprime les deux coordonnées de TOUS les fichiers de la liste. C’est le retour en arrière quand l’appareil a enregistré une mauvaise position : effacer, puis saisir ou lire la bonne.',
        'it': 'Rimuove entrambe le coordinate da OGNI file dell’elenco. È la via di ritorno quando la fotocamera ha registrato una posizione sbagliata: cancellare, poi inserire o leggere quella giusta.',
    },
    'Remove both coordinates from all {n} files?': {
        'de': 'Beide Koordinaten aus allen {n} Dateien entfernen?',
        'es': '¿Eliminar ambas coordenadas de los {n} archivos?',
        'fr': 'Supprimer les deux coordonnées des {n} fichiers ?',
        'it': 'Rimuovere entrambe le coordinate da tutti i {n} file?',
    },
    'No Wikidata item under "depicts" to take a coordinate from.': {
        'de': 'Unter „Bildet ab“ steht kein Wikidata-Item, aus dem eine Koordinate kommen könnte.',
        'es': 'No hay ningún elemento de Wikidata en «representa» del que tomar una coordenada.',
        'fr': 'Aucun élément Wikidata sous « représente » dont tirer une coordonnée.',
        'it': 'Nessun elemento Wikidata in «raffigura» da cui prendere una coordinata.',
    },
    'Wikidata could not be reached: {error}': {
        'de': 'Wikidata war nicht erreichbar: {error}',
        'es': 'No se pudo acceder a Wikidata: {error}',
        'fr': 'Wikidata est inaccessible : {error}',
        'it': 'Wikidata non raggiungibile: {error}',
    },
    'That item carries no coordinate (P625).': {
        'de': 'Dieses Item trägt keine Koordinate (P625).',
        'es': 'Ese elemento no tiene coordenada (P625).',
        'fr': 'Cet élément ne porte pas de coordonnée (P625).',
        'it': 'Questo elemento non ha una coordinata (P625).',
    },
    'Nothing left to undo.': {
        'de': 'Nichts mehr rückgängig zu machen.',
        'es': 'No queda nada que deshacer.',
        'fr': 'Plus rien à annuler.',
        'it': 'Non c’è più nulla da annullare.',
    },
    'Undone.': {
        'de': 'Rückgängig gemacht.',
        'es': 'Deshecho.',
        'fr': 'Annulé.',
        'it': 'Annullato.',
    },
    'Undone in another folder: {name}': {
        'de': 'Rückgängig gemacht in einem anderen Ordner: {name}',
        'es': 'Deshecho en otra carpeta: {name}',
        'fr': 'Annulé dans un autre dossier : {name}',
        'it': 'Annullato in un’altra cartella: {name}',
    },
    'Asking Wikidata…': {
        'de': 'Frage Wikidata…',
        'es': 'Consultando Wikidata…',
        'fr': 'Interrogation de Wikidata…',
        'it': 'Interrogo Wikidata…',
    },
    'Match GPX track': {
        'de': 'GPX-Track zuordnen',
        'es': 'Asignar traza GPX',
        'fr': 'Associer une trace GPX',
        'it': 'Associa traccia GPX',
    },
    'Match GPX track…': {
        'de': 'GPX-Track zuordnen…',
        'es': 'Asignar traza GPX…',
        'fr': 'Associer une trace GPX…',
        'it': 'Associa traccia GPX…',
    },
    'Matches a logger track against the capture times of the files and fills the camera positions. Shows every match before anything is written.': {
        'de': 'Ordnet einen Logger-Track den Aufnahmezeiten der Dateien zu und füllt die Kamerastandorte. Zeigt jede Zuordnung, bevor etwas geschrieben wird.',
        'es': 'Asigna una traza de registrador a las horas de captura de los archivos y rellena las posiciones de la cámara. Muestra cada coincidencia antes de escribir nada.',
        'fr': 'Associe une trace de logger aux heures de prise de vue des fichiers et remplit les positions de l’appareil. Montre chaque correspondance avant toute écriture.',
        'it': 'Associa una traccia del logger agli orari di scatto dei file e compila le posizioni della fotocamera. Mostra ogni corrispondenza prima di scrivere.',
    },
    'No track picked yet': {
        'de': 'Noch kein Track gewählt',
        'es': 'Aún no se ha elegido una traza',
        'fr': 'Aucune trace choisie',
        'it': 'Nessuna traccia scelta',
    },
    'Pick GPX file…': {
        'de': 'GPX-Datei wählen…',
        'es': 'Elegir archivo GPX…',
        'fr': 'Choisir un fichier GPX…',
        'it': 'Scegli file GPX…',
    },
    'Track': {
        'de': 'Track',
        'es': 'Traza',
        'fr': 'Trace',
        'it': 'Traccia',
    },
    'Camera clock offset from UTC': {
        'de': 'Kamerauhr-Versatz zu UTC',
        'es': 'Desfase del reloj de la cámara respecto a UTC',
        'fr': 'Décalage de l’horloge de l’appareil par rapport à UTC',
        'it': 'Scarto dell’orologio della fotocamera rispetto a UTC',
    },
    'Maximum time gap': {
        'de': 'Maximaler Zeitabstand',
        'es': 'Diferencia máxima de tiempo',
        'fr': 'Écart de temps maximal',
        'it': 'Distanza temporale massima',
    },
    'How far the CAMERA clock stood from UTC when the pictures were taken.\nPreset from this computer\'s time zone - right exactly when the camera\nclock stood in this zone. A trip abroad or a drifting camera clock\nneeds a correction here.': {
        'de': 'Wie weit die KAMERAUHR bei der Aufnahme von UTC entfernt stand.\nVorbelegt aus der Zeitzone dieses Rechners — richtig genau dann, wenn die\nKamerauhr in dieser Zone stand. Eine Reise ins Ausland oder eine\nnachgehende Kamerauhr braucht hier eine Korrektur.',
        'es': 'Cuánto se alejaba el reloj de la CÁMARA de UTC al tomar las fotos.\nPrefijado con la zona horaria de este equipo: correcto justo cuando el\nreloj de la cámara estaba en esta zona. Un viaje al extranjero o un reloj\ndesajustado requiere una corrección aquí.',
        'fr': 'De combien l’horloge de l’APPAREIL s’écartait d’UTC à la prise de vue.\nPrérempli avec le fuseau de cet ordinateur — juste exactement quand\nl’horloge de l’appareil était dans ce fuseau. Un voyage à l’étranger ou\nune horloge qui dérive demande une correction ici.',
        'it': 'Quanto l’orologio della FOTOCAMERA distava da UTC allo scatto.\nPreimpostato con il fuso di questo computer — esatto proprio quando\nl’orologio della fotocamera era in questo fuso. Un viaggio all’estero o un\norologio che deriva richiede qui una correzione.',
    },
    'A photo further than this from every track point gets NO position\nrather than a wrong one - a logger that was off for an hour must not\npin the photo to wherever the track stopped.': {
        'de': 'Ein Foto, das weiter als das von jedem Trackpunkt entfernt ist, bekommt\nKEINEN Standort statt eines falschen — ein Logger, der eine Stunde aus\nwar, darf das Foto nicht dorthin heften, wo der Track gerade endete.',
        'es': 'Una foto más alejada que esto de todos los puntos de la traza NO recibe\nposición en lugar de una errónea: un registrador apagado una hora no debe\nfijar la foto donde la traza se detuvo.',
        'fr': 'Une photo plus éloignée que cela de chaque point de la trace ne reçoit\nAUCUNE position plutôt qu’une fausse — un logger éteint une heure ne doit\npas épingler la photo là où la trace s’est arrêtée.',
        'it': 'Una foto più lontana di così da ogni punto della traccia NON riceve\nposizione anziché una sbagliata — un logger spento per un’ora non deve\nfissare la foto dove la traccia si è fermata.',
    },
    'File': {
        'de': 'Datei',
        'es': 'Archivo',
        'fr': 'Fichier',
        'it': 'File',
    },
    'Capture time': {
        'de': 'Aufnahmezeit',
        'es': 'Hora de captura',
        'fr': 'Heure de prise de vue',
        'it': 'Orario di scatto',
    },
    'Matched position': {
        'de': 'Zugeordneter Standort',
        'es': 'Posición asignada',
        'fr': 'Position associée',
        'it': 'Posizione associata',
    },
    'Overwrite camera positions the files already have': {
        'de': 'Vorhandene Kamerastandorte überschreiben',
        'es': 'Sobrescribir posiciones de cámara existentes',
        'fr': 'Écraser les positions d’appareil existantes',
        'it': 'Sovrascrivi le posizioni della fotocamera esistenti',
    },
    'Off: only files WITHOUT a camera position get one. On: the matched\nposition replaces what is there - for the case where the camera GPS\nwas wrong and has been cleared or is to be replaced outright.': {
        'de': 'Aus: nur Dateien OHNE Kamerastandort bekommen einen. An: die zugeordnete\nPosition ersetzt den vorhandenen Wert — für den Fall, dass das Kamera-GPS\nfalsch war und gelöscht wurde oder direkt ersetzt werden soll.',
        'es': 'Desactivado: solo los archivos SIN posición de cámara reciben una.\nActivado: la posición asignada sustituye a la existente, para cuando el\nGPS de la cámara era erróneo y se borró o debe sustituirse directamente.',
        'fr': 'Désactivé : seuls les fichiers SANS position d’appareil en reçoivent une.\nActivé : la position associée remplace l’existante — pour le cas où le GPS\nde l’appareil était faux et a été effacé ou doit être remplacé.',
        'it': 'Disattivato: solo i file SENZA posizione della fotocamera ne ricevono\nuna. Attivato: la posizione associata sostituisce quella esistente — per\nil caso in cui il GPS della fotocamera era sbagliato ed è stato cancellato\no va sostituito direttamente.',
    },
    'no capture time': {
        'de': 'keine Aufnahmezeit',
        'es': 'sin hora de captura',
        'fr': 'pas d’heure de prise de vue',
        'it': 'nessun orario di scatto',
    },
    'no track point close enough': {
        'de': 'kein Trackpunkt nah genug',
        'es': 'ningún punto de la traza suficientemente cercano',
        'fr': 'aucun point de trace assez proche',
        'it': 'nessun punto della traccia abbastanza vicino',
    },
    '(kept - has a position)': {
        'de': '(bleibt — hat schon einen Standort)',
        'es': '(se conserva: ya tiene posición)',
        'fr': '(conservé — a déjà une position)',
        'it': '(mantenuto — ha già una posizione)',
    },
    '{points} track points; {matched} of {total} files matched, {applied} would be written.': {
        'de': '{points} Trackpunkte; {matched} von {total} Dateien zugeordnet, {applied} würden geschrieben.',
        'es': '{points} puntos de traza; {matched} de {total} archivos asignados, {applied} se escribirían.',
        'fr': '{points} points de trace ; {matched} fichiers sur {total} associés, {applied} seraient écrits.',
        'it': '{points} punti della traccia; {matched} file su {total} associati, {applied} verrebbero scritti.',
    },
    'The track holds no usable points.': {
        'de': 'Der Track enthält keine brauchbaren Punkte.',
        'es': 'La traza no contiene puntos utilizables.',
        'fr': 'La trace ne contient aucun point utilisable.',
        'it': 'La traccia non contiene punti utilizzabili.',
    },
    'Apply to files': {
        'de': 'Auf Dateien anwenden',
        'es': 'Aplicar a los archivos',
        'fr': 'Appliquer aux fichiers',
        'it': 'Applica ai file',
    },
    'The list holds no files.': {
        'de': 'Die Liste enthält keine Dateien.',
        'es': 'La lista no contiene archivos.',
        'fr': 'La liste ne contient aucun fichier.',
        'it': 'L’elenco non contiene file.',
    },
    'GPX positions written to {n} file(s).': {
        'de': 'GPX-Standorte in {n} Datei(en) geschrieben.',
        'es': 'Posiciones GPX escritas en {n} archivo(s).',
        'fr': 'Positions GPX écrites dans {n} fichier(s).',
        'it': 'Posizioni GPX scritte in {n} file.',
    },
    '&Location': {
        'de': '&Standort',
        'es': '&Ubicación',
        'fr': '&Lieu',
        'it': '&Luogo',
    },
    '&Read location from file': {
        'de': 'Standort aus Datei &lesen',
        'es': '&Leer ubicación del archivo',
        'fr': '&Lire le lieu depuis le fichier',
        'it': '&Leggi il luogo dal file',
    },
    '&Match GPX track…': {
        'de': 'GPX-Track &zuordnen…',
        'es': '&Asignar traza GPX…',
        'fr': '&Associer une trace GPX…',
        'it': '&Associa traccia GPX…',
    },
    '&Clear all location data': {
        'de': 'Alle Standortdaten lös&chen',
        'es': '&Borrar todos los datos de ubicación',
        'fr': '&Effacer toutes les données de lieu',
        'it': '&Cancella tutti i dati di luogo',
    },
    'Camera position from the .xmp sidecar, or from the EXIF when the sidecar has none.': {
        'de': 'Kamerastandort aus der .xmp-Begleitdatei, oder aus den EXIF-Daten, wenn diese keinen hat.',
        'es': 'Posición de la cámara desde el archivo .xmp asociado, o del EXIF si aquel no la tiene.',
        'fr': 'Position de l’appareil depuis le fichier .xmp associé, ou depuis l’EXIF s’il n’en contient pas.',
        'it': 'Posizione della fotocamera dal file .xmp associato, o dall’EXIF se quello non ne ha.',
    },
    'Match a logger track against the capture times and fill the camera positions.': {
        'de': 'Ordnet einen Logger-Track den Aufnahmezeiten zu und füllt die Kamerastandorte.',
        'es': 'Asigna una traza de registrador a las horas de captura y rellena las posiciones de la cámara.',
        'fr': 'Associe une trace de logger aux heures de prise de vue et remplit les positions de l’appareil.',
        'it': 'Associa una traccia del logger agli orari di scatto e compila le posizioni della fotocamera.',
    },
    'Remove both coordinates from every file in the list.': {
        'de': 'Entfernt beide Koordinaten aus jeder Datei der Liste.',
        'es': 'Elimina ambas coordenadas de todos los archivos de la lista.',
        'fr': 'Supprime les deux coordonnées de tous les fichiers de la liste.',
        'it': 'Rimuove entrambe le coordinate da ogni file dell’elenco.',
    },
    'Strongly recommended fields in this section are still empty.': {
        'de': 'Dringend empfohlene Felder in diesem Abschnitt sind noch leer.',
        'es': 'Campos muy recomendados de esta sección siguen vacíos.',
        'fr': 'Des champs fortement recommandés de cette section sont encore vides.',
        'it': 'Campi fortemente consigliati di questa sezione sono ancora vuoti.',
    },
    'Add capture settings to the structured data at upload': {
        'de': 'Aufnahmedaten beim Hochladen in die strukturierten Daten eintragen',
        'es': 'Añadir los ajustes de captura a los datos estructurados al subir',
        'fr': 'Ajouter les réglages de prise de vue aux données structurées à l’envoi',
        'it': 'Aggiungi le impostazioni di scatto ai dati strutturati al caricamento',
    },
    'Copies exposure time, f-number, ISO, focal length, the capture date and\nthe media type from the file into the structured data at upload - plus the\ncamera (and lens) as a Wikidata item, but ONLY when the EXIF string maps\nto exactly one item. Nothing to fill in; ambiguous cameras are skipped.': {
        'de': 'Übernimmt Belichtungszeit, Blendenzahl, ISO, Brennweite, das Aufnahmedatum\nund den Medientyp beim Hochladen aus der Datei in die strukturierten Daten —\ndazu die Kamera (und das Objektiv) als Wikidata-Item, aber NUR, wenn der\nEXIF-String auf genau ein Item passt. Nichts auszufüllen; mehrdeutige Kameras\nwerden übersprungen.',
        'es': 'Copia el tiempo de exposición, el número f, la ISO, la distancia focal, la\nfecha de captura y el tipo de medio del archivo a los datos estructurados al\nsubir; además la cámara (y el objetivo) como elemento de Wikidata, pero SOLO\ncuando la cadena EXIF corresponde exactamente a un elemento. Nada que\nrellenar; las cámaras ambiguas se omiten.',
        'fr': 'Copie le temps de pose, l’ouverture, l’ISO, la focale, la date de prise de\nvue et le type de média du fichier vers les données structurées à l’envoi —\nplus l’appareil (et l’objectif) comme élément Wikidata, mais SEULEMENT si la\nchaîne EXIF correspond à exactement un élément. Rien à remplir ; les\nappareils ambigus sont ignorés.',
        'it': 'Copia tempo di esposizione, numero f, ISO, lunghezza focale, data di scatto\ne tipo di media dal file nei dati strutturati al caricamento — inoltre la\nfotocamera (e l’obiettivo) come elemento Wikidata, ma SOLO quando la stringa\nEXIF corrisponde esattamente a un elemento. Nulla da compilare; le fotocamere\nambigue vengono saltate.',
    },
    'Remove both coordinates from all {n} files - in Cammello AND from the image files themselves? JPEG and TIFF are changed on disk; RAW files are left alone. Place names (city, country) are kept.': {
        'de': 'Beide Koordinaten aus allen {n} Dateien entfernen — in Cammello UND aus den Bilddateien selbst? JPEG und TIFF werden auf der Platte geändert, RAW-Dateien bleiben unangetastet. Ortsnamen (Stadt, Land) bleiben erhalten.',
        'es': '¿Eliminar ambas coordenadas de los {n} archivos, en Cammello Y de los propios archivos de imagen? JPEG y TIFF se modifican en el disco; los archivos RAW no se tocan. Los nombres de lugar (ciudad, país) se conservan.',
        'fr': 'Supprimer les deux coordonnées des {n} fichiers — dans Cammello ET dans les fichiers image eux-mêmes ? Les JPEG et TIFF sont modifiés sur le disque ; les fichiers RAW sont laissés intacts. Les noms de lieu (ville, pays) sont conservés.',
        'it': 'Rimuovere entrambe le coordinate da tutti i {n} file — in Cammello E dai file immagine stessi? JPEG e TIFF vengono modificati sul disco; i file RAW restano intatti. I nomi di luogo (città, paese) vengono mantenuti.',
    },
    'Clearing location data…': {
        'de': 'Standortdaten werden gelöscht…',
        'es': 'Borrando los datos de ubicación…',
        'fr': 'Effacement des données de lieu…',
        'it': 'Cancellazione dei dati di luogo…',
    },
    'Writing positions…': {
        'de': 'Standorte werden geschrieben…',
        'es': 'Escribiendo las posiciones…',
        'fr': 'Écriture des positions…',
        'it': 'Scrittura delle posizioni…',
    },
    'Location cleared: {wiped} file(s), {skipped} skipped, {failed} failed.': {
        'de': 'Standort gelöscht: {wiped} Datei(en), {skipped} übersprungen, {failed} fehlgeschlagen.',
        'es': 'Ubicación borrada: {wiped} archivo(s), {skipped} omitidos, {failed} fallidos.',
        'fr': 'Lieu effacé : {wiped} fichier(s), {skipped} ignorés, {failed} en échec.',
        'it': 'Luogo cancellato: {wiped} file, {skipped} saltati, {failed} falliti.',
    },
    'GPX: {touched} matched, {written} written into files, {skipped} skipped, {failed} failed.': {
        'de': 'GPX: {touched} zugeordnet, {written} in Dateien geschrieben, {skipped} übersprungen, {failed} fehlgeschlagen.',
        'es': 'GPX: {touched} asignados, {written} escritos en archivos, {skipped} omitidos, {failed} fallidos.',
        'fr': 'GPX : {touched} associés, {written} écrits dans les fichiers, {skipped} ignorés, {failed} en échec.',
        'it': 'GPX: {touched} associati, {written} scritti nei file, {skipped} saltati, {failed} falliti.',
    },
    'Sublocation': {
        'de': 'Ortsteil',
        'es': 'Sublocalidad',
        'fr': 'Lieu-dit',
        'it': 'Località',
    },
    'Caption': {
        'de': 'Bildunterschrift',
        'es': 'Leyenda',
        'fr': 'Légende',
        'it': 'Didascalia',
    },
    'Information': {
        'de': 'Information',
        'es': 'Información',
        'fr': 'Information',
        'it': 'Information',
    },
    'still empty: {fields}': {
        'de': 'noch leer: {fields}',
        'es': 'aún vacío: {fields}',
        'fr': 'encore vide : {fields}',
        'it': 'ancora vuoto: {fields}',
    },
    'Strongly recommended: the caption is the structured half, the Information text the wikitext half of the description.': {
        'de': 'Dringend empfohlen: Die Bildunterschrift ist die strukturierte Hälfte, der Information-Text die Wikitext-Hälfte der Beschreibung.',
        'es': 'Muy recomendable: la leyenda es la mitad estructurada y el texto de Information la mitad en wikitexto de la descripción.',
        'fr': 'Fortement recommandé : la légende est la moitié structurée, le texte Information la moitié en wikitexte de la description.',
        'it': 'Fortemente consigliato: la didascalia è la metà strutturata, il testo Information la metà in wikitesto della descrizione.',
    },
    'Alt text for screen readers (SDC only)': {
        'de': 'Alt-Text für Screenreader (nur SDC)',
        'es': 'Texto alternativo para lectores de pantalla (solo SDC)',
        'fr': 'Texte alternatif pour lecteurs d’écran (SDC uniquement)',
        'it': 'Testo alternativo per screen reader (solo SDC)',
    },
    'What someone who cannot see the picture needs to know, in one sentence.\nUploaded as the "alt text" statement (P11265) in this language.\n\nNot the same as the caption: the caption names WHAT this is, the alt\ntext describes what can be SEEN. Commons stores it only in the\nstructured data - there is no wikitext equivalent.': {
        'de': 'Was jemand wissen muss, der das Bild nicht sehen kann — in einem Satz.\nWird als Aussage „Alt-Text" (P11265) in dieser Sprache hochgeladen.\n\nNicht dasselbe wie die Bildunterschrift: Die Unterschrift benennt, WAS das\nist, der Alt-Text beschreibt, was zu SEHEN ist. Commons speichert ihn nur\nin den strukturierten Daten — ein Wikitext-Gegenstück gibt es nicht.',
        'es': 'Lo que necesita saber quien no puede ver la imagen, en una frase.\nSe sube como la declaración «texto alternativo» (P11265) en este idioma.\n\nNo es lo mismo que la leyenda: la leyenda nombra QUÉ es esto, el texto\nalternativo describe lo que se VE. Commons lo guarda solo en los datos\nestructurados; no hay equivalente en wikitexto.',
        'fr': 'Ce que doit savoir quelqu’un qui ne voit pas l’image, en une phrase.\nEnvoyé comme déclaration « texte alternatif » (P11265) dans cette langue.\n\nCe n’est pas la légende : la légende nomme CE QUE c’est, le texte\nalternatif décrit ce qui est VISIBLE. Commons ne le stocke que dans les\ndonnées structurées ; il n’y a pas d’équivalent en wikitexte.',
        'it': 'Ciò che deve sapere chi non può vedere l’immagine, in una frase.\nCaricato come dichiarazione «testo alternativo» (P11265) in questa lingua.\n\nNon è la didascalia: la didascalia dice CHE COSA è, il testo alternativo\ndescrive ciò che si VEDE. Commons lo memorizza solo nei dati strutturati:\nnon esiste un equivalente in wikitesto.',
    },
    'Language code (e.g. nl, pt, ja, ms-Arab, zh-Hant):': {
        'de': 'Sprachcode (z. B. nl, pt, ja, ms-Arab, zh-Hant):',
        'es': 'Código de idioma (p. ej. nl, pt, ja, ms-Arab, zh-Hant):',
        'fr': 'Code de langue (p. ex. nl, pt, ja, ms-Arab, zh-Hant) :',
        'it': 'Codice lingua (p. es. nl, pt, ja, ms-Arab, zh-Hant):',
    },
    'Not a valid language code: {code}': {
        'de': 'Kein gültiger Sprachcode: {code}',
        'es': 'Código de idioma no válido: {code}',
        'fr': 'Code de langue non valide : {code}',
        'it': 'Codice lingua non valido: {code}',
    },
    'Commons does not accept "{code}" as a caption language.': {
        'de': 'Commons akzeptiert „{code}" nicht als Sprache für Bildunterschriften.',
        'es': 'Commons no acepta «{code}» como idioma de leyenda.',
        'fr': 'Commons n’accepte pas « {code} » comme langue de légende.',
        'it': 'Commons non accetta «{code}» come lingua della didascalia.',
    },
    'Workflow changed': {
        'de': 'Workflow gewechselt',
        'es': 'Flujo de trabajo cambiado',
        'fr': 'Flux de travail modifié',
        'it': 'Flusso di lavoro cambiato',
    },
    '{n} file(s) still carry values in fields this workflow hides ({fields}). Hidden does not mean inactive - they would still be uploaded. Clear them now?': {
        'de': '{n} Datei(en) haben noch Werte in Feldern, die dieser Workflow ausblendet ({fields}). Ausgeblendet heißt nicht inaktiv — sie würden trotzdem hochgeladen. Jetzt leeren?',
        'es': '{n} archivo(s) conservan valores en campos que este flujo de trabajo oculta ({fields}). Oculto no significa inactivo: se subirían igualmente. ¿Vaciarlos ahora?',
        'fr': '{n} fichier(s) contiennent encore des valeurs dans des champs masqués par ce flux de travail ({fields}). Masqué ne veut pas dire inactif : ils seraient tout de même envoyés. Les vider maintenant ?',
        'it': '{n} file contengono ancora valori in campi che questo flusso di lavoro nasconde ({fields}). Nascosto non significa inattivo: verrebbero comunque caricati. Svuotarli ora?',
    },
    'Check for &updates…': {
        'de': 'Nach &Aktualisierungen suchen…',
        'es': 'Buscar &actualizaciones…',
        'fr': 'Rechercher des &mises à jour…',
        'it': 'Cerca &aggiornamenti…',
    },
    'Ask GitHub whether a newer release exists.': {
        'de': 'Fragt GitHub, ob es eine neuere Fassung gibt.',
        'es': 'Pregunta a GitHub si existe una versión más reciente.',
        'fr': 'Demande à GitHub s’il existe une version plus récente.',
        'it': 'Chiede a GitHub se esiste una versione più recente.',
    },
    'Check for updates': {
        'de': 'Nach Aktualisierungen suchen',
        'es': 'Buscar actualizaciones',
        'fr': 'Rechercher des mises à jour',
        'it': 'Cerca aggiornamenti',
    },
    'Asking GitHub…': {
        'de': 'Frage GitHub…',
        'es': 'Consultando GitHub…',
        'fr': 'Interrogation de GitHub…',
        'it': 'Interrogo GitHub…',
    },
    'Could not reach GitHub: {error}': {
        'de': 'GitHub war nicht erreichbar: {error}',
        'es': 'No se pudo contactar con GitHub: {error}',
        'fr': 'GitHub est injoignable : {error}',
        'it': 'GitHub non raggiungibile: {error}',
    },
    'You are running the newest version ({version}).': {
        'de': 'Du verwendest die neueste Fassung ({version}).',
        'es': 'Estás usando la versión más reciente ({version}).',
        'fr': 'Vous utilisez la version la plus récente ({version}).',
        'it': 'Stai usando la versione più recente ({version}).',
    },
    'Version {new} ({kind}) is available - you are running {old}.': {
        'de': 'Fassung {new} ({kind}) ist verfügbar — du verwendest {old}.',
        'es': 'La versión {new} ({kind}) está disponible; estás usando {old}.',
        'fr': 'La version {new} ({kind}) est disponible — vous utilisez {old}.',
        'it': 'La versione {new} ({kind}) è disponibile — stai usando {old}.',
    },
    'Check for new versions at startup (once a day)': {
        'de': 'Beim Start nach neuen Fassungen suchen (einmal täglich)',
        'es': 'Buscar versiones nuevas al iniciar (una vez al día)',
        'fr': 'Rechercher de nouvelles versions au démarrage (une fois par jour)',
        'it': 'Cerca nuove versioni all’avvio (una volta al giorno)',
    },
    'Only tell me about stable versions': {
        'de': 'Nur über stabile Fassungen informieren',
        'es': 'Informar solo de versiones estables',
        'fr': 'Ne signaler que les versions stables',
        'it': 'Segnala solo le versioni stabili',
    },
    'Releases with an EVEN final digit are stable, odd ones are experimental.\nWhile you are running an experimental version you are told about\nexperimental ones regardless.': {
        'de': 'Fassungen mit GERADER Endziffer sind stabil, ungerade sind experimentell.\nSolange du selbst eine experimentelle Fassung verwendest, wirst du auch\nüber experimentelle informiert.',
        'es': 'Las versiones con última cifra PAR son estables; las impares, experimentales.\nMientras uses una versión experimental se te informará igualmente de las\nexperimentales.',
        'fr': 'Les versions dont le dernier chiffre est PAIR sont stables, les impaires sont expérimentales.\nTant que vous utilisez une version expérimentale, les versions\nexpérimentales vous sont signalées malgré tout.',
        'it': 'Le versioni con ultima cifra PARI sono stabili, quelle dispari sperimentali.\nFinché usi una versione sperimentale vieni informato comunque di quelle\nsperimentali.',
    },
    'Gallery page:': {
        'de': 'Galerieseite:',
        'es': 'Página de galería:',
        'fr': 'Page de galerie :',
        'it': 'Pagina della galleria:',
    },
    'The FULL name of the gallery page these uploads are listed on,\ne.g. "User:Seewolf/Berlinale 2026". Plain text, no brackets.\n\nLeave empty for no gallery. Since 0.15.2 this is the whole name -\nthere is no separate prefix setting any more.': {
        'de': 'Der VOLLE Name der Galerieseite, auf der diese Uploads gelistet werden,\nz. B. „User:Seewolf/Berlinale 2026". Reiner Text, keine Klammern.\n\nLeer lassen heißt: keine Galerie. Seit 0.15.2 ist das der ganze Name —\neine eigene Präfix-Einstellung gibt es nicht mehr.',
        'es': 'El nombre COMPLETO de la página de galería donde se listan estas subidas,\np. ej. «User:Seewolf/Berlinale 2026». Texto simple, sin corchetes.\n\nDéjalo vacío para no usar galería. Desde 0.15.2 este es el nombre entero:\nya no hay un ajuste de prefijo aparte.',
        'fr': 'Le nom COMPLET de la page de galerie où ces envois sont listés,\np. ex. « User:Seewolf/Berlinale 2026 ». Texte brut, sans crochets.\n\nLaisser vide pour ne pas utiliser de galerie. Depuis 0.15.2 c’est le nom\nentier — il n’y a plus de réglage de préfixe séparé.',
        'it': 'Il nome COMPLETO della pagina della galleria in cui questi caricamenti\nsono elencati, p. es. «User:Seewolf/Berlinale 2026». Testo semplice,\nsenza parentesi.\n\nLascia vuoto per non usare una galleria. Dalla 0.15.2 questo è il nome\nintero: non esiste più un’impostazione di prefisso separata.',
    },
    'working version': {
        'de': 'Arbeitsversion',
        'es': 'versión de trabajo',
        'fr': 'version de travail',
        'it': 'versione di lavoro',
    },
    'test version': {
        'de': 'Testversion',
        'es': 'versión de prueba',
        'fr': 'version de test',
        'it': 'versione di prova',
    },
    'Open download page': {
        'de': 'Download-Seite öffnen',
        'es': 'Abrir la página de descarga',
        'fr': 'Ouvrir la page de téléchargement',
        'it': 'Apri la pagina di download',
    },
    'Releases with an ODD minor number (the digit behind the first dot) are\ntest versions, even ones are working versions. While you are running a\ntest version you are told about test versions regardless.': {
        'de': 'Fassungen mit UNGERADER Minor-Nummer (der Ziffer hinter dem ersten Punkt)\nsind Testversionen, gerade sind Arbeitsversionen. Solange du selbst eine\nTestversion verwendest, wirst du auch über Testversionen informiert.',
        'es': 'Las versiones con número menor IMPAR (la cifra tras el primer punto) son\nversiones de prueba; las pares son versiones de trabajo. Mientras uses una\nversión de prueba se te informará igualmente de las de prueba.',
        'fr': 'Les versions dont le numéro mineur (le chiffre après le premier point) est\nIMPAIR sont des versions de test, les paires des versions de travail. Tant\nque vous utilisez une version de test, celles-ci vous sont signalées.',
        'it': 'Le versioni con numero minore DISPARI (la cifra dopo il primo punto) sono\nversioni di prova, quelle pari versioni di lavoro. Finché usi una versione\ndi prova vieni informato comunque di quelle di prova.',
    },
    'Only tell me about working versions': {
        'de': 'Nur über Arbeitsversionen informieren',
        'es': 'Informar solo de versiones de trabajo',
        'fr': 'Ne signaler que les versions de travail',
        'it': 'Segnala solo le versioni di lavoro',
    },
    '(no source names available)': {
        'de': '(keine Quellnamen verfügbar)',
        'es': '(no hay nombres de origen disponibles)',
        'fr': '(aucun nom source disponible)',
        'it': '(nessun nome di origine disponibile)',
    },
    'File naming:': {
        'de': 'Dateibenennung:',
        'es': 'Nombre de archivo:',
        'fr': 'Nom de fichier :',
        'it': 'Denominazione file:',
    },
    'Custom text:': {
        'de': 'Benutzerdefinierter Text:',
        'es': 'Texto personalizado:',
        'fr': 'Texte personnalisé :',
        'it': 'Testo personalizzato:',
    },
    'Template:': {
        'de': 'Vorlage:',
        'es': 'Plantilla:',
        'fr': 'Modèle :',
        'it': 'Modello:',
    },
    'Example:': {
        'de': 'Beispiel:',
        'es': 'Ejemplo:',
        'fr': 'Exemple :',
        'it': 'Esempio:',
    },
    'Custom name - original file number': {
        'de': 'Benutzerdefinierter Name – Originaldateinummer',
        'es': 'Nombre personalizado – número de archivo original',
        'fr': 'Nom personnalisé – numéro de fichier d’origine',
        'it': 'Nome personalizzato – numero file originale',
    },
    'Custom name - sequence': {
        'de': 'Benutzerdefinierter Name – Sequenz',
        'es': 'Nombre personalizado – secuencia',
        'fr': 'Nom personnalisé – séquence',
        'it': 'Nome personalizzato – sequenza',
    },
    'Custom name (x of y)': {
        'de': 'Benutzerdefinierter Name (x von y)',
        'es': 'Nombre personalizado (x de y)',
        'fr': 'Nom personnalisé (x sur y)',
        'it': 'Nome personalizzato (x di y)',
    },
    'Original file name': {
        'de': 'Originaldateiname',
        'es': 'Nombre de archivo original',
        'fr': 'Nom de fichier d’origine',
        'it': 'Nome file originale',
    },
    'Original file name - sequence': {
        'de': 'Originaldateiname – Sequenz',
        'es': 'Nombre de archivo original – secuencia',
        'fr': 'Nom de fichier d’origine – séquence',
        'it': 'Nome file originale – sequenza',
    },
    'Date - original file name': {
        'de': 'Datum – Originaldateiname',
        'es': 'Fecha – nombre de archivo original',
        'fr': 'Date – nom de fichier d’origine',
        'it': 'Data – nome file originale',
    },
    'Date - custom name - sequence': {
        'de': 'Datum – Benutzerdefinierter Name – Sequenz',
        'es': 'Fecha – nombre personalizado – secuencia',
        'fr': 'Date – nom personnalisé – séquence',
        'it': 'Data – nome personalizzato – sequenza',
    },
    'Custom template…': {
        'de': 'Eigene Vorlage…',
        'es': 'Plantilla propia…',
        'fr': 'Modèle personnalisé…',
        'it': 'Modello personalizzato…',
    },
    'Free template. {n} running number, {c} original file number, {name}\noriginal file name, {text} the custom text above, {date} the capture date.': {
        'de': 'Freie Vorlage. {n} laufende Nummer, {c} Originaldateinummer, {name}\nOriginaldateiname, {text} der Text oben, {date} das Aufnahmedatum.',
        'es': 'Plantilla libre. {n} número correlativo, {c} número de archivo original,\n{name} nombre original, {text} el texto de arriba, {date} la fecha de captura.',
        'fr': 'Modèle libre. {n} numéro courant, {c} numéro de fichier d’origine, {name}\nnom d’origine, {text} le texte ci-dessus, {date} la date de prise de vue.',
        'it': 'Modello libero. {n} numero progressivo, {c} numero file originale, {name}\nnome originale, {text} il testo sopra, {date} la data di scatto.',
    },
    'Open directory…': {
        'de': 'Verzeichnis öffnen…',
        'es': 'Abrir directorio…',
        'fr': 'Ouvrir un répertoire…',
        'it': 'Apri directory…',
    },
    'Open directory': {
        'de': 'Verzeichnis öffnen',
        'es': 'Abrir directorio',
        'fr': 'Ouvrir le répertoire',
        'it': 'Apri directory',
    },
    'Select directory': {
        'de': 'Verzeichnis auswählen',
        'es': 'Seleccionar directorio',
        'fr': 'Choisir un répertoire',
        'it': 'Seleziona directory',
    },
    'No uploadable files in this directory.': {
        'de': 'In diesem Verzeichnis liegen keine hochladbaren Dateien.',
        'es': 'En este directorio no hay archivos que se puedan subir.',
        'fr': 'Ce répertoire ne contient aucun fichier téléversable.',
        'it': 'In questa directory non ci sono file caricabili.',
    },
    'This directory holds {n} files. Loading them all takes a while and a lot of memory. Continue?': {
        'de': 'In diesem Verzeichnis liegen {n} Dateien. Alle zu laden dauert und braucht viel Speicher. Weiter?',
        'es': 'Este directorio contiene {n} archivos. Cargarlos todos lleva tiempo y mucha memoria. ¿Continuar?',
        'fr': 'Ce répertoire contient {n} fichiers. Les charger tous prend du temps et beaucoup de mémoire. Continuer ?',
        'it': 'Questa directory contiene {n} file. Caricarli tutti richiede tempo e molta memoria. Continuare?',
    },
    'Reading files…': {
        'de': 'Dateien werden gelesen…',
        'es': 'Leyendo archivos…',
        'fr': 'Lecture des fichiers…',
        'it': 'Lettura dei file…',
    },
    'Reading file {i} of {n}…': {
        'de': 'Datei {i} von {n} wird gelesen…',
        'es': 'Leyendo el archivo {i} de {n}…',
        'fr': 'Lecture du fichier {i} sur {n}…',
        'it': 'Lettura del file {i} di {n}…',
    },
    'cancelled': {
        'de': 'abgebrochen',
        'es': 'cancelado',
        'fr': 'annulé',
        'it': 'annullato',
    },
    'Load every uploadable file of one directory into the table,\nwithout going through the culling module. Only the directory\nitself, not its subdirectories.': {
        'de': 'Lädt jede hochladbare Datei eines Verzeichnisses in die Tabelle,\nohne den Weg über das Culling-Modul. Nur das Verzeichnis selbst,\nnicht seine Unterverzeichnisse.',
        'es': 'Carga en la tabla todos los archivos subibles de un directorio,\nsin pasar por el módulo de selección. Solo el directorio en sí,\nno sus subdirectorios.',
        'fr': 'Charge dans le tableau tous les fichiers téléversables d’un\nrépertoire, sans passer par le module de tri. Le répertoire\nseul, pas ses sous-répertoires.',
        'it': 'Carica nella tabella ogni file caricabile di una directory,\nsenza passare dal modulo di selezione. Solo la directory\nstessa, non le sue sottodirectory.',
    },
    'Open &workflow file…': {
        'de': 'Workflow-&Datei öffnen…',
        'es': 'Abrir archivo de &flujos…',
        'fr': 'Ouvrir le fichier de &workflows…',
        'it': 'Apri il file dei &flussi…',
    },
    'Edit the workflows in a text editor.': {
        'de': 'Die Workflows in einem Texteditor bearbeiten.',
        'es': 'Editar los flujos de trabajo en un editor de texto.',
        'fr': 'Modifier les workflows dans un éditeur de texte.',
        'it': 'Modificare i flussi di lavoro in un editor di testo.',
    },
    'Reload &workflows': {
        'de': '&Workflows neu laden',
        'es': 'Recargar &flujos',
        'fr': 'Recharger les &workflows',
        'it': 'Ricarica i &flussi',
    },
    'Read the workflow file again after editing it.': {
        'de': 'Die Workflow-Datei nach dem Bearbeiten erneut einlesen.',
        'es': 'Volver a leer el archivo de flujos después de editarlo.',
        'fr': 'Relire le fichier de workflows après modification.',
        'it': 'Rileggere il file dei flussi dopo la modifica.',
    },
    'Workflows': {
        'de': 'Workflows',
        'es': 'Flujos de trabajo',
        'fr': 'Workflows',
        'it': 'Flussi di lavoro',
    },
    'The workflow file could not be written: {error}': {
        'de': 'Die Workflow-Datei konnte nicht geschrieben werden: {error}',
        'es': 'No se pudo escribir el archivo de flujos: {error}',
        'fr': 'Le fichier de workflows n’a pas pu être écrit : {error}',
        'it': 'Non è stato possibile scrivere il file dei flussi: {error}',
    },
    'The workflow file could not be read, so the built-in workflows are being used:\n\n{error}': {
        'de': 'Die Workflow-Datei konnte nicht gelesen werden, daher gelten die eingebauten Workflows:\n\n{error}',
        'es': 'No se pudo leer el archivo de flujos, así que se usan los flujos integrados:\n\n{error}',
        'fr': 'Le fichier de workflows n’a pas pu être lu ; les workflows intégrés sont utilisés :\n\n{error}',
        'it': 'Non è stato possibile leggere il file dei flussi, quindi si usano quelli integrati:\n\n{error}',
    },
    'Workflows reloaded. Some entries were ignored:\n\n{list}': {
        'de': 'Workflows neu geladen. Einige Einträge wurden übergangen:\n\n{list}',
        'es': 'Flujos recargados. Se omitieron algunas entradas:\n\n{list}',
        'fr': 'Workflows rechargés. Certaines entrées ont été ignorées :\n\n{list}',
        'it': 'Flussi ricaricati. Alcune voci sono state ignorate:\n\n{list}',
    },
    'Workflows reloaded: {n}': {
        'de': 'Workflows neu geladen: {n}',
        'es': 'Flujos recargados: {n}',
        'fr': 'Workflows rechargés : {n}',
        'it': 'Flussi ricaricati: {n}',
    },
    'Creator (Q-number):': {
        'de': 'Ersteller (Q-Nummer):',
        'es': 'Creador (número Q):',
        'fr': 'Créateur (numéro Q) :',
        'it': 'Creatore (numero Q):',
    },
    'This file is yours to edit. Cammello reads it at startup;': {
        'de': 'Diese Datei ist zum Bearbeiten da. Cammello liest sie beim Start;',
        'es': 'Este archivo es para que lo edites. Cammello lo lee al arrancar;',
        'fr': 'Ce fichier est à vous. Cammello le lit au démarrage ;',
        'it': 'Questo file è tuo da modificare. Cammello lo legge all’avvio;',
    },
    'File > Reload workflows picks up changes without a restart.': {
        'de': 'Datei > Workflows neu laden übernimmt Änderungen ohne Neustart.',
        'es': 'Archivo > Recargar flujos aplica los cambios sin reiniciar.',
        'fr': 'Fichier > Recharger les workflows applique les changements sans redémarrer.',
        'it': 'File > Ricarica i flussi applica le modifiche senza riavviare.',
    },
    'A new workflow is a new [[workflow]] block - nothing else.': {
        'de': 'Ein neuer Workflow ist ein neuer [[workflow]]-Block, nichts weiter.',
        'es': 'Un flujo nuevo es un bloque [[workflow]] nuevo, nada más.',
        'fr': 'Un nouveau workflow est un nouveau bloc [[workflow]], rien de plus.',
        'it': 'Un nuovo flusso è un nuovo blocco [[workflow]], nulla di più.',
    },
    'Lines starting with # are comments.': {
        'de': 'Zeilen, die mit # beginnen, sind Kommentare.',
        'es': 'Las líneas que empiezan con # son comentarios.',
        'fr': 'Les lignes commençant par # sont des commentaires.',
        'it': 'Le righe che iniziano con # sono commenti.',
    },
    'Per workflow:': {
        'de': 'Je Workflow:',
        'es': 'Por flujo:',
        'fr': 'Par workflow :',
        'it': 'Per flusso:',
    },
    'internal, never shown, do not change it later': {
        'de': 'intern, nie sichtbar, später nicht mehr ändern',
        'es': 'interno, nunca visible, no cambiarlo después',
        'fr': 'interne, jamais affiché, ne le changez pas ensuite',
        'it': 'interno, mai mostrato, non cambiarlo in seguito',
    },
    'what the dropdown shows': {
        'de': 'was im Auswahlfeld steht',
        'es': 'lo que muestra el desplegable',
        'fr': 'ce que la liste déroulante affiche',
        'it': 'ciò che mostra il menu a tendina',
    },
    'fields to HIDE - anything not listed stays visible': {
        'de': 'Felder, die VERSTECKT werden - alles Ungenannte bleibt sichtbar',
        'es': 'campos que se OCULTAN: lo no listado sigue visible',
        'fr': 'champs à MASQUER - tout ce qui n’est pas listé reste visible',
        'it': 'campi da NASCONDERE - ciò che non è elencato resta visibile',
    },
    'Two optional sections per workflow:': {
        'de': 'Zwei freiwillige Abschnitte je Workflow:',
        'es': 'Dos secciones opcionales por flujo:',
        'fr': 'Deux sections facultatives par workflow :',
        'it': 'Due sezioni opzionali per flusso:',
    },
    'fills the field if it is still empty': {
        'de': 'füllt das Feld, solange es leer ist',
        'es': 'rellena el campo si aún está vacío',
        'fr': 'remplit le champ s’il est encore vide',
        'it': 'riempie il campo se è ancora vuoto',
    },
    'grey hint only, never uploaded': {
        'de': 'nur grauer Hinweis, wird nie hochgeladen',
        'es': 'solo una pista gris, nunca se sube',
        'fr': 'simple indication grise, jamais téléversée',
        'it': 'solo un suggerimento grigio, mai caricato',
    },
    'Available field names:': {
        'de': 'Verfügbare Feldnamen:',
        'es': 'Nombres de campo disponibles:',
        'fr': 'Noms de champs disponibles :',
        'it': 'Nomi dei campi disponibili:',
    },
    'hide only': {
        'de': 'nur verstecken',
        'es': 'solo ocultar',
        'fr': 'masquer seulement',
        'it': 'solo nascondere',
    },
    'Anything Cammello cannot make sense of is listed in the log;': {
        'de': 'Alles, womit Cammello nichts anfangen kann, steht im Log;',
        'es': 'Todo lo que Cammello no entiende aparece en el registro;',
        'fr': 'Tout ce que Cammello ne comprend pas figure dans le journal ;',
        'it': 'Tutto ciò che Cammello non capisce è riportato nel log;',
    },
    'a broken file never stops the program - the built-in': {
        'de': 'eine kaputte Datei hält das Programm nie auf - dann gelten',
        'es': 'un archivo roto nunca detiene el programa: entonces valen',
        'fr': 'un fichier cassé n’arrête jamais le programme - alors les',
        'it': 'un file rotto non blocca mai il programma - allora valgono',
    },
    'workflows take over until it parses again.': {
        'de': 'die eingebauten Workflows, bis sie wieder lesbar ist.',
        'es': 'los flujos integrados hasta que vuelva a ser legible.',
        'fr': 'workflows intégrés s’appliquent jusqu’à ce qu’il soit relisible.',
        'it': 'i flussi integrati finché non è di nuovo leggibile.',
    },
    'Uploads': {
        'de': 'Uploads',
        'es': 'Subidas',
        'fr': 'Téléversements',
        'it': 'Caricamenti',
    },
    'Wikimedia Commons': {
        'de': 'Wikimedia Commons',
        'es': 'Wikimedia Commons',
        'fr': 'Wikimedia Commons',
        'it': 'Wikimedia Commons',
    },
    'Upload to Commons': {
        'de': 'Zu Commons hochladen',
        'es': 'Subir a Commons',
        'fr': 'Téléverser vers Commons',
        'it': 'Carica su Commons',
    },
    'Uploads the files selected on the left (or all, when nothing is selected) to Commons, with the descriptions from the MediaWiki module. Files marked for commercial use are skipped.': {
        'de': 'Lädt die links ausgewählten Dateien (oder alle, wenn nichts ausgewählt ist) mit den Beschreibungen aus dem MediaWiki-Modul zu Commons hoch. Für den kommerziellen Kanal markierte Dateien werden übersprungen.',
        'es': 'Sube a Commons los archivos seleccionados a la izquierda (o todos, si no hay ninguno seleccionado) con las descripciones del módulo MediaWiki. Los archivos marcados para uso comercial se omiten.',
        'fr': 'Téléverse vers Commons les fichiers sélectionnés à gauche (ou tous, si aucun n’est sélectionné) avec les descriptions du module MediaWiki. Les fichiers marqués pour un usage commercial sont ignorés.',
        'it': 'Carica su Commons i file selezionati a sinistra (o tutti, se non ne è selezionato nessuno) con le descrizioni del modulo MediaWiki. I file contrassegnati per uso commerciale vengono saltati.',
    },
    'The filter matches no files, so there is nothing to upload.': {
        'de': 'Der Filter trifft auf keine Datei zu, es gibt also nichts hochzuladen.',
        'es': 'El filtro no coincide con ningún archivo, así que no hay nada que subir.',
        'fr': 'Le filtre ne correspond à aucun fichier : il n’y a rien à téléverser.',
        'it': 'Il filtro non corrisponde a nessun file, quindi non c’è nulla da caricare.',
    },
    'Select images with {n} stars or more (click again to switch it off).': {
        'de': 'Bilder mit {n} Sternen oder mehr auswählen (nochmal klicken schaltet ab).',
        'es': 'Seleccionar imágenes con {n} estrellas o más (pulsa de nuevo para desactivarlo).',
        'fr': 'Sélectionner les images à {n} étoiles ou plus (recliquer pour désactiver).',
        'it': 'Seleziona le immagini con {n} stelle o più (clicca di nuovo per disattivare).',
    },
    'Marked for Commons (CC)': {
        'de': 'Für Commons markiert (CC)',
        'es': 'Marcado para Commons (CC)',
        'fr': 'Marqué pour Commons (CC)',
        'it': 'Contrassegnato per Commons (CC)',
    },
    'Marked for commercial use': {
        'de': 'Für kommerzielle Nutzung markiert',
        'es': 'Marcado para uso comercial',
        'fr': 'Marqué pour usage commercial',
        'it': 'Contrassegnato per uso commerciale',
    },
    'No channel mark': {
        'de': 'Ohne Kanalmarkierung',
        'es': 'Sin marca de canal',
        'fr': 'Sans marque de canal',
        'it': 'Senza contrassegno di canale',
    },
    'Switch the filter off': {
        'de': 'Filter abschalten',
        'es': 'Desactivar el filtro',
        'fr': 'Désactiver le filtre',
        'it': 'Disattiva il filtro',
    },
    '{n} colour(s)': {
        'de': '{n} Farbe(n)',
        'es': '{n} color(es)',
        'fr': '{n} couleur(s)',
        'it': '{n} colore/i',
    },
    '{n} channel(s)': {
        'de': '{n} Kanal/Kanäle',
        'es': '{n} canal(es)',
        'fr': '{n} canal/canaux',
        'it': '{n} canale/i',
    },
    'The file could not be read: {path} ({reason})': {
        'de': 'Die Datei konnte nicht gelesen werden: {path} ({reason})',
        'es': 'No se pudo leer el archivo: {path} ({reason})',
        'fr': 'Le fichier n’a pas pu être lu : {path} ({reason})',
        'it': 'Non è stato possibile leggere il file: {path} ({reason})',
    },
    'Unreadable': {
        'de': 'Nicht lesbar',
        'es': 'Ilegible',
        'fr': 'Illisible',
        'it': 'Illeggibile',
    },
    '{n} file(s) could not be read from disk and were not uploaded - see the log for the paths. They stay in the queue and can be resumed.': {
        'de': '{n} Datei(en) konnten nicht von der Platte gelesen werden und wurden nicht hochgeladen — die Pfade stehen im Log. Sie bleiben in der Warteschlange und können später fortgesetzt werden.',
        'es': 'No se pudieron leer {n} archivo(s) del disco y no se subieron; las rutas están en el registro. Permanecen en la cola y se pueden reanudar.',
        'fr': '{n} fichier(s) n’ont pas pu être lus sur le disque et n’ont pas été téléversés — les chemins figurent dans le journal. Ils restent dans la file et peuvent être repris.',
        'it': 'Non è stato possibile leggere {n} file dal disco e non sono stati caricati — i percorsi sono nel log. Restano in coda e possono essere ripresi.',
    },
    '{n} file(s) could not be read from disk last time (offline files, a disconnected drive). Make sure they are available, then resume.': {
        'de': '{n} Datei(en) waren beim letzten Mal nicht von der Platte lesbar (Online-only-Dateien, ein getrenntes Laufwerk). Sorge dafür, dass sie verfügbar sind, und setze dann fort.',
        'es': 'La última vez no se pudieron leer {n} archivo(s) del disco (archivos en línea, una unidad desconectada). Asegúrate de que estén disponibles y luego reanuda.',
        'fr': 'La dernière fois, {n} fichier(s) n’ont pas pu être lus sur le disque (fichiers en ligne uniquement, un lecteur déconnecté). Assurez-vous qu’ils sont disponibles, puis reprenez.',
        'it': 'L’ultima volta non è stato possibile leggere {n} file dal disco (file solo online, un’unità scollegata). Assicurati che siano disponibili, poi riprendi.',
    },
    'The file is on a network or removable drive. Copy it to a local folder and try again.': {
        'de': 'Die Datei liegt auf einem Netz- oder Wechsellaufwerk. Kopiere sie in einen lokalen Ordner und versuche es erneut.',
        'es': 'El archivo está en una unidad de red o extraíble. Cópialo a una carpeta local e inténtalo de nuevo.',
        'fr': 'Le fichier se trouve sur un lecteur réseau ou amovible. Copiez-le dans un dossier local et réessayez.',
        'it': 'Il file si trova su un’unità di rete o rimovibile. Copialo in una cartella locale e riprova.',
    },
    'Store password (in the system keyring)': {
        'de': 'Passwort speichern (im System-Schlüsselbund)',
        'es': 'Guardar la contraseña (en el llavero del sistema)',
        'fr': 'Enregistrer le mot de passe (dans le trousseau du système)',
        'it': 'Salva la password (nel portachiavi di sistema)',
    },
    'Store password': {
        'de': 'Passwort speichern',
        'es': 'Guardar la contraseña',
        'fr': 'Enregistrer le mot de passe',
        'it': 'Salva la password',
    },
    'Kept in the system keyring when one is available; otherwise in the settings as plain text.': {
        'de': 'Liegt im System-Schlüsselbund, wenn einer verfügbar ist; sonst im Klartext in den Einstellungen.',
        'es': 'Se guarda en el llavero del sistema si hay uno disponible; si no, en texto plano en la configuración.',
        'fr': 'Conservé dans le trousseau du système s’il y en a un ; sinon en clair dans les réglages.',
        'it': 'Conservata nel portachiavi di sistema se disponibile; altrimenti in chiaro nelle impostazioni.',
    },
    'Use the classic authorization (OAuth 1.0a)': {
        'de': 'Klassische Autorisierung verwenden (OAuth 1.0a)',
        'es': 'Usar la autorización clásica (OAuth 1.0a)',
        'fr': 'Utiliser l’autorisation classique (OAuth 1.0a)',
        'it': 'Usa l’autorizzazione classica (OAuth 1.0a)',
    },
    'If nothing happens: paste the address bar line here': {
        'de': 'Wenn nichts passiert: die Zeile aus der Adressleiste hier einfügen',
        'es': 'Si no pasa nada: pega aquí la línea de la barra de direcciones',
        'fr': 'Si rien ne se passe : collez ici la ligne de la barre d’adresse',
        'it': 'Se non succede nulla: incolla qui la riga della barra degli indirizzi',
    },
    'No authorization code found in the pasted text.': {
        'de': 'Im eingefügten Text wurde kein Bestätigungscode gefunden.',
        'es': 'No se encontró ningún código de autorización en el texto pegado.',
        'fr': 'Aucun code d’autorisation trouvé dans le texte collé.',
        'it': 'Nessun codice di autorizzazione trovato nel testo incollato.',
    },
    'Network error during the token exchange: {error}': {
        'de': 'Netzwerkfehler beim Token-Tausch: {error}',
        'es': 'Error de red durante el intercambio de tokens: {error}',
        'fr': 'Erreur réseau pendant l’échange de jetons : {error}',
        'it': 'Errore di rete durante lo scambio dei token: {error}',
    },
    'The token exchange failed: {error}': {
        'de': 'Der Token-Tausch ist fehlgeschlagen: {error}',
        'es': 'El intercambio de tokens falló: {error}',
        'fr': 'L’échange de jetons a échoué : {error}',
        'it': 'Lo scambio dei token non è riuscito: {error}',
    },
    'Network error during the sign-in check: {error}': {
        'de': 'Netzwerkfehler bei der Anmeldeprüfung: {error}',
        'es': 'Error de red durante la comprobación de inicio de sesión: {error}',
        'fr': 'Erreur réseau pendant la vérification de connexion : {error}',
        'it': 'Errore di rete durante la verifica dell’accesso: {error}',
    },
    'The sign-in check returned no usable answer.': {
        'de': 'Die Anmeldeprüfung lieferte keine verwertbare Antwort.',
        'es': 'La comprobación de inicio de sesión no devolvió una respuesta utilizable.',
        'fr': 'La vérification de connexion n’a renvoyé aucune réponse exploitable.',
        'it': 'La verifica dell’accesso non ha restituito una risposta utilizzabile.',
    },
    'The server did not recognise the sign-in.': {
        'de': 'Der Server hat die Anmeldung nicht erkannt.',
        'es': 'El servidor no reconoció el inicio de sesión.',
        'fr': 'Le serveur n’a pas reconnu la connexion.',
        'it': 'Il server non ha riconosciuto l’accesso.',
    },
    'Cammello is authorized. You can close this window.': {
        'de': 'Cammello ist autorisiert. Du kannst dieses Fenster schließen.',
        'es': 'Cammello está autorizado. Puedes cerrar esta ventana.',
        'fr': 'Cammello est autorisé. Vous pouvez fermer cette fenêtre.',
        'it': 'Cammello è autorizzato. Puoi chiudere questa finestra.',
    },
    'This authorization answer does not belong to the running Cammello session and was ignored.': {
        'de': 'Diese Autorisierungsantwort gehört nicht zur laufenden Cammello-Sitzung und wurde verworfen.',
        'es': 'Esta respuesta de autorización no pertenece a la sesión de Cammello en curso y se ignoró.',
        'fr': 'Cette réponse d’autorisation n’appartient pas à la session Cammello en cours et a été ignorée.',
        'it': 'Questa risposta di autorizzazione non appartiene alla sessione Cammello in corso ed è stata ignorata.',
    },
    'Waiting for the authorization…': {
        'de': 'Warte auf die Autorisierung…',
        'es': 'Esperando la autorización…',
        'fr': 'En attente de l’autorisation…',
        'it': 'In attesa dell’autorizzazione…',
    },
    'Port {port} is already in use, so the sign-in answer cannot be received. Close the other program or paste the code manually.': {
        'de': 'Port {port} ist bereits belegt, die Anmeldeantwort kann nicht empfangen werden. Schließe das andere Programm oder füge den Code von Hand ein.',
        'es': 'El puerto {port} ya está en uso, así que no se puede recibir la respuesta de inicio de sesión. Cierra el otro programa o pega el código manualmente.',
        'fr': 'Le port {port} est déjà utilisé : la réponse de connexion ne peut pas être reçue. Fermez l’autre programme ou collez le code manuellement.',
        'it': 'La porta {port} è già in uso, quindi la risposta di accesso non può essere ricevuta. Chiudi l’altro programma o incolla il codice manualmente.',
    },
    'The authorization timed out. Start it again when you are ready.': {
        'de': 'Die Autorisierung ist abgelaufen. Starte sie neu, wenn du bereit bist.',
        'es': 'La autorización caducó. Iníciala de nuevo cuando estés listo.',
        'fr': 'L’autorisation a expiré. Relancez-la quand vous êtes prêt.',
        'it': 'L’autorizzazione è scaduta. Avviala di nuovo quando sei pronto.',
    },
}
