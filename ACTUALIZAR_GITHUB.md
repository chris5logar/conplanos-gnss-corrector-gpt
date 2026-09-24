# ACTUALIZAR CONPLANOS GNSS

## V10

Reemplaza en GitHub los archivos con los mismos nombres del proyecto:

- `app.py`
- `core.py`
- `history.py`
- `certificate.py`
- `ephemeris.py`
- `requirements.txt`
- `packages.txt`
- `templates/plaque_generada_template.png` y demás plantillas si se incluyen

No crees archivos `app_v10.py`, `core_v10.py`, etc. La estrategia es siempre mantener los mismos nombres para que GitHub los reemplace.

### Nueva interfaz V10

- Efemérides en vista compacta de tres días.
- ESA e IGS principales visibles; otras soluciones dentro de un expander.
- Descarga directa a la derecha de cada producto.
- Visor de certificados con búsqueda por UTM WGS84.
- Conversión automática UTM → WGS84.
- Zoom automático al punto más cercano.
- Puntos certificados y externos con simbología diferente.
- Punto más cercano resaltado.
- Corrección del `StreamlitWidgetAlreadyInstantiatedError` del visor.
- Historial persistente mediante Google Sheets.

### Historial permanente

Configura Google Sheets siguiendo `GOOGLE_SHEETS_Y_LOGIN.md`.


### V10.1
- Efemérides finales en tarjetas compactas de 3 días, con todos los productos disponibles en filas cortas y botón de descarga a la derecha.
- Fecha y búsqueda en una sola línea para reducir espacio vertical.
- Se eliminó el alto fijo que provocaba grandes espacios en blanco.
