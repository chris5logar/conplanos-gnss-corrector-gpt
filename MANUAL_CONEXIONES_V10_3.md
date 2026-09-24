# CONPLANOS GNSS V10.3 — MANUAL DE CONEXIONES

## Objetivo

Esta versión deja preparada la aplicación para cuatro integraciones:

1. **Google Sheets** — historial permanente de puntos.
2. **Google Drive** — almacenamiento de PDF y Word generados.
3. **Login con Google** — acceso mediante cuenta Google.
4. **Google Maps Embed** — mapa de Google incrustado dentro de la aplicación (opcional).

El mapa PyDeck/CARTO y los botones que abren Google Maps funcionan sin necesidad de activar Google Maps Embed.

---

# ORDEN RECOMENDADO

Haz las conexiones exactamente en este orden:

**PASO 0 → GitHub/Streamlit → Google Cloud → Sheets → Drive → Login → Maps → prueba final**

No pegues ninguna clave privada en GitHub.

---

# PASO 0 — SUBIR V10.3

1. Descarga el ZIP de esta versión.
2. Descomprime el ZIP.
3. Reemplaza en tu repositorio los archivos existentes por los de V10.3.
4. Si aparece `drive.py`, súbelo también.
5. Conserva la carpeta `templates/` completa.
6. No subas un archivo real llamado `.streamlit/secrets.toml`.
7. Espera a que Streamlit Community Cloud termine el despliegue.

La aplicación debe abrir antes de configurar Google. En la parte superior aparecerán indicadores de las conexiones.

---

# PASO 1 — CREAR UN PROYECTO GOOGLE CLOUD

Entra a Google Cloud Console:

https://console.cloud.google.com/

Crea un proyecto llamado:

`CONPLANOS-GNSS`

Usa un solo proyecto para todas las integraciones de esta aplicación.

---

# PASO 2 — ACTIVAR GOOGLE SHEETS API Y GOOGLE DRIVE API

Dentro del proyecto:

**APIs y servicios → Biblioteca**

Activa:

- Google Sheets API
- Google Drive API

Estas dos son las conexiones principales para el historial y los archivos.

---

# PASO 3 — CREAR CUENTA DE SERVICIO

Ruta aproximada:

**IAM y administración → Cuentas de servicio → Crear cuenta de servicio**

Nombre sugerido:

`conplanos-gnss`

Google generará un correo parecido a:

`conplanos-gnss@TU-PROYECTO.iam.gserviceaccount.com`

Guarda ese correo.

---

# PASO 4 — CREAR CLAVE JSON DE LA CUENTA DE SERVICIO

En la cuenta de servicio:

**Claves → Agregar clave → Crear clave nueva → JSON**

Descarga el JSON.

**NO lo subas a GitHub y NO lo compartas por WhatsApp.**

Lo utilizaremos para llenar los campos `[gcp_service_account]` de Streamlit Secrets.

---

# PASO 5 — CREAR GOOGLE SHEET

Crea una hoja:

`CONPLANOS GNSS - HISTORIAL`

Copia su URL.

Si la URL es:

`https://docs.google.com/spreadsheets/d/1ABC123XYZ/edit`

el ID es:

`1ABC123XYZ`

No necesitas crear manualmente las pestañas `Puntos` y `OtrosPuntos`; la aplicación puede crearlas.

---

# PASO 6 — COMPARTIR EL SHEET CON LA CUENTA DE SERVICIO

En Google Sheets:

**Compartir → agrega el correo de la cuenta de servicio → Editor**

Ejemplo:

`conplanos-gnss@TU-PROYECTO.iam.gserviceaccount.com`

Este paso es obligatorio.

---

# PASO 7 — PREPARAR STREAMLIT SECRETS PARA SHEETS + DRIVE

En Streamlit Community Cloud:

**Tu app → Manage app → Settings → Secrets**

Pega una configuración basada en `STREAMLIT_SECRETS_EJEMPLO.toml`.

Completa:

- `GOOGLE_SHEET_ID`
- todos los campos de `[gcp_service_account]`

Puedes dejar fuera por ahora:

- `GOOGLE_DRIVE_FOLDER_ID`
- `GOOGLE_MAPS_EMBED_API_KEY`
- `[auth]`

Guarda.

---

# PASO 8 — PROBAR GOOGLE SHEETS

Abre CONPLANOS:

**Certificados → Historial y mapa**

Debes ver:

`Google Sheets · conectado`

Luego genera un certificado de prueba.

Revisa el Sheet.

La aplicación debe crear/usar:

- `Puntos`
- `OtrosPuntos`

Si aparece `SpreadsheetNotFound`, casi siempre debes revisar que el Sheet fue compartido con el correo exacto de la cuenta de servicio.

---

# PASO 9 — PROBAR GOOGLE DRIVE

No necesitas crear una carpeta obligatoriamente.

V10.3 puede crear/reutilizar:

`CONPLANOS GNSS - CERTIFICADOS`

en el Drive de la cuenta de servicio.

Cuando generes un certificado, V10.3 intentará guardar:

- PDF
- Word

y mostrará botones para abrirlos desde Drive.

Además, el historial guarda los enlaces en:

- `drive_pdf`
- `drive_word`
- `drive_carpeta`

### Si quieres una carpeta específica

1. Crea la carpeta en Drive.
2. Compártela con la cuenta de servicio como Editor si es necesario para tu configuración.
3. Copia el ID de la carpeta.
4. En Secrets agrega:

`GOOGLE_DRIVE_FOLDER_ID = "ID_DE_LA_CARPETA"`

---

# PASO 10 — CONFIGURAR LOGIN CON GOOGLE

En Google Cloud entra a **Google Auth Platform**.

Configura la aplicación y crea un cliente OAuth de tipo:

**Web application**

Usa como URI de redirección exactamente:

`https://procesaconplanos.streamlit.app/oauth2callback`

Si tu URL de Streamlit cambia, usa la URL real de tu aplicación.

Obtendrás:

- Client ID
- Client Secret

---

# PASO 11 — AGREGAR LOGIN A STREAMLIT SECRETS

En:

**Streamlit → Manage app → Settings → Secrets**

agrega:

```toml
[auth]
redirect_uri = "https://procesaconplanos.streamlit.app/oauth2callback"
cookie_secret = "UNA_CLAVE_LARGA_Y_ALEATORIA"
client_id = "TU_CLIENT_ID"
client_secret = "TU_CLIENT_SECRET"
server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
```

Guarda y reinicia la aplicación.

La aplicación debería mostrar:

**INICIAR SESIÓN CON GOOGLE**

---

# PASO 12 — RESTRINGIR QUIÉN PUEDE ENTRAR

Si solamente tú debes usar CONPLANOS, agrega:

```toml
AUTHORIZED_GOOGLE_EMAILS = "tu-correo@gmail.com"
```

Para varios usuarios:

```toml
AUTHORIZED_GOOGLE_EMAILS = "correo1@gmail.com,correo2@gmail.com"
```

Si esta variable no existe, el login funciona sin esa lista de restricción.

---

# PASO 13 — GOOGLE MAPS EMBED (OPCIONAL)

No necesitas esto para el mapa actual.

Actívalo solamente si quieres que Google Maps aparezca incrustado dentro de CONPLANOS.

En Google Cloud:

1. APIs y servicios → Biblioteca.
2. Habilita **Maps Embed API**.
3. Crea una API Key.
4. Restringe la clave para producción.
5. Coloca la clave en Streamlit Secrets:

```toml
GOOGLE_MAPS_EMBED_API_KEY = "AIza..."
```

Al tenerla, V10.3 mostrará el mapa Google incrustado cuando se localice un punto.

---

# PASO 14 — PLACES / GEOCODING (NO ACTIVAR TODAVÍA)

La búsqueda actual de lugares abre Google Maps mediante URL.

No necesitas Places API ni Geocoding API para esa función.

Si posteriormente quieres escribir dentro de CONPLANOS:

`Municipalidad de Pisac`

y que la aplicación obtenga automáticamente las coordenadas del lugar, entonces agregaremos una conexión específica de Places/Geocoding.

No actives APIs adicionales sin necesidad.

---

# PASO 15 — PRUEBA FINAL

Haz estas pruebas en orden:

### Prueba A — Login

- cerrar sesión
- iniciar sesión con Google
- verificar correo/nombre

### Prueba B — Sheets

- generar certificado
- revisar pestaña `Puntos`
- comprobar coordenadas
- comprobar código
- comprobar solicitante

### Prueba C — Drive

- abrir PDF desde Drive
- abrir Word desde Drive
- comprobar que los enlaces aparecen en el Sheet

### Prueba D — Mapa

- abrir Historial y mapa
- seleccionar punto
- ubicar por Este/Norte/Zona
- encontrar punto más cercano
- abrir Google Maps

### Prueba E — Persistencia

- reiniciar/redeployar Streamlit
- volver a abrir historial
- comprobar que los puntos siguen allí

---

# QUÉ HACES TÚ Y QUÉ HAGO YO

## Tú

- Crear proyecto Google Cloud.
- Activar APIs.
- Crear cuenta de servicio.
- Crear clave JSON.
- Crear Google Sheet.
- Compartir el Sheet con la cuenta de servicio.
- Crear OAuth para Login.
- Crear API Key de Maps Embed si decides usarla.
- Pegar Secrets en Streamlit.
- Subir V10.3 a GitHub.

## Yo

- Programación de Google Sheets.
- Programación de Google Drive.
- Programación del Login.
- Control de usuarios autorizados.
- Programación del mapa.
- Integración de enlaces de Drive en el historial.
- Manejo de errores de conexión.
- Diseño de la interfaz.
- Corrección de errores que aparezcan durante la configuración.
- Nuevas automatizaciones posteriores.

---

# SEGURIDAD

Nunca subas a GitHub:

- `secrets.toml`
- JSON de cuenta de servicio
- claves privadas
- Client Secret
- API Keys sin restricciones cuando no sea necesario

Streamlit recomienda mantener los secretos fuera del repositorio y utilizar su sistema de Secrets para Community Cloud.

---

# FUENTES OFICIALES

Streamlit Secrets:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management

Streamlit Login Google:
https://docs.streamlit.io/develop/tutorials/authentication/google

Streamlit st.login:
https://docs.streamlit.io/develop/api-reference/user/st.login

Google Maps Embed API:
https://developers.google.com/maps/documentation/embed/quickstart

Google Cloud Console:
https://console.cloud.google.com/
