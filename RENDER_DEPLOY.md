# CONPLANOS GNSS en Render

## Servicio

- Nombre: `conplanos-gnss`.
- Fuente: este repositorio, rama `main`, raíz sin subdirectorio.
- Runtime: Docker, `./Dockerfile`, contexto `.`.
- Instancia: Free; no se requiere cambiar el plan del workspace.
- Región: Virginia, junto a la base de datos existente.
- Build Command: Render construye el Dockerfile; no hay campo de Build Command personalizado en este runtime. La instalación Python es `python -m pip install -r requirements.txt && python -m pip check`.
- Start Command / Docker Command: `python start_render.py`.
- Comando ejecutado: `python -m streamlit run app.py --server.address=0.0.0.0 --server.port=$PORT --server.headless=true`; el script lee `PORT` sin depender de expansión del shell y usa 10000 si no está definido.
- Health Check Path: `/_stcore/health`.
- Deploy manual: al usar la URL pública del repositorio, seleccionar Manual Deploy → Deploy latest commit después de cambios en `main`.

El Dockerfile instala Tesseract con español e inglés, fuentes y zona horaria de Perú. La aplicación se ejecuta como usuario sin privilegios. Los secretos se excluyen del contexto de Docker.

## Integraciones opcionales

Configurar en Render un Secret File con nombre `secrets.toml` solo cuando se disponga de las credenciales reales. Streamlit lo lee desde `/etc/secrets/secrets.toml`; nunca subirlo a GitHub. Usar `STREAMLIT_SECRETS_EJEMPLO.toml` como estructura, sin copiar valores de ejemplo.

Para Google Login, usar como `auth.redirect_uri` la URL pública real de Render seguida de `/oauth2callback` y registrar esa misma URI en el cliente OAuth de Google. Después del futuro cambio de dominio habrá que actualizar ambas ubicaciones.

Sin secretos de Google, las herramientas locales funcionan, pero Login, Sheets, Drive y Maps Embed quedan pendientes. El historial se limita a la sesión. La base de datos `conplanos-db` no se usa en esta versión del código.

## Verificación

Ejecutar `python verify_local.py` desde la raíz con las dependencias instaladas para comprobar las cuatro pantallas, corrección CSV, interpolación TIN, transformación UTM y generación PDF/Word con datos sintéticos.

Comprobar también la URL HTTPS en un navegador, las cuatro herramientas, una carga de archivos de prueba y la descarga de resultados. El endpoint de salud solo verifica que el servidor está listo; no reemplaza las pruebas funcionales.

## Dominio futuro y límites

No cambiar HostGator, Cloudflare ni DNS durante esta etapa. El futuro CNAME de `app.conplanos.com` debe apuntar al hostname exacto asignado por Render, sin `https://` ni rutas. Confirmarlo en Custom Domains antes del cambio futuro. No modificar `conplanos.com`.

La instancia Free se suspende tras inactividad y tiene 512 MB RAM. El primer acceso puede tardar y archivos grandes/OCR concurrente pueden superar sus recursos. No se garantiza disponibilidad continua con esta instancia. No se configura disco persistente ni se cambia de plan.
