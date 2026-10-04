"""Local smoke checks using synthetic coordinates, never client documents."""
from pathlib import Path
import csv
import io
import tempfile
import zipfile

import fitz
from pyproj import Transformer
from streamlit.testing.v1 import AppTest
from certificate import CertificateData, make_plaque, generate_certificate_pdf, generate_certificate_docx
from core import read_csv, apply_correction, generate_derived_data, CoordinatePoint


def main():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception, [e.message for e in app.exception]
    for name in ["Corrector GNSS", "Generador de data", "Certificados", "Efemérides precisas"]:
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception, [e.message for e in app.exception]
        print("PASS screen:", name)
    fields = ["Nombre", "e", "n", "h", "Código", "Base", "Tipo de Antena", "Altura de Antena", "Número de Observación", "Solución", "Método de encuesta"]
    rows = []
    for name, e, n, h in [("BASE", 500000, 8500000, 3000), ("A", 500010, 8500000, 3010), ("B", 500000, 8500010, 3020), ("C", 500010, 8500010, 3030)]:
        rows.append(dict(zip(fields, [name, e, n, h, "PG", "BASE", "ANT", 2, 60, "Fijo", "Topográfico"])))
    text = io.StringIO()
    writer = csv.DictWriter(text, fields)
    writer.writeheader(); writer.writerows(rows)
    info = read_csv(text.getvalue().encode("utf-8-sig"))
    corrected, polygon, result = apply_correction(info, 500001, 8500002, 3003)
    reread = read_csv(corrected)
    assert float(reread.rows[1]["e"]) == 500011
    assert float(reread.rows[1]["n"]) == 8500002
    assert reread.rows[1]["Número de Observación"] == "60"
    assert polygon and result["delta_h"] == 3
    generated, summary = generate_derived_data(info, [CoordinatePoint(name="NEW", e=500005, n=8500005)])
    derived = read_csv(generated)
    assert abs(float(derived.rows[-1]["h"]) - 3015) < 0.0001
    print("PASS CSV correction and TIN interpolation")
    lon, lat = Transformer.from_crs(32718, 4326, always_xy=True).transform(500000, 8500000)
    assert -90 < lat < 0 and -180 < lon < 0
    print("PASS UTM transformation")
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        data = CertificateData(codigo="TEST-001", solicitante="Prueba técnica", norte="8500000.0000", este="500000.0000", zona="18 Sur", anio="2026", fecha_emision="04/10/2026")
        plaque = make_plaque(data.codigo, directory / "plaque.png", year=data.anio)
        pdf = generate_certificate_pdf(data, plaque, "templates/certificate_template.pdf", directory / "certificate.pdf")
        with fitz.open(pdf) as document:
            assert len(document) == 1
            assert data.codigo in document[0].get_text()
        docx = generate_certificate_docx(data, plaque, "templates/certificado_punto_geodesico_template.docx", directory / "certificate.docx")
        with zipfile.ZipFile(docx) as document:
            assert document.testzip() is None
            assert data.codigo in document.read("word/document.xml").decode()
        print("PASS PDF and Word certificates")


if __name__ == "__main__":
    main()
