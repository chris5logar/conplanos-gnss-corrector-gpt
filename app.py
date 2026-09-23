from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
import tempfile
import os

import streamlit as st

from core import (
    apply_correction,
    choose_height,
    corrected_filename,
    csv_point_quality_summary,
    generated_data_filename,
    generate_derived_data,
    parse_report_pdfs,
    polygon_filename,
    read_coordinate_points,
    read_csv,
)

from ephemeris import find_products, group_by_day
from history import configured as history_configured, append_point, load_points, make_record, dms_to_decimal

from certificate import (
    CertificateData,
    extract_certificate_data,
    generate_certificate_docx,
    generate_certificate_pdf,
    make_plaque,
    today_defaults,
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"


st.set_page_config(
    page_title="CONPLANOS - Herramientas GNSS",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top:.7rem;padding-bottom:.8rem;max-width:1500px;}
      .small {font-size:.76rem;line-height:1.35;}
      .tiny {font-size:.66rem;line-height:1.25;color:#6b7280;}
      .card {border:1px solid #e5e7eb;border-radius:12px;padding:.60rem .72rem;margin-bottom:.48rem;background:#fff;}
      .card-title {font-size:.82rem;font-weight:700;margin-bottom:.28rem;}
      .ok,.warn,.bad,.neutral {border-radius:8px;padding:.36rem .48rem;margin:.16rem 0;font-size:.72rem;line-height:1.28;}
      .ok {color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;}
      .warn {color:#92400e;background:#fffbeb;border:1px solid #fde68a;}
      .bad {color:#991b1b;background:#fef2f2;border:1px solid #fecaca;}
      .neutral {color:#374151;background:#f9fafb;border:1px solid #e5e7eb;}
      .step {font-size:.70rem;color:#6b7280;margin-bottom:.08rem;text-transform:uppercase;letter-spacing:.03em;}
      .app-title {font-size:1.62rem;font-weight:800;margin-bottom:.0rem;}
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
    counts = Counter(
        (r.get("Código") or "").strip()
        for r in csv_info.rows[1:]
        if (r.get("Código") or "").strip()
    )
    return " · ".join(f"{c} ({n})" for c,n in counts.most_common(4)) or "No identificado"


def show_help(tool):
    if tool == "Corrector GNSS":
        st.info(
            "Lee el CSV nativo de campo y, opcionalmente, el informe de procesamiento Leica. "
            "Comprueba base, solución, antena, altura y calidad; obtiene las coordenadas procesadas "
            "y genera un CSV CORREGIDO y un CSV POLIGONO."
        )
    elif tool == "Generador de data":
        st.warning(
            "Genera DATA DERIVADA para control o preparación. No representa una medición original "
            "de campo ni debe presentarse como observación GNSS real."
        )
    elif tool == "Certificados":
        st.info(
            "Genera certificados de punto geodésico a partir del punto MÓVIL del informe Leica y permite "
            "consultar el historial y mapa de puntos certificados."
        )
    else:
        st.info(
            "Busca efemérides finales precisas para el día anterior, el día de observación y el día siguiente. "
            "Prioriza ESA 5 min e IGS Final 15 min y muestra otras opciones disponibles."
        )


# ------------------ Sidebar principal ------------------

with st.sidebar:
    st.markdown("## 🧭 CONPLANOS GNSS")
    tool = st.radio(
        "Herramienta",
        ["Corrector GNSS", "Generador de data", "Certificados", "Efemérides precisas"],
        label_visibility="collapsed",
    )
    st.divider()

    st.markdown("### Ayuda rápida")
    with st.expander("¿Qué hace esta herramienta?", expanded=True):
        show_help(tool)

    with st.expander("Versiones", expanded=False):
        st.markdown(
            """
            **V1** · Corrección CSV + coordenadas.

            **V2** · Informe Leica + control de alturas.

            **V3** · Interfaz compacta.

            **V4** · Generador de data derivada.

            **V5** · Menú profesional + certificado.

            **V6** · Punto móvil Leica + extracción automática.

            **V7** · Efemérides + historial Google Sheets + mapa.
            """
        )

    st.caption("CONPLANOS GNSS · versión 7")

# ------------------ Encabezado ------------------

st.markdown('<div class="app-title">🛰️ CONPLANOS - Herramientas GNSS</div>', unsafe_allow_html=True)

if tool == "Corrector GNSS":
    # ========================================================
    # Corrector GNSS
    # ========================================================
    left, right = st.columns([2.25, 1.0], gap="large")

    with left:
        st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
        st.subheader("Sube el CSV nativo del levantamiento en campo")
        csv_file = st.file_uploader(
            "CSV nativo",
            type=["csv"],
            label_visibility="collapsed",
            key="corrector_csv_v5",
            help="Es la data original de campo.",
        )

        if csv_file:
            try:
                csv_info = read_csv(csv_file.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer el CSV: {exc}")
                st.stop()

            with right:
                card(
                    "📋 Resumen de la data nativa",
                    f"Archivo: {csv_file.name}<br>"
                    f"Registros: <b>{len(csv_info.rows)}</b><br>"
                    f"Base detectada: <b>{csv_info.base_name}</b><br>"
                    f"Fijo: <b>{len(csv_info.fixed_points)}</b> · No Fijo: <b>{len(csv_info.non_fixed_points)}</b>"
                )
                st.markdown(
                    f'<div class="card" style="border:2px solid #0f766e;background:#f0fdfa;">'
                    f'<div class="card-title">📍 COORDENADAS DE LA BASE DE LA DATA NATIVA</div>'
                    f'<div class="small"><b>E:</b> {csv_info.base_original_e:.4f} m &nbsp; <b>N:</b> {csv_info.base_original_n:.4f} m &nbsp; <b>H:</b> {csv_info.base_original_h:.4f} m</div></div>',
                    unsafe_allow_html=True,
                )
                if csv_info.different_base_points:
                    status(f"🔴 Hay {len(csv_info.different_base_points)} punto(s) con base diferente.", "bad")
                elif csv_info.missing_base_points:
                    status(f"🟡 Hay {len(csv_info.missing_base_points)} punto(s) sin Base.", "warn")
                else:
                    status("🟢 Base: todos conformes.", "ok")

                if csv_info.non_fixed_points:
                    names = ", ".join(p for p,_ in csv_info.non_fixed_points[:5])
                    status(f"🔴 No Fijo: {len(csv_info.non_fixed_points)} punto(s): {names}", "bad")
                else:
                    status(f"🟢 Solución: {len(csv_info.fixed_points)} Fijo.", "ok")

                if csv_info.antenna_height_counts:
                    rows = []
                    for (ant,h),n in csv_info.antenna_height_counts.items():
                        rows.append(f"{ant or '(vacío)'} · {h or '(vacío)'} · {n} rep.")
                    card("📡 Antena y altura", "<br>".join(rows))

                card("🏷️ Códigos", code_summary(csv_info))

                q = csv_point_quality_summary(csv_info)
                pdop = q["pdop"]
                if pdop[0] is not None:
                    card("🎯 Calidad rápida", f"PDOP: {pdop[0]:.3f}–{pdop[1]:.3f}")

            st.radio(
                "Origen de las coordenadas corregidas",
                ["📄 Informe de procesamiento", "✍️ Coordenadas manuales"],
                horizontal=True,
                key="correction_mode_v5",
            )
            mode = st.session_state["correction_mode_v5"]

            report = None
            height_choice = None
            processed_e = processed_n = processed_h = None

            if mode == "📄 Informe de procesamiento":
                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Sube el informe de procesamiento GNSS")
                pdf_files = st.file_uploader(
                    "PDF de procesamiento",
                    type=["pdf"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key="corrector_pdf_v5",
                )

                if pdf_files:
                    try:
                        report = parse_report_pdfs([(p.name, p.getvalue()) for p in pdf_files])
                    except Exception as exc:
                        st.error(f"No se pudo leer el informe: {exc}")
                        st.stop()

                    if report.mobile_e is None or report.mobile_n is None:
                        st.error("No se pudieron extraer las coordenadas X/Y del punto procesado.")
                        st.stop()

                    if report.solution_type and "fijo" in report.solution_type.casefold():
                        report_solution = "🟢 Fijo (Fase)"
                    else:
                        report_solution = f"🟡 {report.solution_type or 'No identificada'}"

                    with right:
                        card(
                            "📄 Resumen del procesamiento",
                            f"Referencia: <b>{report.reference_name or '—'}</b><br>"
                            f"Punto procesado: <b>{report.mobile_name or '—'}</b><br>"
                            f"Solución: <b>{report_solution}</b><br>"
                            f"Lectura: <b>{report.duration or '—'}</b><br>"
                            f"Distancia: <b>{report.distance_m/1000:.3f} km</b>" if report.distance_m else "Distancia: <b>—</b>"
                        )
                        card(
                            "📡 Equipo",
                            f"Referencia: {report.reference_receiver or '—'}<br>"
                            f"Antena ref.: {report.reference_antenna or '—'}<br>"
                            f"Móvil: {report.mobile_receiver or '—'}<br>"
                            f"Antena móvil: {report.mobile_antenna or '—'}<br>"
                            f"Altura móvil: {report.mobile_antenna_height_m or '—'} m"
                        )
                        card(
                            "🎯 Calidad Leica",
                            f"CQ 1D: {report.cq1d_m if report.cq1d_m is not None else '—'} m<br>"
                            f"CQ 2D: {report.cq2d_m if report.cq2d_m is not None else '—'} m<br>"
                            f"CQ 3D: {report.cq3d_m if report.cq3d_m is not None else '—'} m<br>"
                            f"M0: {report.m0_m if report.m0_m is not None else '—'} m"
                        )

                    height_mode = st.radio(
                        "Altura para la corrección",
                        ["Automática", "Ortométrica", "Elipsoidal WGS84"],
                        horizontal=True,
                        index=0,
                        key="height_mode_v5",
                        help="Automática selecciona la altura con menor diferencia absoluta respecto a la H del CSV.",
                    )
                    try:
                        height_choice = choose_height(csv_info.base_original_h, report, height_mode)
                    except Exception as exc:
                        st.error(str(exc))
                        st.stop()

                    processed_e, processed_n = report.mobile_e, report.mobile_n
                    processed_h = height_choice["selected_h"]

                    with right:
                        st.markdown(
                            f'<div class="card" style="border:2px solid #2563eb;background:#eff6ff;">'
                            f'<div class="card-title">📍 COORDENADAS DEL PUNTO MÓVIL PROCESADO</div>'
                            f'<div class="small"><b>E:</b> {processed_e:.4f} m &nbsp; <b>N:</b> {processed_n:.4f} m &nbsp; <b>H:</b> {processed_h:.4f} m</div></div>',
                            unsafe_allow_html=True,
                        )
                        card("📏 Altura usada",
                            f"H CSV base: {csv_info.base_original_h:.4f} m<br>"
                            f"Ortométrica: {report.mobile_h_ortho:.4f} m · Δ {height_choice['diffs'].get('Ortométrica', float('nan')):.4f} m<br>"
                            f"Elipsoidal: {report.mobile_h_ellip:.4f} m · Δ {height_choice['diffs'].get('Elipsoidal WGS84', float('nan')):.4f} m<br>"
                            f"<b>Usada: {height_choice['selected_type']} · {processed_h:.4f} m</b>")
                        for w in height_choice["warnings"]:
                            status("🟡 " + w, "warn")

                    # No antenna mismatch warning: reference/mobile are different roles.
                    st.caption(
                        "ℹ️ La antena de referencia y la antena móvil se muestran por separado. "
                        "Una diferencia entre ambas es normal cuando se procesan equipos distintos."
                    )

                else:
                    st.info("Sube el informe de procesamiento para extraer automáticamente las coordenadas.")
            else:
                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Ingresa las coordenadas corregidas manualmente")
                m1, m2, m3 = st.columns(3)
                processed_e = m1.number_input("Este E", value=float(csv_info.base_original_e), format="%.4f", key="manual_e_v7")
                processed_n = m2.number_input("Norte N", value=float(csv_info.base_original_n), format="%.4f", key="manual_n_v7")
                processed_h = m3.number_input("Altura H", value=float(csv_info.base_original_h), format="%.4f", key="manual_h_v7")

                with right:
                    st.markdown(
                        f'<div class="card" style="border:2px solid #2563eb;background:#eff6ff;">'
                        f'<div class="card-title">📍 COORDENADAS DE CORRECCIÓN</div>'
                        f'<div class="small"><b>E:</b> {processed_e:.4f} m &nbsp; <b>N:</b> {processed_n:.4f} m &nbsp; <b>H:</b> {processed_h:.4f} m</div></div>',
                        unsafe_allow_html=True,
                    )

            if processed_e is not None and processed_n is not None and processed_h is not None:
                st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
                if st.button("🚀 GENERAR CSV CORREGIDA Y POLIGONO", type="primary", use_container_width=True):
                    corrected_bytes, polygon_bytes, calc = apply_correction(
                        csv_info, float(processed_e), float(processed_n), float(processed_h)
                    )
                    cc1, cc2, cc3 = st.columns(3)
                    cc1.metric("ΔE", f"{calc['delta_e']:+.4f} m")
                    cc2.metric("ΔN", f"{calc['delta_n']:+.4f} m")
                    cc3.metric("ΔH", f"{calc['delta_h']:+.4f} m")

                    d1, d2 = st.columns(2)
                    with d1:
                        st.download_button(
                            "⬇️ Descargar CORREGIDA",
                            corrected_bytes,
                            file_name=corrected_filename(csv_file.name),
                            mime="text/csv",
                            use_container_width=True,
                        )
                    with d2:
                        st.download_button(
                            "⬇️ Descargar POLIGONO",
                            polygon_bytes,
                            file_name=polygon_filename(csv_file.name),
                            mime="text/csv",
                            use_container_width=True,
                        )
        else:
            st.info("Sube el CSV nativo para comenzar.")

elif tool == "Generador de data":
    # ========================================================
    # Generador de data
    # ========================================================
    left, right = st.columns([2.25, 1.0], gap="large")

    with left:
        st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
        st.subheader("Sube la data nativa matriz")
        native_file = st.file_uploader(
            "CSV nativo matriz",
            type=["csv"],
            label_visibility="collapsed",
            key="native_generator_csv_v5",
        )

        if native_file:
            try:
                native_info = read_csv(native_file.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer la data nativa: {exc}")
                st.stop()

            with right:
                card(
                    "📋 Resumen de la data matriz",
                    f"Registros: <b>{len(native_info.rows)}</b><br>"
                    f"Base: <b>{native_info.base_name}</b><br>"
                    f"Fijo: <b>{len(native_info.fixed_points)}</b><br>"
                    f"Códigos: <b>{code_summary(native_info)}</b>"
                )
                status("🟢 Data matriz cargada.", "ok")

            st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
            st.subheader("Sube las coordenadas finales del plano")
            plan_file = st.file_uploader(
                "CSV o Excel con E/N",
                type=["csv", "xlsx", "xlsm"],
                label_visibility="collapsed",
                key="plan_generator_file_v5",
            )

            if plan_file:
                try:
                    plan_points = read_coordinate_points(plan_file.getvalue(), plan_file.name)
                except Exception as exc:
                    st.error(f"No se pudo leer el archivo de plano: {exc}")
                    st.stop()

                t1, t2, t3 = st.columns(3)
                t1.metric("Coordenadas del plano", len(plan_points))

                tolerance = t2.number_input(
                    "Tolerancia de coincidencia (m)",
                    min_value=0.0001,
                    max_value=1.0,
                    value=0.0100,
                    step=0.001,
                    format="%.4f",
                    help="Si la distancia a una coordenada nativa es <= tolerancia, se conserva la fila nativa.",
                )

                neighbors = t3.number_input(
                    "Vecinos para interpolar H",
                    min_value=1,
                    max_value=12,
                    value=4,
                    step=1,
                )

                with right:
                    card(
                        "🧩 Regla de generación",
                        "🟢 Coincidente → conserva fila nativa.<br>"
                        "🔵 Nueva → E/N del plano + H interpolada.<br>"
                        "🏷️ Código → punto nativo más cercano.<br>"
                        "📋 Otros campos → referencia nativa más cercana.<br>"
                        "⚠️ Resultado = data derivada, no observación original."
                    )

                if st.button("🧩 GENERAR DATA DERIVADA", type="primary", use_container_width=True):
                    out_bytes, summary = generate_derived_data(
                        native_info, plan_points,
                        match_tolerance_m=float(tolerance),
                        idw_neighbors=int(neighbors),
                    )

                    with right:
                        card(
                            "📊 Resultado",
                            f"Entrada: <b>{summary['input_points']}</b><br>"
                            f"Coincidentes: <b>{summary['matched_points']}</b><br>"
                            f"Nuevos: <b>{summary['generated_points']}</b><br>"
                            f"Dist. media al vecino: <b>{summary['mean_nearest_distance_m']:.4f} m</b>"
                        )

                    st.success("✅ Data derivada generada.")
                    st.download_button(
                        "⬇️ Descargar DATA GENERADA",
                        out_bytes,
                        file_name=generated_data_filename(native_file.name),
                        mime="text/csv",
                        use_container_width=True,
                    )
        else:
            st.info("Sube la data nativa matriz para comenzar.")

elif tool == "Certificados":
    # ========================================================
    # Certificados: generar + historial/mapa
    # ========================================================
    st.subheader("📜 Certificados de punto geodésico")
    tab_gen, tab_hist = st.tabs(["📜 Generar certificado", "🗺️ Historial y mapa"])

    with tab_gen:
        left, right = st.columns([2.0, 1.05], gap="large")
        defaults = today_defaults()
        with left:
            st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
            st.subheader("Sube el informe de procesamiento Leica")
            report_file = st.file_uploader(
                "Informe de Procesamiento GNSS", type=["pdf"], key="certificate_pdf_v7",
                help="El certificado usa los datos del PUNTO MÓVIL del informe Leica."
            )
            if not report_file:
                st.info("Sube el informe Leica para llenar automáticamente los datos técnicos del punto móvil.")
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

                st.success("✅ Datos del PUNTO MÓVIL extraídos automáticamente.")
                st.markdown('<div class="step">DATOS DEL PUNTO MÓVIL</div>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="card" style="border:2px solid #2563eb;background:#eff6ff;">'
                    f'<div class="card-title">📍 Coordenadas certificadas</div>'
                    f'<div class="small"><b>N:</b> {data.norte} m &nbsp; <b>E:</b> {data.este} m &nbsp; <b>Zona:</b> {data.zona}<br>'
                    f'<b>Lat:</b> {data.latitud} &nbsp; <b>Lon:</b> {data.longitud}<br>'
                    f'<b>H elipsoidal:</b> {data.alt_ellipsoidal} m</div></div>', unsafe_allow_html=True)

                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Datos que debes ingresar manualmente")
                st.warning("🔴 Código del punto y Solicitante son obligatorios. No se extraen del informe Leica.")
                data.codigo = st.text_input("Código del punto geodésico *", key="cert_codigo_v7", placeholder="Ejemplo: PG2625")
                data.solicitante = st.text_input("Solicitante *", key="cert_solicitante_v7", placeholder="Nombre del propietario o solicitante")

                st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
                image_file = st.file_uploader("Fotografía de la placa o punto geodésico (opcional)", type=["png", "jpg", "jpeg"], key="certificate_img_v7")
                if image_file:
                    st.success("✅ Se utilizará la fotografía proporcionada.")
                else:
                    st.info("Si no subes una foto, se generará una placa ilustrativa con el código.")

                st.markdown('<div class="step">PASO 4</div>', unsafe_allow_html=True)
                generate = st.button("📜 GENERAR CERTIFICADO PDF + WORD", type="primary", use_container_width=True)

                if generate:
                    if not data.codigo.strip() or not data.solicitante.strip():
                        st.error("⚠️ Debes ingresar el Código del punto geodésico y el Solicitante.")
                        st.stop()
                    if not data.correlativo:
                        data.correlativo = f"CP-{data.anio}-{data.codigo.strip().upper()}"
                    tmpdir = Path(tempfile.mkdtemp(prefix="conplanos_cert_"))
                    try:
                        if image_file:
                            image_path = tmpdir / "punto.png"
                            image_path.write_bytes(image_file.getvalue())
                        else:
                            image_path = make_plaque(data.codigo, tmpdir / "placa_generada.png")
                        docx_path = tmpdir / f"Certificado_{data.codigo.strip()}.docx"
                        pdf_path = tmpdir / f"Certificado_{data.codigo.strip()}.pdf"
                        generate_certificate_docx(data, image_path, TEMPLATES_DIR / "certificado_punto_geodesico_template.docx", docx_path)
                        generate_certificate_pdf(data, image_path, TEMPLATES_DIR / "certificate_template.pdf", pdf_path)
                        st.session_state["last_certificate_record"] = make_record(data, report, report_file.name, pdf_path.name, docx_path.name)
                        st.session_state["last_certificate_paths"] = (pdf_path.read_bytes(), docx_path.read_bytes(), pdf_path.name, docx_path.name)
                        if history_configured():
                            try:
                                append_point(st.session_state["last_certificate_record"])
                                st.success("✅ Certificado generado y registrado en Google Sheets.")
                            except Exception as exc:
                                st.warning(f"Certificado generado. No se pudo guardar en Google Sheets: {exc}")
                        else:
                            st.success("✅ Certificado generado. Google Sheets aún no está configurado.")
                    except Exception as exc:
                        st.error(f"No se pudo generar el certificado: {exc}")

        with right:
            card("📌 Regla del certificado", "El certificado corresponde al <b>PUNTO MÓVIL</b> del informe Leica. La estación de referencia no se certifica en este documento.")
            card("🤖 Automático", "Norte · Este · Zona · Latitud · Longitud · H elipsoidal · Estación GNSS · Fecha de posicionamiento · Año")
            card("✍️ Manual obligatorio", "<b>Código del punto geodésico</b><br><b>Solicitante</b>")
            card("📅 Fecha de emisión", f"Automática: <b>{defaults.fecha_emision}</b>")
            if report_file:
                card("📄 Informe", f"Archivo: {report_file.name}<br>Referencia: {report.reference_name or '—'}<br>Móvil: {report.mobile_name or '—'}<br>Solución: {report.solution_type or report.solution_state or '—'}")

    with tab_hist:
        st.markdown('<div class="step">HISTORIAL</div>', unsafe_allow_html=True)
        if not history_configured():
            st.warning("Google Sheets no está configurado todavía. La herramienta está preparada para conectarse mediante Streamlit Secrets.")
            st.code('[gcp_service_account]\ntype = "service_account"\n...\n\nGOOGLE_SHEET_ID = "ID_DE_TU_HOJA"')
        else:
            try:
                records = load_points()
            except Exception as exc:
                st.error(f"No se pudo leer Google Sheets: {exc}")
                records = []
            if not records:
                st.info("Todavía no hay puntos certificados registrados.")
            else:
                import pydeck as pdk
                import pandas as pd
                rows = []
                for r in records:
                    lat = dms_to_decimal(r.get("latitud", ""))
                    lon = dms_to_decimal(r.get("longitud", ""))
                    if lat is not None and lon is not None:
                        rr = dict(r); rr["lat"] = lat; rr["lon"] = lon; rows.append(rr)
                f1, f2 = st.columns([1.5, 1])
                search = f1.text_input("🔎 Buscar código o solicitante", key="hist_search_v7")
                years = sorted({str(r.get("anio", "")) for r in records if r.get("anio")}, reverse=True)
                year = f2.selectbox("Año", ["Todos"] + years, key="hist_year_v7")
                filtered = [r for r in rows if (not search or search.casefold() in (r.get("codigo", "") + " " + r.get("solicitante", "")).casefold()) and (year == "Todos" or r.get("anio") == year)]
                st.caption(f"{len(filtered)} punto(s) mostrado(s) de {len(records)} registrado(s).")
                if filtered:
                    df = pd.DataFrame(filtered)
                    layer = pdk.Layer("ScatterplotLayer", data=df, id="puntos-certificados", get_position="[lon, lat]", get_fill_color="[15, 118, 110, 190]", get_radius=45, pickable=True, auto_highlight=True)
                    center_lat = float(df["lat"].mean()); center_lon = float(df["lon"].mean())
                    deck = pdk.Deck(layers=[layer], initial_view_state=pdk.ViewState(latitude=center_lat, longitude=center_lon, zoom=9), tooltip={"text": "{codigo}\n{solicitante}\n{fecha_posicion}"}, map_style=None)
                    event = st.pydeck_chart(deck, on_select="rerun", selection_mode="single-object", key="cert_map_v7")
                    selected = None
                    try:
                        objs = event.selection.objects.get("puntos-certificados", [])
                        if objs: selected = objs[0]
                    except Exception:
                        pass
                    if selected:
                        st.markdown(f"### 📍 {selected.get('codigo','Punto')}")
                        a,b = st.columns(2)
                        a.metric("Norte", f"{selected.get('norte','—')} m"); b.metric("Este", f"{selected.get('este','—')} m")
                        card("Ficha del punto", f"Solicitante: <b>{selected.get('solicitante','—')}</b><br>Zona: {selected.get('zona','—')}<br>Latitud: {selected.get('latitud','—')}<br>Longitud: {selected.get('longitud','—')}<br>H elipsoidal: {selected.get('alt_ellipsoidal','—')} m<br>Estación: {selected.get('estacion_gnss','—')}<br>Fecha posición: {selected.get('fecha_posicion','—')}<br>Fecha emisión: {selected.get('fecha_emision','—')}<br>Solución: {selected.get('solucion','—')}<br>Duración: {selected.get('duracion_lectura','—')}<br>Distancia: {selected.get('distancia_m','—')} m")
                else:
                    st.info("No hay coordenadas geográficas válidas para mostrar en el mapa.")

elif tool == "Efemérides precisas":
    st.subheader("📡 Efemérides precisas")
    st.caption("Busca productos finales para: un día antes · día de lectura · un día después.")
    target = st.date_input("Fecha de lectura", value=date.today(), key="eph_date_v7")
    st.markdown("**Prioridad de búsqueda:** ESA Final 5 min → IGS Final 15 min → otras soluciones Final 5 min.")
    if st.button("🔎 BUSCAR EFEMÉRIDES FINALES", type="primary", use_container_width=True):
        with st.spinner("Comprobando disponibilidad de productos oficiales…"):
            products = find_products(target, check=True)
        grouped = group_by_day(products)
        for d in [target + timedelta(days=delta) for delta in (-1,0,1)]:
            st.markdown(f"### {d.strftime('%d/%m/%Y')} — {'día anterior' if d < target else 'día de lectura' if d == target else 'día siguiente'}")
            for p in grouped.get(d, []):
                if p.status == "Disponible":
                    st.markdown(f"🟢 **{p.label}** · {p.sampling} · `{p.filename}`  ")
                    st.markdown(f"[⬇️ Descargar producto]({p.url})")
                elif p.source in {"ESA", "IGS"}:
                    st.markdown(f"⚪ **{p.label}** · {p.status} · `{p.filename}`")
        st.info("Nota: CDDIS puede requerir autenticación Earthdata. ESA publica sus Final por día en su archivo oficial.")
