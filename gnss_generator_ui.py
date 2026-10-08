"""CONPLANOS Generador de data: interfaz compacta sobre los cálculos existentes.

El primer CSV es la plantilla maestra; esta capa solo presenta controles,
resúmenes y descargas. No modifica la interpolación ni el contenido GNSS.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path
import re

import streamlit as st

from core import (
    extract_coordinate_sources,
    generate_derived_data,
    generated_data_filename,
    merge_csv_payloads,
    native_updated,
    read_csv,
    zip_artifacts,
)
from gnss_corrector_ui import _esc, _line, _overrides, _panel, _section, _show_styles, _tiles

UI_VERSION = "10.6.8"


def _generator_source(upload, index):
    raw = upload.getvalue()
    key = f"gen_mapping_{index}_{hashlib.sha256(raw).hexdigest()[:12]}"
    mapping = st.session_state.get(key)
    try:
        return read_csv(raw, column_overrides=mapping)
    except ValueError as exc:
        if "columnas críticas" not in str(exc).casefold():
            raise
        mapping = _overrides(raw, upload.name, key)
        if mapping:
            st.session_state[key] = mapping
            return read_csv(raw, column_overrides=mapping)
        return None


def _row_base_differences(info):
    """Only mobile rows are checked; the first row is the GNSS base."""
    col = info.columns.get("base")
    if not col:
        return []
    mismatches = []
    for line, row in enumerate(info.rows[1:], start=3):
        value = str(row.get(col) or "").strip()
        if value and value.casefold() != info.base_name.casefold():
            mismatches.append((line, str(row.get(info.columns["name"]) or ""), value))
    return mismatches


def _matrix_overview(name, info, count):
    content = '<div class="cp-file">' + _esc(name) + '</div>'
    content += _tiles([("CSV MATRIZ", count), ("REGISTROS", len(info.rows)),
                       ("COLUMNAS", len(info.fieldnames))])
    content += _line("Base del levantamiento", info.base_name)
    content += _section("BASE GNSS DEL CSV · UTM")
    content += _tiles([
        ("ESTE (E)", f"{info.base_original_e:.4f}"),
        ("NORTE (N)", f"{info.base_original_n:.4f}"),
        ("ALTURA", f"{info.base_original_h:.4f} m"),
    ])
    content += _section("CALIDAD DE LA DATA MATRIZ")
    content += _tiles([
        ("FIX", len(info.fixed_points)),
        ("NO FIX", len(info.non_fixed_points)),
        ("FORMATO", f"{len(info.fieldnames)} columnas"),
    ])
    content += '<p class="cp-footnote">El primer CSV determina encabezados, orden y base. La fila base no participa en la evaluación FIX.</p>'
    return _panel("RESUMEN DEL CSV MATRIZ", content)


def _plan_overview(points, diagnostics, source_count):
    detail = '<div class="cp-file">Coordenadas finales del proyecto</div>'
    detail += _tiles([("ARCHIVOS", source_count), ("PUNTOS LEÍDOS", len(points)),
                      ("FUENTES", len({p.source for p in points}))])
    successes = [d for d in diagnostics if not str(d.get("resultado", "")).startswith("ERROR")]
    errors = [d for d in diagnostics if str(d.get("resultado", "")).startswith("ERROR")]
    detail += _line("Archivos interpretados", len(successes))
    detail += _line("Archivos con advertencia", len(errors))
    detail += _section("CRITERIO DE GENERACIÓN")
    detail += _line("Coordenadas", "Este/Norte del plano")
    detail += _line("Altura de puntos nuevos", "TIN / IDW estimada")
    detail += _line("CSV de salida", "Plantilla del primer archivo")
    detail += '<p class="cp-footnote"><b>Dato derivado:</b> las alturas interpoladas no son mediciones GNSS. Los parámetros de calidad no se inventan en puntos nuevos.</p>'
    return _panel("RESUMEN DE COORDENADAS DEL PLANO", detail)


def _alert(label, details, max_items=6):
    if not details:
        return
    items = details[:max_items]
    more = f" y {len(details)-max_items} más" if len(details) > max_items else ""
    st.error(label + ": " + "; ".join(items) + more)


def render_generator():
    """Rediseña únicamente la UI: mantiene las llamadas vigentes a core.py."""
    _show_styles()
    st.markdown(
        '<div class="cp-heading"><h2>Generador de data GNSS</h2>'
        f'<span>CONPLANOS · PLANTILLA NATIVA · V{UI_VERSION}</span></div>',
        unsafe_allow_html=True,
    )
    st.caption("Conserva el formato del CSV matriz y genera puntos derivados desde las coordenadas del plano.")

    # 01 · CSV matriz y resumen, misma estructura que el Corrector GNSS.
    mleft, mright = st.columns([1.35, 1], gap="medium")
    infos = []
    uploads = []
    with mleft:
        st.markdown('<div class="cp-tag">01 · CSV NATIVO MATRIZ</div>', unsafe_allow_html=True)
        st.caption("Carga uno o varios CSV. El primero define todas las columnas de salida.")
        uploads = st.file_uploader(
            "CSV nativo matriz", type=["csv"], accept_multiple_files=True,
            label_visibility="collapsed", key="generator_native_v8",
        )
        for idx, upload in enumerate(uploads or []):
            try:
                csv_info = _generator_source(upload, idx)
                if csv_info:
                    infos.append((upload.name, csv_info))
            except Exception as exc:
                st.error(f"{upload.name}: {exc}")

    base_warnings = []
    has_other_bases = False
    has_nonfix = False
    same_base = False
    if infos:
        same_base = len({info.base_name.casefold() for _, info in infos}) == 1
        for name, info in infos:
            mismatches = _row_base_differences(info)
            if mismatches:
                has_other_bases = True
                base_warnings.extend(
                    f"{name} · fila {line}: {point} usa {value}"
                    for line, point, value in mismatches
                )
            if info.non_fixed_points:
                has_nonfix = True
                states = Counter(v or "Sin estado" for _, v in info.non_fixed_points)
                _alert(
                    f"🔴 {name} · {len(info.non_fixed_points)} móviles sin solución FIX",
                    [f"{state} ({n})" for state, n in states.items()],
                )
    with mright:
        if infos:
            st.markdown(_matrix_overview(infos[0][0], infos[0][1], len(infos)), unsafe_allow_html=True)
        else:
            st.markdown(_panel("RESUMEN DEL CSV MATRIZ", '<p class="cp-footnote">Elige un CSV para conocer la base, coordenadas y calidad del levantamiento.</p>'), unsafe_allow_html=True)

    if infos and not same_base:
        st.error("Las matrices contienen distintas bases GNSS. No se permite generar un único proyecto.")
    if base_warnings:
        _alert("🔴 Referencias GNSS diferentes a la base principal", base_warnings)
    if infos and len(infos) > 1:
        with st.expander("Comparar bases de los CSV cargados", expanded=False):
            st.dataframe([
                {"Archivo": name, "Base GNSS": info.base_name,
                 "Este (m)": info.base_original_e, "Norte (m)": info.base_original_n,
                 "Altura (m)": info.base_original_h}
                for name, info in infos
            ], width="stretch", hide_index=True)

    # 02 · Fuentes de coordenadas de diseño y su propio resumen.
    pleft, pright = st.columns([1.35, 1], gap="medium")
    plans, plan_points, diagnostics = [], [], []
    tolerance = 0.0
    neighbors = 6
    with pleft:
        st.markdown('<div class="cp-tag">02 · COORDENADAS FINALES DEL PLANO</div>', unsafe_allow_html=True)
        st.caption("Admite CSV, Excel, PDF, DOCX e imágenes con coordenadas UTM.")
        plans = st.file_uploader(
            "Coordenadas finales", type=["csv", "xlsx", "xlsm", "pdf", "docx", "png",
                                         "jpg", "jpeg", "webp", "tif", "tiff", "bmp"],
            accept_multiple_files=True, label_visibility="collapsed", key="generator_plan_v8",
        )
        if plans:
            try:
                coords, diagnostics = extract_coordinate_sources(
                    [(f.name, f.getvalue()) for f in plans]
                )
                plan_points = [p for p in coords if p.e is not None and p.n is not None]
            except Exception as exc:
                st.error(f"No se pudieron interpretar las coordenadas: {exc}")
        if plan_points:
            with st.expander(f"Revisar {len(plan_points)} puntos y diagnósticos de lectura", expanded=False):
                st.dataframe([
                    {"Archivo": p.source or "—", "Punto": p.name or "—",
                     "Este (m)": round(p.e, 4), "Norte (m)": round(p.n, 4),
                     "Zona": p.zone or "—"}
                    for p in plan_points
                ], width="stretch", hide_index=True)
                if diagnostics:
                    st.dataframe(diagnostics, width="stretch", hide_index=True)
        if diagnostics:
            failed = [d for d in diagnostics if str(d.get("resultado", "")).startswith("ERROR")]
            if failed:
                _alert("Archivos que requieren revisión", [f"{d.get('archivo')}: {d.get('resultado')}" for d in failed])
        opt_a, opt_b = st.columns(2, gap="small")
        with opt_a:
            tolerance = st.number_input(
                "Coincidencia (m)", min_value=0.0, max_value=1.0, value=0.0,
                step=0.001, format="%.4f", key="gen_tol_v8",
                help="Con 0.0000, las coordenadas deben coincidir exactamente.",
            )
        with opt_b:
            neighbors = st.number_input(
                "Vecinos IDW", min_value=3, max_value=16, value=6, step=1,
                key="gen_neighbors_v8",
                help="Se utiliza IDW cuando no es posible interpolar dentro del TIN.",
            )

    with pright:
        if plans:
            st.markdown(_plan_overview(plan_points, diagnostics, len(plans)), unsafe_allow_html=True)
        else:
            st.markdown(_panel("RESUMEN DEL PLANO", '<p class="cp-footnote">Carga un archivo con coordenadas Este y Norte. Se mostrará la cantidad de puntos y la fuente de cada uno.</p>'), unsafe_allow_html=True)

    # Generar solo con las matrices y los puntos correctamente cargados.
    if base_warnings:
        approved = st.checkbox(
            "He revisado las referencias GNSS diferentes. Comprendo que el generador "
            "no transforma mediciones entre bases distintas.",
            value=False, key="gen_base_review_v1065",
        )
    else:
        approved = True
    if has_nonfix:
        st.warning("La data matriz incluye puntos sin FIX. Revisa estos puntos: el generador no convierte soluciones flotantes en mediciones fijas.")

    # No persistir archivos de otro proyecto si se sustituyen cargas u opciones.
    current_signature = (
        UI_VERSION,  # Prevent downloads generated by older releases from being reused.
        tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (uploads or [])),
        tuple((f.name, hashlib.sha256(f.getvalue()).hexdigest()) for f in (plans or [])),
        float(tolerance), int(neighbors),
    )
    if st.session_state.get("gen_signature_v1065") != current_signature:
        st.session_state["gen_signature_v1065"] = current_signature
        st.session_state.pop("generator_result_v8", None)

    st.markdown('<div class="cp-tag">03 · GENERAR Y DESCARGAR DATA</div>', unsafe_allow_html=True)
    can_generate = bool(infos) and bool(plan_points) and same_base and approved and len(infos) == len(uploads or [])
    if st.button(
        "✓ GENERAR DATA DERIVADA", type="primary", width="stretch",
        disabled=not can_generate, key="generate_data_v8",
    ):
        try:
            native_raws = [f.getvalue() for f in uploads]
            native_joined, _ = merge_csv_payloads(native_raws, require_same_base=True)
            combined_info = read_csv(native_joined)
            generated, summary = generate_derived_data(
                combined_info, plan_points,
                match_tolerance_m=float(tolerance), idw_neighbors=int(neighbors),
            )
            by_source = defaultdict(list)
            for point in plan_points:
                by_source[point.source or "Coordenadas"].append(point)
            separate = []
            for source, coords in by_source.items():
                payload, detail = generate_derived_data(
                    combined_info, coords,
                    match_tolerance_m=float(tolerance), idw_neighbors=int(neighbors),
                )
                safe = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(source).stem)[:70]
                separate.append((safe, payload, generated_data_filename(safe + ".csv"), detail))
            native_updated_joined, _ = native_updated(combined_info)
            bundle = [
                ("DATA_GENERADA_UNIDA.csv", generated),
                ("NATIVA_ACTUALIZADA_UNIDA.csv", native_updated_joined),
            ]
            bundle.extend((f"SEPARADO_{name}.csv", payload) for name, payload, _, _ in separate)
            st.session_state["generator_result_v8"] = {
                "out": generated,
                "summary": summary,
                "separate": separate,
                "native": native_updated_joined,
                "package": zip_artifacts(bundle),
            }
            st.success("Data generada. Los archivos y sus columnas originales están listos.")
        except Exception as exc:
            st.error(f"No se pudo generar la data derivada: {exc}")

    result = st.session_state.get("generator_result_v8")
    if result:
        summary = result["summary"]
        st.markdown(_panel(
            "RESULTADO DEL GENERADOR · DATOS DERIVADOS",
            _tiles([
                ("PUNTOS DE ENTRADA", summary["input_points"]),
                ("COINCIDENTES", summary["matched_points"]),
                ("NUEVOS", summary["generated_points"]),
            ]) + _line("Distancia media al vecino", f"{summary['mean_nearest_distance_m']:.4f} m")
            + _line("Interpolación de alturas", ", ".join(
                f"{k}: {v}" for k, v in summary.get("interpolation_methods", {}).items()
            ) or "Sin puntos nuevos")
            + '<p class="cp-footnote">Alturas generadas = estimaciones TIN/IDW. Nunca presentarlas como lecturas GNSS observadas.</p>'
        ), unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3, gap="small")
        c1.download_button("↓ DATA GENERADA UNIDA", result["out"],
            file_name="CONPLANOS_DATA_GENERADA_UNIDA.csv", mime="text/csv",
            width="stretch", on_click="ignore", key="gen_union_v8")
        c2.download_button("↓ NATIVA ACTUALIZADA", result["native"],
            file_name="CONPLANOS_NATIVA_ACTUALIZADA_UNIDA.csv", mime="text/csv",
            width="stretch", on_click="ignore", key="gen_native_v8")
        c3.download_button("↓ TODO EN ZIP", result["package"],
            file_name="CONPLANOS_GENERADOR_RESULTADOS.zip", mime="application/zip",
            width="stretch", on_click="ignore", key="gen_zip_v8")
        if result["separate"]:
            with st.expander("Descargas separadas por archivo", expanded=False):
                for idx, (name, payload, filename, summary) in enumerate(result["separate"]):
                    st.download_button(f"↓ {name}", payload,
                        file_name=filename, mime="text/csv", width="stretch",
                        on_click="ignore", key=f"gen_sep_{idx}_v8")
        if st.button("Limpiar resultados del generador", key="clear_gen_v8"):
            st.session_state.pop("generator_result_v8", None)
            st.rerun()
