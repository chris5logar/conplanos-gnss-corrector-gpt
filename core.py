from __future__ import annotations

from collections import Counter
import csv
import io
import re
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional
import math
import zipfile


OBSERVATION_VALUE = "60"
HEIGHT_WARNING_M = 40.0


@dataclass
class ReportInfo:
    project: Optional[str] = None
    software: Optional[str] = None
    baseline: Optional[str] = None
    reference_name: Optional[str] = None
    mobile_name: Optional[str] = None

    start: Optional[str] = None
    end: Optional[str] = None
    duration: Optional[str] = None
    processed_at: Optional[str] = None

    reference_e: Optional[float] = None
    reference_n: Optional[float] = None
    reference_h_ellip: Optional[float] = None
    reference_h_ortho: Optional[float] = None

    mobile_e: Optional[float] = None
    mobile_n: Optional[float] = None
    mobile_h_ellip: Optional[float] = None
    mobile_h_ortho: Optional[float] = None

    distance_m: Optional[float] = None

    cq1d_m: Optional[float] = None
    cq2d_m: Optional[float] = None
    cq3d_m: Optional[float] = None
    std_distance_m: Optional[float] = None
    m0_m: Optional[float] = None

    solution_type: Optional[str] = None
    solution_state: Optional[str] = None
    solution_start: Optional[str] = None
    solution_end: Optional[str] = None
    solution_duration: Optional[str] = None

    reference_receiver: Optional[str] = None
    reference_receiver_sn: Optional[str] = None
    mobile_receiver: Optional[str] = None
    mobile_receiver_sn: Optional[str] = None

    reference_antenna: Optional[str] = None
    reference_antenna_sn: Optional[str] = None
    mobile_antenna: Optional[str] = None
    mobile_antenna_sn: Optional[str] = None

    reference_antenna_height_m: Optional[float] = None
    mobile_antenna_height_m: Optional[float] = None
    mobile_lat: Optional[str] = None
    mobile_lon: Optional[str] = None
    utm_zone: Optional[str] = None
    point_code: Optional[str] = None

    raw_pdf_names: list[str] | None = None
    detected_baselines: list[str] | None = None


@dataclass
class CSVInfo:
    encoding: str
    delimiter: str
    fieldnames: list[str]
    rows: list[dict[str, str]]
    base_name: str

    distinct_bases: list[str]
    missing_base_points: list[str]
    different_base_points: list[tuple[str, str]]

    fixed_points: list[str]
    non_fixed_points: list[tuple[str, str]]

    antenna_height_counts: dict[tuple[str, str], int]

    base_original_e: float
    base_original_n: float
    base_original_h: float

    base_csv_antenna: Optional[str] = None
    base_csv_height_m: Optional[float] = None


def _detect_encoding(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            raw.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo identificar la codificación del archivo.")


def _detect_delimiter(text: str) -> str:
    first_line = text.splitlines()[0] if text.splitlines() else ""
    candidates = {
        ",": first_line.count(","),
        ";": first_line.count(";"),
        "\t": first_line.count("\t"),
        "|": first_line.count("|"),
    }
    delimiter = max(candidates, key=candidates.get)
    if candidates[delimiter] == 0:
        return ","
    return delimiter


def _decimal(value: str | None) -> Decimal:
    if value is None or str(value).strip() == "":
        raise ValueError("Se esperaba un número y se encontró un valor vacío.")
    value = str(value).strip().replace(",", "")
    try:
        return Decimal(value)
    except Exception as exc:
        raise ValueError(f"Valor numérico inválido: {value!r}") from exc


def _float_or_none(value: str | None) -> Optional[float]:
    if value is None or not str(value).strip():
        return None
    try:
        return float(str(value).replace(",", "").strip())
    except Exception:
        return None


def _format_decimal(value: Decimal, places: int = 4) -> str:
    quantum = Decimal("1." + ("0" * places)) if places else Decimal("1")
    return format(value.quantize(quantum, rounding=ROUND_HALF_UP), "f")


def _places(value: str | None) -> int:
    value = (value or "").strip()
    if "." not in value:
        return 0
    return len(value.rsplit(".", 1)[1])


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\u00a0", " ")).strip()


def _number_tokens(lines: list[str], label: str, count: int = 2) -> list[float]:
    """Finds numeric values after a label, skipping digits that belong to the label."""
    label_norm = _clean_line(label).casefold()
    for i, line in enumerate(lines):
        current = _clean_line(line)
        if current.casefold().startswith(label_norm):
            values: list[float] = []
            # Only use text after the label on the same line, then subsequent lines.
            same_line_rest = current[len(_clean_line(label)):].strip()
            candidates = []
            if same_line_rest:
                candidates.append(same_line_rest)
            candidates.extend(lines[i + 1 : min(len(lines), i + 9)])

            for candidate in candidates:
                candidate = _clean_line(candidate)
                matches = re.findall(r"[-+]?\d[\d,]*(?:\.\d+)?", candidate)
                for token in matches:
                    try:
                        values.append(float(token.replace(",", "")))
                    except ValueError:
                        pass
                if len(values) >= count:
                    return values[:count]
    return []


def _one_number(lines: list[str], label: str) -> Optional[float]:
    vals = _number_tokens(lines, label, count=1)
    return vals[0] if vals else None


def _first_nonempty_after(lines: list[str], label: str) -> Optional[str]:
    label_norm = _clean_line(label).casefold()
    for i, line in enumerate(lines):
        if _clean_line(line).casefold().startswith(label_norm):
            for candidate in lines[i + 1 : i + 6]:
                candidate = _clean_line(candidate)
                if candidate and not candidate.casefold().startswith("sn"):
                    return candidate
    return None


def parse_report_pdfs(pdf_items) -> ReportInfo:
    """
    pdf_items: iterable of (filename, bytes)
    Supports Leica Infinity 4-page Summary and 19-page Detail-style reports.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError as exc:
        raise RuntimeError(
            "PyMuPDF no está instalado. Ejecute: pip install pymupdf"
        ) from exc

    combined_lines: list[str] = []
    names: list[str] = []

    for name, raw in pdf_items:
        names.append(name)
        doc = fitz.open(stream=raw, filetype="pdf")
        page_texts = [page.get_text("text") for page in doc]
        combined_lines.extend(
            line
            for text in page_texts
            for line in text.splitlines()
            if _clean_line(line)
        )

    lines = [_clean_line(x) for x in combined_lines if _clean_line(x)]
    text = "\n".join(lines)

    info = ReportInfo(raw_pdf_names=names, detected_baselines=[])

    def regex(pattern: str, flags=re.I | re.S):
        m = re.search(pattern, text, flags)
        return m.group(1).strip() if m else None

    info.project = regex(r"Nombre del proyecto:\s*(.+)")
    info.software = regex(r"Software aplicaci[oó]n:\s*(.+)")

    baseline_matches = re.findall(r"L[ií]nea base\s+(.+)", text, re.I)
    info.detected_baselines = []
    for b in baseline_matches:
        b = _clean_line(b)
        if b and b not in info.detected_baselines:
            info.detected_baselines.append(b)

    info.baseline = info.detected_baselines[0] if info.detected_baselines else None
    if info.baseline and " - " in info.baseline:
        info.reference_name, info.mobile_name = [
            _clean_line(x) for x in info.baseline.split(" - ", 1)
        ]
    else:
        info.reference_name = info.baseline

    m = re.search(
        r"Hora Inicio - Hora Fin:\s*"
        r"([0-9]{2}/[0-9]{2}/[0-9]{4}\s+[0-9:]+)\s*-\s*"
        r"([0-9]{2}/[0-9]{2}/[0-9]{4}\s+[0-9:]+)",
        text,
        re.I,
    )
    if m:
        info.start, info.end = m.group(1), m.group(2)

    info.duration = regex(r"Duraci[oó]n:\s*([0-9:]+)")
    info.processed_at = regex(r"Fecha/Hora Procesados:\s*(.+)")

    x = _number_tokens(lines, "Coordenada X:", 2)
    y = _number_tokens(lines, "Coordenada Y:", 2)
    he = _number_tokens(lines, "Altura Elip WGS84:", 2)
    ho = _number_tokens(lines, "Altura Ortom.:", 2)

    if len(x) >= 2:
        info.reference_e, info.mobile_e = x[0], x[1]
    if len(y) >= 2:
        info.reference_n, info.mobile_n = y[0], y[1]
    if len(he) >= 2:
        info.reference_h_ellip, info.mobile_h_ellip = he[0], he[1]
    if len(ho) >= 2:
        info.reference_h_ortho, info.mobile_h_ortho = ho[0], ho[1]

    info.distance_m = _one_number(lines, "Dist. Geom.:")
    # "Desv. Estd. Dist. Geom." is handled by a direct normalized label.
    info.std_distance_m = _one_number(lines, "Desv. Estd. Dist. Geom.:")
    info.m0_m = _one_number(lines, "M0:")
    info.cq1d_m = _one_number(lines, "CQ 1D:")
    info.cq2d_m = _one_number(lines, "CQ 2D:")
    info.cq3d_m = _one_number(lines, "CQ 3D:")

    info.solution_type = _first_nonempty_after(lines, "Tipo de Solución:")
    # Some PDFs contain the label as "Tipo de Solucion" without accent.
    if not info.solution_type:
        info.solution_type = _first_nonempty_after(lines, "Tipo de Solucion:")

    # Estado de la solución final.
    # Infinity puede separar cada encabezado/valor en líneas distintas.
    for i, line in enumerate(lines):
        if line.casefold() == "duración" and i >= 3:
            window = lines[max(0, i - 6): i + 4]
            if "Desde Época" in window or "A Época" in window:
                for j, candidate in enumerate(lines[i + 1: i + 8], start=i + 1):
                    if candidate.casefold() in {"solucionado", "solución", "fijo"}:
                        after = lines[j + 1: j + 4]
                        if len(after) >= 3 and re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$", after[0]):
                            info.solution_state = candidate
                            info.solution_start = after[0]
                            info.solution_end = after[1] if len(after) > 1 else None
                            info.solution_duration = after[2] if len(after) > 2 else None
                            break
        if info.solution_state:
            break

    # Fallback: locate the final occurrence of "Solucionado" followed by
    # two timestamps and a duration.
    if not info.solution_state:
        for i, line in enumerate(lines):
            if line.casefold() == "solucionado":
                after = lines[i + 1: i + 4]
                if (
                    len(after) >= 3
                    and re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$", after[0])
                    and re.match(r"^\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2}$", after[1])
                    and re.match(r"^\d{2}:\d{2}:\d{2}$", after[2])
                ):
                    info.solution_state = "Solucionado"
                    info.solution_start = after[0]
                    info.solution_end = after[1]
                    info.solution_duration = after[2]
        if info.solution_state:
            pass

    # Receptores. El formato estándar de Infinity contiene:
    # TRIMBLE... / SN
    # CHC... / SN
    for i, line in enumerate(lines):
        if line.casefold().startswith("nombre del receptor"):
            vals = []
            for candidate in lines[i + 1 : i + 7]:
                c = _clean_line(candidate)
                if not c or c.casefold().startswith("sn"):
                    continue
                if c.casefold().startswith("nombre de antena"):
                    break
                vals.append(c)
            if len(vals) >= 4:
                info.reference_receiver = vals[0].rstrip("/")
                info.reference_receiver_sn = vals[1]
                info.mobile_receiver = vals[2].rstrip("/")
                info.mobile_receiver_sn = vals[3]
            break

    for i, line in enumerate(lines):
        if line.casefold().startswith("nombre de antena"):
            # e.g. "Nombre de Antena / SN: TRM115000.00 TZGD /"
            first = re.split(r":\s*", line, maxsplit=1)
            first_value = first[1].strip().rstrip("/") if len(first) == 2 else ""
            vals = []
            if first_value:
                vals.append(first_value)
            for candidate in lines[i + 1 : i + 5]:
                c = _clean_line(candidate)
                if not c or c.casefold().startswith("desplazamiento de fase"):
                    break
                vals.append(c)
            if len(vals) >= 3:
                info.reference_antenna = vals[0]
                info.reference_antenna_sn = vals[1]
                info.mobile_antenna = vals[2].split("/")[0].strip()
                if "/" in vals[2]:
                    info.mobile_antenna_sn = vals[2].split("/", 1)[1].strip()
            break

    heights = _number_tokens(lines, "Altura de Antena:", 2)
    if len(heights) >= 2:
        info.reference_antenna_height_m = heights[0]
        info.mobile_antenna_height_m = heights[1]

    # Additional fields used by the point certificate.
    # Leica Infinity places the reference value and mobile value on
    # consecutive PDF text lines. We explicitly select the SECOND value.
    def _second_line_after_label(label: str) -> Optional[str]:
        label_norm = _clean_line(label).casefold()
        for i, line in enumerate(lines):
            if _clean_line(line).casefold().startswith(label_norm):
                vals = []
                for candidate in lines[i + 1 : i + 5]:
                    c = _clean_line(candidate)
                    if c:
                        vals.append(c)
                    if len(vals) >= 2:
                        return vals[1]
        return None

    info.mobile_lat = _second_line_after_label("Latitud WGS84:")
    info.mobile_lon = _second_line_after_label("Longitud WGS84:")

    # Coordinate system can be split across several PDF text lines, so inspect
    # the full report text rather than requiring the label on one line.
    m = re.search(r"WGS84_UTM_(\d{1,2})S", text, re.I)
    if m:
        info.utm_zone = m.group(1)

    # A normal Leica processing report may not contain the final project
    # point code; the certificate UI therefore requests it manually.
    pc = regex(r"(?:C[oó]digo del punto geod[eé]sico|C[oó]digo del punto)\s*:?\s*([A-Za-z0-9_-]+)")
    if pc:
        info.point_code = pc

    return info


def read_csv(raw_bytes: bytes) -> CSVInfo:
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)
    delimiter = _detect_delimiter(text)

    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("El CSV no tiene encabezados.")

    rows = list(reader)

    required = {
        "Nombre",
        "e",
        "n",
        "h",
        "Código",
        "Base",
        "Tipo de Antena",
        "Altura de Antena",
        "Número de Observación",
        "Solución",
    }
    missing = [x for x in required if x not in reader.fieldnames]
    if missing:
        raise ValueError("Faltan columnas requeridas: " + ", ".join(missing))

    if not rows:
        raise ValueError("El CSV no contiene filas.")

    base = rows[0]
    base_name = (base.get("Nombre") or "").strip()
    if not base_name:
        raise ValueError(
            "La fila 2 de Excel (primera fila de datos) no tiene nombre de base."
        )

    distinct_bases: list[str] = []
    missing_base_points: list[str] = []
    different_base_points: list[tuple[str, str]] = []

    for row in rows[1:]:
        point = (row.get("Nombre") or "").strip()
        b = (row.get("Base") or "").strip()
        if not b:
            missing_base_points.append(point)
        elif b not in distinct_bases:
            distinct_bases.append(b)
        if b and b != base_name:
            different_base_points.append((point, b))

    fixed_points: list[str] = []
    non_fixed_points: list[tuple[str, str]] = []
    for row in rows[1:]:
        point = (row.get("Nombre") or "").strip()
        solution = (row.get("Solución") or "").strip()
        if solution.casefold() == "fijo":
            fixed_points.append(point)
        else:
            non_fixed_points.append((point, solution))

    antenna_height_counts: dict[tuple[str, str], int] = {}
    for row in rows[1:]:
        ant = (row.get("Tipo de Antena") or "").strip()
        height = (row.get("Altura de Antena") or "").strip()
        key = (ant, height)
        antenna_height_counts[key] = antenna_height_counts.get(key, 0) + 1

    base_ant = (base.get("Tipo de Antena") or "").strip() or None
    base_height = _float_or_none(base.get("Altura de Antena"))

    return CSVInfo(
        encoding=encoding,
        delimiter=delimiter,
        fieldnames=list(reader.fieldnames),
        rows=rows,
        base_name=base_name,
        distinct_bases=distinct_bases,
        missing_base_points=missing_base_points,
        different_base_points=different_base_points,
        fixed_points=fixed_points,
        non_fixed_points=non_fixed_points,
        antenna_height_counts=antenna_height_counts,
        base_original_e=float(_decimal(base["e"])),
        base_original_n=float(_decimal(base["n"])),
        base_original_h=float(_decimal(base["h"])),
        base_csv_antenna=base_ant,
        base_csv_height_m=base_height,
    )


def choose_height(
    csv_base_h: float,
    report: ReportInfo,
    mode: str = "Automática",
) -> dict:
    candidates = {
        "Ortométrica": report.mobile_h_ortho,
        "Elipsoidal WGS84": report.mobile_h_ellip,
    }
    diffs = {
        name: abs(csv_base_h - value)
        for name, value in candidates.items()
        if value is not None
    }

    if mode == "Ortométrica":
        selected = "Ortométrica"
    elif mode == "Elipsoidal WGS84":
        selected = "Elipsoidal WGS84"
    else:
        if not diffs:
            raise ValueError(
                "El informe no contiene altura ortométrica ni elipsoidal para comparar."
            )
        selected = min(diffs, key=diffs.get)

    selected_h = candidates[selected]
    if selected_h is None:
        raise ValueError(f"El informe no contiene {selected} para el punto móvil.")

    warnings: list[str] = []
    if diffs.get(selected, 0) > HEIGHT_WARNING_M:
        warnings.append(
            f"La diferencia entre H del CSV y la altura {selected.lower()} del informe "
            f"es {diffs[selected]:.4f} m, superior al umbral de {HEIGHT_WARNING_M:.0f} m."
        )

    other = (
        "Elipsoidal WGS84" if selected == "Ortométrica" else "Ortométrica"
    )
    if other in diffs and selected in diffs and diffs[other] > HEIGHT_WARNING_M:
        warnings.append(
            f"La alternativa {other.lower()} difiere {diffs[other]:.4f} m "
            f"respecto del H del CSV."
        )

    if len(diffs) == 2 and abs(diffs["Ortométrica"] - diffs["Elipsoidal WGS84"]) < 1.0:
        warnings.append(
            "Las dos alturas del informe están muy próximas respecto al H del CSV; "
            "se recomienda confirmar manualmente el tipo de altura."
        )

    return {
        "selected_type": selected,
        "selected_h": selected_h,
        "diffs": diffs,
        "warnings": warnings,
    }


def antenna_discrepancy(report: ReportInfo, csv_info: CSVInfo) -> Optional[str]:
    if not report.mobile_antenna or not csv_info.rows:
        return None

    observed = [
        (row.get("Tipo de Antena") or "").strip()
        for row in csv_info.rows[1:]
        if (row.get("Tipo de Antena") or "").strip()
    ]
    unique = sorted(set(observed))
    if not unique:
        return None

    if all(x.casefold() != report.mobile_antenna.casefold() for x in unique):
        return (
            f"El informe Leica indica antena móvil '{report.mobile_antenna}', "
            f"mientras que el CSV contiene: {', '.join(unique)}."
        )
    return None


def apply_correction(
    csv_info: CSVInfo,
    corrected_e: float,
    corrected_n: float,
    corrected_h: float,
) -> tuple[bytes, bytes, dict]:
    """
    Applies a single translation ΔE/ΔN/ΔH to every row.
    Base row is replaced exactly by the corrected coordinates.
    All later rows get Número de Observación = 65.
    """
    de = Decimal(str(corrected_e)) - Decimal(str(csv_info.base_original_e))
    dn = Decimal(str(corrected_n)) - Decimal(str(csv_info.base_original_n))
    dh = Decimal(str(corrected_h)) - Decimal(str(csv_info.base_original_h))

    # Preserve 4 decimals, as in the Leica sample.
    corrected_rows: list[dict[str, str]] = []

    for idx, row in enumerate(csv_info.rows):
        new = dict(row)
        old_e = _decimal(row["e"])
        old_n = _decimal(row["n"])
        old_h = _decimal(row["h"])

        if idx == 0:
            new["e"] = _format_decimal(Decimal(str(corrected_e)), 4)
            new["n"] = _format_decimal(Decimal(str(corrected_n)), 4)
            new["h"] = _format_decimal(Decimal(str(corrected_h)), 4)
        else:
            new["e"] = _format_decimal(old_e + de, 4)
            new["n"] = _format_decimal(old_n + dn, 4)
            new["h"] = _format_decimal(old_h + dh, 4)
            new["Número de Observación"] = OBSERVATION_VALUE

            # Fill a blank Base with the main base name, but keep explicit
            # conflicting values so the discrepancy is visible.
            if not (new.get("Base") or "").strip():
                new["Base"] = csv_info.base_name

        corrected_rows.append(new)

    out1 = io.StringIO(newline="")
    w1 = csv.DictWriter(
        out1,
        fieldnames=csv_info.fieldnames,
        delimiter=csv_info.delimiter,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    w1.writeheader()
    for row in corrected_rows:
        w1.writerow({c: row.get(c, "") for c in csv_info.fieldnames})

    poly_fields = ["Nombre", "e", "n", "h", "Código"]
    out2 = io.StringIO(newline="")
    w2 = csv.DictWriter(
        out2,
        fieldnames=poly_fields,
        delimiter=csv_info.delimiter,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    w2.writeheader()
    for row in corrected_rows:
        w2.writerow({c: row.get(c, "") for c in poly_fields})

    return (
        out1.getvalue().encode(csv_info.encoding),
        out2.getvalue().encode(csv_info.encoding),
        {
            "delta_e": float(de),
            "delta_n": float(dn),
            "delta_h": float(dh),
            "corrected_rows": corrected_rows,
        },
    )


def corrected_filename(original_name: str) -> str:
    p = Path(original_name)
    stem = re.sub(r"nativo|nativa", "CORREGIDA", p.stem, flags=re.I)
    if stem == p.stem:
        stem = f"{p.stem} CORREGIDA"
    return f"{stem}{p.suffix or '.csv'}"


def polygon_filename(original_name: str) -> str:
    p = Path(original_name)
    return f"{p.stem} POLIGONO{p.suffix or '.csv'}"


def csv_point_quality_summary(csv_info: CSVInfo) -> dict:
    rows = csv_info.rows[1:]

    def values(col):
        vals = []
        for row in rows:
            v = _float_or_none(row.get(col))
            if v is not None:
                vals.append(v)
        return vals

    def minmax(col):
        vals = values(col)
        return (min(vals), max(vals)) if vals else (None, None)

    return {
        "rms_error": minmax("RMS Error"),
        "x_precision": minmax("X Precisión"),
        "y_precision": minmax("Y Precisión"),
        "horizontal_error": minmax("Horizontal Error"),
        "vertical_error": minmax("Vertical Error"),
        "pdop": minmax("PDOP"),
        "hdop": minmax("HDOP"),
        "vdop": minmax("VDOP"),
    }


def dataclass_dict(obj):
    return asdict(obj)

# ============================================================
# V8 - Ingreso múltiple, normalización, lectura inteligente e interpolación TIN
# ============================================================

@dataclass
class CoordinatePoint:
    e: float
    n: float
    name: Optional[str] = None
    source: Optional[str] = None
    zone: Optional[int] = None


def _norm_header(value: str) -> str:
    value = (value or "").strip().casefold()
    value = value.replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value


def _coordinate_column(fieldnames: list[str], aliases: list[str]) -> Optional[str]:
    normalized = {_norm_header(f): f for f in fieldnames}
    for alias in aliases:
        key = _norm_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def _parse_flexible_number(value: str) -> float:
    """Parses common decimal/thousands conventions used in Spanish reports."""
    s = str(value).strip().replace("\u00a0", "")
    if not s:
        raise ValueError("Número vacío")
    s = re.sub(r"[^0-9+\-.,]", "", s)
    if "," in s and "." in s:
        # Whichever separator appears last is treated as decimal separator.
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts[-1]) in (1, 2, 3, 4) and len(parts) == 2:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    return float(s)


def _utm_pair(a: float, b: float) -> tuple[float, float] | None:
    """Return (E,N) only when the pair looks like metric UTM coordinates."""
    vals = [float(a), float(b)]
    first_e, first_n = vals
    if 10_000 <= first_e <= 1_000_000 and 1_000_000 <= first_n <= 10_000_000:
        return first_e, first_n
    if 10_000 <= vals[1] <= 1_000_000 and 1_000_000 <= vals[0] <= 10_000_000:
        return vals[1], vals[0]
    return None


def _extract_utm_pairs_from_text(text: str) -> list[CoordinatePoint]:
    """Reads UTM E/N pairs from prose, tables and labeled lines."""
    points: list[CoordinatePoint] = []
    seen: set[tuple[float, float]] = set()
    lines = [_clean_line(x) for x in text.splitlines() if _clean_line(x)]

    # First: explicit labels such as Este: ... / Norte: ... or E=... N=...
    label_patterns = [
        re.compile(r"\b(?:este|easting|este\s*\(?e\)?|x)\b\s*[:=]?\s*([-+]?\d[\d.,]*)", re.I),
        re.compile(r"\b(?:norte|northing|norte\s*\(?n\)?|y)\b\s*[:=]?\s*([-+]?\d[\d.,]*)", re.I),
    ]
    for line in lines:
        em = label_patterns[0].search(line)
        nm = label_patterns[1].search(line)
        if em and nm:
            try:
                e = _parse_flexible_number(em.group(1)); n = _parse_flexible_number(nm.group(1))
                pair = _utm_pair(e, n)
                if pair:
                    key = (round(pair[0], 4), round(pair[1], 4))
                    if key not in seen:
                        seen.add(key)
                        points.append(CoordinatePoint(pair[0], pair[1]))
            except Exception:
                pass

    # Second: any table/prose line containing a UTM-sized pair.
    num_pattern = re.compile(r"[-+]?\d[\d\s.,]*\d|[-+]?\d")
    for line in lines:
        raw_tokens = num_pattern.findall(line)
        if len(raw_tokens) < 2:
            continue
        nums: list[float] = []
        for token in raw_tokens:
            try:
                nums.append(_parse_flexible_number(token))
            except Exception:
                continue
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                pair = _utm_pair(nums[i], nums[j])
                if not pair:
                    continue
                key = (round(pair[0], 4), round(pair[1], 4))
                if key not in seen:
                    seen.add(key)
                    points.append(CoordinatePoint(pair[0], pair[1]))
                break

    return points


def _extract_text_from_docx(raw_bytes: bytes) -> str:
    try:
        from lxml import etree
    except ImportError as exc:
        raise RuntimeError("Se necesita lxml para leer DOCX.") from exc
    with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
        xml = z.read("word/document.xml")
    root = etree.fromstring(xml)
    parts = [t for t in root.xpath("//w:t/text()", namespaces={"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}) if t]
    return "\n".join(parts)


def _extract_text_from_pdf(raw_bytes: bytes) -> str:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF no está instalado.") from exc
    doc = fitz.open(stream=raw_bytes, filetype="pdf")
    return "\n".join(page.get_text("text") for page in doc)


def _ocr_image(raw_bytes: bytes) -> str:
    try:
        import pytesseract
        from PIL import Image, ImageOps, ImageEnhance, ImageFilter
    except ImportError as exc:
        raise RuntimeError("OCR no disponible. Instala pytesseract.") from exc
    image = Image.open(io.BytesIO(raw_bytes)).convert("L")
    image = ImageOps.autocontrast(image)
    image = image.resize((image.width * 2, image.height * 2))
    image = ImageEnhance.Sharpness(image).enhance(1.6)
    image = image.filter(ImageFilter.SHARPEN)
    try:
        return pytesseract.image_to_string(image, lang="spa+eng", config="--psm 6")
    except Exception:
        try:
            return pytesseract.image_to_string(image, lang="eng", config="--psm 6")
        except Exception as exc:
            raise RuntimeError(f"No se pudo ejecutar OCR: {exc}") from exc


def _sheet_rows_to_points(rows: list[dict], fieldnames: list[str], source: str) -> list[CoordinatePoint]:
    e_col = _coordinate_column(fieldnames, ["e", "este", "x", "coordenada x", "east", "easting", "este (e)"])
    n_col = _coordinate_column(fieldnames, ["n", "norte", "y", "coordenada y", "north", "northing", "norte (n)"])
    name_col = _coordinate_column(fieldnames, ["nombre", "punto", "point", "id", "codigo", "codigo punto", "vertice"])
    if not e_col or not n_col:
        raise ValueError(f"{source}: no se encontraron columnas Este/E y Norte/N (o X/Y).")
    out: list[CoordinatePoint] = []
    for idx, row in enumerate(rows, start=1):
        e_raw, n_raw = row.get(e_col), row.get(n_col)
        if e_raw in (None, "") or n_raw in (None, ""):
            continue
        try:
            e = _parse_flexible_number(e_raw)
            n = _parse_flexible_number(n_raw)
        except Exception as exc:
            raise ValueError(f"{source}: coordenada inválida en fila {idx}.") from exc
        out.append(CoordinatePoint(e=e, n=n, name=str(row.get(name_col)).strip() if name_col and row.get(name_col) not in (None, "") else None, source=source))
    if not out:
        raise ValueError(f"{source}: no se encontraron coordenadas válidas.")
    return out


def read_coordinate_points(raw_bytes: bytes, filename: str = "coordenadas.csv") -> list[CoordinatePoint]:
    """Read plan coordinates from CSV or Excel. Expected E/N; name is optional."""
    suffix = Path(filename).suffix.casefold()
    rows: list[dict] = []
    if suffix in {".xlsx", ".xlsm", ".xltx", ".xltm"}:
        try:
            from openpyxl import load_workbook
        except ImportError as exc:
            raise RuntimeError("Para Excel se necesita openpyxl.") from exc
        wb = load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
        ws = wb.active
        iterator = ws.iter_rows(values_only=True)
        try:
            headers = [str(x).strip() if x is not None else "" for x in next(iterator)]
        except StopIteration as exc:
            raise ValueError("El Excel no contiene encabezados.") from exc
        for values in iterator:
            rows.append({headers[i]: values[i] if i < len(values) else None for i in range(len(headers))})
        return _sheet_rows_to_points(rows, headers, filename)

    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding)
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError(f"{filename}: el archivo no tiene encabezados.")
    return _sheet_rows_to_points(list(reader), list(reader.fieldnames), filename)


def _detect_zone_from_text(text: str) -> Optional[int]:
    patterns = [
        r"WGS84[_\s-]*UTM[_\s-]*(\d{1,2})\s*[NS]", r"\bzona\s*(?:utm)?\s*[:\-]?\s*(\d{1,2})\b", r"UTM\s*(?:zona)?\s*(\d{1,2})"
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            z = int(m.group(1))
            if 1 <= z <= 60:
                return z
    return None


def extract_coordinate_sources(sources: list[tuple[str, bytes]]) -> tuple[list[CoordinatePoint], list[dict[str, str]]]:
    """Read multiple coordinate sources: CSV/XLSX, PDF/DOCX and images with OCR."""
    all_points: list[CoordinatePoint] = []
    diagnostics: list[dict[str, str]] = []
    for filename, raw in sources:
        suffix = Path(filename).suffix.casefold()
        try:
            if suffix in {".csv", ".xlsx", ".xlsm", ".xltx", ".xltm"}:
                pts = read_coordinate_points(raw, filename)
                zone = None
                for p in pts:
                    p.zone = zone
                all_points.extend(pts)
                diagnostics.append({"archivo": filename, "resultado": f"{len(pts)} coordenada(s) leída(s)", "método": "Tabla"})
                continue

            if suffix == ".pdf":
                zone = None
                try:
                    report = parse_report_pdfs([(filename, raw)])
                except Exception:
                    report = None
                if report and report.mobile_e is not None and report.mobile_n is not None:
                    point = CoordinatePoint(
                        report.mobile_e, report.mobile_n,
                        name=report.point_code or Path(filename).stem,
                        source=filename,
                        zone=int(report.utm_zone) if report.utm_zone and report.utm_zone.isdigit() else None,
                    )
                    all_points.append(point)
                    diagnostics.append({"archivo": filename, "resultado": "1 coordenada móvil Leica", "método": "Leica/PDF"})
                    continue
                text = _extract_text_from_pdf(raw)
                zone = _detect_zone_from_text(text)
                pts = _extract_utm_pairs_from_text(text)
                for p in pts:
                    p.source = filename
                    p.zone = zone
                    p.name = Path(filename).stem
                if pts:
                    all_points.extend(pts)
                    diagnostics.append({"archivo": filename, "resultado": f"{len(pts)} coordenada(s) leída(s)", "método": "PDF/texto"})
                    continue
                raise ValueError("No se encontraron pares UTM en el texto del PDF.")

            if suffix == ".docx":
                text = _extract_text_from_docx(raw)
                zone = _detect_zone_from_text(text)
                pts = _extract_utm_pairs_from_text(text)
                for p in pts:
                    p.source = filename; p.zone = zone; p.name = Path(filename).stem
                if not pts:
                    raise ValueError("No se encontraron pares UTM en el DOCX.")
                all_points.extend(pts)
                diagnostics.append({"archivo": filename, "resultado": f"{len(pts)} coordenada(s) leída(s)", "método": "DOCX/texto"})
                continue

            if suffix in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
                text = _ocr_image(raw)
                zone = _detect_zone_from_text(text)
                pts = _extract_utm_pairs_from_text(text)
                for p in pts:
                    p.source = filename; p.zone = zone; p.name = Path(filename).stem
                if not pts:
                    raise ValueError("OCR ejecutado, pero no se encontraron pares UTM.")
                all_points.extend(pts)
                diagnostics.append({"archivo": filename, "resultado": f"{len(pts)} coordenada(s) OCR", "método": "OCR"})
                continue

            raise ValueError("Tipo de archivo no soportado.")
        except Exception as exc:
            diagnostics.append({"archivo": filename, "resultado": f"ERROR: {exc}", "método": "—"})

    if not all_points:
        raise ValueError("No se pudo extraer ninguna coordenada. Revisa los formatos o ingrésalas en CSV/Excel.")
    return all_points, diagnostics


def _serialize_rows(rows: list[dict[str, str]], fieldnames: list[str], encoding: str = "utf-8-sig", delimiter: str = ",") -> bytes:
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=fieldnames, delimiter=delimiter, lineterminator="\r\n", extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row.get(c, "") for c in fieldnames})
    return out.getvalue().encode(encoding)


def _normalize_rows(rows: list[dict[str, str]], base_name: str | None = None, start_number: int = 1) -> list[dict[str, str]]:
    if not rows:
        return []
    out = [dict(rows[0])]
    base = base_name or (rows[0].get("Nombre") or "").strip()
    seq = start_number
    for row in rows[1:]:
        new = dict(row)
        new["Nombre"] = str(seq)
        if "Base" in new:
            new["Base"] = base
        if "Número de Observación" in new:
            new["Número de Observación"] = OBSERVATION_VALUE
        if "Método de encuesta" in new:
            new["Método de encuesta"] = "Topográfico"
        out.append(new)
        seq += 1
    return out


def native_updated(csv_info: CSVInfo) -> tuple[bytes, list[dict[str, str]]]:
    rows = _normalize_rows(csv_info.rows, csv_info.base_name)
    return _serialize_rows(rows, csv_info.fieldnames, csv_info.encoding, csv_info.delimiter), rows


def apply_correction(
    csv_info: CSVInfo,
    corrected_e: float,
    corrected_n: float,
    corrected_h: float,
) -> tuple[bytes, bytes, dict]:
    """Apply one translation and then normalize point sequence/observation metadata."""
    de = Decimal(str(corrected_e)) - Decimal(str(csv_info.base_original_e))
    dn = Decimal(str(corrected_n)) - Decimal(str(csv_info.base_original_n))
    dh = Decimal(str(corrected_h)) - Decimal(str(csv_info.base_original_h))

    corrected_rows_raw: list[dict[str, str]] = []
    for idx, row in enumerate(csv_info.rows):
        new = dict(row)
        old_e = _decimal(row["e"]); old_n = _decimal(row["n"]); old_h = _decimal(row["h"])
        if idx == 0:
            new["e"] = _format_decimal(Decimal(str(corrected_e)), 4)
            new["n"] = _format_decimal(Decimal(str(corrected_n)), 4)
            new["h"] = _format_decimal(Decimal(str(corrected_h)), 4)
        else:
            new["e"] = _format_decimal(old_e + de, 4)
            new["n"] = _format_decimal(old_n + dn, 4)
            new["h"] = _format_decimal(old_h + dh, 4)
            new["Base"] = csv_info.base_name
        corrected_rows_raw.append(new)

    corrected_rows = _normalize_rows(corrected_rows_raw, csv_info.base_name)
    corrected_bytes = _serialize_rows(corrected_rows, csv_info.fieldnames, csv_info.encoding, csv_info.delimiter)

    poly_fields = [c for c in ["Nombre", "e", "n", "h", "Código"] if c in csv_info.fieldnames]
    polygon_bytes = _serialize_rows(corrected_rows, poly_fields, csv_info.encoding, csv_info.delimiter)

    return corrected_bytes, polygon_bytes, {
        "delta_e": float(de),
        "delta_n": float(dn),
        "delta_h": float(dh),
        "corrected_rows": corrected_rows,
        "fieldnames": list(csv_info.fieldnames),
        "encoding": csv_info.encoding,
        "delimiter": csv_info.delimiter,
    }


def _xy_distance(a_e: float, a_n: float, b_e: float, b_n: float) -> float:
    return ((a_e - b_e) ** 2 + (a_n - b_n) ** 2) ** 0.5


def _idw_height(native_rows: list[dict[str, str]], target_e: float, target_n: float, k: int = 6) -> tuple[float, list[float], str]:
    candidates = []
    seen = set()
    for row in native_rows:
        try:
            e = float(_decimal(row["e"])); n = float(_decimal(row["n"])); h = float(_decimal(row["h"]))
        except Exception:
            continue
        key = (round(e, 6), round(n, 6))
        if key in seen:
            continue
        seen.add(key)
        d = _xy_distance(target_e, target_n, e, n)
        candidates.append((d, h))
    if not candidates:
        raise ValueError("La data nativa no tiene alturas válidas para interpolar.")
    candidates.sort(key=lambda x: x[0])
    nearest = candidates[: max(1, min(k, len(candidates)))]
    if nearest[0][0] <= 1e-9:
        return nearest[0][1], [nearest[0][0]], "Coincidencia exacta"
    weights = [1.0 / max(d, 1e-9) ** 2 for d, _ in nearest]
    h = sum(w * val for w, (_, val) in zip(weights, nearest)) / sum(weights)
    return h, [d for d, _ in nearest], "IDW fallback"


def _tin_height(native_rows: list[dict[str, str]], target_e: float, target_n: float) -> tuple[float, list[float], str] | None:
    """Piecewise-linear terrain surface over a Delaunay TIN; return None outside hull."""
    try:
        import numpy as np
        from scipy.spatial import Delaunay
    except Exception:
        return None
    pts = []
    seen = set()
    for row in native_rows:
        try:
            e = float(_decimal(row["e"])); n = float(_decimal(row["n"])); h = float(_decimal(row["h"]))
        except Exception:
            continue
        key = (round(e, 6), round(n, 6))
        if key in seen:
            continue
        seen.add(key); pts.append((e, n, h))
    if len(pts) < 3:
        return None
    xy = np.array([[p[0], p[1]] for p in pts], dtype=float)
    z = np.array([p[2] for p in pts], dtype=float)
    try:
        tri = Delaunay(xy)
        simplex = int(tri.find_simplex(np.array([[target_e, target_n]], dtype=float))[0])
        if simplex < 0:
            return None
        transform = tri.transform[simplex]
        delta = np.array([target_e, target_n]) - transform[2]
        bary = np.dot(transform[:2], delta)
        weights = np.r_[bary, 1 - bary.sum()]
        verts = tri.simplices[simplex]
        h = float(np.dot(weights, z[verts]))
        distances = [math.hypot(target_e - xy[i, 0], target_n - xy[i, 1]) for i in verts]
        return h, distances, "TIN lineal"
    except Exception:
        return None


def generate_derived_data(
    csv_info: CSVInfo,
    plan_points: list[CoordinatePoint],
    match_tolerance_m: float = 0.0,
    idw_neighbors: int = 6,
) -> tuple[bytes, dict]:
    """Generate a coherent derived dataset with base first and sequential points.

    Heights use a Delaunay TIN and barycentric linear interpolation when the target
    falls inside the native convex hull; outside it, the method falls back to IDW.
    """
    if match_tolerance_m < 0:
        raise ValueError("La tolerancia no puede ser negativa.")
    if not csv_info.rows:
        raise ValueError("La data nativa está vacía.")
    native = csv_info.rows
    native_xy = []
    for idx, row in enumerate(native):
        try:
            e = float(_decimal(row["e"])); n = float(_decimal(row["n"]))
        except Exception:
            continue
        native_xy.append((idx, e, n))
    if not native_xy:
        raise ValueError("La data nativa no tiene coordenadas E/N válidas.")

    output_rows: list[dict[str, str]] = [dict(native[0])]
    matched = 0; generated = 0; distances: list[float] = []; generated_points: list[dict] = []

    for point in plan_points:
        # If the source itself labels the coordinate as the project base, keep the
        # native base row as the single authoritative base instead of generating a
        # second point from the plan coordinate.
        if point.name and point.name.strip().casefold() == csv_info.base_name.strip().casefold():
            matched += 1
            continue
        nearest_idx, nearest_e, nearest_n = min(native_xy, key=lambda item: _xy_distance(point.e, point.n, item[1], item[2]))
        distance = _xy_distance(point.e, point.n, nearest_e, nearest_n)
        distances.append(distance)
        if distance <= match_tolerance_m:
            if nearest_idx == 0:
                matched += 1
                continue  # base is already present exactly once
            output_rows.append(dict(native[nearest_idx])); matched += 1
            continue

        template = dict(native[nearest_idx])
        tin = _tin_height(native, point.e, point.n)
        if tin is None:
            h, interpolation_distances, method = _idw_height(native, point.e, point.n, k=idw_neighbors)
        else:
            h, interpolation_distances, method = tin
        template["e"] = _format_decimal(Decimal(str(point.e)), 4)
        template["n"] = _format_decimal(Decimal(str(point.n)), 4)
        template["h"] = _format_decimal(Decimal(str(h)), 4)
        template["Base"] = csv_info.base_name
        template["Número de Observación"] = OBSERVATION_VALUE
        template["Método de encuesta"] = "Topográfico"
        generated += 1
        generated_points.append({
            "e": point.e, "n": point.n, "h": h, "distancia_vecino_m": distance,
            "codigo": template.get("Código", ""), "metodo_h": method,
            "interpolacion_vecinos_m": interpolation_distances,
            "fuente": point.source or "",
        })
        output_rows.append(template)

    output_rows = _normalize_rows(output_rows, csv_info.base_name)
    out = _serialize_rows(output_rows, csv_info.fieldnames, csv_info.encoding, csv_info.delimiter)
    methods = Counter(item["metodo_h"] for item in generated_points)
    return out, {
        "input_points": len(plan_points),
        "matched_points": matched,
        "generated_points": generated,
        "max_nearest_distance_m": max(distances) if distances else 0.0,
        "mean_nearest_distance_m": (sum(distances) / len(distances)) if distances else 0.0,
        "generated_detail": generated_points,
        "match_tolerance_m": match_tolerance_m,
        "idw_neighbors": idw_neighbors,
        "interpolation_methods": dict(methods),
    }


def corrected_filename(original_name: str) -> str:
    p = Path(original_name)
    stem = re.sub(r"nativo|nativa", "CORREGIDA", p.stem, flags=re.I)
    if stem == p.stem:
        stem = f"{p.stem} CORREGIDA"
    return f"{stem}{p.suffix or '.csv'}"


def native_updated_filename(original_name: str) -> str:
    p = Path(original_name)
    stem = re.sub(r"nativo|nativa", "NATIVA ACTUALIZADA", p.stem, flags=re.I)
    if stem == p.stem:
        stem = f"{p.stem} NATIVA ACTUALIZADA"
    return f"{stem}{p.suffix or '.csv'}"


def polygon_filename(original_name: str) -> str:
    p = Path(original_name)
    return f"{p.stem} POLIGONO{p.suffix or '.csv'}"


def merged_filename(prefix: str, ext: str = ".csv") -> str:
    return f"{prefix}{ext if ext.startswith('.') else '.' + ext}"


def _csv_payload_rows(raw: bytes) -> tuple[list[dict[str, str]], list[str], str, str]:
    encoding = _detect_encoding(raw)
    text = raw.decode(encoding)
    delimiter = _detect_delimiter(text)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
    if not reader.fieldnames:
        raise ValueError("CSV sin encabezados.")
    return list(reader), list(reader.fieldnames), encoding, delimiter


def merge_csv_payloads(payloads: list[bytes], *, require_same_base: bool = True) -> tuple[bytes, dict]:
    if not payloads:
        raise ValueError("No hay archivos para unir.")
    datasets = [_csv_payload_rows(p) for p in payloads]
    fieldnames: list[str] = []
    for _, cols, _, _ in datasets:
        for c in cols:
            if c not in fieldnames:
                fieldnames.append(c)
    rows_sets = [ds[0] for ds in datasets]
    base_names = [(rows[0].get("Nombre") or "").strip() for rows in rows_sets if rows]
    if require_same_base and len({b.casefold() for b in base_names if b}) > 1:
        raise ValueError("No se pueden unir archivos con bases diferentes. Primero normaliza/usa la misma base.")
    if not rows_sets or not rows_sets[0]:
        raise ValueError("El primer CSV no contiene filas.")
    base_name = base_names[0]
    merged_rows: list[dict[str, str]] = [dict(rows_sets[0][0])]
    for rows in rows_sets:
        merged_rows.extend(dict(r) for r in rows[1:])
    merged_rows = _normalize_rows(merged_rows, base_name)
    encoding, delimiter = datasets[0][2], datasets[0][3]
    return _serialize_rows(merged_rows, fieldnames, encoding, delimiter), {
        "rows": len(merged_rows), "base": base_name, "fieldnames": fieldnames,
        "encoding": encoding, "delimiter": delimiter,
    }


def zip_artifacts(files: list[tuple[str, bytes]]) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for name, payload in files:
            z.writestr(name, payload)
    return out.getvalue()


def csv_point_quality_summary(csv_info: CSVInfo) -> dict:
    rows = csv_info.rows[1:]

    def values(col):
        vals = []
        for row in rows:
            v = _float_or_none(row.get(col))
            if v is not None:
                vals.append(v)
        return vals

    def minmax(col):
        vals = values(col)
        return (min(vals), max(vals)) if vals else (None, None)

    return {
        "rms_error": minmax("RMS Error"),
        "x_precision": minmax("X Precisión"),
        "y_precision": minmax("Y Precisión"),
        "horizontal_error": minmax("Horizontal Error"),
        "vertical_error": minmax("Vertical Error"),
        "pdop": minmax("PDOP"),
        "hdop": minmax("HDOP"),
        "vdop": minmax("VDOP"),
    }


def dataclass_dict(obj):
    return asdict(obj)
