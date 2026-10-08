"""Pantalla de corrección GNSS CONPLANOS, independiente del generador de data."""
from __future__ import annotations

from collections import Counter
import hashlib
import html
import io
import math
import re
from pathlib import Path
import unicodedata

import streamlit as st

from core import (
    apply_correction,
    choose_height,
    corrected_filename,
    csv_point_quality_summary,
    merge_csv_payloads,
    native_updated,
    native_updated_filename,
    parse_report_pdfs,
    polygon_filename,
    read_csv,
    zip_artifacts,
)
from cad_export import export_corrected_dxf

UI_VERSION = "10.6.8"


def _esc(value):
    return html.escape(str(value if value is not None and value != "" else "—"))


def _norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return "".join(c for c in text if not unicodedata.combining(c)).strip()


def _fixed(value):
    text = " ".join(_norm(value).replace("_", " ").split())
    return (
        text in {"fijo", "fixed", "fix", "rtk fixed", "rtk fix", "fijo fase", "fixed phase"}
        or text.startswith(("fijo ", "fixed ", "rtk fixed ", "rtk fix "))
    )


def _panel(title, content):
    return (
        '<section class="cp-card"><div class="cp-card-heading">' + _esc(title)
        + '</div>' + content + "</section>"
    )


def _line(label, value):
    return '<div class="cp-line"><span>' + _esc(label) + '</span><strong>' + _esc(value) + '</strong></div>'


def _tiles(values):
    return '<div class="cp-tiles">' + "".join(
        '<div class="cp-tile"><small>' + _esc(label) + '</small><b>' + _esc(value) + '</b></div>'
        for label, value in values
    ) + '</div>'


def _section(label):
    return '<div class="cp-subsection">' + _esc(label) + '</div>'


def _range(info, semantic):
    low, high = csv_point_quality_summary(info).get(semantic, (None, None))
    if low is None:
        return "—"
    return f"{low:.3f}" if low == high else f"{low:.3f}–{high:.3f}"


def _show_styles():
    st.markdown(
        """
<style>
.cp-heading{display:flex;align-items:baseline;justify-content:space-between;gap:1rem;margin:0 0 .45rem}
.cp-heading h2{font-size:1.35rem;margin:0;letter-spacing:-.02em}
.cp-heading span{color:#0b827d;font-weight:850;font-size:.65rem}
.cp-tag{font-size:.68rem;font-weight:850;color:#0b827d;letter-spacing:.035em;margin:.38rem 0 .28rem}
.cp-caption{font-size:.68rem;opacity:.67;margin:-.08rem 0 .44rem}
.cp-card{border:1px solid rgba(111,127,135,.25);border-radius:12px;background:var(--background-color);
padding:.62rem .72rem;box-shadow:0 1px 7px rgba(15,34,38,.04);margin-bottom:.28rem}
.cp-card-heading{font-weight:850;font-size:.69rem;letter-spacing:.065em;color:#0b827d;
border-bottom:1px solid rgba(111,127,135,.18);padding-bottom:.26rem;margin-bottom:.32rem}
.cp-file{font-size:.8rem;font-weight:790;overflow-wrap:anywhere;margin:.1rem 0 .34rem}
.cp-line{display:flex;justify-content:space-between;align-items:baseline;gap:.4rem;margin:.2rem 0;font-size:.7rem}
.cp-line span{opacity:.67;white-space:nowrap}.cp-line strong{font-size:.73rem;text-align:right;overflow-wrap:anywhere}
.cp-tiles{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.28rem;margin:.3rem 0}
.cp-tile{background:var(--secondary-background-color);padding:.34rem .4rem;border-radius:7px;min-width:0}
.cp-tile small{font-size:.55rem;opacity:.67;display:block}
.cp-tile b{font-size:.81rem;display:block;margin-top:.12rem;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
.cp-subsection{font-size:.63rem;letter-spacing:.04em;font-weight:820;color:#0b827d;margin:.52rem 0 .16rem}
.cp-footnote{font-size:.6rem;opacity:.68;line-height:1.4;margin:.44rem 0 0}
.cp-geo-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:.45rem;margin:.38rem 0 .5rem}
.cp-geo-card{border:1px solid rgba(111,127,135,.24);border-radius:10px;min-width:0;padding:.5rem .5rem .42rem;background:var(--background-color)}
.cp-geo-card--mobile{border:1px solid rgba(12,128,120,.44);background:linear-gradient(160deg,rgba(20,155,142,.075),transparent 68%)}
.cp-geo-head{font-size:.6rem;font-weight:850;letter-spacing:.042em;color:#0b827d}
.cp-geo-card--reference .cp-geo-head{color:var(--text-color);opacity:.72}
.cp-geo-name{font-size:.72rem;font-weight:850;line-height:1.24;margin:.14rem 0 .34rem;overflow-wrap:anywhere}
.cp-geo-group{font-size:.58rem;letter-spacing:.035em;font-weight:820;color:#0b827d;margin:.39rem 0 .13rem;border-top:1px solid rgba(111,127,135,.18);padding-top:.3rem}
.cp-geo-pair{display:flex;align-items:baseline;justify-content:space-between;gap:.25rem;font-size:.63rem;margin:.13rem 0}
.cp-geo-pair span{opacity:.72;flex-shrink:0}
.cp-geo-pair strong{text-align:right;font-size:.66rem;font-variant-numeric:tabular-nums;overflow-wrap:anywhere;min-width:0}
.cp-geo-source{font-size:.57rem;color:var(--text-color);opacity:.65;margin:.3rem 0 0;line-height:1.25}
.cp-geo-grid{grid-template-columns:minmax(0,1.13fr) minmax(0,.87fr);align-items:start}
.cp-geo-card--mobile{border:1px solid rgba(12,128,120,.55);background:linear-gradient(165deg,rgba(20,155,142,.085),transparent 78%);box-shadow:0 2px 12px rgba(15,86,77,.06)}
.cp-geo-card--mobile .cp-geo-head{color:#08766f}
.cp-geo-card--reference{background:var(--secondary-background-color)}
.cp-coordinate-stack{display:flex;flex-direction:column;gap:.17rem;padding:.12rem 0 .2rem}
.cp-coordinate-item{display:flex;justify-content:space-between;align-items:baseline;gap:.3rem;padding:.22rem .25rem;border-bottom:1px solid rgba(111,127,135,.12);font-variant-numeric:tabular-nums}
.cp-coordinate-item span{font-size:.61rem;opacity:.73}
.cp-coordinate-item strong{font-size:.75rem;font-weight:850;text-align:right;overflow-wrap:anywhere;line-height:1.34}
.cp-coordinate-item--emphasis{background:rgba(15,133,122,.045);border-radius:5px}
.cp-geo-card--mobile .cp-coordinate-item--emphasis strong{font-size:.81rem}
.cp-tile--baseline{border:1px solid transparent}
.cp-tile--ok{border-color:rgba(14,126,96,.35);background:rgba(27,151,109,.08)}
.cp-tile--caution{border-color:rgba(209,149,31,.57);background:rgba(228,168,48,.16)}
.cp-tile--danger{border-color:rgba(199,50,50,.7);background:rgba(215,50,50,.12)}
.cp-tile--danger b{color:#d43c3c;font-weight:900}
.cp-tile--caution b{color:#9c6700}
.cp-geo-grid{grid-template-columns:1fr;gap:.45rem}
.cp-geo-card{padding:.5rem .67rem .44rem}
.cp-coordinate-stack{gap:.05rem}
.cp-geo-card--mobile{border-width:2px}
@media(max-width:660px){.cp-geo-grid{grid-template-columns:1fr}}

.cp-geo-note{font-size:.6rem;line-height:1.35;opacity:.68;margin:.2rem 0 .4rem}
@media(max-width:650px){.cp-geo-grid{grid-template-columns:1fr}}
.cp-banner{font-size:.7rem;padding:.46rem .6rem;border-radius:8px;margin:.25rem 0}
.cp-banner-red{border:1px solid #e88c8c;background:rgba(215,45,45,.09);color:var(--text-color)}
.cp-banner-orange{border:1px solid #dca864;background:rgba(220,154,36,.08);color:var(--text-color)}
.cp-banner strong{font-weight:850}
[data-testid="stFileUploader"] section{min-height:46px!important;padding:.28rem .42rem!important}
[data-testid="stFileUploader"] small{font-size:.62rem!important}
@media(max-width:900px){.cp-heading{flex-wrap:wrap}}
</style>
""", unsafe_allow_html=True,
    )


def _overrides(raw, label, key):
    """Manual resolution only when the critical aliases do not match."""
    import csv
    from core import _detect_encoding, _detect_delimiter
    try:
        text = raw.decode(_detect_encoding(raw))
        headers = list(csv.reader(io.StringIO(text), delimiter=_detect_delimiter(text)))[0]
    except Exception:
        return None
    if not headers:
        return None
    with st.expander("Revisar columnas de " + label, expanded=True):
        st.warning("No se reconocieron algunas columnas. Asigna Este, Norte, Elevación y Nombre.")
        c1, c2, c3, c4 = st.columns(4)
        mapping = {}
        for col, semantic, term in zip((c1, c2, c3, c4),
                                       ("e", "n", "h", "name"),
                                       ("este", "norte", "elev", "nombre")):
            defaults = [i for i, h in enumerate(headers) if term in _norm(h)]
            with col:
                mapping[semantic] = st.selectbox(
                    semantic.upper(), headers, index=defaults[0] if defaults else 0,
                    key=f"{key}_{semantic}",
                )
        return mapping


def _load_info(upload, idx):
    raw = upload.getvalue()
    key = f"cp_mapping_{idx}_{hashlib.sha256(raw).hexdigest()[:12]}"
    overrides = st.session_state.get(key)
    try:
        return read_csv(raw, column_overrides=overrides)
    except ValueError as exc:
        if "columnas críticas" not in _norm(str(exc)):
            raise
        overrides = _overrides(raw, upload.name, key)
        if overrides:
            st.session_state[key] = overrides
            return read_csv(raw, column_overrides=overrides)
        return None


def _base_discrepancies(info):
    col = info.columns.get("base")
    if not col:
        return []
    mismatches = []
    for line, row in enumerate(info.rows[1:], start=3):
        reference = str(row.get(col) or "").strip()
        if reference and _norm(reference) != _norm(info.base_name):
            mismatches.append((line, reference, row.get(info.columns["name"], "")))
    return mismatches


def _observation_changes(info):
    col = info.columns.get("observation")
    if not col:
        return []
    changes = []
    for line, row in enumerate(info.rows[1:], start=3):
        value = str(row.get(col) or "").strip()
        if not value:
            continue
        try:
            count = float(value.replace(",", "."))
            if math.isfinite(count) and count < 60:
                changes.append((line, value))
        except ValueError:
            continue
    return changes


def _lat_lon(e, n, zone, hemisphere):
    if e is None or n is None or not zone:
        return None
    try:
        from pyproj import Transformer
        z = int(zone)
        if not 1 <= z <= 60:
            return None
        epsg = (32600 if hemisphere == "N" else 32700) + z
        lon, lat = Transformer.from_crs(epsg, 4326, always_xy=True).transform(float(e), float(n))
        if math.isfinite(lat) and math.isfinite(lon):
            return f"{lat:.8f}, {lon:.8f}"
    except (ValueError, TypeError):
        pass
    return None





def _original_project_name(filename: str) -> str:
    """Remove previous processing suffixes, preserving the project's actual name."""
    text = Path(filename.replace(chr(92), "/")).stem.strip()
    suffix = re.compile(
        r"(?i)[\s_.-]+(?:sin[\s_-]*corr(?:egir|eccion|ección)?|"
        r"nativ[oa]|actualizad[oa]|corregid[oa]|pol[ií]gono|rtk|cpimp)$"
    )
    for _ in range(12):
        cleaned = suffix.sub("", text).strip(" ._-")
        if cleaned == text:
            break
        text = cleaned
    return text or Path(filename).stem.strip() or "CONPLANOS"


def _correction_filenames(filename: str) -> tuple[str, str, str, str]:
    base = _original_project_name(filename)
    return (
        f"{base} RTK nativo.csv",
        f"{base} RTK corregido.csv",
        f"{base} Polígono corregido.csv",
        f"{base} Polígono corregido.dxf",
    )


def _baseline_distance_status(distance_m: float | None):
    """Advisory review thresholds, not a universal engineering restriction."""
    if distance_m is None:
        return "—", "unknown"
    try:
        km = float(distance_m) / 1000.0
    except (TypeError, ValueError):
        return "—", "unknown"
    if not math.isfinite(km) or km < 0:
        return "—", "unknown"
    return f"{km:.3f} km", ("danger" if km > 100 else "caution" if km > 80 else "ok")


def _baseline_tile(distance_m):
    value, level = _baseline_distance_status(distance_m)
    return (
        '<div class="cp-tile cp-tile--baseline cp-tile--' + level +
        '"><small>DISTANCIA ERP–PUNTO</small><b>' + _esc(value) + '</b></div>'
    )


def _report_coordinate_card(report, kind: str) -> str:
    """Professional geodetic summary: mobile UTM + geographic, ERP geographic.

    UTM coordinates (Este/Norte) are projected coordinates, not ECEF Cartesian X/Y/Z.
    Keep orthometric H with UTM and ellipsoidal h with geographic WGS84 only.
    """
    if kind not in {"mobile", "reference"}:
        raise ValueError("Tipo de punto inválido.")
    is_mobile = kind == "mobile"
    name = report.mobile_name if is_mobile else report.reference_name
    e = report.mobile_e if is_mobile else report.reference_e
    n = report.mobile_n if is_mobile else report.reference_n
    h_ortho = report.mobile_h_ortho if is_mobile else report.reference_h_ortho
    h_ellip = report.mobile_h_ellip if is_mobile else report.reference_h_ellip
    lat_report = report.mobile_lat if is_mobile else report.reference_lat
    lon_report = report.mobile_lon if is_mobile else report.reference_lon
    hemi = (report.utm_hemisphere or "").upper()
    zone = str(report.utm_zone) if report.utm_zone else None
    if lat_report and lon_report:
        lat, lon = lat_report, lon_report
        source = "Geográficas extraídas del informe Leica"
    elif zone and hemi in ("N", "S"):
        latlon = _lat_lon(e, n, zone, hemi)
        if latlon is not None:
            lat, lon = latlon.split(", ", 1)
            source = "Geográficas calculadas desde UTM, no extraídas del PDF"
        else:
            lat = lon = "—"
            source = "Coordenadas geográficas no disponibles"
    else:
        lat = lon = "—"
        source = "Geográficas no disponibles; zona UTM sin identificar"

    def height(value):
        return f"{value:.4f} m" if value is not None else "—"

    def item(label, value, primary=False):
        return ('<div class="cp-coordinate-item'
                + (' cp-coordinate-item--emphasis' if primary else '')
                + '"><span>' + _esc(label) + '</span><strong>'
                + _esc(value) + '</strong></div>')

    label = "PUNTO GEODÉSICO ELABORADO" if is_mobile else "ERP · ESTACIÓN DE RASTREO PERMANENTE"
    css_class = "cp-geo-card cp-geo-card--mobile" if is_mobile else "cp-geo-card cp-geo-card--reference"
    content = (
        '<article class="' + css_class + '">'
        '<div class="cp-geo-head">' + _esc(label) + '</div>'
        '<div class="cp-geo-name">' + _esc(name) + '</div>'
    )
    if is_mobile:
        utm_title = f"UTM WGS84 · Zona {zone}{hemi}" if zone and hemi in ("N", "S") else "UTM · Zona no identificada"
        content += (
            '<div class="cp-geo-group">' + _esc(utm_title) + '</div>'
            '<div class="cp-coordinate-stack">'
            + item("Este (E)", height(e), primary=True)
            + item("Norte (N)", height(n), primary=True)
            + item("Altura ortométrica (H)", height(h_ortho), primary=True)
            + '</div>'
        )
    content += (
        '<div class="cp-geo-group">COORDENADAS GEOGRÁFICAS · WGS84</div>'
        '<div class="cp-coordinate-stack">'
        + item("Latitud", lat, primary=is_mobile)
        + item("Longitud", lon, primary=is_mobile)
        + item("Altura elipsoidal (h)", height(h_ellip), primary=is_mobile)
        + '</div>'
        '<div class="cp-geo-source">' + _esc(source) + '</div>'
        '</article>'
    )
    return content


def _read_report_uploads(pdfs):
    reports = []
    for f in (pdfs or []):
        try:
            reports.append((f.name, parse_report_pdfs([(f.name, f.getvalue())])))
        except Exception as exc:
            st.error(f"No se pudo leer el informe {f.name}: {exc}")
    return reports


def render_corrector():
    _show_styles()
    st.markdown(f'<div class="cp-heading"><h2>Corrección GNSS</h2><span>CONPLANOS · RTK / ESTÁTICO · V{UI_VERSION}</span></div>', unsafe_allow_html=True)

    # 01. El resumen del CSV se coloca en su misma fila.
    source_left, source_right = st.columns([1.35, 1], gap="medium")
    infos = []
    with source_left:
        st.markdown('<div class="cp-tag">01 · LEVANTAMIENTO RTK GNSS NATIVO</div>', unsafe_allow_html=True)
        st.caption("Sube el CSV nativo. El primero será la plantilla de todas las descargas.")
        uploads = st.file_uploader("CSV nativo", type=["csv"], accept_multiple_files=True,
                                   label_visibility="collapsed", key="corrector_native_v8")
        for idx, f in enumerate(uploads or []):
            try:
                parsed = _load_info(f, idx)
                if parsed is not None:
                    infos.append((f.name, parsed))
            except Exception as exc:
                st.error(f"{f.name}: {exc}")

    problems = []
    total_change = 0
    for file_name, info in infos:
        mismatches = _base_discrepancies(info)
        obs_changes = _observation_changes(info)
        total_change += len(obs_changes)
        if mismatches:
            details = ", ".join(f"fila {line} ({point}: {ref})" for line, ref, point in mismatches[:12])
            problems.append(f"{file_name}: {len(mismatches)} punto(s) con otra base: {details}")
        if info.non_fixed_points:
            counts = Counter(status for _, status in info.non_fixed_points)
            detail = ", ".join(f"{label or 'Sin estado'}: {n}" for label, n in counts.items())
            problems.append(f"{file_name}: {len(info.non_fixed_points)} punto(s) no FIX: {detail}")
        if obs_changes:
            st.caption(f"{file_name}: {len(obs_changes)} observación(es) con valor inferior a 60; se normalizarán a 60 en los archivos derivados, conservando el CSV original.")

    with source_right:
        if not infos:
            st.markdown(_panel("RESUMEN DEL CSV", '<p class="cp-footnote">Aparecerá al cargar el archivo.</p>'), unsafe_allow_html=True)
        else:
            name, info = infos[0]
            body = '<div class="cp-file">' + _esc(name) + '</div>'
            body += _tiles([("REGISTROS", len(info.rows)), ("FIJOS", len(info.fixed_points)),
                            ("NO FIX", len(info.non_fixed_points))])
            body += _line("Base del levantamiento", info.base_name) + _line("Plantilla", f"{len(info.fieldnames)} columnas")
            body += _section("COORDENADAS DE BASE · CSV") + _tiles([
                ("ESTE (X)", f"{info.base_original_e:.4f}"), ("NORTE (Y)", f"{info.base_original_n:.4f}"),
                ("ALTURA", f"{info.base_original_h:.4f}")])
            body += _section("CALIDAD DE PUNTOS MÓVILES") + _tiles([
                ("PDOP", _range(info, "pdop")), ("HDOP", _range(info, "hdop")),
                ("RMS", _range(info, "rms_error"))])
            body += '<p class="cp-footnote">El primer registro es la base. No participa en FIX, observaciones ni advertencias de puntos móviles.</p>'
            st.markdown(_panel("RESUMEN DEL CSV NATIVO", body), unsafe_allow_html=True)

    if problems:
        st.markdown(
            '<div class="cp-banner cp-banner-red"><strong>ATENCIÓN · REVISIÓN GNSS</strong><div>'
            + '</div><div>'.join(_esc(p) for p in problems)
            + '</div></div>', unsafe_allow_html=True,
        )

    # 02: PDF y origen de corrección son un único paso con su diagnóstico a la derecha.
    pdf_left, pdf_right = st.columns([1.35, 1], gap="medium")
    corrections = {}
    selected_reports = {}
    caution_height = []
    mode = "PDF"
    reports = []
    with pdf_left:
        st.markdown('<div class="cp-tag">02 · PROCESAMIENTO DEL PUNTO GEODÉSICO GNSS</div>', unsafe_allow_html=True)
        st.caption("Carga el informe Leica del punto geodésico procesado o introduce sus coordenadas corregidas.")
        pdfs = st.file_uploader("Informes Leica", type=["pdf"], accept_multiple_files=True,
                                label_visibility="collapsed", key="corrector_reports_v8")
        reports = _read_report_uploads(pdfs)
        mode = st.radio("Fuente de coordenadas", ["Informe PDF", "Coordenadas manuales"],
                        horizontal=True, label_visibility="collapsed", key="cp_mode_v1063")
        if infos:
            if mode == "Informe PDF":
                if not reports:
                    st.caption("PDF pendiente; puedes pasar a coordenadas manuales.")
                for idx, (name, info) in enumerate(infos):
                    if not reports:
                        break
                    if len(reports) > 1:
                        options = ["— Seleccionar informe —"] + [f"{file} · {rep.mobile_name or 'Punto móvil'}" for file, rep in reports]
                        choice = st.selectbox(f"Informe para {name}", options, key=f"cp_rep_{idx}_1063")
                        if choice == options[0]:
                            continue
                        rep_name, rep = reports[options.index(choice) - 1]
                    else:
                        rep_name, rep = reports[0]
                    selected_reports[name] = (rep_name, rep)
                    if rep.mobile_e is None or rep.mobile_n is None:
                        st.error(f"{rep_name}: no se identificaron las coordenadas del punto móvil.")
                        continue
                    h_mode = st.selectbox(
                        "Tipo de altura", ["Automática", "Ortométrica", "Elipsoidal WGS84"],
                        key=f"cp_height_{idx}_1063",
                    )
                    try:
                        height = choose_height(info.base_original_h, rep, h_mode)
                        corrections[name] = (rep.mobile_e, rep.mobile_n, height["selected_h"], rep, height)
                        st.caption(
                            f"Altura seleccionada: **{height['selected_type']}** · "
                            f"**{height['selected_h']:.4f} m** · Diferencia: "
                            f"**{height['diffs'].get(height['selected_type'], 0):.4f} m**."
                        )
                        if height["diffs"].get(height["selected_type"], 0) > 20:
                            caution_height.append(name)
                        for warning in height["warnings"]:
                            st.warning(warning)
                    except Exception as exc:
                        st.error(f"No se pudo elegir la altura de {name}: {exc}")
            else:
                for idx, (name, info) in enumerate(infos):
                    if len(infos) > 1:
                        st.caption(name)
                    c1, c2, c3 = st.columns(3, gap="small")
                    e = c1.number_input("Este (X)", value=float(info.base_original_e),
                                        format="%.4f", key=f"cp_e_{idx}_1063")
                    n = c2.number_input("Norte (Y)", value=float(info.base_original_n),
                                        format="%.4f", key=f"cp_n_{idx}_1063")
                    h = c3.number_input("Altura", value=float(info.base_original_h),
                                        format="%.4f", key=f"cp_h_{idx}_1063")
                    corrections[name] = (e, n, h, None, None)
        else:
            st.caption("Completa primero el paso 01.")

    with pdf_right:
        name = infos[0][0] if infos else None
        rep_file, rep = selected_reports.get(name, (None, None))
        if rep is None and reports:
            rep_file, rep = reports[0]
        if not rep:
            st.markdown(_panel("RESUMEN DEL INFORME GNSS", '<p class="cp-footnote">Sube el informe Leica para identificar la ERP, el punto geodésico, duración y calidad.</p>'), unsafe_allow_html=True)
        else:
            zone, hemi = rep.utm_zone, rep.utm_hemisphere or "S"
            reference_geo = _lat_lon(rep.reference_e, rep.reference_n, zone, hemi)
            mobile_geo = _lat_lon(rep.mobile_e, rep.mobile_n, zone, hemi)
            distance = rep.distance_m
            dist_caption = "Distancia geométrica"
            if distance is None and all(v is not None for v in (rep.reference_e, rep.reference_n, rep.mobile_e, rep.mobile_n)):
                distance = math.hypot(rep.reference_e - rep.mobile_e, rep.reference_n - rep.mobile_n)
                dist_caption = "Distancia horizontal calculada"
            body = _line("Informe", rep_file)
            body += _line("Base de referencia", rep.reference_name)
            body += _line("Punto móvil", rep.mobile_name)
            body += (
                '<div class="cp-tiles">'
                + '<div class="cp-tile"><small>TIEMPO DE LECTURA</small><b>'
                + _esc(rep.solution_duration or rep.duration or "—") + '</b></div>'
                + _baseline_tile(distance)
                + '<div class="cp-tile"><small>SOLUCIÓN</small><b>'
                + _esc(rep.solution_type or rep.solution_state or "—") + '</b></div>'
                + '</div>'
            )
            if dist_caption != "Distancia geométrica":
                body += _line("Tipo de distancia", "Horizontal calculada desde UTM")
            body += _section("EQUIPOS · RECEPTOR / ANTENA")
            body += _line("Receptor base", rep.reference_receiver) + _line("Receptor móvil", rep.mobile_receiver)
            body += _line("Antena base", rep.reference_antenna) + _line("Antena móvil", rep.mobile_antenna)
            body += _line("Altura antena móvil", f"{rep.mobile_antenna_height_m:.4f} m" if rep.mobile_antenna_height_m is not None else "—")
            body += _section("COORDENADAS DE LA ERP Y DEL PUNTO GEODÉSICO")
            body += (
                '<div class="cp-geo-grid">'
                + _report_coordinate_card(rep, "reference")
                + _report_coordinate_card(rep, "mobile")
                + '</div>'
            )
            body += (
                '<p class="cp-geo-note">UTM: Este, Norte y altura ortométrica. '
                'Geográficas WGS84: latitud, longitud y altura elipsoidal, '
                'según el informe. Los datos convertidos se identifican expresamente.</p>'
            )
            body += _section("PRECISIONES Y ERRORES DEL INFORME")
            body += _tiles([("CQ 1D", f"{rep.cq1d_m:.4f} m" if rep.cq1d_m is not None else "—"),
                            ("CQ 2D", f"{rep.cq2d_m:.4f} m" if rep.cq2d_m is not None else "—"),
                            ("CQ 3D", f"{rep.cq3d_m:.4f} m" if rep.cq3d_m is not None else "—")])
            body += _tiles([("ERROR X", f"{rep.error_x_m:.4f} m" if rep.error_x_m is not None else "—"),
                            ("ERROR Y", f"{rep.error_y_m:.4f} m" if rep.error_y_m is not None else "—"),
                            ("ERROR Z", f"{rep.error_z_m:.4f} m" if rep.error_z_m is not None else "—")])
            if name in corrections:
                e, n, h, _, hc = corrections[name]
                body += _section("ALTURA APLICADA Y AJUSTES DEL CSV")
                body += _line(
                    "Altura seleccionada",
                    f"{hc['selected_type']} · {h:.4f} m" if hc else f"Manual · {h:.4f} m",
                )
                if infos:
                    original = infos[0][1]
                    body += _line("ΔE / ΔN / ΔH",
                                  f"{e-original.base_original_e:+.4f} / {n-original.base_original_n:+.4f} / {h-original.base_original_h:+.4f} m")
            body += '<p class="cp-footnote">La zona UTM debe estar identificada para convertir latitud/longitud. CQ no equivale a errores X/Y/Z.</p>'
            st.markdown(_panel("RESUMEN DEL INFORME GNSS", body), unsafe_allow_html=True)
            _, baseline_level = _baseline_distance_status(distance)
            if baseline_level == "danger":
                st.error("🔴 Línea base superior a 100 km. Supera el umbral de revisión configurado: verifica el procesamiento y los requisitos técnicos aplicables.")
            elif baseline_level == "caution":
                st.warning("🟡 Línea base superior a 80 km. Revisa el procesamiento, la calidad y los requisitos técnicos aplicables.")
            if not _fixed(rep.solution_type or rep.solution_state):
                st.error("🔴 ADVERTENCIA CRÍTICA: la solución del PDF no se ha identificado como FIJA. Verifica el procesamiento antes de certificar.")

    if caution_height:
        st.error("🔴 DIFERENCIA DE ALTURA SUPERIOR A 20 m. Comprueba datum, modelo geoidal y tipo de altura antes de continuar.")
    distinct_bases = len({info.base_name.casefold() for _, info in infos}) == 1 if infos else False
    has_base_conflicts = any(_base_discrepancies(info) for _, info in infos)
    consent = True
    if has_base_conflicts:
        consent = st.checkbox(
            "He revisado las filas que utilizan otra base y autorizo procesarlas bajo una única traslación "
            "(la discrepancia original seguirá registrada).", value=False, key="cp_base_consent_v1063",
        )
    height_consent = True
    if caution_height:
        height_consent = st.checkbox(
            "He verificado personalmente la diferencia de altura superior a 20 m.",
            value=False, key="cp_height_consent_v1063",
        )

    # 03: resultado siempre ocupa el ancho completo para facilitar descargas.
    st.markdown('<div class="cp-tag">03 · GENERAR Y DESCARGAR</div>', unsafe_allow_html=True)
    signature = (
        UI_VERSION,  # Invalidate persisted download payloads from previous releases.
        tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (uploads or [])),
        tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (pdfs or [])),
        mode,
        tuple((name, round(float(v[0]), 6), round(float(v[1]), 6), round(float(v[2]), 6))
              for name, v in corrections.items()),
        tuple((name, selected_reports[name][0]) for name in selected_reports),
    )
    if st.session_state.get("cp_signature_v1063") != signature:
        st.session_state["cp_signature_v1063"] = signature
        st.session_state.pop("cp_artifacts_v1063", None)

    ready = bool(infos) and len(corrections) == len(infos) and consent and height_consent
    if st.button("✓ GENERAR CORRECCIÓN · CSV + CAD", type="primary", use_container_width=True,
                 disabled=not ready, key="cp_generate_v1063"):
        try:
            results = []
            native_all, corrected_all, polygon_all, signatures = [], [], [], []
            for name, info in infos:
                e, n, h, _, _ = corrections[name]
                corrected_b, polygon_b, calc = apply_correction(info, float(e), float(n), float(h))
                native_b, _ = native_updated(info)
                dxf = export_corrected_dxf(read_csv(corrected_b))
                filenames = _correction_filenames(name)
                results.append((name, native_b, corrected_b, polygon_b, dxf, filenames, calc))
                native_all.append(native_b)
                corrected_all.append(corrected_b)
                polygon_all.append(polygon_b)
                signatures.append((round(float(e), 4), round(float(n), 4), round(float(h), 4)))
            bundle = []
            for name, native_b, corrected_b, polygon_b, dxf_b, files, calc in results:
                bundle.extend(zip(files, (native_b, corrected_b, polygon_b, dxf_b)))
            # El CSV original sin alteraciones es la referencia de auditoría.
            for idx, f in enumerate(uploads or []):
                bundle.append((f"ORIGINAL_{idx+1}_{f.name}", f.getvalue()))
            audit = (
                "CONPLANOS GNSS · Registro de normalización\\n"
                "Los valores de Número de observación inferiores a 60 se normalizaron a 60 "
                "en los CSV derivados por instrucción del usuario. Esto NO representa nuevas épocas GNSS medidas.\\n"
                f"Registros normalizados: {total_change}\\n"
                "Toda observación instrumental original se conserva en ORIGINAL_*.csv.\\n"
                "Revisar referencias de base, soluciones no FIX y altura antes de usar para certificación.\\n"
            )
            bundle.append(("AUDITORIA_CONPLANOS.txt", audit.encode("utf-8")))
            combined = None
            if len(results) > 1 and distinct_bases and len(set(signatures)) == 1:
                try:
                    n_all, _ = merge_csv_payloads(native_all)
                    c_all, _ = merge_csv_payloads(corrected_all)
                    p_all, _ = merge_csv_payloads(polygon_all)
                    combined = (n_all, c_all, p_all)
                    bundle.extend([
                        ("CONPLANOS RTK nativo unido.csv", n_all),
                        ("CONPLANOS RTK corregido unido.csv", c_all),
                        ("CONPLANOS Polígono corregido unido.csv", p_all),
                        ("CONPLANOS Polígono corregido unido.dxf", export_corrected_dxf(read_csv(c_all))),
                    ])
                except Exception as exc:
                    st.warning(f"No se pudieron unir los archivos: {exc}")
            st.session_state["cp_artifacts_v1063"] = (results, zip_artifacts(bundle), combined)
            st.success("Archivos generados. Descarga el nativo, corregido y CAD DXF.")
        except Exception as exc:
            st.error(f"No se pudieron generar los archivos: {type(exc).__name__}: {exc}")

    saved = st.session_state.get("cp_artifacts_v1063")
    if saved:
        results, all_zip, combined = saved
        for idx, (name, native_b, corrected_b, polygon_b, dxf_b, files, calc) in enumerate(results):
            if len(results) > 1:
                st.markdown("**" + name + "**")
            c1, c2, c3, c4 = st.columns(4, gap="small")
            for column, label, data, filename, mime, suffix in (
                (c1, "↓ DATA RTK NATIVA ACTUALIZADA", native_b, files[0], "text/csv", "n"),
                (c2, "↓ DATA RTK CORREGIDA CSV", corrected_b, files[1], "text/csv", "c"),
                (c3, "↓ POLÍGONO CORREGIDO CSV", polygon_b, files[2], "text/csv", "p"),
                (c4, "↓ POLÍGONO CORREGIDO DXF", dxf_b, files[3], "application/dxf", "d"),
            ):
                with column:
                    st.download_button(label, data, file_name=filename, mime=mime,
                                       use_container_width=True, on_click="ignore",
                                       key=f"cp_dl_{idx}_{suffix}_1063")
            st.caption(
                f"**Desplazamiento aplicado:** ΔE {calc['delta_e']:+.4f} m · "
                f"ΔN {calc['delta_n']:+.4f} m · ΔH {calc['delta_h']:+.4f} m"
            )
        d1, d2 = st.columns([1, 2], gap="small")
        with d1:
            st.download_button("↓ TODO EN ZIP + ORIGINALES + AUDITORÍA", all_zip,
                               file_name=(_original_project_name(infos[0][0]) + " RTK completo.zip" if len(infos) == 1 else "CONPLANOS RTK completo.zip"),
                               mime="application/zip", use_container_width=True,
                               on_click="ignore", key="cp_zip_v1063")
        if combined:
            with d2:
                with st.expander("Descargas combinadas (misma base)", expanded=False):
                    cc1, cc2 = st.columns(2)
                    cc1.download_button("↓ DATA RTK NATIVA UNIDA", combined[0],
                                       file_name="CONPLANOS RTK nativo unido.csv",
                                       mime="text/csv", on_click="ignore", key="cp_merged_native_1063")
                    cc2.download_button("↓ DATA RTK CORREGIDA UNIDA", combined[1],
                                       file_name="CONPLANOS RTK corregido unido.csv",
                                       mime="text/csv", on_click="ignore", key="cp_merged_corr_1063")
