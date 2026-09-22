# COMO ACTUALIZAR TU REPOSITORIO ACTUAL A V5

Tu repositorio actual ya existe. NO necesitas crear otro.

## 1. Archivos que debes reemplazar

En GitHub reemplaza estos archivos en la raíz:

- `app.py`
- `core.py`
- `requirements.txt`
- `README.md`

Y agrega este archivo nuevo:

- `certificate.py`

## 2. Carpeta nueva `templates`

Crea en GitHub:

```text
templates/
```

y sube dentro:

```text
templates/
├── certificado_punto_geodesico_template.docx
├── certificate_template.pdf
├── certificate_background.png
├── logo_ls.png
└── plaque_generada_template.png
```

## 3. NO cambies

Puedes dejar como están:

```text
.streamlit/config.toml
.gitignore
```

## 4. Estructura final

```text
conplanos-gnss-corrector-gpt/
├── app.py
├── core.py
├── certificate.py
├── requirements.txt
├── README.md
├── .gitignore
├── .streamlit/
│   └── config.toml
└── templates/
    ├── certificado_punto_geodesico_template.docx
    ├── certificate_template.pdf
    ├── certificate_background.png
    ├── logo_ls.png
    └── plaque_generada_template.png
```

## 5. Orden recomendado en GitHub

1. Reemplaza `app.py`.
2. Reemplaza `core.py`.
3. Reemplaza `requirements.txt`.
4. Reemplaza `README.md`.
5. Sube `certificate.py`.
6. Crea la carpeta `templates` y sube los 5 archivos.
7. Haz `Commit changes` directamente en `main`.

Streamlit Community Cloud detectará el commit y reconstruirá la aplicación.

## 6. Qué cambia en V5

### Corrector GNSS
- La diferencia entre antena de referencia y móvil ya NO se marca como error.
- Se muestran ambas por separado porque pueden ser equipos distintos.
- Se mantiene el control de base, Fijo, altura, calidad y corrección.

### Certificado
Nuevo menú:
`📜 Certificado de punto geodésico`

Puede:
- leer datos del informe Leica;
- permitir edición manual de todos los campos;
- usar fecha de emisión actual por defecto;
- permitir cambiar fecha de emisión;
- aceptar foto real de la placa;
- generar una placa gráfica si no hay foto;
- entregar PDF y Word.

El PDF y Word se basan directamente en el formato de certificado proporcionado.

## 7. No subas datos de clientes

No subas al repositorio:
- CSV de clientes;
- informes GNSS de clientes;
- fotos de puntos de clientes;
- contraseñas;
- tokens;
- credenciales NTRIP.
