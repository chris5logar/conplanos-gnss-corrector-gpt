## V9.1 — corrección de arranque

Se corrigió un error de importación en `core.py` que impedía iniciar la app en Streamlit Cloud. Reemplaza `app.py` y `core.py` por los de esta versión.

# CONPLANOS GNSS

Aplicación Streamlit para apoyo al procesamiento y gestión de datos GNSS de CONPLANOS.

## Módulos V9

- **Corrector GNSS**: uno o varios CSV nativos, informes Leica, corrección de E/N/H, data nativa actualizada, data corregida, polígono, unión con una sola base y secuencia continua.
- **Generador de data**: uno o varios CSV nativos; lectura de coordenadas desde CSV, Excel, PDF, DOCX e imágenes mediante OCR; tolerancia de coincidencia desde 0; altura mediante TIN lineal con IDW de respaldo; base única y secuencia continua.
- **Certificados**: certificado desde el PUNTO MÓVIL Leica, descargas persistentes PDF/Word, historial y visor WGS84, Google Maps y registro de puntos externos. Si no se adjunta foto, usa la placa oficial de referencia CONPLANOS y reemplaza automáticamente el código y el año.
- **Efemérides precisas**: productos finales para día anterior, día de lectura y día siguiente.

## Estructura fija

La aplicación mantiene nombres estables para facilitar reemplazos en GitHub:

```text
app.py
core.py
history.py
certificate.py
ephemeris.py
requirements.txt
.streamlit/config.toml
templates/
```

Las siguientes versiones deben reemplazar los mismos nombres, no crear `app_v9.py`, `core_v9.py`, etc.

## Seguridad

No publiques `secrets.toml`, claves privadas de Google ni el JSON real de la cuenta de servicio. Usa Streamlit Secrets.

Consulta:
- `ACTUALIZAR_GITHUB.md`
- `GOOGLE_SHEETS_Y_LOGIN.md`
- `STREAMLIT_SECRETS_EJEMPLO.toml`


### V10.1
- Efemérides finales en tarjetas compactas de 3 días, con todos los productos disponibles en filas cortas y botón de descarga a la derecha.
- Fecha y búsqueda en una sola línea para reducir espacio vertical.
- Se eliminó el alto fijo que provocaba grandes espacios en blanco.
