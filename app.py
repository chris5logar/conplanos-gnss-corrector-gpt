from __future__ import annotations

from collections import Counter

import streamlit as st

from core import (
    HEIGHT_WARNING_M,
    antenna_discrepancy,
    apply_correction,
    choose_height,
    corrected_filename,
    csv_point_quality_summary,
    generate_derived_data,
    generated_data_filename,
    parse_report_pdfs,
    polygon_filename,
    read_coordinate_points,
    read_csv,
)

st.set_page_config(
    page_title="CONPLANOS – GNSS",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
      .block-container {padding-top: .8rem; padding-bottom: .8rem; max-width: 1550px;}
      .small {font-size:.78rem; line-height:1.35;}
      .tiny {font-size:.68rem; line-height:1.25; color:#6b7280;}
      .card {border:1px solid #e5e7eb; border-radius:12px; padding:.65rem .78rem; margin-bottom:.55rem; background:#fff;}
      .card-title {font-size:.84rem; font-weight:700; margin-bottom:.3rem;}
      .kv {margin:.11rem 0;}
      .label {color:#6b7280;}
      .ok,.warn,.bad,.neutral {border-radius:8px; padding:.38rem .5rem; margin:.2rem 0; font-size:.76rem; line-height:1.3;}
      .ok {color:#166534;background:#f0fdf4;border:1px solid #bbf7d0;}
      .warn {color:#92400e;background:#fffbeb;border:1px solid #fde68a;}
      .bad {color:#991b1b;background:#fef2f2;border:1px solid #fecaca;}
      .neutral {color:#374151;background:#f9fafb;border:1px solid #e5e7eb;}
      .step {font-size:.75rem;color:#6b7280;margin-bottom:.08rem;}
      .version {font-size:.66rem;color:#6b7280;}
    </style>
    """,
    unsafe_allow_html=True,
)


def html_card(title: str, body: str) -> str:
    return f'<div class="card"><div class="card-title">{title}</div><div class="small">{body}</div></div>'


def status_line(text: str, kind: str = "ok") -> str:
    return f'<div class="{kind}">{text}</div>'


def fmt_m(value, decimals=4):
    return "—" if value is None else f"{value:,.{decimals}f} m"


def fmt_km(value):
    return "—" if value is None else f"{value/1000:,.3f} km"


def summarize_codes(csv_info):
    counts = Counter((row.get("Código") or "").strip() for row in csv_info.rows[1:] if (row.get("Código") or "").strip())
    return " · ".join(f"{code} ({n})" for code, n in counts.most_common(4)) if counts else "No identificado"


def csv_status_html(csv_info):
    parts = []
    if csv_info.different_base_points:
        parts.append(status_line(f"🔴 <b>Base:</b> {len(csv_info.different_base_points)} punto(s) usan una base distinta de <b>{csv_info.base_name}</b>.", "bad"))
    elif csv_info.missing_base_points:
        parts.append(status_line(f"🟡 <b>Base:</b> {len(csv_info.missing_base_points)} punto(s) sin base.", "warn"))
    else:
        parts.append(status_line(f"🟢 <b>Base:</b> todos los puntos usan <b>{csv_info.base_name}</b>.", "ok"))

    if csv_info.non_fixed_points:
        names = ", ".join(f"{p} ({s or 'sin solución'})" for p, s in csv_info.non_fixed_points[:6])
        extra = " …" if len(csv_info.non_fixed_points) > 6 else ""
        parts.append(status_line(f"🔴 <b>Solución:</b> {len(csv_info.non_fixed_points)} punto(s) no Fijo: {names}{extra}", "bad"))
    else:
        parts.append(status_line(f"🟢 <b>Solución:</b> {len(csv_info.fixed_points)} punto(s) Fijo.", "ok"))
    return "".join(parts)


# ============================================================
# Encabezado + guía
# ============================================================

st.markdown('<h1 style="margin-bottom:.05rem">🛰️ CONPLANOS – Herramientas GNSS</h1>', unsafe_allow_html=True)
st.caption("V4 · Corrector GNSS + Generador de data derivada para control y preparación de levantamientos.")

with st.sidebar:
    st.header("Ayuda rápida")
    with st.expander("ℹ️ ¿Qué hace esta aplicación?", expanded=True):
        st.markdown(
            """
            **Corrector GNSS**
            1. Lee el CSV nativo de campo.
            2. Comprueba base, solución Fijo, antena, alturas y calidad.
            3. Lee el informe Leica y extrae las coordenadas procesadas.
            4. Compara H ortométrica vs. elipsoidal.
            5. Genera `CORREGIDA.csv` y `POLIGONO.csv`.

            **Generador de data derivada**
            1. Lee el CSV nativo matriz.
            2. Lee E/N de un CSV o Excel de coordenadas de plano.
            3. Si una coordenada coincide, conserva su fila nativa.
            4. Si es nueva, conserva E/N del plano, interpola H y toma el código y demás atributos del punto nativo más cercano.

            **Importante:** el segundo módulo produce **data derivada**, no sustituye mediciones originales de campo.
            """
        )
    with st.expander("🧭 Versiones", expanded=False):
        st.markdown(
            """
            **V1** · Corrección automática desde CSV + coordenadas.

            **V2** · Lectura de informe Leica, selección de altura y controles de calidad.

            **V3** · Interfaz compacta con resúmenes laterales y alertas.

            **V4** · Generador de data derivada desde coordenadas de plano + guía integrada.
            """
        )
    st.markdown('<div class="version">CONPLANOS GNSS · versión 4</div>', unsafe_allow_html=True)

# ============================================================
# Pestañas
# ============================================================

tab_corrector, tab_generator = st.tabs(["🛰️ Corrector GNSS", "🧩 Generador de data"])

with tab_corrector:
    left, right = st.columns([2.25, 1.05], gap="large")

    with left:
        st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
        st.subheader("Sube el CSV nativo del levantamiento en campo")
        csv_file = st.file_uploader(
            "CSV nativo",
            type=["csv"],
            label_visibility="collapsed",
            key="corrector_csv",
            help="Es el archivo original de la data de campo. La aplicación lo usa como matriz de referencia.",
        )
        if not csv_file:
            st.info("Sube el CSV nativo para comenzar.")
        else:
            try:
                csv_info = read_csv(csv_file.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer el CSV: {exc}")
                st.stop()

            st.markdown(csv_status_html(csv_info), unsafe_allow_html=True)

            with st.expander("Ver detalles del CSV", expanded=False):
                q = csv_point_quality_summary(csv_info)
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Registros", len(csv_info.rows))
                c2.metric("Base", csv_info.base_name)
                c3.metric("Fijo", len(csv_info.fixed_points))
                c4.metric("No Fijo", len(csv_info.non_fixed_points))
                st.write(f"**Códigos:** {summarize_codes(csv_info)}")
                if csv_info.antenna_height_counts:
                    st.write("**Antena / altura / repeticiones:**")
                    st.table([
                        {"Antena": a or "(vacía)", "Altura": h or "(vacía)", "Repeticiones": n}
                        for (a, h), n in csv_info.antenna_height_counts.items()
                    ])
                if q["pdop"][0] is not None:
                    st.write(f"**PDOP:** {q['pdop'][0]:.4f}–{q['pdop'][1]:.4f}")

            mode = st.radio(
                "Origen de las coordenadas corregidas",
                ["📄 Informe de procesamiento", "✍️ Coordenadas manuales"],
                horizontal=True,
                key="correction_mode",
            )

            report = None
            height_choice = None
            processed_e = processed_n = processed_h = None

            if mode == "📄 Informe de procesamiento":
                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Sube el informe de procesamiento GNSS")
                pdf_files = st.file_uploader(
                    "Informe PDF",
                    type=["pdf"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                    key="corrector_pdf",
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

                    height_mode = st.radio(
                        "Altura para la corrección",
                        ["Automática", "Ortométrica", "Elipsoidal WGS84"],
                        horizontal=True,
                        index=0,
                        key="height_mode",
                        help="Automática selecciona la altura con menor diferencia absoluta respecto a la H del CSV.",
                    )
                    try:
                        height_choice = choose_height(csv_info.base_original_h, report, height_mode)
                    except Exception as exc:
                        st.error(str(exc))
                        st.stop()
                    processed_e, processed_n = report.mobile_e, report.mobile_n
                    processed_h = height_choice["selected_h"]
                else:
                    st.info("Sube el informe Leica para extraer las coordenadas procesadas automáticamente.")
            else:
                st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
                st.subheader("Ingresa las coordenadas corregidas manualmente")
                m1, m2, m3 = st.columns(3)
                processed_e = m1.number_input("Este E", value=float(csv_info.base_original_e), format="%.4f", key="manual_e")
                processed_n = m2.number_input("Norte N", value=float(csv_info.base_original_n), format="%.4f", key="manual_n")
                processed_h = m3.number_input("Altura H", value=float(csv_info.base_original_h), format="%.4f", key="manual_h")
                st.selectbox("Tipo de altura", ["Ortométrica", "Elipsoidal WGS84", "No especificado"], key="manual_height_type")

            st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
            if st.button("🚀 GENERAR CSV CORREGIDA Y POLIGONO", type="primary", use_container_width=True, key="generate_corrector"):
                if processed_e is None or processed_n is None or processed_h is None:
                    st.error("Primero carga el informe o ingresa las coordenadas.")
                else:
                    try:
                        corrected_bytes, polygon_bytes, calc = apply_correction(csv_info, float(processed_e), float(processed_n), float(processed_h))
                        st.success("✅ Corrección terminada.")
                        a, b, c = st.columns(3)
                        a.metric("ΔE", f"{calc['delta_e']:+.4f} m")
                        b.metric("ΔN", f"{calc['delta_n']:+.4f} m")
                        c.metric("ΔH", f"{calc['delta_h']:+.4f} m")
                        d1, d2 = st.columns(2)
                        with d1:
                            st.download_button("⬇️ Descargar CORREGIDA", corrected_bytes, corrected_filename(csv_file.name), "text/csv", use_container_width=True, key="download_corrected")
                        with d2:
                            st.download_button("⬇️ Descargar POLIGONO", polygon_bytes, polygon_filename(csv_file.name), "text/csv", use_container_width=True, key="download_polygon")
                    except Exception as exc:
                        st.error(f"No se pudo aplicar la corrección: {exc}")

    with right:
        if csv_file:
            st.markdown(html_card(
                "📋 CSV nativo",
                f"""
                <div class='kv'><span class='label'>Archivo:</span> <b>{csv_file.name}</b></div>
                <div class='kv'><span class='label'>Registros:</span> {len(csv_info.rows)}</div>
                <div class='kv'><span class='label'>Base:</span> <b>{csv_info.base_name}</b></div>
                <div class='kv'><span class='label'>Fijo:</span> {len(csv_info.fixed_points)} · <span class='label'>No Fijo:</span> {len(csv_info.non_fixed_points)}</div>
                <div class='kv'><span class='label'>Códigos:</span> {summarize_codes(csv_info)}</div>
                """), unsafe_allow_html=True)
            if csv_info.antenna_height_counts:
                text = "".join(f"<div class='kv'><span class='label'>{a or '(vacía)'}</span> · {h or '(vacía)'} · <b>{n} rep.</b></div>" for (a,h),n in csv_info.antenna_height_counts.items())
                st.markdown(html_card("📡 Antena / altura", text), unsafe_allow_html=True)
            st.markdown(html_card("🔎 Estado", csv_status_html(csv_info)), unsafe_allow_html=True)

        if report is None:
            st.markdown(html_card("📄 Procesamiento", '<div class="tiny">Aún no se ha cargado el informe.</div>'), unsafe_allow_html=True)
        else:
            ref = report.reference_name or "—"
            mobile = report.mobile_name or "—"
            sol = report.solution_type or "—"
            state = report.solution_state or "—"
            sol_kind = "ok" if ("fijo" in sol.casefold() or state.casefold() == "solucionado") else "warn"
            body = f"""
            <div class='kv'><span class='label'>Referencia:</span> <b>{ref}</b></div>
            <div class='kv'><span class='label'>Punto procesado:</span> <b>{mobile}</b></div>
            {status_line(f'🟢 <b>Solución:</b> {sol} · {state}', sol_kind)}
            <div class='kv'><span class='label'>Lectura:</span> <b>{report.duration or '—'}</b></div>
            <div class='kv'><span class='label'>Distancia:</span> <b>{fmt_km(report.distance_m)}</b></div>
            <div class='kv'><span class='label'>Antena:</span> <b>{report.mobile_antenna or '—'}</b></div>
            <div class='kv'><span class='label'>Altura antena:</span> {fmt_m(report.mobile_antenna_height_m)}</div>
            <div class='kv'><span class='label'>Código:</span> {summarize_codes(csv_info) if csv_file else '—'}</div>
            <div class='kv'><span class='label'>Inicio:</span> {report.start or '—'}</div>
            <div class='kv'><span class='label'>CQ 3D:</span> {fmt_m(report.cq3d_m)}</div>
            """
            st.markdown(html_card("📄 Resumen del procesamiento", body), unsafe_allow_html=True)

            if height_choice:
                ortho = report.mobile_h_ortho
                ellip = report.mobile_h_ellip
                od = abs(csv_info.base_original_h - ortho) if ortho is not None else None
                ed = abs(csv_info.base_original_h - ellip) if ellip is not None else None
                st.markdown(html_card(
                    "📏 Altura usada",
                    f"""
                    <div class='kv'><span class='label'>H CSV:</span> {csv_info.base_original_h:.4f} m</div>
                    <div class='kv'><span class='label'>Ortométrica:</span> {fmt_m(ortho)} · Δ {fmt_m(od)}</div>
                    <div class='kv'><span class='label'>Elipsoidal:</span> {fmt_m(ellip)} · Δ {fmt_m(ed)}</div>
                    <div class='kv'><span class='label'>Usada:</span> <b>{height_choice['selected_type']}</b> · {fmt_m(height_choice['selected_h'])}</div>
                    """), unsafe_allow_html=True)
                if height_choice["warnings"]:
                    for warning in height_choice["warnings"]:
                        st.markdown(status_line("⚠️ " + warning, "warn"), unsafe_allow_html=True)

            discrepancy = antenna_discrepancy(report, csv_info)
            if discrepancy:
                st.markdown(status_line("⚠️ " + discrepancy, "warn"), unsafe_allow_html=True)
            st.markdown(html_card(
                "🎯 Calidad",
                f"<div class='kv'>CQ 1D: {fmt_m(report.cq1d_m)} · CQ 2D: {fmt_m(report.cq2d_m)} · CQ 3D: {fmt_m(report.cq3d_m)}</div><div class='kv'>M0: {fmt_m(report.m0_m)}</div>"
            ), unsafe_allow_html=True)
            if processed_e is not None:
                st.markdown(html_card("📍 Coordenadas de corrección", f"<div class='kv'>E <b>{processed_e:.4f}</b> · N <b>{processed_n:.4f}</b> · H <b>{processed_h:.4f}</b></div>"), unsafe_allow_html=True)

with tab_generator:
    st.markdown("### 🧩 Generador de data derivada")
    st.caption("Usa una data nativa como matriz y un archivo de coordenadas E/N del plano para preparar una data derivada de trabajo.")
    st.warning("⚠️ El resultado es data derivada/interpolada para preparación o control. No debe presentarse como medición original de campo.")

    g_left, g_right = st.columns([2.25, 1.05], gap="large")
    with g_left:
        st.markdown('<div class="step">PASO 1</div>', unsafe_allow_html=True)
        st.subheader("Sube la data nativa matriz")
        g_csv = st.file_uploader("CSV nativo matriz", type=["csv"], label_visibility="collapsed", key="generator_native")
        if g_csv:
            try:
                g_info = read_csv(g_csv.getvalue())
            except Exception as exc:
                st.error(f"No se pudo leer la data nativa: {exc}")
                st.stop()

            st.markdown('<div class="step">PASO 2</div>', unsafe_allow_html=True)
            st.subheader("Sube las coordenadas finales del plano")
            st.caption("Puede ser CSV o Excel. Debe contener E/N o X/Y. El nombre del punto es opcional.")
            plan_file = st.file_uploader("Coordenadas del plano", type=["csv", "xlsx", "xlsm"], label_visibility="collapsed", key="generator_plan")

            if plan_file:
                try:
                    plan_points = read_coordinate_points(plan_file.getvalue(), plan_file.name)
                except Exception as exc:
                    st.error(f"No se pudieron leer las coordenadas del plano: {exc}")
                    st.stop()

                st.success(f"✅ Se detectaron {len(plan_points)} coordenadas E/N del plano.")
                tol = st.number_input("Tolerancia para considerar una coordenada coincidente (m)", min_value=0.001, max_value=1.0, value=0.010, step=0.001, format="%.3f", help="Si la distancia entre el punto del plano y un punto nativo es menor o igual a esta tolerancia, se conserva la fila nativa.")
                k = st.number_input("Puntos vecinos para interpolar la altura", min_value=1, max_value=8, value=4, step=1)

                st.markdown('<div class="step">PASO 3</div>', unsafe_allow_html=True)
                if st.button("🧩 GENERAR DATA DERIVADA", type="primary", use_container_width=True, key="generate_derived"):
                    try:
                        generated_bytes, result = generate_derived_data(g_info, plan_points, float(tol), int(k))
                    except Exception as exc:
                        st.error(f"No se pudo generar la data: {exc}")
                    else:
                        st.success("✅ Data derivada generada.")
                        a,b,c = st.columns(3)
                        a.metric("Coordenadas", result["input_points"])
                        b.metric("Coincidentes", result["matched_points"])
                        c.metric("Nuevas / interpoladas", result["generated_points"])
                        st.download_button("⬇️ Descargar DATA GENERADA", generated_bytes, generated_data_filename(g_csv.name), "text/csv", use_container_width=True, key="download_generated")
                        st.caption(f"Vecino más lejano usado como referencia: {result['max_nearest_distance_m']:.3f} m · promedio: {result['mean_nearest_distance_m']:.3f} m")
                        if result["generated_detail"]:
                            with st.expander("Ver puntos nuevos e interpolados", expanded=False):
                                st.dataframe(result["generated_detail"], use_container_width=True)
            else:
                st.info("Sube las coordenadas del plano para continuar.")
        else:
            st.info("Sube primero la data nativa matriz.")

    with g_right:
        if g_csv:
            st.markdown(html_card(
                "📋 Matriz nativa",
                f"""
                <div class='kv'><span class='label'>Archivo:</span> <b>{g_csv.name}</b></div>
                <div class='kv'><span class='label'>Registros:</span> {len(g_info.rows)}</div>
                <div class='kv'><span class='label'>Base:</span> <b>{g_info.base_name}</b></div>
                <div class='kv'><span class='label'>Antena:</span> {g_info.base_csv_antenna or '—'}</div>
                <div class='kv'><span class='label'>Altura base:</span> {fmt_m(g_info.base_csv_height_m)}</div>
                <div class='kv'><span class='label'>Fijo:</span> {len(g_info.fixed_points)} · No Fijo: {len(g_info.non_fixed_points)}</div>
                """), unsafe_allow_html=True)
        st.markdown(html_card(
            "🧭 Regla de generación",
            "<div class='kv'>🟢 Coincidente → conserva la fila nativa.</div><div class='kv'>🔵 Nueva → E/N del plano + H interpolada.</div><div class='kv'>🏷️ Código → punto nativo más cercano.</div><div class='kv'>📋 Otros campos → referencia del punto nativo más cercano.</div><div class='kv'>🔢 PDOP y demás valores → se toman de esa referencia, no se inventa un valor fuera del patrón.</div>",
        ), unsafe_allow_html=True)
        if plan_file:
            st.markdown(html_card("📐 Plano", f"<div class='kv'><span class='label'>Archivo:</span> <b>{plan_file.name}</b></div><div class='kv'><span class='label'>Puntos E/N:</span> {len(plan_points)}</div>"), unsafe_allow_html=True)

