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
    assert merged_info.rows[2]["Observación"] == "", "No fabricar observaciones ausentes del segundo equipo"
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
    assert 'VERSION = "10.6.4"' in source
    ui = Path("gnss_corrector_ui.py").read_text(encoding="utf-8")
    assert 'key="corrector_native_v8"' in ui
    assert 'key="corrector_reports_v8"' in ui
    assert 'from gnss_corrector_ui import render_corrector' in source
    assert 'len({base_coord_signature})' not in source
    ui = Path("gnss_corrector_ui.py").read_text(encoding="utf-8")
    assert '↓ NATIVA ACTUALIZADA' in ui and '↓ CORREGIDA CSV' in ui
    assert 'TIEMPO DE LECTURA' in ui and 'Distancia geométrica' in ui
    assert 'CALIDAD DE PUNTOS MÓVILES' in ui and 'PRECISIONES Y ERRORES DEL INFORME' in ui
    assert 'Google Maps Embed' not in source and 'Google Maps Embed' not in ui
    print("PASS 7: compact dashboard, dual upload, merge TypeError regression and downloads")


def test_cpimp_dxf_and_gnss_observation_rules():
    """CAD uses East=X North=Y, CPimp settings and excludes the GNSS base."""
    import ezdxf
    from cad_export import export_corrected_dxf
    headers = ["Solución", "Elevación", "Nombre", "N/S de la base del GNSS",
               "Norte", "Número de Observación", "Este", "Código"]
    rows = [
        ["BASE", "3693.0000", "B_001", "", "8494580.0000", "8", "222259.0000", "BASE"],
        ["Fijo (Fase)", "3693.1000", "P1", "B_001", "8494581.0000", "5", "222260.0000", "L1"],
        ["Flotante", "3693.2000", "P2", "B_002", "8494582.0000", "75", "222261.0000", "L1"],
    ]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(headers)
    writer.writerows(rows)
    info = read_csv(output.getvalue().encode("utf-8-sig"))
    assert len(info.fixed_points) == 1, info.fixed_points
    assert len(info.non_fixed_points) == 1 and info.non_fixed_points[0][1] == "Flotante"
    assert info.different_base_points == [("P2", "B_002")]
    native, _ = native_updated(info)
    reread = read_csv(native)
    assert reread.rows[0]["Número de Observación"] == "8"
    assert reread.rows[1]["Número de Observación"] == "60"
    assert reread.rows[2]["Número de Observación"] == "75"
    assert reread.rows[2]["N/S de la base del GNSS"] == "B_002"
    corrected, _, calc = apply_correction(info, 222259.1, 8494580.2, 3693.3)
    reread_corr = read_csv(corrected)
    assert reread_corr.rows[1]["Número de Observación"] == "60"
    assert reread_corr.rows[2]["Número de Observación"] == "75"
    assert reread_corr.rows[0]["Número de Observación"] == "8"
    cad = export_corrected_dxf(reread_corr)
    doc = ezdxf.read(io.StringIO(cad.decode("utf-8")))
    assert {"Pun_TODOS", "pol_TODOS"}.issubset(set(doc.layers.entries.keys())) or (
        "Pun_TODOS" in doc.layers and "pol_TODOS" in doc.layers)
    model = doc.modelspace()
    points = list(model.query("POINT"))
    texts = list(model.query("TEXT"))
    lines = list(model.query("LWPOLYLINE"))
    assert len(points) == 2, "Base must be excluded from CAD drawing"
    assert len(texts) == 4 and all(abs(t.dxf.height - .04) < 1e-9 for t in texts)
    assert len(lines) == 1
    assert abs(points[0].dxf.location.x - 222260.1) < 1e-5  # East is X
    assert abs(points[0].dxf.location.y - 8494581.2) < 1e-5  # North is Y
    assert lines[0].dxf.flags == 0  # open polyline, CPimp default
    print("PASS 8: CPimp DXF, native/corrected observation minimum, alternate base and non-FIX")


def test_height_selection_nearest_20m():
    from core import ReportInfo, choose_height
    pdf = ReportInfo(mobile_h_ortho=3691.7, mobile_h_ellip=3732.5)
    selection = choose_height(3693.0, pdf, "Automática")
    assert selection["selected_type"] == "Ortométrica"
    assert abs(selection["selected_h"] - 3691.7) < 1e-8
    far = choose_height(3800.0, pdf, "Automática")
    assert any("20" in x for x in far["warnings"])
    print("PASS 9: nearest ortho/ellip height selection and 20m warning")


def test_gnss_coordinate_cards_mobile_and_reference():
    """Card labels pair UTM with H ortho and geographic with h ellip for both stations."""
    from core import ReportInfo
    from gnss_corrector_ui import _report_coordinate_card
    rep = ReportInfo(
        utm_zone="18", utm_hemisphere="S",
        mobile_name="Ruth Ccatca", mobile_e=222259.4808, mobile_n=8494579.9537,
        mobile_h_ortho=3691.6519, mobile_h_ellip=3738.9468,
        mobile_lat="13 36 15 S", mobile_lon="71 34 00 O",
        reference_name="CS01", reference_e=177222.4, reference_n=8500000.4,
        reference_h_ortho=3363.7346, reference_h_ellip=3410.0095,
        reference_lat="13 30 00 S", reference_lon="71 40 00 O",
    )
    mobile_html = _report_coordinate_card(rep, "mobile")
    ref_html = _report_coordinate_card(rep, "reference")
    assert "PUNTO GEODÉSICO MÓVIL" in mobile_html
    assert "ESTACIÓN DE REFERENCIA" in ref_html
    assert "Ruth Ccatca" in mobile_html and "CS01" in ref_html
    assert "UTM WGS84 · Zona 18S" in mobile_html
    for expected in ("222259.4808 m", "8494579.9537 m",
                     "3691.6519 m", "3738.9468 m", "13 36 15 S", "71 34 00 O"):
        assert expected in mobile_html, expected
    for expected in ("177222.4000 m", "8500000.4000 m",
                     "3363.7346 m", "3410.0095 m", "13 30 00 S", "71 40 00 O"):
        assert expected in ref_html, expected
    assert "Latitud y longitud extraídas del PDF" in mobile_html
    assert "Latitud y longitud extraídas del PDF" in ref_html
    assert mobile_html.index("H ortométrica") < mobile_html.index("GEOGRÁFICAS · WGS84")
    assert mobile_html.index("h elipsoidal") > mobile_html.index("GEOGRÁFICAS · WGS84")

    # Explicit conversion only if both zone and hemisphere are available.
    rep.reference_lat = rep.reference_lon = None
    converted = _report_coordinate_card(rep, "reference")
    assert "convertidas de UTM" in converted
    rep.utm_hemisphere = None
    missing = _report_coordinate_card(rep, "reference")
    assert "sin conversión" in missing
    assert "convertidas de UTM" not in missing
    print("PASS 10: paired coordinate cards, correct heights, CRS and conversion provenance")


def test_report_reference_geographic_extraction():
    """Reference = first column and mobile = second; never confuse station roles."""
    import fitz
    from core import parse_report_pdfs
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (40, 72),
        "Latitud WGS84:\n-13.50000000\n-13.60416667\n"
        "Longitud WGS84:\n-71.66666667\n-71.56666667\n"
        "WGS84_UTM_18S",
        fontsize=12,
    )
    report = parse_report_pdfs([("synthetic-coordinates.pdf", doc.tobytes())])
    doc.close()
    assert report.reference_lat == "-13.50000000", report.reference_lat
    assert report.mobile_lat == "-13.60416667", report.mobile_lat
    assert report.reference_lon == "-71.66666667", report.reference_lon
    assert report.mobile_lon == "-71.56666667", report.mobile_lon
    assert report.utm_zone == "18" and report.utm_hemisphere == "S"
    print("PASS 11: real PDF extraction of two geographic coordinate columns")

def main():
    test_column_order_and_preservation()
    test_synonyms_and_varied_equipment()
    test_missing_optional_columns()
    test_multiple_csv_merging_with_master_template()
    test_synthetic_point_clearing_and_tin()
    test_streamlit_app_and_certificates()
    test_corrector_dashboard_regressions()
    test_cpimp_dxf_and_gnss_observation_rules()
    test_height_selection_nearest_20m()
    test_gnss_coordinate_cards_mobile_and_reference()
    test_report_reference_geographic_extraction()
    print("\n✅ ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    main()
