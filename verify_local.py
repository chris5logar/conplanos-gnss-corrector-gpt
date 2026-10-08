"""Comprehensive local test suite for CONPLANOS GNSS V10.6."""
from pathlib import Path
import csv
import io
import tempfile
import zipfile

import fitz  # PyMuPDF
from pyproj import Transformer
from streamlit.testing.v1 import AppTest
from certificate import CertificateData, make_plaque, generate_certificate_pdf, generate_certificate_docx
from core import (
    read_csv,
    apply_correction,
    native_updated,
    generate_derived_data,
    merge_csv_payloads,
    CoordinatePoint,
)


def test_column_order_and_preservation():
    """Test 1: Column reordering, preservation of unknown columns and exact header schema."""
    custom_fields = ["Elevación", "Lote", "Norte", "Este", "Propietario", "Nombre de punto", "Notas"]
    rows = [
        {"Elevación": "3000.000", "Lote": "L1", "Norte": "8500000.000", "Este": "500000.000", "Propietario": "Juan", "Nombre de punto": "BASE_PROY", "Notas": "Base de control"},
        {"Elevación": "3010.500", "Lote": "L2", "Norte": "8500020.000", "Este": "500010.000", "Propietario": "Pedro", "Nombre de punto": "PTO_01", "Notas": "Esquina A"},
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=custom_fields)
    w.writeheader()
    w.writerows(rows)
    raw = out.getvalue().encode("utf-8-sig")

    info = read_csv(raw)
    assert info.fieldnames == custom_fields, f"Expected exact custom fieldnames, got {info.fieldnames}"
    assert info.base_original_e == 500000.0
    assert info.base_original_n == 8500000.0
    assert info.base_original_h == 3000.0

    # Test correction
    corrected_b, poly_b, calc = apply_correction(info, 500002.0, 8500005.0, 3004.0)
    corr_info = read_csv(corrected_b)
    assert corr_info.fieldnames == custom_fields, "Corrected output must preserve original reordered fieldnames"
    assert corr_info.rows[0]["Propietario"] == "Juan"
    assert corr_info.rows[0]["Lote"] == "L1"
    assert corr_info.rows[1]["Notas"] == "Esquina A"
    assert float(corr_info.rows[1]["Este"]) == 500012.0
    assert float(corr_info.rows[1]["Norte"]) == 8500025.0
    assert float(corr_info.rows[1]["Elevación"]) == 3014.5
    assert corr_info.rows[1][corr_info.columns["name"]] == "1"

    print("PASS 1: Column reordering & unknown fields preservation")


def test_synonyms_and_varied_equipment():
    """Test 2: Synonyms from CHC, Trimble, Leica, South, Emlid, etc."""
    english_fields = ["Point ID", "Easting", "Northing", "Elevation", "Feature Code", "Survey Method", "Epochs", "PDOP"]
    rows = [
        {"Point ID": "REF_BASE", "Easting": "200000.00", "Northing": "8000000.00", "Elevation": "1500.00", "Feature Code": "PG", "Survey Method": "Static", "Epochs": "1800", "PDOP": "1.2"},
        {"Point ID": "ROVER_01", "Easting": "200050.00", "Northing": "8000050.00", "Elevation": "1510.00", "Feature Code": "RAD", "Survey Method": "RTK", "Epochs": "5", "PDOP": "1.8"},
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=english_fields)
    w.writeheader()
    w.writerows(rows)
    raw = out.getvalue().encode("utf-8")

    info = read_csv(raw)
    assert info.columns["name"] == "Point ID"
    assert info.columns["e"] == "Easting"
    assert info.columns["n"] == "Northing"
    assert info.columns["h"] == "Elevation"
    assert info.columns["code"] == "Feature Code"
    assert info.columns["method"] == "Survey Method"
    assert info.columns["observation"] == "Epochs"

    print("PASS 2: Synonyms detection across varied equipment formats")


def test_missing_optional_columns():
    """Test 3: Missing optional columns (No Base, no Observation, no Method, no Antenna)."""
    minimal_fields = ["Name", "Easting", "Northing", "Elevation"]
    rows = [
        {"Name": "B01", "Easting": "1000.0", "Northing": "5000.0", "Elevation": "100.0"},
        {"Name": "P01", "Easting": "1010.0", "Northing": "5010.0", "Elevation": "105.0"},
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=minimal_fields)
    w.writeheader()
    w.writerows(rows)
    raw = out.getvalue().encode("utf-8")

    info = read_csv(raw)
    updated_b, _ = native_updated(info)
    reread = read_csv(updated_b)
    assert reread.fieldnames == minimal_fields, "Must NOT inject optional columns if absent in template"
    assert reread.rows[1]["Name"] == "1"

    print("PASS 3: Missing optional columns handling without error or column injection")


def test_multiple_csv_merging_with_master_template():
    """Test 4: Merging multiple CSVs using the FIRST CSV as master template."""
    master_fields = ["Nombre", "Este", "Norte", "Elevación", "Código", "Observación", "Método"]
    csv1_rows = [
        {"Nombre": "BASE_MASTER", "Este": "300000.0", "Norte": "9000000.0", "Elevación": "500.0", "Código": "BM", "Observación": "60", "Método": "Topográfico"},
        {"Nombre": "P1", "Este": "300010.0", "Norte": "9000010.0", "Elevación": "502.0", "Código": "EST", "Observación": "60", "Método": "Topográfico"},
    ]
    out1 = io.StringIO()
    w1 = csv.DictWriter(out1, fieldnames=master_fields)
    w1.writeheader(); w1.writerows(csv1_rows)

    second_fields = ["Point", "Easting", "Northing", "Elevation", "Code"]
    csv2_rows = [
        {"Point": "BASE_MASTER", "Easting": "300000.0", "Northing": "9000000.0", "Elevation": "500.0", "Code": "BM"},
        {"Point": "P2", "Easting": "300020.0", "Northing": "9000020.0", "Elevation": "505.0", "Code": "EST"},
    ]
    out2 = io.StringIO()
    w2 = csv.DictWriter(out2, fieldnames=second_fields)
    w2.writeheader(); w2.writerows(csv2_rows)

    merged_bytes, summary = merge_csv_payloads(
        [out1.getvalue().encode("utf-8"), out2.getvalue().encode("utf-8")],
        require_same_base=True,
    )
    merged_info = read_csv(merged_bytes)
    assert merged_info.fieldnames == master_fields, "Merged output must use Master CSV header schema"
    assert len(merged_info.rows) == 3  # Base + P1 + P2
    assert merged_info.rows[2]["Nombre"] == "2"
    assert merged_info.rows[2]["Observación"] == "60"
    assert merged_info.rows[2]["Método"] == "Topográfico"

    print("PASS 4: Multi-CSV merging with Master CSV template")


def test_synthetic_point_clearing_and_tin():
    """Test 5: TIN height interpolation & clearing synthetic observed GNSS quality parameters."""
    fields = ["Punto", "Este", "Norte", "Elevación", "Código", "PDOP", "RMS", "Fecha"]
    rows = [
        {"Punto": "BASE", "Este": "500000.0", "Norte": "8500000.0", "Elevación": "3000.0", "Código": "BM", "PDOP": "1.1", "RMS": "0.005", "Fecha": "2026-01-01"},
        {"Punto": "1", "Este": "500010.0", "Norte": "8500000.0", "Elevación": "3010.0", "Código": "P", "PDOP": "1.3", "RMS": "0.008", "Fecha": "2026-01-01"},
        {"Punto": "2", "Este": "500000.0", "Norte": "8500010.0", "Elevación": "3020.0", "Código": "P", "PDOP": "1.2", "RMS": "0.007", "Fecha": "2026-01-01"},
        {"Punto": "3", "Este": "500010.0", "Norte": "8500010.0", "Elevación": "3030.0", "Código": "P", "PDOP": "1.4", "RMS": "0.009", "Fecha": "2026-01-01"},
    ]
    out = io.StringIO()
    w = csv.DictWriter(out, fieldnames=fields)
    w.writeheader(); w.writerows(rows)
    info = read_csv(out.getvalue().encode("utf-8"))

    # Plan point inside the square -> TIN interpolation
    plan_pts = [CoordinatePoint(name="NEW_SYNTHETIC", e=500005.0, n=8500005.0)]
    gen_bytes, summary = generate_derived_data(info, plan_pts)
    gen_info = read_csv(gen_bytes)

    synthetic_row = gen_info.rows[-1]
    assert abs(float(synthetic_row["Elevación"]) - 3015.0) < 0.001
    # Requirement 10: Synthetic point MUST NOT fake observed PDOP, RMS, or Date
    assert synthetic_row["PDOP"] == "", "Synthetic point must clear PDOP"
    assert synthetic_row["RMS"] == "", "Synthetic point must clear RMS"
    assert synthetic_row["Fecha"] == "", "Synthetic point must clear Date"

    print("PASS 5: Synthetic point TIN interpolation & clearing observed parameters")


def test_streamlit_app_and_certificates():
    """Test 6: Streamlit app test and certificate generation."""
    app = AppTest.from_file("app.py", default_timeout=30).run()
    assert not app.exception, [e.message for e in app.exception]
    for name in ["Corrector GNSS", "Generador de data", "Certificados", "Efemérides precisas"]:
        app.sidebar.radio[0].set_value(name).run()
        assert not app.exception, [e.message for e in app.exception]

    lon, lat = Transformer.from_crs(32718, 4326, always_xy=True).transform(500000, 8500000)
    assert -90 < lat < 0 and -180 < lon < 0

    with tempfile.TemporaryDirectory() as directory:
        dpath = Path(directory)
        data = CertificateData(
            codigo="TEST-001",
            solicitante="Prueba técnica",
            norte="8500000.0000",
            este="500000.0000",
            zona="18 Sur",
            anio="2026",
            fecha_emision="04/10/2026",
        )
        plaque = make_plaque(data.codigo, dpath / "plaque.png", year=data.anio)
        pdf = generate_certificate_pdf(data, plaque, "templates/certificate_template.pdf", dpath / "certificate.pdf")
        with fitz.open(pdf) as doc:
            assert len(doc) == 1
            assert data.codigo in doc[0].get_text()

        docx = generate_certificate_docx(
            data, plaque, "templates/certificado_punto_geodesico_template.docx", dpath / "certificate.docx"
        )
        with zipfile.ZipFile(docx) as doc:
            assert doc.testzip() is None
            assert data.codigo in doc.read("word/document.xml").decode()

    print("PASS 6: Streamlit app & PDF/Word certificate generation")



def test_corrector_dashboard_regressions():
    """Regression guard for the native CSV and PDF first-screen workflow."""
    import ast
    source = Path("app.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert 'VERSION = "10.6.2"' in source
    assert 'key="corrector_native_v8"' in source
    assert 'key="corrector_reports_v8"' in source
    assert 'len(set(signatures)) == 1' in source
    assert 'len({base_coord_signature})' not in source
    assert '↓ NATIVA ACTUALIZADA' in source and '↓ CORREGIDA' in source
    assert 'Tiempo estático' in source and 'Distancia geométrica' in source
    assert 'CALIDAD DEL CSV' in source and 'PRECISIONES DEL PDF' in source
    assert 'Google Maps Embed' not in source
    print("PASS 7: compact dashboard, dual upload, merge TypeError regression and downloads")

def main():
    test_column_order_and_preservation()
    test_synonyms_and_varied_equipment()
    test_missing_optional_columns()
    test_multiple_csv_merging_with_master_template()
    test_synthetic_point_clearing_and_tin()
    test_streamlit_app_and_certificates()
    test_corrector_dashboard_regressions()
    print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
