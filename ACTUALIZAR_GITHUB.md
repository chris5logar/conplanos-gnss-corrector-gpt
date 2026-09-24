# Actualizar CONPLANOS GNSS a V10.3

Reemplaza los archivos del repositorio por los de este ZIP manteniendo exactamente los mismos nombres.

Cambios V10.3:
- Efemérides con verificación real del contenido del archivo (no basta HTTP 200).
- Prioridad por cada fecha: Final → Rapid → Ultra-Rapid.
- No se generan enlaces Final/Rapid para fechas futuras solo por patrón de nombre.
- Ultra-Rapid solo aparece si el archivo real está disponible y cubre la fecha; se identifica si la cobertura es observada, mixta o predicha.
- Si no existe un producto verificable, se muestra un mensaje explícito.
- La fecha por defecto usa la fecha local de Perú (America/Lima).
- Modo claro/oscuro mediante el selector de tema de Streamlit (⋮ → Settings → Theme).
- CSS adaptado a variables de tema para que las tarjetas y paneles también cambien de apariencia.

Después del reemplazo, espera el redeploy de Streamlit Cloud.
