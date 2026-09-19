# CONPLANOS – Corrector GNSS Leica Infinity V2

Aplicación Streamlit para automatizar la corrección de coordenadas de levantamientos exportados desde Leica Infinity.

## Qué hace

### Modo 1 – Informe Leica
Subes:
1. El CSV nativo exportado de Leica Infinity.
2. El Resumen de Procesamiento GNSS o el Informe detallado (puedes subir ambos).

La aplicación:
- identifica la base en la fila 2 (primera fila de datos);
- extrae del informe las coordenadas X/Y del punto móvil;
- extrae altura elipsoidal WGS84 y altura ortométrica;
- compara ambas con la altura del CSV;
- selecciona automáticamente la altura más coherente, dejando visible la comparación;
- marca una alerta si la diferencia supera 40 m;
- muestra solución Fijo, duración, fecha/hora, receptor, antena, altura y distancia geométrica a la referencia;
- muestra CQ 1D/2D/3D y M0 tal como aparecen en el informe;
- verifica la columna Base del CSV;
- revisa si los puntos tienen solución Fijo;
- muestra una alerta cuando la antena del CSV y la antena del informe no coinciden.

### Modo 2 – Manual
No necesitas PDF. Introduces E/N/H procesadas de la base directamente.

### Salidas

1. `... CORREGIDA.csv`
   - conserva todas las columnas originales;
   - corrige E/N/H;
   - la base queda exactamente con las coordenadas procesadas;
   - puntos posteriores: `Número de Observación = 65`;
   - Base vacía en puntos posteriores se completa con el nombre de la base principal;
   - no se modifican los demás campos.

2. `... POLIGONO.csv`
   - solamente: `Nombre,e,n,h,Código`.

## Importante sobre la altura

La aplicación no asume que `h` es siempre ortométrica o elipsoidal.

Cuando recibe un informe Leica, compara:

- H del punto base en el CSV;
- H ortométrica del informe;
- H elipsoidal WGS84 del informe.

El modo automático elige la opción con menor diferencia absoluta, pero la interfaz muestra ambas diferencias y alerta cuando el desvío supera 40 m.

Esto es una comprobación de consistencia de datos, no un sustituto del criterio geodésico del profesional.

## Importante sobre la referencia ERP IGN

El informe solo identifica la referencia que aparece en la línea base (por ejemplo `CS01`).

La interfaz tiene una casilla para que el usuario confirme que esa referencia corresponde al ERP/base IGN antes de mostrarla como “Distancia al ERP IGN”. Esto evita asumir una equivalencia que el PDF no demuestre por sí solo.

## Ejecutar localmente

```bash
py -m pip install -r requirements.txt
streamlit run app.py
```

Abrirá la aplicación en el navegador.

## Google Colab

Usa el notebook:
`CONPLANOS_GNSS_CORRECTOR_V2_COLAB.ipynb`

Ejecuta sus celdas en orden.

## Publicar gratis en Streamlit Community Cloud

1. Crea una cuenta de GitHub.
2. Crea un repositorio público, por ejemplo:
   `conplanos-gnss-corrector`
3. Sube:
   - `app.py`
   - `core.py`
   - `requirements.txt`
   - `.streamlit/config.toml`
   - `.gitignore`
4. Entra a `https://share.streamlit.io/`
5. Conecta GitHub.
6. Pulsa **Create app**.
7. Selecciona:
   - Repository: tu repositorio
   - Branch: `main`
   - Main file path: `app.py`
8. Elige un subdominio, por ejemplo:
   `conplanos-gnss-corrector`
9. Deploy.

Streamlit Community Cloud es un servicio gratuito y las aplicaciones desplegadas tienen una URL `streamlit.app`.

## Privacidad

En una aplicación pública, los archivos que los usuarios carguen se procesan en la infraestructura del servicio. No incluyas contraseñas, tokens, credenciales NTRIP ni otros secretos en el código o repositorio.

Para trabajos con información sensible de clientes, considera:
- repositorio privado;
- aplicación privada;
- o una instalación local.

## Actualizaciones

El repositorio de GitHub es la fuente de la aplicación. Al subir cambios al repositorio, Community Cloud actualiza la aplicación.

## Pruebas

El archivo `tests/test_sample.py` valida el formato con el informe y CSV de prueba proporcionados durante el desarrollo.
