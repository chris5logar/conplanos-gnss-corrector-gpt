# Google Colab - CONPLANOS V5

Para probar V5 en Colab:

```python
!pip -q install streamlit>=1.40,<2 PyMuPDF>=1.24,<2 openpyxl>=3.1,<4 python-docx>=1.1,<2 reportlab>=4.0,<5 Pillow>=10,<12
```

Después copia o sube al entorno los archivos del paquete:
- app.py
- core.py
- certificate.py
- templates/
- requirements.txt

Y ejecuta:

```python
!streamlit run /content/app.py --server.headless true --server.port 8501 > /content/streamlit.log 2>&1 &
!npx --yes localtunnel --port 8501
```

Abre la URL temporal `https://xxxxx.loca.lt` que aparezca.

En V5 el certificado PDF se genera directamente con ReportLab para no depender de LibreOffice en Streamlit Cloud.
