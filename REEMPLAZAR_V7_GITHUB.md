# CONPLANOS GNSS V7 — actualización

## Archivos a reemplazar/agregar

Reemplaza en la raíz:
- `app.py`
- `core.py` (puedes reemplazarlo por el V6 si no hiciste cambios propios; V7 es compatible)
- `requirements.txt`

Agrega:
- `ephemeris.py`
- `history.py`
- `STREAMLIT_SECRETS_EJEMPLO.toml` (solo como guía; NO contiene credenciales)

Conserva:
- `certificate.py`
- `.streamlit/config.toml`
- `templates/`

No subas `__pycache__` ni archivos `.pyc`.

## Nuevas funciones V7

### Efemérides precisas
En el menú izquierdo aparece `📡 Efemérides precisas`.

El usuario introduce la fecha de lectura y la aplicación busca:
- día anterior;
- día de lectura;
- día siguiente.

Prioridad:
1. ESA Final 5 min (`ESA0OPSFIN...01D_05M_ORB.SP3.gz`)
2. IGS Final combinado 15 min (`IGS0OPSFIN...01D_15M_ORB.SP3.gz`)
3. Otras AC Final 5 min: CODE, GFZ, GRG y JPL.

Los enlaces son directos a los archivos oficiales. CDDIS puede requerir Earthdata.

### Certificados + historial
`📜 Certificados` tiene dos pestañas:
- Generar certificado
- Historial y mapa

Al generar un certificado, se puede registrar automáticamente el expediente técnico en Google Sheets.

### Mapa
El historial convierte latitud/longitud del informe Leica a decimal y permite seleccionar un punto sobre el mapa para ver su ficha.

### Coordenadas resaltadas
El Corrector GNSS resalta visualmente:
- coordenadas de la base de la data nativa;
- coordenadas del punto móvil procesado.

No se resalta la coordenada de la estación de referencia del informe, porque no es el punto que se está certificando.

## Google Sheets

1. Crea una Google Sheet.
2. Crea/usa una cuenta de servicio de Google Cloud.
3. Habilita Google Sheets API y Google Drive API.
4. Comparte la hoja con el `client_email` de la cuenta de servicio como Editor.
5. En Streamlit Cloud abre `Manage app -> Settings -> Secrets`.
6. Copia la estructura de `STREAMLIT_SECRETS_EJEMPLO.toml` y reemplaza los valores por los reales.
7. NO subas `secrets.toml` ni el JSON de la cuenta de servicio a GitHub.

La primera vez que se use el historial, la aplicación crea la pestaña `Puntos` y sus encabezados.

## Importante para una aplicación pública

Una aplicación pública sin autenticación permite que cualquier visitante que genere un certificado escriba un registro en la hoja. Si quieres que solo el personal de CONPLANOS pueda registrar puntos, el siguiente paso debe ser agregar autenticación de usuarios/roles antes de dejar habilitada la escritura pública.
