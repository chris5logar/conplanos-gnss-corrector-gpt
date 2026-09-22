from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional


OBSERVATION_VALUE = "65"
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
# V4 - Generador de data derivada desde coordenadas de plano
# ============================================================

@dataclass
class CoordinatePoint:
    e: float
    n: float
    name: Optional[str] = None


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
    else:
        encoding = _detect_encoding(raw_bytes)
        text = raw_bytes.decode(encoding)
        delimiter = _detect_delimiter(text)
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError("El archivo de coordenadas no tiene encabezados.")
        rows = list(reader)

    if not rows:
        raise ValueError("El archivo de coordenadas no contiene filas.")

    fieldnames = list(rows[0].keys())
    e_col = _coordinate_column(fieldnames, ["e", "este", "x", "coordenada x", "east", "eastings"])
    n_col = _coordinate_column(fieldnames, ["n", "norte", "y", "coordenada y", "north", "northings"])
    name_col = _coordinate_column(fieldnames, ["nombre", "punto", "point", "id", "codigo punto"])
    if not e_col or not n_col:
        raise ValueError("No se encontraron las columnas Este/E y Norte/N. El archivo debe contener E/N o X/Y.")

    points: list[CoordinatePoint] = []
    for idx, row in enumerate(rows, start=1):
        e_raw = row.get(e_col)
        n_raw = row.get(n_col)
        if e_raw is None or n_raw is None or str(e_raw).strip() == "" or str(n_raw).strip() == "":
            continue
        try:
            e = float(str(e_raw).replace(",", "").strip())
            n = float(str(n_raw).replace(",", "").strip())
        except ValueError as exc:
            raise ValueError(f"Coordenada inválida en la fila {idx}: E={e_raw!r}, N={n_raw!r}") from exc
        name = str(row.get(name_col)).strip() if name_col and row.get(name_col) not in (None, "") else None
        points.append(CoordinatePoint(e=e, n=n, name=name))

    if not points:
        raise ValueError("No se encontraron coordenadas válidas E/N.")
    return points


def _xy_distance(a_e: float, a_n: float, b_e: float, b_n: float) -> float:
    return ((a_e - b_e) ** 2 + (a_n - b_n) ** 2) ** 0.5


def _idw_height(native_rows: list[dict[str, str]], target_e: float, target_n: float, k: int = 4) -> tuple[float, list[float]]:
    candidates = []
    for row in native_rows:
        try:
            e = float(_decimal(row["e"]))
            n = float(_decimal(row["n"]))
            h = float(_decimal(row["h"]))
        except Exception:
            continue
        d = _xy_distance(target_e, target_n, e, n)
        candidates.append((d, h))
    if not candidates:
        raise ValueError("La data nativa no tiene alturas válidas para interpolar.")
    candidates.sort(key=lambda x: x[0])
    nearest = candidates[: max(1, min(k, len(candidates)))]
    if nearest[0][0] == 0:
        return nearest[0][1], [nearest[0][0]]
    weights = [1.0 / max(d, 1e-9) ** 2 for d, _ in nearest]
    h = sum(w * val for w, (_, val) in zip(weights, nearest)) / sum(weights)
    return h, [d for d, _ in nearest]


def _copy_value_from_nearest(row: dict[str, str], column: str, fallback: str = "") -> str:
    value = row.get(column)
    return fallback if value is None else str(value)


def generate_derived_data(
    csv_info: CSVInfo,
    plan_points: list[CoordinatePoint],
    match_tolerance_m: float = 0.01,
    idw_neighbors: int = 4,
) -> tuple[bytes, dict]:
    """Create a derived GNSS-style CSV from plan E/N points.

    Matching points keep their native row. New points use the nearest native row as
    metadata template, interpolate H with IDW, and retain the plan E/N.
    """
    if match_tolerance_m < 0:
        raise ValueError("La tolerancia no puede ser negativa.")
    native = csv_info.rows
    if not native:
        raise ValueError("La data nativa está vacía.")

    native_xy = []
    for idx, row in enumerate(native):
        try:
            e = float(_decimal(row["e"]))
            n = float(_decimal(row["n"]))
        except Exception:
            continue
        native_xy.append((idx, e, n))

    output_rows: list[dict[str, str]] = []
    matched = 0
    generated = 0
    distances: list[float] = []
    generated_points: list[dict] = []

    # For generated names when the plan file has no name column.
    new_counter = 1

    for point in plan_points:
        nearest_idx, nearest_e, nearest_n = min(
            native_xy,
            key=lambda item: _xy_distance(point.e, point.n, item[1], item[2]),
        )
        distance = _xy_distance(point.e, point.n, nearest_e, nearest_n)
        distances.append(distance)

        if distance <= match_tolerance_m:
            row = dict(native[nearest_idx])
            # Preserve the native coordinates for a true match.
            matched += 1
            output_rows.append(row)
            continue

        template = dict(native[nearest_idx])
        h, interpolation_distances = _idw_height(native, point.e, point.n, k=idw_neighbors)
        new_name = point.name or f"P{new_counter:03d}"
        if not point.name:
            new_counter += 1

        template["Nombre"] = new_name
        template["e"] = _format_decimal(Decimal(str(point.e)), 4)
        template["n"] = _format_decimal(Decimal(str(point.n)), 4)
        template["h"] = _format_decimal(Decimal(str(h)), 4)
        # Keep nearest code, including blank code if the nearest point is blank.
        template["Código"] = _copy_value_from_nearest(native[nearest_idx], "Código", "")
        # Base and observation metadata remain coherent with the native dataset.
        template["Base"] = _copy_value_from_nearest(native[nearest_idx], "Base", csv_info.base_name)
        template["Número de Observación"] = OBSERVATION_VALUE
        generated += 1
        generated_points.append({
            "nombre": new_name,
            "e": point.e,
            "n": point.n,
            "h": h,
            "distancia_vecino_m": distance,
            "codigo": template.get("Código", ""),
            "interpolacion_vecinos_m": interpolation_distances,
        })
        output_rows.append(template)

    out = io.StringIO(newline="")
    writer = csv.DictWriter(
        out,
        fieldnames=csv_info.fieldnames,
        delimiter=csv_info.delimiter,
        lineterminator="\r\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in output_rows:
        writer.writerow({c: row.get(c, "") for c in csv_info.fieldnames})

    return out.getvalue().encode(csv_info.encoding), {
        "input_points": len(plan_points),
        "matched_points": matched,
        "generated_points": generated,
        "max_nearest_distance_m": max(distances) if distances else 0.0,
        "mean_nearest_distance_m": (sum(distances) / len(distances)) if distances else 0.0,
        "generated_detail": generated_points,
        "match_tolerance_m": match_tolerance_m,
        "idw_neighbors": idw_neighbors,
    }


def generated_data_filename(original_name: str) -> str:
    p = Path(original_name)
    stem = re.sub(r"nativo|nativa", "GENERADA", p.stem, flags=re.I)
    if stem == p.stem:
        stem = f"{p.stem} GENERADA"
    return f"{stem}{p.suffix or '.csv'}"
