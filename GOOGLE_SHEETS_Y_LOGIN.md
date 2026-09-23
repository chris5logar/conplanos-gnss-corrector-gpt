# Configuración de Google Sheets y acceso con Google

## A. Google Sheets para historial

1. En Google Cloud crea/usa un proyecto.
2. Habilita Google Sheets API.
3. Crea una cuenta de servicio y descarga su JSON.
4. Crea una hoja de cálculo en Google Sheets.
5. Comparte esa hoja con el `client_email` de la cuenta de servicio con permiso de Editor.
6. Copia el ID de la hoja desde la URL: `https://docs.google.com/spreadsheets/d/ESTE_ES_EL_ID/edit`.
7. En Streamlit Cloud abre **Settings → Secrets**.
8. Copia la estructura de `STREAMLIT_SECRETS_EJEMPLO.toml` y reemplaza los valores por los del JSON y la hoja.
9. Guarda Secrets y reinicia la app.

CONPLANOS crea/usa dos pestañas: `Puntos` para certificados y `OtrosPuntos` para puntos externos registrados desde documentos.

## B. Inicio de sesión con Google

V8 usa el inicio de sesión OIDC de Streamlit/Google.

1. En Google Cloud configura Google Auth Platform.
2. Crea un cliente OAuth de tipo Web Application.
3. Agrega como URI de redirección autorizada:
   `https://procesaconplanos.streamlit.app/oauth2callback`
4. Copia `client_id` y `client_secret` en `[auth]` de Streamlit Secrets.
5. Genera un `cookie_secret` largo y aleatorio.
6. Guarda Secrets.

Cuando `[auth]` esté configurado, CONPLANOS mostrará primero **INICIAR SESIÓN CON GOOGLE**.

`AUTHORIZED_GOOGLE_EMAILS` es opcional. Si lo defines, separa correos por coma para restringir el acceso.

## Importante

La autenticación de Google y la escritura en Google Sheets son dos configuraciones diferentes:
- OIDC identifica al usuario que entra a la app.
- La cuenta de servicio permite a la app escribir/leer la hoja compartida.

Nunca subas `secrets.toml`, el JSON de la cuenta de servicio ni claves privadas a GitHub.

## C. Google Maps integrado

V8 funciona sin API key para abrir Google Maps mediante Maps URLs. Si quieres el mapa de Google incrustado dentro de la propia página, crea una API key para Maps Embed y agrega en Secrets: `GOOGLE_MAPS_EMBED_API_KEY = "..."`.
