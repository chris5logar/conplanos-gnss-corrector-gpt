# CONPLANOS – Herramientas GNSS V4

Aplicación Streamlit para dos flujos:

1. **Corrector GNSS**: toma un CSV nativo de campo y lo corrige usando un informe de procesamiento Leica o coordenadas introducidas manualmente.
2. **Generador de data derivada**: toma un CSV nativo matriz y un archivo CSV/Excel con coordenadas E/N de plano, conserva los puntos coincidentes y genera puntos nuevos con altura interpolada y atributos de referencia del punto nativo más cercano.

## Qué hace el Corrector GNSS

- identifica la base de la primera fila de datos;
- verifica bases diferentes o faltantes;
- identifica puntos Fijo/no Fijo;
- resume antena y altura de antena y sus repeticiones;
- lee el informe Leica y extrae referencia, punto procesado, solución, duración, distancia, antena, altura, fecha y CQ;
- compara H ortométrica y H elipsoidal con la H del CSV;
- genera `CORREGIDA.csv` y `POLIGONO.csv`.

## Qué hace el Generador de data derivada

- acepta CSV o Excel de coordenadas E/N;
- permite definir tolerancia de coincidencia;
- si el punto del plano coincide con uno nativo, conserva la fila nativa;
- si es nuevo, conserva E/N del plano;
- interpola H con IDW usando los vecinos nativos más cercanos;
- toma el Código del punto nativo más cercano;
- toma Base, antena, PDO(PDOP), solución y demás campos como referencia del punto nativo más cercano;
- usa `Número de Observación = 65` para puntos nuevos;
- muestra un resumen de cuántos puntos coincidieron y cuántos fueron generados.

> El Generador produce **data derivada/interpolada**. No debe confundirse con mediciones originales de campo ni utilizarse para alterar o reemplazar evidencia de observación sin una justificación técnica documentada.

## Versiones

- **V1**: corrección automática desde CSV + coordenadas.
- **V2**: lectura de informe Leica, selección de altura y controles.
- **V3**: interfaz compacta con resúmenes laterales.
- **V4**: guía integrada + pestaña Generador de data derivada.

## Archivos para GitHub

```text
app.py
core.py
requirements.txt
README.md
.gitignore
.streamlit/config.toml
```

## Ejecutar localmente

```bash
py -m pip install -r requirements.txt
streamlit run app.py
```

## Streamlit Community Cloud

Repositorio GitHub → branch `main` → archivo principal `app.py`.

No subir PDFs/CSV de clientes, credenciales NTRIP, contraseñas ni proyectos Leica al repositorio.
