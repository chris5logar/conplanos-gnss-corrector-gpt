from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import re
import tempfile

import streamlit as st

from core import (
    apply_correction,
    choose_height,
    csv_point_quality_summary,
    corrected_filename,
    extract_coordinate_sources,
    generated_data_filename,
    generate_derived_data,
    merge_csv_payloads,
    native_updated,
    native_updated_filename,
    parse_report_pdfs,
    polygon_filename,
    read_csv,
    zip_artifacts,
)
# Streamlit reruns may reuse a cached core module from a previous deploy.
# Recover once if the loaded module predates the flexible CSV reader.
import inspect as _inspect
import importlib as _importlib
import core as _gnss_core
if "column_overrides" not in _inspect.signature(_gnss_core.read_csv).parameters:
    _gnss_core = _importlib.reload(_gnss_core)
    for _symbol in (
        "apply_correction", "choose_height", "csv_point_quality_summary",
        "corrected_filename", "extract_coordinate_sources",
        "generated_data_filename", "generate_derived_data",
        "merge_csv_payloads", "native_updated", "native_updated_filename",
        "parse_report_pdfs", "polygon_filename", "read_csv", "zip_artifacts",
    ):
        globals()[_symbol] = getattr(_gnss_core, _symbol)
    if "column_overrides" not in _inspect.signature(read_csv).parameters:
        raise RuntimeError("No se cargó la versión actual de core.py. Reinicia la app en Streamlit Cloud.")

from ephemeris import find_best_for_day, now_lima, now_utc, today_lima
from drive import configured as drive_configured, upload_bytes as drive_upload_bytes
from history import (
    append_external_points,
    append_point,
    configured as history_configured,
    dms_to_decimal,
    load_external_points,
    load_points,
    make_external_record,
    make_record,
)
from certificate import (
    extract_certificate_data,
    generate_certificate_docx,
    generate_certificate_pdf,
    make_plaque,
    today_defaults,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
LOGO_PATH = TEMPLATES_DIR / "logo_conplanos.png"
VERSION = "10.6.3"

st.set_page_config(
    page_title="CONPLANOS GNSS",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top:.65rem;padding-bottom:.8rem;max-width:1540px;}
      .small {font-size:.78rem;line-height:1.38;}
      .tiny {font-size:.68rem;line-height:1.25;color:rgba(127,127,127,.92);}
      .card {border:1px solid rgba(127,127,127,.22);border-radius:14px;padding:.65rem .78rem;margin-bottom:.5rem;background:var(--background-color);color:var(--text-color);}
      .card-title {font-size:.84rem;font-weight:750;margin-bottom:.28rem;}
      .ok,.warn,.bad,.neutral {border-radius:9px;padding:.42rem .55rem;margin:.18rem 0;font-size:.75rem;line-height:1.3;color:var(--text-color);}
      .ok {background:rgba(34,197,94,.10);border:1px solid rgba(34,197,94,.28);}
      .warn {background:rgba(245,158,11,.10);border:1px solid rgba(245,158,11,.28);}
      .bad {background:rgba(239,68,68,.10);border:1px solid rgba(239,68,68,.28);}
      .neutral {background:var(--secondary-background-color);border:1px solid rgba(127,127,127,.22);}
      .step {font-size:.70rem;color:rgba(127,127,127,.92);margin-bottom:.08rem;text-transform:uppercase;letter-spacing:.035em;}
      .app-title {font-size:1.64rem;font-weight:800;margin-bottom:.05rem;color:var(--text-color);}
      .brand-footer {margin-top:1.2rem;padding:.65rem .4rem;border-top:1px solid rgba(127,127,127,.22);text-align:center;color:rgba(127,127,127,.92);font-size:.72rem;}
      .brand-badge {border-radius:11px;overflow:hidden;border:1px solid rgba(127,127,127,.22);margin:.2rem 0 .7rem 0;background:#111;}
      .download-head {font-size:.88rem;font-weight:750;margin-top:.8rem;margin-bottom:.35rem;}

      /* CONPLANOS GNSS 10.6.2 · panel compacto */
      .gnss-head h2{font-size:1.35rem;margin:0;font-weight:800;line-height:1.2;color:var(--text-color)}
      .gnss-head p{font-size:.72rem;opacity:.65;margin:.15rem 0 .55rem}
      .gnss-label{font-size:.71rem;font-weight:800;color:#0f766e;margin:.25rem 0 .3rem}
      .gnss-panel{border:1px solid rgba(128,128,128,.25);border-radius:12px;padding:.65rem .75rem;background:var(--background-color)}
      .gnss-h{font-size:.65rem;letter-spacing:.06em;color:#0d7c77;font-weight:850;border-bottom:1px solid rgba(128,128,128,.17);padding:.48rem 0 .2rem;margin-bottom:.3rem}
      .gnss-h:first-child{padding-top:0}
      .gnss-row{display:flex;justify-content:space-between;align-items:baseline;gap:.4rem;font-size:.69rem;margin:.2rem 0}
      .gnss-row span{opacity:.69;white-space:nowrap}.gnss-row strong{font-size:.72rem;text-align:right;overflow-wrap:anywhere}
      .gnss-triple{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.28rem;margin:.3rem 0}
      .gnss-stat{padding:.34rem .3rem;border-radius:7px;background:var(--secondary-background-color);overflow:hidden}
      .gnss-stat small{display:block;font-size:.54rem;opacity:.7;white-space:nowrap}
      .gnss-stat strong{display:block;font-size:.83rem;line-height:1.2;overflow-wrap:anywhere;font-variant-numeric:tabular-nums;margin-top:.14rem}
      .gnss-foot{font-size:.60rem;opacity:.65;line-height:1.35;margin-top:.45rem}
      .gnss-file{font-size:.78rem;font-weight:800;overflow-wrap:anywhere;margin:.25rem 0}
      [data-testid="stFileUploader"] section{min-height:46px!important;padding:.3rem .5rem!important}
      @media(max-width:900px){.gnss-row{flex-wrap:wrap}}
      .eph-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:.65rem;margin-top:.55rem;}
      .eph-card {border:1px solid rgba(127,127,127,.22);border-radius:12px;background:var(--background-color);padding:.55rem .62rem;box-shadow:0 1px 2px rgba(15,23,42,.05);color:var(--text-color);}
      .eph-card-head {display:flex;align-items:center;justify-content:space-between;gap:.45rem;padding-bottom:.35rem;border-bottom:1px solid rgba(127,127,127,.16);margin-bottom:.12rem;}
      .eph-card-title {font-size:.84rem;font-weight:800;color:var(--text-color);line-height:1.15;}
      .eph-card-sub {font-size:.62rem;color:rgba(127,127,127,.92);margin-top:.08rem;}
      .eph-item {display:grid;grid-template-columns:92px minmax(0,1fr) 34px;gap:.42rem;align-items:center;padding:.42rem 0;border-bottom:1px solid rgba(127,127,127,.12);}
      .eph-item:last-child {border-bottom:0;}
      .eph-badge {font-size:.69rem;font-weight:800;color:var(--text-color);}
      .eph-badge small {display:block;font-size:.58rem;font-weight:600;color:rgba(127,127,127,.92);margin-top:.08rem;}
      .eph-file {font-size:.60rem;line-height:1.15;color:rgba(127,127,127,.92);word-break:break-word;}
      .eph-ok {display:inline-block;margin-left:.25rem;width:7px;height:7px;border-radius:50%;background:#22c55e;vertical-align:middle;}
      .eph-muted {font-size:.64rem;color:rgba(127,127,127,.92);padding:.35rem 0;}
      .eph-more {font-size:.69rem;color:#0f766e;font-weight:700;margin-top:.35rem;line-height:1.25;}
      .eph-download {display:inline-flex;align-items:center;justify-content:center;width:32px;height:28px;border:1px solid rgba(127,127,127,.22);border-radius:8px;text-decoration:none;background:var(--secondary-background-color);color:#0f766e;font-size:.88rem;}
      .eph-download:hover {background:rgba(15,118,110,.12);border-color:rgba(15,118,110,.35);}
      .map-legend {font-size:.72rem;color:rgba(127,127,127,.92);margin:.35rem 0 .55rem;}
      .eph-priority {display:inline-flex;align-items:center;gap:.35rem;padding:.22rem .42rem;border-radius:999px;font-size:.63rem;font-weight:800;margin-bottom:.34rem;border:1px solid rgba(127,127,127,.18);background:var(--secondary-background-color);}
      .eph-primary-file {font-size:.67rem;line-height:1.25;margin:.25rem 0 .35rem;color:var(--text-color);}
      .eph-note {font-size:.62rem;line-height:1.25;color:rgba(127,127,127,.92);margin-top:.35rem;}
      .eph-not-found {padding:.55rem .6rem;border-radius:10px;border:1px dashed rgba(127,127,127,.30);background:var(--secondary-background-color);font-size:.67rem;line-height:1.3;color:var(--text-color);}
      @media (max-width: 900px) { .eph-grid {grid-template-columns:1fr;} }
    </style>
    """,
    unsafe_allow_html=True,
)


def card(title, body):
    st.markdown(
        f'<div class="card"><div class="card-title">{title}</div><div class="small">{body}</div></div>',
        unsafe_allow_html=True,
    )


def status(text, kind="ok"):
    st.markdown(f'<div class="{kind}">{text}</div>', unsafe_allow_html=True)


def code_summary(csv_info):
    c_col = (csv_info.columns or {}).get("code")
    if not c_col:
        return "No identificado"
    counts = Counter(
        (r.get(c_col) or "").strip()
        for r in csv_info.rows[1:]
        if (r.get(c_col) or "").strip()
    )
    return " · ".join(f"{c} ({n})" for c, n in counts.most_common(4)) or "No identificado"


def show_help(tool):
    if tool == "Corrector GNSS":
        st.info(
            "CSV y PDF desde el inicio. Revisa el resumen técnico, corrige y descarga archivos "
            "con las mismas columnas del nativo."
        )
    elif tool == "Generador de data":
        st.warning(
            "Genera DATA DERIVADA utilizando el primer CSV como plantilla maestra. "
            "Las alturas estimadas se calculan mediante una red TIN lineal dentro de la envolvente "
            "y mediante IDW como respaldo fuera de ella. No inventa ni altera métricas observadas."
        )
    elif tool == "Certificados":
        st.info(
            "Genera el certificado desde el PUNTO MÓVIL Leica, guarda historial en Google Sheets y permite consultar "
            "puntos certificados y puntos externos en un visor con referencia WGS84."
        )
    else:
        st.info(
            "Verifica productos reales para un día antes, el día de observación y el día siguiente. Prioridad: Final → Rapid → Ultra-Rapid."
        )


def auth_is_configured() -> bool:
    try:
        auth = st.secrets.get("auth")
        if not auth:
            return False
        return bool(auth.get("client_id") and auth.get("client_secret") and auth.get("redirect_uri"))
    except Exception:
        return False


def maybe_require_login():
    if not auth_is_configured():
        return
    if not getattr(st.user, "is_logged_in", False):
        st.markdown('<div style="max-width:520px;margin:10vh auto 0 auto;text-align:center;">', unsafe_allow_html=True)
        if LOGO_PATH.exists():
            st.image(str(LOGO_PATH), width=270)
        st.title("Acceso a CONPLANOS GNSS")
        st.write("Inicia sesión con tu cuenta de Google para entrar a la aplicación.")
        st.button("🔐 INICIAR SESIÓN CON GOOGLE", on_click=st.login, type="primary", use_container_width=True)
        st.caption("La autenticación se realiza mediante Google OIDC y no guarda tu contraseña en CONPLANOS.")
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()
    allowed = st.secrets.get("AUTHORIZED_GOOGLE_EMAILS", "")
    if allowed:
        emails = {x.strip().casefold() for x in str(allowed).split(",") if x.strip()}
        current = str(getattr(st.user, "email", "")).casefold()
        if current not in emails:
            st.error("Esta cuenta de Google no está autorizada para usar CONPLANOS GNSS.")
            st.button("Cerrar sesión", on_click=st.logout)
            st.stop()


def integration_status():
    """Compact status panel for external integrations."""
    items = [
        ("Google Sheets", history_configured()),
        ("Google Drive", drive_configured()),
        ("Login Google", auth_is_configured()),
    ]
    cols = st.columns(len(items))
    for col, (label, ok) in zip(cols, items):
        with col:
            status(("🟢 " if ok else "🟡 ") + label + (" · conectado" if ok else " · pendiente"), "ok" if ok else "warn")


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(a)))


def utm_to_wgs84(e, n, zone, south=True):
    try:
        from pyproj import Transformer
        epsg = 32700 + int(zone) if south else 32600 + int(zone)
        transformer = Transformer.from_crs(epsg, 4326, always_xy=True)
        lon, lat = transformer.transform(float(e), float(n))
        return float(lat), float(lon)
    except Exception:
        return None, None


def cert_record_to_map(r):
    lat = dms_to_decimal(r.get("latitud", ""))
    lon = dms_to_decimal(r.get("longitud", ""))
    if lat is None or lon is None:
        return None
    return {
        **r,
        "lat": lat,
        "lon": lon,
        "tipo_mapa": "Certificado",
        "etiqueta": r.get("codigo", "Punto"),
    }


def external_record_to_map(r):
    try:
        lat = float(r.get("latitud")); lon = float(r.get("longitud"))
    except Exception:
        return None
    return {
        **r,
        "lat": lat,
        "lon": lon,
        "tipo_mapa": "Externo",
        "etiqueta": r.get("codigo") or r.get("nombre") or "Punto externo",
    }


def prompt_manual_column_mapping(file_bytes: bytes, filename: str, key_prefix: str) -> dict[str, str] | None:
    """Displays an interactive column selector when critical columns are ambiguous or unmapped."""
    import csv, io
    from core import _detect_encoding, _detect_delimiter
    try:
        encoding = _detect_encoding(file_bytes)
        text = file_bytes.decode(encoding)
        delimiter = _detect_delimiter(text)
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
        headers = list(reader.fieldnames or [])
    except Exception:
        headers = []

    if not headers:
        return None

    st.warning(f"⚠️ Por favor confirma la asignación de columnas para **{filename}**:")
    cols = st.columns(4)
    overrides = {}

    def candidate(label_sub):
        for h in headers:
            if label_sub.lower() in h.lower():
                return h
        return headers[0]

    with cols[0]:
        overrides["e"] = st.selectbox(f"Este (E) [{filename}]", headers, index=headers.index(candidate("este")) if candidate("este") in headers else 0, key=f"{key_prefix}_e")
    with cols[1]:
        overrides["n"] = st.selectbox(f"Norte (N) [{filename}]", headers, index=headers.index(candidate("norte")) if candidate("norte") in headers else min(1, len(headers)-1), key=f"{key_prefix}_n")
    with cols[2]:
        overrides["h"] = st.selectbox(f"Elevación (H) [{filename}]", headers, index=headers.index(candidate("ele")) if candidate("ele") in headers else min(2, len(headers)-1), key=f"{key_prefix}_h")
    with cols[3]:
        overrides["name"] = st.selectbox(f"Nombre [{filename}]", headers, index=headers.index(candidate("nom")) if candidate("nom") in headers else 0, key=f"{key_prefix}_name")

    return overrides


maybe_require_login()

# ------------------ Sidebar ------------------
with st.sidebar:
    if LOGO_PATH.exists():
        st.markdown('<div class="brand-badge">', unsafe_allow_html=True)
        st.image(str(LOGO_PATH), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
    st.markdown("## 🛰️ CONPLANOS GNSS")
    tool = st.radio(
        "Herramienta",
        ["Corrector GNSS", "Generador de data", "Certificados", "Efemérides precisas"],
        label_visibility="collapsed",
    )
    st.divider()

    st.markdown("### Ayuda")
    with st.expander("¿Qué hace esta herramienta?", expanded=tool != "Corrector GNSS"):
        show_help(tool)

    with st.expander("Versiones", expanded=False):
        st.markdown(
            f"""
            **V10.6 · Plantilla Maestra Nativa + mapeo semántico universal flexible + preservación de encabezados/orden original + soporte para cualquier fabricante (Trimble, CHC, Leica, South, Emlid, etc.).**

            **V10.5 · CSV nativo adaptable + Efemérides verificadas por disponibilidad real + prioridad Final → Rapid → Ultra-Rapid + modo oscuro.**

            **V9.1 · Corrección de arranque + placa oficial CONPLANOS como respaldo + código y año dinámicos.**

            **V8 · Múltiples archivos + descargas persistentes + lectura inteligente E/N + TIN de alturas + visor WGS84 + login Google.**

            **V7 · Efemérides + historial Google Sheets + mapa.**

            **V6 · Punto móvil Leica + extracción automática.**

            **V5 · Menú profesional + certificado.**

            **V4 · Generador de data derivada.**

            **V3 · Interfaz compacta.**

            **V2 · Informe Leica + control de alturas.**

            **V1 · Corrección CSV + coordenadas.**
            """
        )

    if auth_is_configured() and getattr(st.user, "is_logged_in", False):
        st.caption(f"👤 {getattr(st.user, 'name', '') or getattr(st.user, 'email', '')}")
        st.button("Cerrar sesión", on_click=st.logout, use_container_width=True)
    st.caption(f"CONPLANOS GNSS · versión {VERSION}")
    st.caption("🎨 Tema claro/oscuro: ⋮ → Settings → Theme")

if tool != "Corrector GNSS":
    st.markdown('<div class="app-title">🛰️ CONPLANOS - Herramientas GNSS</div>', unsafe_allow_html=True)
    integration_status()

# ========================================================
# Corrector GNSS
# ========================================================
if tool == "Corrector GNSS":
    from gnss_corrector_ui import render_corrector
    render_corrector()


# ========================================================
# Generador de data
# ========================================================
elif tool == "Generador de data":
    left, right = st.columns([2.25, 1.0], gap="large")
    with left:
        st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
        st.subheader("Sube una o varias datas nativas matriz")
        gen_native_uploads = st.file_uploader(
            "CSV nativos matriz", type=["csv"], accept_multiple_files=True,
            label_visibility="collapsed", key="generator_native_v8",
            help="El primer CSV actuará como plantilla maestra."
        )
    if not gen_native_uploads:
        st.info("Sube una o varias datas nativas para comenzar.")
    else:
        gen_infos = []
        for idx, f in enumerate(gen_native_uploads):
            raw = f.getvalue()
            try:
                overrides = st.session_state.get(f"gen_col_override_{idx}")
                csv_i = read_csv(raw, column_overrides=overrides)
                gen_infos.append((f.name, csv_i))
            except ValueError as exc:
                if "columnas críticas" in str(exc).lower():
                    overrides = prompt_manual_column_mapping(raw, f.name, f"gen_map_{idx}")
                    if overrides:
                        st.session_state[f"gen_col_override_{idx}"] = overrides
                        try:
                            csv_i = read_csv(raw, column_overrides=overrides)
                            gen_infos.append((f.name, csv_i))
                        except Exception as ex2:
                            status(f"🔴 {f.name}: {ex2}", "bad")
                else:
                    status(f"🔴 {f.name}: {exc}", "bad")
            except Exception as exc:
                status(f"🔴 {f.name}: {exc}", "bad")

        if not gen_infos:
            st.stop()
        base_names = [i.base_name for _, i in gen_infos]
        same_base = len({x.casefold() for x in base_names}) == 1
        with right:
            card(
                "📋 Plantilla Maestra (Matriz)",
                f"<b>{gen_infos[0][0]}</b><br>"
                f"Bases: {len(gen_infos)} · Filas plantilla: {len(gen_infos[0][1].rows)}<br>"
                f"Base principal: <b>{gen_infos[0][1].base_name}</b>"
            )
            status("🟢 Base común lista para unir." if same_base else "🔴 Bases diferentes: no se generará un único proyecto.", "ok" if same_base else "bad")
        with st.expander("📍 Ver coordenadas de las bases", expanded=True):
            for n, i in gen_infos:
                st.markdown(
                    f'<div class="card" style="border:2px solid #0f766e;background:#f0fdfa;">'
                    f'<div class="card-title">{n} · BASE {i.base_name}</div>'
                    f'<div class="small"><b>E:</b> {i.base_original_e:.4f} m &nbsp; <b>N:</b> {i.base_original_n:.4f} m &nbsp; <b>H:</b> {i.base_original_h:.4f} m</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
        st.subheader("Sube las coordenadas finales del plano")
        st.caption("Admite CSV, Excel, PDF, memoria descriptiva DOCX y PDF, JPG/PNG/WebP. Puedes subir varios archivos; la aplicación intentará identificar automáticamente Este/E y Norte/N.")
        plan_uploads = st.file_uploader(
            "Fuentes de coordenadas", type=["csv", "xlsx", "xlsm", "pdf", "docx", "png", "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
            accept_multiple_files=True, label_visibility="collapsed", key="generator_plan_v8",
        )
        if not plan_uploads:
            st.info("Sube al menos un archivo de coordenadas del plano.")
        else:
            sources = [(f.name, f.getvalue()) for f in plan_uploads]
            points, diagnostics = extract_coordinate_sources(sources)
            st.dataframe(diagnostics, use_container_width=True, hide_index=True)
            valid_points = [p for p in points if p.e is not None and p.n is not None]
            st.markdown("**Coordenadas interpretadas por CONPLANOS**")
            st.dataframe(
                [
                    {"Fuente": p.source or "—", "Nombre detectado": p.name or "—", "Este (E)": round(p.e, 4), "Norte (N)": round(p.n, 4), "Zona": p.zone or "—"}
                    for p in valid_points
                ],
                use_container_width=True, hide_index=True,
            )
            t1, t2, t3 = st.columns(3)
            t1.metric("Coordenadas leídas", len(valid_points))
            tolerance = t2.number_input(
                "Tolerancia de coincidencia (m)", min_value=0.0, max_value=1.0, value=0.0000,
                step=0.001, format="%.4f", key="gen_tol_v8",
                help="0.0000 exige coincidencia exacta según los valores numéricos disponibles."
            )
            neighbors = t3.number_input("Vecinos IDW de respaldo", min_value=3, max_value=16, value=6, step=1, key="gen_neighbors_v8")

            with right:
                card("🧩 Regla de generación", "🟢 Coincidente → conserva fila nativa.<br>🔵 Nueva → E/N del plano + H interpolada.<br>🛰️ Base → siempre primera y única.<br>🔢 Punto 1, 2, 3… → secuencia continua.<br>📡 Observación → 60 (si existe en la plantilla).<br>📋 Método de encuesta → Topográfico (si existe).")
                card("⛰️ Naturaleza estimada de datos", "Dentro de la envolvente de los puntos nativos se usa una red TIN (Delaunay) e interpolación lineal. Fuera de esa envolvente se usa IDW como respaldo.<br><b>Atención:</b> Las alturas son estimadas matemáticamente. Los parámetros observados (PDOP, RMS, precisiones) se mantienen vacíos en puntos sintéticos.")

            st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
            if st.button("🧩 GENERAR DATA DERIVADA", type="primary", use_container_width=True, key="generate_data_v8"):
                if not same_base:
                    st.error("Para generar un único proyecto debes usar una sola base común en las datas nativas.")
                else:
                    try:
                        native_raws = [f.getvalue() for f in gen_native_uploads]
                        native_joined, _ = merge_csv_payloads(native_raws, require_same_base=True)
                        combined_info = read_csv(native_joined)
                        out, summary = generate_derived_data(
                            combined_info, valid_points,
                            match_tolerance_m=float(tolerance), idw_neighbors=int(neighbors)
                        )
                        by_source = defaultdict(list)
                        for p in valid_points:
                            by_source[p.source or "Coordenadas"].append(p)
                        separate = []
                        for src, pts in by_source.items():
                            b, s = generate_derived_data(combined_info, pts, match_tolerance_m=float(tolerance), idw_neighbors=int(neighbors))
                            safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(src).stem)[:70]
                            separate.append((safe, b, generated_data_filename(safe + ".csv"), s))
                        native_joined_updated, _ = native_updated(combined_info)
                        package = [("DATA_GENERADA_UNIDA.csv", out), ("NATIVA_ACTUALIZADA_UNIDA.csv", native_joined_updated)]
                        package.extend((f"SEPARADO_{name}.csv", b) for name, b, _, _ in separate)
                        st.session_state["generator_result_v8"] = {
                            "out": out,
                            "summary": summary,
                            "separate": separate,
                            "native": native_joined_updated,
                            "package": zip_artifacts(package),
                        }
                        st.success("✅ Data derivada generada. Las descargas quedaron persistentes.")
                    except Exception as exc:
                        st.error(f"No se pudo generar la data derivada: {exc}")

            result = st.session_state.get("generator_result_v8")
            if result:
                s = result["summary"]
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Entrada", s["input_points"])
                c2.metric("Coincidentes", s["matched_points"])
                c3.metric("Nuevos", s["generated_points"])
                c4.metric("Dist. media", f"{s['mean_nearest_distance_m']:.4f} m")
                st.caption("Métodos de altura: " + ", ".join(f"{k}: {v}" for k, v in s.get("interpolation_methods", {}).items()) if s.get("interpolation_methods") else "No hubo puntos nuevos que interpolar.")
                db1, db2, db3 = st.columns(3)
                db1.download_button("⬇️ DATA GENERADA UNIDA", result["out"], file_name="CONPLANOS_DATA_GENERADA_UNIDA.csv", mime="text/csv", use_container_width=True, on_click="ignore", key="gen_union_v8")
                db2.download_button("⬇️ NATIVA ACTUALIZADA UNIDA", result["native"], file_name="CONPLANOS_NATIVA_ACTUALIZADA_UNIDA.csv", mime="text/csv", use_container_width=True, on_click="ignore", key="gen_native_v8")
                db3.download_button("📦 DESCARGAR TODO (ZIP)", result["package"], file_name="CONPLANOS_GENERADOR_RESULTADOS.zip", mime="application/zip", use_container_width=True, on_click="ignore", key="gen_zip_v8")
                if result["separate"]:
                    st.markdown('<div class="download-head">📥 Resultados separados por archivo/fuente</div>', unsafe_allow_html=True)
                    for idx, (name, b, _, ss) in enumerate(result["separate"]):
                        st.download_button(f"⬇️ {name}", b, file_name=f"{name}_DATA_GENERADA.csv", mime="text/csv", use_container_width=True, on_click="ignore", key=f"gen_sep_{idx}_v8")
                if st.button("🧹 Limpiar resultados del generador", key="clear_gen_v8"):
                    st.session_state.pop("generator_result_v8", None)
                    st.rerun()

# ========================================================
# Certificados
# ========================================================
elif tool == "Certificados":
    st.subheader("📜 Certificados de punto geodésico")
    tab_gen, tab_hist = st.tabs(["📜 Generar certificado", "🗺️ Historial y mapa"])

    with tab_gen:
        left, right = st.columns([2.0, 1.05], gap="large")
        defaults = today_defaults()
        report_file = None
        data = None
        report = None
        with left:
            st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
            st.subheader("Sube el informe de procesamiento Leica")
            report_file = st.file_uploader("Informe de Procesamiento GNSS", type=["pdf"], key="certificate_pdf_v8")
            if not report_file:
                st.info("El certificado toma exclusivamente los datos técnicos del PUNTO MÓVIL.")
            else:
                try:
                    report = parse_report_pdfs([(report_file.name, report_file.getvalue())])
                    data = extract_certificate_data(report, defaults)
                except Exception as exc:
                    st.error(f"No se pudo extraer el informe Leica: {exc}")
                    st.stop()
                missing = [label for label, value in [
                    ("Norte", data.norte), ("Este", data.este), ("Zona", data.zona),
                    ("Latitud", data.latitud), ("Longitud", data.longitud),
                    ("Alt. elipsoidal", data.alt_ellipsoidal), ("Estación GNSS", data.estacion_gnss),
                    ("Fecha de posicionamiento", data.fecha_posicion),
                ] if not str(value).strip()]
                if missing:
                    st.error("Faltan datos técnicos del informe: " + ", ".join(missing))
                    st.stop()
                status("🟢 Datos técnicos del PUNTO MÓVIL extraídos automáticamente.", "ok")
                card("📍 Coordenadas certificadas", f"<b>N:</b> {data.norte} m · <b>E:</b> {data.este} m · <b>Zona:</b> {data.zona}<br><b>Lat:</b> {data.latitud} · <b>Lon:</b> {data.longitud}<br><b>H elipsoidal:</b> {data.alt_ellipsoidal} m")

                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Datos manuales obligatorios")
                st.warning("Código del punto y Solicitante son los únicos datos que debes ingresar manualmente.")
                data.codigo = st.text_input("Código del punto geodésico *", key="cert_codigo_v8")
                data.solicitante = st.text_input("Solicitante *", key="cert_solicitante_v8")
                st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
                image_file = st.file_uploader("Fotografía de la placa/punto (opcional)", type=["png", "jpg", "jpeg"], key="certificate_img_v9", help="Si no adjuntas una fotografía, se usará automáticamente la placa oficial de referencia CONPLANOS y se reemplazarán el código y el año.")
                if image_file:
                    st.image(image_file, width=260)
                else:
                    st.info("Sin fotografía: se usará automáticamente la placa oficial CONPLANOS, cambiando solo el código del punto y el año.")
                st.markdown('<div class="step">PASO 4</div>', unsafe_allow_html=True)
                if st.button("📜 GENERAR CERTIFICADO PDF + WORD", type="primary", use_container_width=True, key="cert_generate_v8"):
                    if not data.codigo.strip() or not data.solicitante.strip():
                        st.error("Debes ingresar el Código y el Solicitante.")
                    else:
                        if not data.correlativo:
                            data.correlativo = f"CP-{data.anio}-{data.codigo.strip().upper()}"
                        tmpdir = Path(tempfile.mkdtemp(prefix="conplanos_cert_"))
                        try:
                            if image_file:
                                image_path = tmpdir / "punto.png"; image_path.write_bytes(image_file.getvalue())
                            else:
                                image_path = make_plaque(data.codigo, tmpdir / "placa_generada.png", template_path=TEMPLATES_DIR / "plaque_generada_template.png", year=data.anio)
                            docx_path = tmpdir / f"Certificado_{data.codigo.strip()}.docx"
                            pdf_path = tmpdir / f"Certificado_{data.codigo.strip()}.pdf"
                            generate_certificate_docx(data, image_path, TEMPLATES_DIR / "certificado_punto_geodesico_template.docx", docx_path)
                            generate_certificate_pdf(data, image_path, TEMPLATES_DIR / "certificate_template.pdf", pdf_path)
                            pdf_bytes = pdf_path.read_bytes()
                            docx_bytes = docx_path.read_bytes()
                            record = make_record(data, report, report_file.name, pdf_path.name, docx_path.name)
                            drive_info = {"pdf": "", "word": "", "folder": ""}
                            if drive_configured():
                                try:
                                    up_pdf = drive_upload_bytes(pdf_bytes, pdf_path.name, "application/pdf")
                                    up_docx = drive_upload_bytes(docx_bytes, docx_path.name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                                    drive_info = {"pdf": up_pdf.get("url", ""), "word": up_docx.get("url", ""), "folder": "CONPLANOS GNSS - CERTIFICADOS"}
                                    record["drive_pdf"] = drive_info["pdf"]
                                    record["drive_word"] = drive_info["word"]
                                    record["drive_carpeta"] = drive_info["folder"]
                                except Exception as exc:
                                    st.warning(f"📁 Certificado generado, pero Google Drive no pudo guardar los archivos: {exc}")
                            st.session_state["certificate_output_v8"] = {
                                "pdf": pdf_bytes, "pdf_name": pdf_path.name,
                                "docx": docx_bytes, "docx_name": docx_path.name,
                                "record": record, "drive": drive_info,
                            }
                            st.session_state.setdefault("cert_session_records_v8", []).append(record)
                            if history_configured():
                                try:
                                    append_point(record)
                                    if drive_info["pdf"] and drive_info["word"]:
                                        st.success("✅ Certificado generado, guardado en Google Drive y registrado en Google Sheets.")
                                    else:
                                        st.success("✅ Certificado generado y registrado en Google Sheets.")
                                except Exception as exc:
                                    st.warning(f"✅ Certificado generado, pero Google Sheets no pudo guardar el registro: {exc}")
                            else:
                                st.success("✅ Certificado generado. Google Sheets todavía no está configurado.")
                        except Exception as exc:
                            st.error(f"No se pudo generar el certificado: {exc}")

                output = st.session_state.get("certificate_output_v8")
                if output:
                    st.markdown('<div class="download-head">📥 Descargas del certificado</div>', unsafe_allow_html=True)
                    c1, c2 = st.columns(2)
                    c1.download_button("⬇️ Descargar CERTIFICADO PDF", output["pdf"], file_name=output["pdf_name"], mime="application/pdf", use_container_width=True, on_click="ignore", key="cert_pdf_dl_v8")
                    c2.download_button("⬇️ Descargar WORD editable", output["docx"], file_name=output["docx_name"], mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True, on_click="ignore", key="cert_docx_dl_v8")
                    drive_info = output.get("drive", {})
                    if drive_info.get("pdf") or drive_info.get("word"):
                        st.markdown("**☁️ Archivos guardados en Google Drive**")
                        d1, d2 = st.columns(2)
                        if drive_info.get("pdf"):
                            d1.link_button("📄 Abrir PDF en Drive", drive_info["pdf"], use_container_width=True)
                        if drive_info.get("word"):
                            d2.link_button("📝 Abrir Word en Drive", drive_info["word"], use_container_width=True)
        with right:
            card("📌 Regla del certificado", "El certificado corresponde al <b>PUNTO MÓVIL</b>. La estación de referencia no se certifica.")
            card("🤖 Automático", "Norte · Este · Zona · Latitud · Longitud · H elipsoidal · Estación GNSS · Fecha de posicionamiento · Año")
            card("✍️ Manual", "Código del punto geodésico · Solicitante")
            card("☁️ Historial", "Google Sheets guarda el registro técnico. Si no está configurado, la sesión mantiene el historial local.")

    with tab_hist:
        st.markdown('<div class="step">VISOR DE PUNTOS</div>', unsafe_allow_html=True)
        cert_records = st.session_state.get("cert_session_records_v8", [])
        ext_records = st.session_state.get("external_session_records_v8", [])
        if history_configured():
            try:
                cert_records = load_points() or cert_records
                ext_records = load_external_points() or ext_records
            except Exception as exc:
                status(f"🟡 Google Sheets: {exc}", "warn")

        map_points = []
        for r in cert_records:
            p = cert_record_to_map(r)
            if p:
                map_points.append(p)
        for r in ext_records:
            p = external_record_to_map(r)
            if p:
                map_points.append(p)

        # ---------------- Search / locate ----------------
        search_left, search_right = st.columns([1.7, 1.15], gap="large")
        with search_left:
            st.markdown("**🎯 Buscar por coordenadas WGS84 / UTM**")
            a1, a2, a3 = st.columns([1.15, 1.15, .72])
            e_text = a1.text_input("Este (E)", placeholder="Ej. 180000.1234", key="map_utm_e_v10")
            n_text = a2.text_input("Norte (N)", placeholder="Ej. 8550000.5678", key="map_utm_n_v10")
            zone = a3.number_input("Zona", min_value=1, max_value=60, value=18, step=1, key="map_utm_zone_v10")
            hemi = a3.selectbox("Hemisferio", ["Sur", "Norte"], index=0, key="map_utm_hemi_v10")
            if st.button("🎯 UBICAR Y BUSCAR PUNTO MÁS CERCANO", type="primary", key="map_find_nearest_v10", use_container_width=True):
                try:
                    e_val = float(str(e_text).replace(",", "").strip())
                    n_val = float(str(n_text).replace(",", "").strip())
                    target_lat, target_lon = utm_to_wgs84(e_val, n_val, int(zone), south=(hemi == "Sur"))
                    if target_lat is None or target_lon is None:
                        raise ValueError("No se pudo convertir la coordenada UTM a WGS84.")
                    st.session_state["map_target_utm_v10"] = {"e": e_val, "n": n_val, "zone": int(zone), "hemi": hemi}
                    st.session_state["map_target_wgs84_v10"] = (target_lat, target_lon)
                    st.session_state["map_nearest_result_v10"] = None
                    if map_points:
                        nearest = min(map_points, key=lambda q: haversine_m(target_lat, target_lon, q["lat"], q["lon"]))
                        distance = haversine_m(target_lat, target_lon, nearest["lat"], nearest["lon"])
                        st.session_state["map_nearest_result_v10"] = (nearest, distance)
                    st.session_state["map_view_version_v10"] = st.session_state.get("map_view_version_v10", 0) + 1
                except Exception as exc:
                    st.error(f"Revisa E, N y zona UTM: {exc}")

        with search_right:
            st.markdown("**📍 Historial geodésico**")
            st.caption("Usa las coordenadas UTM para buscar puntos dentro del visor de CONPLANOS.")
            if history_configured():
                st.success(f"☁️ Historial permanente conectado · {len(cert_records)} certificados · {len(ext_records)} puntos externos")
            else:
                st.warning("☁️ Google Sheets no está configurado: el historial se conserva solo durante esta sesión.")

        nearest_data = st.session_state.get("map_nearest_result_v10")
        target_wgs = st.session_state.get("map_target_wgs84_v10")
        if nearest_data and target_wgs:
            nearest, dist = nearest_data
            status(f"📍 <b>{nearest.get('etiqueta','Punto')}</b> es el punto más cercano · distancia horizontal aproximada: <b>{dist:.2f} m</b>.", "ok")
            u = st.session_state.get("map_target_utm_v10", {})
            st.caption(f"Objetivo UTM WGS84: E {u.get('e','—'):.4f} · N {u.get('n','—'):.4f} · Zona {u.get('zone','—')} {u.get('hemi','')}")

        # ---------------- Register external points ----------------
        with st.expander("📌 Registrar otros puntos geodésicos desde documentos", expanded=False):
            ext_uploads = st.file_uploader(
                "Sube uno o varios PDF/DOCX/CSV/Excel de otros puntos geodésicos",
                type=["pdf", "docx", "csv", "xlsx", "xlsm"],
                accept_multiple_files=True, key="external_points_upload_v10",
                help="La app intentará tomar el punto móvil Leica o pares UTM E/N. Para UTM sin zona usa la zona por defecto."
            )
            default_zone = st.number_input("Zona UTM por defecto", min_value=1, max_value=60, value=18, step=1, key="external_zone_v10")
            if ext_uploads:
                points, diagnostics = extract_coordinate_sources([(f.name, f.getvalue()) for f in ext_uploads])
                st.dataframe(diagnostics, use_container_width=True, hide_index=True)
                external_pending = []
                for i, q in enumerate(points, start=1):
                    if q.e is None or q.n is None:
                        continue
                    z = q.zone or int(default_zone)
                    lat, lon = utm_to_wgs84(q.e, q.n, z, south=True)
                    if lat is None:
                        continue
                    code = q.name or f"EXT-{i:03d}"
                    external_pending.append(make_external_record(
                        codigo=code, nombre=q.name or code, norte=q.n, este=q.e,
                        zona=f"{z} Sur", latitud=lat, longitud=lon,
                        fuente=q.source or "Archivo", observacion="Extraído automáticamente. Verificar antes de usar como referencia oficial."
                    ))
                if external_pending:
                    st.dataframe(external_pending, use_container_width=True, hide_index=True)
                    if st.button("📌 REGISTRAR ESTOS PUNTOS EN EL VISOR", key="register_external_v10", type="primary"):
                        st.session_state.setdefault("external_session_records_v8", []).extend(external_pending)
                        if history_configured():
                            try:
                                append_external_points(external_pending)
                                st.success("✅ Puntos registrados en OtrosPuntos de Google Sheets.")
                            except Exception as exc:
                                st.warning(f"Los puntos quedaron en la sesión, pero no se pudieron guardar en Google Sheets: {exc}")
                        else:
                            st.success("✅ Puntos registrados en esta sesión. Configura Google Sheets para conservarlos.")

        # ---------------- Professional map ----------------
        if not map_points:
            st.info("Todavía no hay puntos con coordenadas geográficas válidas. Genera un certificado o registra otros puntos.")
        else:
            import pydeck as pdk
            target = target_wgs
            nearest = nearest_data[0] if nearest_data else None
            cert_data = [p for p in map_points if p.get("tipo_mapa") == "Certificado"]
            ext_data = [p for p in map_points if p.get("tipo_mapa") == "Externo"]
            nearest_data_list = [nearest] if nearest else []
            target_data = [{"lat": target[0], "lon": target[1], "etiqueta": "COORDENADA OBJETIVO"}] if target else []

            layers = []
            if cert_data:
                layers.append(pdk.Layer(
                    "ScatterplotLayer", data=cert_data, id="certificados", get_position="[lon, lat]",
                    get_fill_color=[15,118,110,220], get_line_color=[255,255,255,230], get_line_width=2,
                    get_radius=55, radius_min_pixels=5, radius_max_pixels=12, pickable=True, auto_highlight=True,
                ))
            if ext_data:
                layers.append(pdk.Layer(
                    "ScatterplotLayer", data=ext_data, id="puntos-externos", get_position="[lon, lat]",
                    get_fill_color=[245,158,11,220], get_line_color=[255,255,255,230], get_line_width=2,
                    get_radius=55, radius_min_pixels=5, radius_max_pixels=12, pickable=True, auto_highlight=True,
                ))
            if nearest_data_list:
                layers.append(pdk.Layer(
                    "ScatterplotLayer", data=nearest_data_list, id="punto-mas-cercano", get_position="[lon, lat]",
                    get_fill_color=[220,38,38,245], get_line_color=[255,255,255,255], get_line_width=3,
                    get_radius=120, radius_min_pixels=10, radius_max_pixels=22, pickable=True,
                ))
            if target_data:
                layers.append(pdk.Layer(
                    "ScatterplotLayer", data=target_data, id="objetivo", get_position="[lon, lat]",
                    get_fill_color=[37,99,235,80], get_line_color=[37,99,235,255], get_line_width=3,
                    get_radius=140, radius_min_pixels=13, radius_max_pixels=28, pickable=False,
                ))
            labels = cert_data + ext_data
            if labels:
                layers.append(pdk.Layer(
                    "TextLayer", data=labels, id="etiquetas-puntos", get_position="[lon, lat]", get_text="etiqueta",
                    get_size=13, get_color=[31,41,55], get_pixel_offset=[0,-18], pickable=False,
                ))

            if target:
                center_lat, center_lon = (nearest["lat"], nearest["lon"]) if nearest else target
                zoom = 17 if nearest else 14
            else:
                center = map_points[0]
                center_lat, center_lon, zoom = center["lat"], center["lon"], 12

            map_key = f"cert_map_v10_{st.session_state.get('map_view_version_v10', 0)}"
            deck = pdk.Deck(
                layers=layers,
                initial_view_state=pdk.ViewState(latitude=float(center_lat), longitude=float(center_lon), zoom=zoom, min_zoom=4, max_zoom=20, pitch=0),
                tooltip={"html": "<b>{etiqueta}</b><br/>{tipo_mapa}<br/>Lat: {lat}<br/>Lon: {lon}<br/>N: {norte}<br/>E: {este}<br/>Zona: {zona}"},
                map_style=None,
            )
            st.markdown('<div class="map-legend">🟢 Certificados · 🟠 Otros puntos · 🔴 Punto más cercano · 🔵 Coordenada objetivo · Haz clic en cualquier punto para ver su ficha.</div>', unsafe_allow_html=True)
            event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key=map_key)
            selected = None
            try:
                for layer_id in ("certificados", "puntos-externos", "punto-mas-cercano"):
                    objs = event.selection.objects.get(layer_id, [])
                    if objs:
                        selected = objs[0]
                        break
            except Exception:
                pass
            if selected:
                st.markdown(f"### 📍 {selected.get('etiqueta', 'Punto')}")
                a, b, c = st.columns(3)
                a.metric("Latitud", f"{float(selected.get('lat', 0)):.8f}")
                b.metric("Longitud", f"{float(selected.get('lon', 0)):.8f}")
                c.metric("Tipo", selected.get("tipo_mapa", "—"))
                if selected.get("tipo_mapa") == "Certificado":
                    card("Ficha del certificado", f"Código: <b>{selected.get('codigo','—')}</b><br>Solicitante: {selected.get('solicitante','—')}<br>N: {selected.get('norte','—')} m · E: {selected.get('este','—')} m<br>Zona: {selected.get('zona','—')}<br>H elipsoidal: {selected.get('alt_ellipsoidal','—')} m<br>Estación: {selected.get('estacion_gnss','—')}<br>Fecha posición: {selected.get('fecha_posicion','—')}")
                else:
                    card("Ficha del punto externo", f"Código: <b>{selected.get('codigo','—')}</b><br>Fuente: {selected.get('fuente','—')}<br>N: {selected.get('norte','—')} m · E: {selected.get('este','—')} m<br>Zona: {selected.get('zona','—')}<br>Observación: {selected.get('observacion','—')}")

# ========================================================
# Efemérides
# ========================================================
elif tool == "Efemérides precisas":
    st.subheader("📡 Efemérides precisas")
    st.caption("Verificación real de disponibilidad · sin inventar enlaces · prioridad Final → Rapid → Ultra-Rapid")

    c_date, c_btn = st.columns([1.25, .75], vertical_alignment="bottom")
    with c_date:
        target = st.date_input("Fecha de lectura", value=today_lima(), key="eph_date_v104", format="DD/MM/YYYY")
    with c_btn:
        search = st.button("🔎 BUSCAR EFEMÉRIDES", type="primary", use_container_width=True, key="search_eph_v104")

    if search:
        results = {}
        days_to_check = [target + timedelta(days=delta) for delta in (-1, 0, 1)]
        with st.spinner("Verificando Final → Rapid → Ultra-Rapid en fuentes oficiales…"):
            with ThreadPoolExecutor(max_workers=3) as ex:
                futures = {ex.submit(find_best_for_day, d, True): d for d in days_to_check}
                for fut in as_completed(futures):
                    d = futures[fut]
                    try:
                        best, alternatives = fut.result()
                    except Exception as exc:
                        best, alternatives = None, []
                    results[d] = {"best": best, "alternatives": alternatives}
        st.session_state["eph_results_v104"] = results
        st.session_state["eph_target_v104"] = target
        st.session_state["eph_checked_utc_v104"] = now_utc().isoformat()

    results = st.session_state.get("eph_results_v104")
    eph_target = st.session_state.get("eph_target_v104", target)
    if results:
        checked_utc = st.session_state.get("eph_checked_utc_v104")
        try:
            checked = datetime.fromisoformat(checked_utc).astimezone(ZoneInfo("America/Lima")) if checked_utc else now_lima()
            checked_text = checked.strftime("%d/%m/%Y %H:%M")
        except Exception:
            checked_text = now_lima().strftime("%d/%m/%Y %H:%M")

        st.markdown(
            '<div class="neutral" style="margin:.35rem 0 .55rem 0;display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;">'
            '<b>Regla:</b> Final → Rapid → Ultra-Rapid &nbsp;·&nbsp; <span>La aplicación solo muestra un producto si verificó que el archivo real responde.</span></div>',
            unsafe_allow_html=True,
        )

        cards = []
        for delta, label in zip((-1, 0, 1), ("DÍA ANTERIOR", "DÍA DE LECTURA", "DÍA SIGUIENTE")):
            d = eph_target + timedelta(days=delta)
            item = results.get(d, {})
            best = item.get("best")
            alternatives = item.get("alternatives", [])

            if best is None:
                body = (
                    f'<div class="eph-not-found"><b>Sin producto verificado.</b><br>'
                    f'No se encontró un Final, Rapid o Ultra-Rapid disponible para {d.strftime("%d/%m/%Y")} en este momento.<br>'
                    f'Esto no significa que el producto nunca exista; solo que aún no fue verificado como disponible.</div>'
                )
            else:
                kind_label = {"Final": "🟢 FINAL · PRIORIDAD 1", "Rapid": "🟡 RAPID · PRIORIDAD 2", "Ultra-Rapid": "🔵 ULTRA-RAPID · PRIORIDAD 3"}.get(best.kind, best.kind)
                note = best.note or "Producto verificado en el archivo oficial."
                body = (
                    f'<div class="eph-priority">{kind_label}</div>'
                    f'<div style="font-weight:800;font-size:.78rem;">{best.label}</div>'
                    f'<div class="eph-primary-file" title="{best.filename}"><b>Archivo:</b> {best.filename}</div>'
                )
                if best.kind == "Ultra-Rapid" and "predicha" in note.lower():
                    body += '<div class="eph-note">⚠️ Para esta fecha la cobertura es <b>predicha</b>. La Ultra-Rapid está diseñada para cubrir tiempo futuro; no es una efeméride Final ni Rapid.</div>'
                else:
                    body += f'<div class="eph-note">{note}</div>'
                body += f'<a class="eph-download" style="width:100%;margin-top:.42rem;" href="{best.url}" target="_blank" rel="noopener noreferrer">⬇ Descargar producto oficial</a>'

                alt_available = [p for p in alternatives if p.status == "Disponible" and p.url and p.filename != best.filename]
                if alt_available:
                    body += f'<div class="eph-note">También hay {len(alt_available)} alternativa(s) verificadas del mismo rango de producto. Se muestran al desplegar “Alternativas”.</div>'

            cards.append(
                f'<div class="eph-card"><div class="eph-card-head"><div>'
                f'<div class="eph-card-title">📅 {d.strftime("%d/%m/%Y")}</div>'
                f'<div class="eph-card-sub">{label}</div></div></div>{body}</div>'
            )
        st.markdown('<div class="eph-grid">' + ''.join(cards) + '</div>', unsafe_allow_html=True)

        with st.expander("🔎 Ver alternativas oficiales verificadas", expanded=False):
            any_alt = False
            for delta, label in zip((-1, 0, 1), ("Día anterior", "Día de lectura", "Día siguiente")):
                d = eph_target + timedelta(days=delta)
                item = results.get(d, {})
                best = item.get("best")
                alternatives = item.get("alternatives", [])
                alt_available = [p for p in alternatives if p.status == "Disponible" and p.url and (not best or p.filename != best.filename)]
                if alt_available:
                    any_alt = True
                    st.markdown(f"**{label} · {d.strftime('%d/%m/%Y')}**")
                    for p in alt_available:
                        cols = st.columns([1.1, 3.1, .8], vertical_alignment="center")
                        cols[0].markdown(f"**{p.source}** · {p.kind}")
                        cols[1].caption(p.filename)
                        cols[2].link_button("⬇", p.url, use_container_width=True)
            if not any_alt:
                st.caption("No hay alternativas adicionales verificadas en este momento.")

        st.caption(
            f"Verificación realizada en tiempo real: {checked_text} (hora Perú). "
            "La Ultra-Rapid puede contener una parte observada y otra predicha; la Final/Rapid no se muestran antes de su liberación."
        )
        st.markdown(
            '[Fuente oficial IGS](https://www.igs.org/products/) · '
            '[Fuente oficial ESA GNSS Products](https://navigation-office.esa.int/GNSS_based_products.html)',
        )

# ------------------ Footer ------------------
st.markdown(
    f'<div class="brand-footer">Creado por <b>Ing Chris</b> · <b>CONPLANOS</b> · 928 400 600 · Herramientas GNSS · v{VERSION}</div>',
    unsafe_allow_html=True,
)
