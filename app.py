from __future__ import annotations

import io
from pathlib import Path

import streamlit as st

from core import (
    HEIGHT_WARNING_M,
    antenna_discrepancy,
    apply_correction,
    choose_height,
    corrected_filename,
    csv_point_quality_summary,
    parse_report_pdfs,
    polygon_filename,
    read_csv,
)


st.set_page_config(
    page_title="CONPLANOS – Corrector GNSS V2",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------
# Estilo ligero
# ------------------------------------------------------------

st.markdown(
    """
    <style>
      .block-container {padding-top: 1.5rem; padding-bottom: 2rem;}
      .small-muted {color:#6b7280; font-size:.9rem;}
      .warning-box {padding: .75rem 1rem; border-radius: .6rem; background:#fff7ed;}
      .ok-box {padding: .75rem 1rem; border-radius: .6rem; background:#f0fdf4;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🛰️ CONPLANOS – Corrector GNSS Leica Infinity")
st.caption(
    "V2 · Corrección automática desde informe Leica o mediante coordenadas manuales."
)

with st.sidebar:
    st.header("1. Modo de trabajo")
    mode = st.radio(
        "Origen de las coordenadas corregidas",
        ["📄 Informe Leica (PDF)", "✍️ Coordenadas manuales"],
    )

    st.divider()
    st.subheader("Reglas automáticas")
    st.write("• La fila 2 del Excel/CSV se toma como base.")
    st.write("• Se verifica la columna Base.")
    st.write("• Puntos posteriores: Número de Observación = 65.")
    st.write("• Se controla la solución Fijo.")
    st.write("• Se comparan alturas elipsoidal/ortométrica.")
    st.write(f"• Umbral de advertencia de altura: {HEIGHT_WARNING_M:.0f} m.")


csv_file = st.file_uploader(
    "📥 Sube primero el CSV exportado desde Leica Infinity",
    type=["csv"],
    help="Se conserva el CSV original; la aplicación genera nuevos archivos.",
)

if not csv_file:
    st.info("Sube el CSV para comenzar.")
    st.stop()

try:
    csv_info = read_csv(csv_file.getvalue())
except Exception as exc:
    st.error(f"No se pudo leer el CSV: {exc}")
    st.stop()

# ------------------------------------------------------------
# Resumen del CSV
# ------------------------------------------------------------

st.subheader("2. Verificación del CSV")

c1, c2, c3, c4 = st.columns(4)
c1.metric("Registros", len(csv_info.rows))
c2.metric("Base detectada", csv_info.base_name)
c3.metric("Puntos Fijo", len(csv_info.fixed_points))
c4.metric("Puntos no Fijo", len(csv_info.non_fixed_points))

if csv_info.different_base_points:
    st.error(
        f"⚠️ Se identificaron bases diferentes a '{csv_info.base_name}' "
        f"en {len(csv_info.different_base_points)} punto(s)."
    )
    with st.expander("Ver puntos con base diferente"):
        st.table(
            [
                {"Punto": p, "Base encontrada": b}
                for p, b in csv_info.different_base_points
            ]
        )
elif csv_info.missing_base_points:
    st.warning(
        f"Hay {len(csv_info.missing_base_points)} punto(s) con Base vacía. "
        "Se completarán con la base principal al generar el CSV corregido."
    )
else:
    st.success(f"✅ Todos los puntos usan la base '{csv_info.base_name}'.")

if csv_info.non_fixed_points:
    st.warning("⚠️ Hay puntos del CSV que no tienen solución Fijo.")
    with st.expander("Ver puntos no Fijo"):
        st.table(
            [
                {"Punto": p, "Solución": s or "(vacía)"}
                for p, s in csv_info.non_fixed_points
            ]
        )

quality = csv_point_quality_summary(csv_info)

with st.expander("Calidad del levantamiento que ya viene en el CSV"):
    q1, q2, q3 = st.columns(3)
    if quality["rms_error"][0] is not None:
        q1.metric(
            "RMS Error",
            f"{quality['rms_error'][0]:.4f}–{quality['rms_error'][1]:.4f} m",
        )
    if quality["horizontal_error"][0] is not None:
        q2.metric(
            "Error horizontal",
            f"{quality['horizontal_error'][0]:.4f}–{quality['horizontal_error'][1]:.4f} m",
        )
    if quality["vertical_error"][0] is not None:
        q3.metric(
            "Error vertical",
            f"{quality['vertical_error'][0]:.4f}–{quality['vertical_error'][1]:.4f} m",
        )

    if csv_info.antenna_height_counts:
        st.write("**Antena / altura registrados en los puntos:**")
        st.table(
            [
                {
                    "Antena": ant or "(vacía)",
                    "Altura": h or "(vacía)",
                    "Repeticiones": count,
                }
                for (ant, h), count in csv_info.antenna_height_counts.items()
            ]
        )

# ------------------------------------------------------------
# Modo PDF
# ------------------------------------------------------------

report = None
height_choice = None
processed_e = None
processed_n = None
processed_h = None

if mode == "📄 Informe Leica (PDF)":
    st.subheader("3. Cargar el informe de procesamiento Leica")

    pdf_files = st.file_uploader(
        "📄 Informe(s) de procesamiento GNSS",
        type=["pdf"],
        accept_multiple_files=True,
        help="Puedes subir el Resumen, el Informe detallado, o ambos.",
    )

    if pdf_files:
        try:
            pdf_items = [(p.name, p.getvalue()) for p in pdf_files]
            report = parse_report_pdfs(pdf_items)
        except Exception as exc:
            st.error(f"No se pudo leer el informe Leica: {exc}")
            st.stop()

        # Baselines
        if report.detected_baselines and len(report.detected_baselines) > 1:
            st.warning(
                "⚠️ El PDF contiene más de una línea base. "
                "La aplicación mostrará la primera detectada."
            )

        st.success("✅ Informe Leica leído correctamente.")

        st.subheader("Resumen del procesamiento Leica")

        a, b, c, d = st.columns(4)
        a.metric("Solución", report.solution_type or "No identificada")
        b.metric("Lectura", report.duration or "No identificada")
        c.metric("Distancia", f"{report.distance_m/1000:.3f} km" if report.distance_m else "—")
        d.metric("Antena móvil", report.mobile_antenna or "No identificada")

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Proyecto", report.project or "—")
        r2.metric("Referencia", report.reference_name or "—")
        r3.metric("Fecha inicio", (report.start or "—").split(" ")[0])
        r4.metric("Procesado", report.processed_at or "—")

        with st.expander("Detalles del equipo y lectura", expanded=True):
            left, right = st.columns(2)

            with left:
                st.markdown("**Referencia**")
                st.write(
                    f"Receptor: {report.reference_receiver or '—'}  \n"
                    f"SN: {report.reference_receiver_sn or '—'}  \n"
                    f"Antena: {report.reference_antenna or '—'}  \n"
                    f"Altura: {report.reference_antenna_height_m or '—'} m"
                )

            with right:
                st.markdown("**Móvil / Punto procesado**")
                st.write(
                    f"Receptor: {report.mobile_receiver or '—'}  \n"
                    f"SN: {report.mobile_receiver_sn or '—'}  \n"
                    f"Antena: {report.mobile_antenna or '—'}  \n"
                    f"Altura: {report.mobile_antenna_height_m or '—'} m"
                )

            if report.start and report.end:
                st.info(
                    f"Lectura: **{report.start} → {report.end}** · "
                    f"Duración: **{report.duration or '—'}**"
                )

        if report.solution_type and "fijo" in report.solution_type.casefold():
            st.success(
                f"✅ Leica reporta una solución **{report.solution_type}**."
            )
        elif report.solution_type:
            st.warning(
                f"⚠️ Leica reporta una solución **{report.solution_type}**."
            )

        if report.solution_state:
            st.write(
                f"**Estado de la solución:** {report.solution_state} · "
                f"{report.solution_start or ''} → {report.solution_end or ''} · "
                f"{report.solution_duration or ''}"
            )

        discrepancy = antenna_discrepancy(report, csv_info)
        if discrepancy:
            st.warning("⚠️ " + discrepancy)

        # Coordenadas automáticas
        st.subheader("4. Coordenadas corregidas detectadas en el informe")

        e1, n1, h1 = st.columns(3)
        e1.metric("Este X", f"{report.mobile_e:.4f} m" if report.mobile_e is not None else "—")
        n1.metric("Norte Y", f"{report.mobile_n:.4f} m" if report.mobile_n is not None else "—")

        height_mode = st.radio(
            "Altura que se usará para corregir",
            [
                "Automática",
                "Ortométrica",
                "Elipsoidal WGS84",
            ],
            horizontal=True,
            index=0,
        )

        if report.mobile_e is None or report.mobile_n is None:
            st.error("No se pudieron extraer X/Y del informe.")
            st.stop()

        try:
            height_choice = choose_height(
                csv_info.base_original_h,
                report,
                height_mode,
            )
        except Exception as exc:
            st.error(str(exc))
            st.stop()

        with st.expander("Verificación de altura (muy importante)", expanded=True):
            st.write(
                "La aplicación compara la altura **H del CSV base** contra las dos alturas "
                "que entrega Leica para el punto procesado."
            )

            orth_diff = height_choice["diffs"].get("Ortométrica")
            ellip_diff = height_choice["diffs"].get("Elipsoidal WGS84")

            h1, h2, h3 = st.columns(3)
            h1.metric(
                "H base CSV",
                f"{csv_info.base_original_h:.4f} m",
            )
            h2.metric(
                "H ortométrica Leica",
                f"{report.mobile_h_ortho:.4f} m" if report.mobile_h_ortho is not None else "—",
                delta=f"{orth_diff:.4f} m" if orth_diff is not None else None,
            )
            h3.metric(
                "H elipsoidal WGS84 Leica",
                f"{report.mobile_h_ellip:.4f} m" if report.mobile_h_ellip is not None else "—",
                delta=f"{ellip_diff:.4f} m" if ellip_diff is not None else None,
            )

            st.info(
                f"✅ La aplicación seleccionará **{height_choice['selected_type']}** "
                f"en este procesamiento."
            )

            for warning in height_choice["warnings"]:
                st.warning("⚠️ " + warning)

        processed_e = report.mobile_e
        processed_n = report.mobile_n
        processed_h = height_choice["selected_h"]

        # Calidad y distancia
        with st.expander("Precisión / calidad reportada por Leica"):
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("CQ 1D", f"{report.cq1d_m:.4f} m" if report.cq1d_m is not None else "—")
            p2.metric("CQ 2D", f"{report.cq2d_m:.4f} m" if report.cq2d_m is not None else "—")
            p3.metric("CQ 3D", f"{report.cq3d_m:.4f} m" if report.cq3d_m is not None else "—")
            p4.metric("M0 Leica", f"{report.m0_m:.4f} m" if report.m0_m is not None else "—")

            st.caption(
                "Los valores CQ y M0 se muestran tal como aparecen en el informe Leica; "
                "no se reinterpretan como un error absoluto independiente del método."
            )

        # Referencia / ERP
        erp_check = st.checkbox(
            f"Marcar '{report.reference_name or 'la referencia'}' como ERP/base IGN",
            value=False,
        )
        if report.distance_m is not None:
            label = (
                "Distancia al ERP/base IGN"
                if erp_check
                else "Distancia geométrica a la referencia del informe"
            )
            st.metric(label, f"{report.distance_m:,.4f} m ({report.distance_m/1000:.4f} km)")

else:
    st.subheader("3. Introducir coordenadas manualmente")

    st.info(
        "Este modo no depende del PDF. Puedes escribir directamente las coordenadas "
        "procesadas/corregidas de la base."
    )

    m1, m2, m3 = st.columns(3)
    processed_e = m1.number_input(
        "Este E", value=float(csv_info.base_original_e), format="%.4f"
    )
    processed_n = m2.number_input(
        "Norte N", value=float(csv_info.base_original_n), format="%.4f"
    )
    processed_h = m3.number_input(
        "Altura H", value=float(csv_info.base_original_h), format="%.4f"
    )

    manual_height_type = st.selectbox(
        "Tipo de altura ingresada",
        ["Ortométrica", "Elipsoidal WGS84", "No especificado"],
    )

    st.caption(
        f"Base detectada en fila 2: **{csv_info.base_name}** · "
        f"E={processed_e:.4f} · N={processed_n:.4f} · H={processed_h:.4f}"
    )

# ------------------------------------------------------------
# Procesar
# ------------------------------------------------------------

st.divider()
st.subheader("5. Generar archivos corregidos")

if st.button("🚀 PROCESAR Y GENERAR LOS 2 CSV", type="primary", use_container_width=True):
    if processed_e is None or processed_n is None or processed_h is None:
        st.error("No hay coordenadas procesadas disponibles.")
        st.stop()

    try:
        corrected_bytes, polygon_bytes, calc = apply_correction(
            csv_info,
            float(processed_e),
            float(processed_n),
            float(processed_h),
        )
    except Exception as exc:
        st.error(f"No se pudo aplicar la corrección: {exc}")
        st.stop()

    st.success("✅ Corrección terminada.")

    x1, x2, x3 = st.columns(3)
    x1.metric("ΔE", f"{calc['delta_e']:+.4f} m")
    x2.metric("ΔN", f"{calc['delta_n']:+.4f} m")
    x3.metric("ΔH", f"{calc['delta_h']:+.4f} m")

    if mode == "📄 Informe Leica (PDF)" and height_choice:
        st.info(
            f"Altura usada para corregir: **{height_choice['selected_type']}** "
            f"({processed_h:.4f} m)."
        )

    # Validación básica del resultado.
    corrected_rows = calc["corrected_rows"]
    nonbase = corrected_rows[1:]

    all_65 = all(
        row.get("Número de Observación", "") == "65"
        for row in nonbase
    )
    if all_65:
        st.success("✅ Número de Observación = 65 aplicado a todos los puntos posteriores a la base.")

    bases_after = sorted(
        set((row.get("Base") or "").strip() for row in nonbase)
    )
    st.caption("Bases existentes después de la generación: " + ", ".join(bases_after))

    original_name = csv_file.name
    corrected_name = corrected_filename(original_name)
    poly_name = polygon_filename(original_name)

    d1, d2 = st.columns(2)
    with d1:
        st.download_button(
            "⬇️ Descargar CSV CORREGIDA",
            data=corrected_bytes,
            file_name=corrected_name,
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Mismo formato y mismas columnas del CSV original.")

    with d2:
        st.download_button(
            "⬇️ Descargar CSV POLIGONO",
            data=polygon_bytes,
            file_name=poly_name,
            mime="text/csv",
            use_container_width=True,
        )
        st.caption("Solo: Nombre, e, n, h, Código.")
