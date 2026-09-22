# CONPLANOS - Herramientas GNSS V5

## Herramientas
1. Corrector GNSS
2. Generador de data
3. Certificado de punto geodésico

## Cambio importante V5
La comparación de antenas entre CSV y PDF ya **no se marca como error** automáticamente.
La aplicación muestra por separado la antena de referencia y la antena móvil, porque que sean distintas puede ser completamente normal.

## Certificado de punto geodésico
La herramienta acepta:
- Informe Leica para extraer automáticamente Norte, Este, Zona, Latitud, Longitud, Altura Elipsoidal, estación GNSS y fecha de posicionamiento.
- O ingreso manual de todos los campos.

Genera:
- PDF de una página con el diseño base del certificado proporcionado.
- Word editable basado en la plantilla proporcionada.

La fecha de emisión se completa con la fecha actual y puede editarse antes de generar.

Si no se proporciona una foto de la placa, se genera una **ilustración** de placa con el código. Debe entenderse como un gráfico generado, no como una fotografía de una placa real.

El certificado mantiene la leyenda del formato proporcionado indicando que no constituye certificación oficial del IGN.

## Publicación en Streamlit
Subir al repositorio:
- app.py
- core.py
- certificate.py
- requirements.txt
- README.md
- .gitignore
- .streamlit/config.toml
- templates/certificado_punto_geodesico_template.docx
- templates/certificate_background.png
- templates/logo_ls.png

Main file: app.py

## Nota de privacidad
No subir PDFs/CSV de clientes ni credenciales al repositorio.
