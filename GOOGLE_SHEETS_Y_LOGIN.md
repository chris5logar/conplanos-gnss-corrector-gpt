# CONPLANOS GNSS · Google Sheets + historial permanente + inicio de sesión Google

## 1. Qué debes entender primero

Hay **dos conexiones diferentes**:

- **Google Sheets**: permite que CONPLANOS guarde y lea el historial de certificados y otros puntos.
- **Inicio de sesión con Google (OIDC)**: permite que el usuario entre a la aplicación con su cuenta de Google.

Puedes activar una, la otra o las dos. Para mantener el historial entre reinicios/actualizaciones de Streamlit Cloud, la parte importante es **Google Sheets**.

---

# A. CONFIGURAR GOOGLE SHEETS PARA EL HISTORIAL

## Paso 1 — Crear o elegir un proyecto en Google Cloud

1. Entra a Google Cloud Console.
2. Crea un proyecto, por ejemplo:

   `CONPLANOS-GNSS`

3. Entra al proyecto.

## Paso 2 — Habilitar APIs

En **APIs y servicios → Biblioteca**, habilita:

- **Google Sheets API**
- **Google Drive API**

CONPLANOS usa una cuenta de servicio y gspread para leer/escribir las hojas; gspread documenta el uso de ambas APIs para este tipo de conexión. citehttps://docs.gspread.org/_/downloads/en/v5.8.1/pdf/

## Paso 3 — Crear la cuenta de servicio

En Google Cloud:

**IAM y administración → Cuentas de servicio → Crear cuenta de servicio**

Nombre sugerido:

`conplanos-gnss`

Google crea un correo parecido a:

`conplanos-gnss@TU-PROYECTO.iam.gserviceaccount.com`

Guarda ese correo; lo necesitarás para compartir la hoja. Google documenta que las cuentas de servicio tienen un correo propio y pueden usarse para acceder a recursos de Workspace. citehttps://cloud.google.com/iam/docs/service-accounts-create

## Paso 4 — Crear una clave JSON

En la cuenta de servicio:

**Keys / Claves → Add key → Create new key → JSON**

Google descargará un archivo `.json`.

Ese archivo contiene una clave privada. **No lo subas a GitHub.** Google recomienda mantener las claves de cuentas de servicio en un lugar seguro. citehttps://cloud.google.com/iam/docs/keys-create-delete

## Paso 5 — Crear la hoja de Google Sheets

Crea una hoja llamada, por ejemplo:

`CONPLANOS GNSS - HISTORIAL`

No necesitas crear manualmente las pestañas `Puntos` y `OtrosPuntos`: CONPLANOS las crea si no existen.

## Paso 6 — Compartir la hoja con la cuenta de servicio

Dentro de Google Sheets pulsa **Compartir**.

Agrega el correo de la cuenta de servicio:

`conplanos-gnss@TU-PROYECTO.iam.gserviceaccount.com`

Permiso:

**Editor**

Google indica que para acceder a un archivo específico no hace falta delegación de dominio: basta compartir el archivo con el correo de la cuenta de servicio. citehttps://developers.google.com/workspace/guides/create-credentials

## Paso 7 — Copiar el ID de la hoja

Si la URL es:

`https://docs.google.com/spreadsheets/d/1ABCxyz123456789/edit`

el ID es únicamente:

`1ABCxyz123456789`

---

# B. CONFIGURAR STREAMLIT CLOUD

En tu aplicación de Streamlit:

**Manage app → Settings → Secrets**

Pega una configuración basada en `STREAMLIT_SECRETS_EJEMPLO.toml`.

Para Google Sheets necesitas, como mínimo:

```toml
GOOGLE_SHEET_ID = "ID_REAL_DE_TU_HOJA"

[gcp_service_account]
type = "service_account"
project_id = "TU_PROJECT_ID"
private_key_id = "TU_PRIVATE_KEY_ID"
private_key = "-----BEGIN PRIVATE KEY-----\nTU_CLAVE\n-----END PRIVATE KEY-----\n"
client_email = "conplanos-gnss@TU-PROYECTO.iam.gserviceaccount.com"
client_id = "TU_CLIENT_ID"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "URL_DEL_CERTIFICADO"
```

Los nombres deben corresponder a los campos del JSON descargado.

**No pegues el JSON completo como un bloque JSON.** CONPLANOS usa los campos de la cuenta dentro de `[gcp_service_account]`.

Streamlit recomienda mantener los secretos fuera del repositorio y colocarlos en su gestor de Secrets. citehttps://docs.streamlit.io/develop/concepts/connections/secrets-management

Después de guardar:

1. Reinicia la aplicación.
2. Entra a **Certificados → Historial y mapa**.
3. Debe aparecer un mensaje verde indicando que el historial está conectado.
4. Genera un certificado de prueba.
5. Revisa tu Google Sheet: CONPLANOS debe crear/agregar el registro en `Puntos`.

Desde ese momento, el historial no depende de la memoria temporal de la sesión: se vuelve a leer desde Google Sheets cada vez que se abre el visor.

---

# C. QUÉ GUARDA CONPLANOS

## Pestaña `Puntos`

Guarda, entre otros:

- fecha de registro
- código
- solicitante
- Norte
- Este
- zona
- latitud / longitud
- altura elipsoidal
- estación GNSS
- fecha de posicionamiento
- año
- solución Leica
- duración de lectura
- calidad CQ
- receptor y antena
- altura de antena
- nombre del informe
- nombre del PDF generado
- nombre del Word generado

## Pestaña `OtrosPuntos`

Guarda puntos externos que registres desde PDF, DOCX, CSV o Excel para usarlos como referencias en el visor.

---

# D. INICIO DE SESIÓN CON GOOGLE

Esto es independiente de Google Sheets.

En Google Cloud configura **Google Auth Platform** y crea un cliente OAuth de tipo **Web application**.

URI de redirección para tu app:

`https://procesaconplanos.streamlit.app/oauth2callback`

En Streamlit Secrets:

```toml
[auth]
redirect_uri = "https://procesaconplanos.streamlit.app/oauth2callback"
cookie_secret = "SECRETO_LARGO_Y_ALEATORIO"
client_id = "TU_CLIENT_ID"
client_secret = "TU_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Streamlit usa OIDC para este inicio de sesión; `st.login()` redirige al proveedor, en este caso Google, y al volver a la app queda disponible la identidad del usuario. citehttps://docs.streamlit.io/develop/api-reference/user/st.login

También puedes limitar quién entra con:

```toml
AUTHORIZED_GOOGLE_EMAILS = "tu_correo@gmail.com,otro_correo@gmail.com"
```

---

# E. SI TODO ESTÁ BIEN CONFIGURADO

En la aplicación deberías ver:

`☁️ Historial permanente conectado`

Y después de una actualización/reinicio de Streamlit, los puntos deben seguir apareciendo porque la fuente permanente es Google Sheets, no `st.session_state`.

---

# F. ERRORES FRECUENTES

### 1. "Google Sheets aún no está configurado"

Revisa que existan:

- `GOOGLE_SHEET_ID`
- `[gcp_service_account]`
- `client_email`
- `private_key`

### 2. "SpreadsheetNotFound" o acceso denegado

La causa habitual es que la hoja **no fue compartida con el correo de la cuenta de servicio**.

### 3. Error de API

Revisa que estén habilitadas:

- Google Sheets API
- Google Drive API

### 4. Error del login Google

Comprueba que el `redirect_uri` sea exactamente el de la aplicación desplegada.

### 5. Nunca subir secretos a GitHub

No subas:

- `secrets.toml`
- JSON de cuenta de servicio
- claves privadas
- client secrets

El repositorio debe contener únicamente el archivo de ejemplo sin credenciales reales.
