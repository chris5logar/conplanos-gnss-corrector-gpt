# CONPLANOS GNSS V4 – Google Colab

La V4 incorpora el **Generador de data derivada** además del Corrector GNSS.

## Corrector

Sube CSV nativo → informe Leica o coordenadas manuales → revisa las alertas → genera CORREGIDA y POLIGONO.

## Generador

Sube:

1. CSV nativo matriz.
2. CSV o Excel con coordenadas E/N del plano.

Configura:

- tolerancia para considerar una coordenada coincidente;
- número de vecinos para interpolar H.

El sistema conserva las filas coincidentes. Para puntos nuevos mantiene E/N del plano, interpola H por IDW y toma el Código y demás atributos del punto nativo más cercano.

El resultado se identifica como **data derivada**.
