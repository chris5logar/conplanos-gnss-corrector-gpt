# Actualizar GitHub -> Streamlit V5

1. En tu repositorio actual, reemplaza:
   - app.py
   - core.py
   - requirements.txt
   - README.md
2. Agrega:
   - certificate.py
   - templates/certificado_punto_geodesico_template.docx
   - templates/certificate_background.png
   - templates/logo_ls.png
3. Conserva:
   - .streamlit/config.toml
   - .gitignore
4. Haz Commit changes en `main`.
5. Streamlit Community Cloud detectará el commit y reconstruirá la app.

## Estructura exacta

```
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
    ├── certificate_background.png
    └── logo_ls.png
```

No subas PDFs/CSV de clientes al repositorio.
