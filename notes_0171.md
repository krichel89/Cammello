# Cammello 0.17.1

Eine Behebung, sonst nichts.

## Absturz beim Stilwechsel

Cammello setzte das anwendungsweite Erscheinungsbild bei jedem neuen
Fenster erneut — auch dann, wenn es sich gar nicht geändert hatte. Qt
poliert dabei jedes Widget nach, das es je gesehen hat. Ist eines davon
inzwischen zerstört, greift dieser Durchlauf ins Leere und das Programm
stürzt ab.

Bemerkbar machte sich das zuerst im automatischen Testlauf auf GitHub, der
seit der 0.17.0 mit einem Speicherzugriffsfehler abbrach und deshalb gar
keine fertigen Programme mehr baute. Die Ursache steckt aber schon länger
drin und ist keine Eigenheit des Testlaufs: Denselben Weg geht Cammello,
wenn du das Farbschema umschaltest oder ein weiteres Fenster öffnest.

Jetzt wird das Erscheinungsbild nur noch gesetzt, wenn es sich wirklich
ändert. Ein echter Schemawechsel kommt unverändert durch.
