"""Diagnoseskript für Windows Portable Devices (0.18.3).

Zweck: herausfinden, was Windows von der angeschlossenen Kamera sieht, damit
der WPD-Backend für Cammello gegen echte Ausgaben geschrieben werden kann
statt gegen geratene COM-Signaturen.

Das Skript koppelt NICHTS an, kopiert NICHTS und ändert NICHTS. Es listet.

    pip install comtypes
    python wpd_probe.py

Die komplette Ausgabe bitte zurückschicken — auch (und gerade) wenn sie mit
einem Fehler endet. Ein Fehler an einer bekannten Stelle ist eine brauchbare
Antwort; geratener Code ist es nicht.
"""
import sys
import traceback


def line(title):
    print()
    print('=' * 70)
    print(title)
    print('=' * 70)


line('Umgebung')
print('Python  :', sys.version.replace('\n', ' '))
print('Platform:', sys.platform)
try:
    import comtypes
    import comtypes.client as cc
    print('comtypes:', comtypes.__version__)
except Exception:
    print('comtypes fehlt. Bitte "pip install comtypes" und noch einmal.')
    traceback.print_exc()
    sys.exit(1)

line('Typbibliotheken laden')
api = types = None
for dll in ('portabledeviceapi.dll', 'portabledevicetypes.dll'):
    try:
        mod = cc.GetModule(dll)
        print(f'{dll}: OK -> {mod.__name__}')
        if 'api' in dll:
            api = mod
        else:
            types = mod
    except Exception:
        print(f'{dll}: FEHLGESCHLAGEN')
        traceback.print_exc()

if api is None:
    print('\nOhne portabledeviceapi.dll geht nichts weiter.')
    sys.exit(1)

line('Was die Typbibliothek anbietet')
for mod, name in ((api, 'portabledeviceapi'), (types, 'portabledevicetypes')):
    if mod is None:
        continue
    interesting = sorted(n for n in dir(mod)
                         if n.startswith(('IPortableDevice', 'PortableDevice',
                                          'WPD_')))
    print(f'\n{name}: {len(interesting)} passende Namen')
    for n in interesting:
        print('   ', n)

line('Geräte aufzählen')
try:
    manager = cc.CreateObject(api.PortableDeviceManager,
                              interface=api.IPortableDeviceManager)
    print('PortableDeviceManager: erzeugt')
except Exception:
    print('PortableDeviceManager konnte nicht erzeugt werden:')
    traceback.print_exc()
    sys.exit(1)

# Die Aufrufform von GetDevices ist genau die Stelle, die ich nicht raten
# will: comtypes bildet [in,out]-Parameter je nach Typbibliothek
# unterschiedlich ab. Deshalb hier mehrere Formen, und die Ausgabe sagt,
# welche greift.
count = None
for label, call in (
        ('GetDevices(None, 0)', lambda: manager.GetDevices(None, 0)),
        ('GetDevices(None, None)', lambda: manager.GetDevices(None, None)),
        ('GetDevices()', lambda: manager.GetDevices()),
):
    try:
        result = call()
        print(f'{label} -> {result!r}')
        count = result
        break
    except Exception as exc:
        print(f'{label} -> Fehler: {exc.__class__.__name__}: {exc}')

if count is None:
    print('\nKeine der Aufrufformen ging durch. Bitte trotzdem die ganze '
          'Ausgabe schicken.')
    sys.exit(0)

try:
    n = int(count)
except Exception:
    n = 0
print(f'\nAnzahl tragbarer Geräte laut Windows: {n}')
if n == 0:
    print('Windows sieht kein tragbares Gerät. Kamera eingeschaltet? '
          'Kabel an einem Port direkt am Rechner (nicht am Hub)?')
    sys.exit(0)

try:
    ids = (comtypes.c_wchar_p * n)()
    manager.GetDevices(ids, n)
    for dev_id in ids:
        print('\nGeräte-ID:', dev_id)
        for getter in ('GetDeviceFriendlyName', 'GetDeviceManufacturer',
                       'GetDeviceDescription'):
            try:
                length = getattr(manager, getter)(dev_id, None, 0)
                buf = comtypes.create_unicode_buffer(int(length))
                getattr(manager, getter)(dev_id, buf, length)
                print(f'  {getter}: {buf.value}')
            except Exception as exc:
                print(f'  {getter}: Fehler {exc.__class__.__name__}: {exc}')
except Exception:
    print('Das Auslesen der Geräte-IDs ist gescheitert:')
    traceback.print_exc()

line('Fertig')
print('Bitte die gesamte Ausgabe zurückschicken.')
