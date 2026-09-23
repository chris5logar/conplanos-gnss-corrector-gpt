# Actualizar CONPLANOS GNSS sin cambiar nombres

La V9 mantiene los nombres principales de los archivos. Para las próximas versiones, reemplaza los archivos indicados por CONPLANOS y mantén el resto del proyecto.

## Archivos que normalmente se reemplazan

- `app.py`
- `core.py`
- `history.py`
- `certificate.py`
- `ephemeris.py`
- `requirements.txt`
- `.streamlit/config.toml` solo si CONPLANOS indica un cambio
- archivos dentro de `templates/` solo cuando se indique

No cambies los nombres a `app_v9.py`, `core_v9.py`, etc. La aplicación siempre trabaja con `app.py`, `core.py`, etc.

## Pasos

1. Abre el repositorio en GitHub.
2. Entra al archivo que CONPLANOS indique.
3. Reemplaza su contenido subiendo el archivo con el mismo nombre o usando `Upload files` y confirmando el reemplazo.
4. Mantén `requirements.txt` en la raíz.
5. No subas `.streamlit/secrets.toml` ni credenciales reales.
6. Espera que Streamlit Community Cloud reconstruya la aplicación.

## V9

V9 agrega la placa oficial CONPLANOS como plantilla de respaldo del certificado: se conservan el diseño de la imagen y se sustituyen dinámicamente el código del punto y el año. También incluye OpenCV para una limpieza natural de los números originales.
