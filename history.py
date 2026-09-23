from __future__ import annotations

from datetime import datetime
from typing import Any

import streamlit as st

HEADERS = [
    "fecha_registro", "codigo", "solicitante", "norte", "este", "zona",
    "latitud", "longitud", "alt_ellipsoidal", "estacion_gnss",
    "fecha_posicion", "fecha_emision", "anio", "tipo_orden", "correlativo",
    "solucion", "duracion_lectura", "distancia_m", "cq1d_m", "cq2d_m",
    "cq3d_m", "m0_m", "receptor_movil", "antena_movil", "altura_antena_movil",
    "informe_leica", "certificado_pdf", "certificado_word", "origen",
]

EXTERNAL_HEADERS = [
    "fecha_registro", "codigo", "nombre", "norte", "este", "zona",
    "latitud", "longitud", "altura", "fuente", "tipo", "observacion",
]


def _get_config():
    try:
        sheet_id = st.secrets.get("GOOGLE_SHEET_ID", "")
        account = st.secrets.get("gcp_service_account")
        return sheet_id, account
    except Exception:
        return "", None


def configured() -> bool:
    sheet_id, account = _get_config()
    return bool(sheet_id and account)


def _client_and_sheet():
    import gspread
    from google.oauth2.service_account import Credentials

    sheet_id, account = _get_config()
    if not sheet_id or not account:
        raise RuntimeError("Google Sheets aún no está configurado en Streamlit Secrets.")
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(dict(account), scopes=scopes)
    client = gspread.authorize(creds)
    return client, client.open_by_key(sheet_id)


def _ensure_headers(ws, headers):
    values = ws.get_all_values()
    if not values:
        if ws.col_count < len(headers):
            ws.resize(cols=len(headers))
        ws.append_row(headers)
        return
    current = list(values[0])
    # Backward compatible: keep existing columns, append any new V8 fields.
    for header in headers:
        if header not in current:
            current.append(header)
            if ws.col_count < len(current):
                ws.resize(cols=len(current))
            ws.update_cell(1, len(current), header)


def _worksheet():
    _, sh = _client_and_sheet()
    try:
        ws = sh.worksheet("Puntos")
    except Exception:
        ws = sh.add_worksheet(title="Puntos", rows=1000, cols=max(30, len(HEADERS)))
    _ensure_headers(ws, HEADERS)
    return ws


def _external_worksheet():
    _, sh = _client_and_sheet()
    try:
        ws = sh.worksheet("OtrosPuntos")
    except Exception:
        ws = sh.add_worksheet(title="OtrosPuntos", rows=1000, cols=len(EXTERNAL_HEADERS))
    _ensure_headers(ws, EXTERNAL_HEADERS)
    return ws


def append_point(record: dict[str, Any]) -> None:
    ws = _worksheet()
    # Respect the sheet's current header order to remain compatible with V7.
    headers = ws.row_values(1)
    row = [record.get(h, "") for h in headers]
    ws.append_row(row, value_input_option="USER_ENTERED")


def load_points() -> list[dict[str, str]]:
    ws = _worksheet()
    return [dict(r) for r in ws.get_all_records()]


def append_external_points(records: list[dict[str, Any]]) -> None:
    if not records:
        return
    ws = _external_worksheet()
    headers = ws.row_values(1)
    rows = [[r.get(h, "") for h in headers] for r in records]
    ws.append_rows(rows, value_input_option="USER_ENTERED")


def load_external_points() -> list[dict[str, str]]:
    ws = _external_worksheet()
    return [dict(r) for r in ws.get_all_records()]


def make_record(data, report, report_filename: str, pdf_name: str = "", word_name: str = "") -> dict[str, Any]:
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    return {
        "fecha_registro": now,
        "codigo": data.codigo,
        "solicitante": data.solicitante,
        "norte": data.norte,
        "este": data.este,
        "zona": data.zona,
        "latitud": data.latitud,
        "longitud": data.longitud,
        "alt_ellipsoidal": data.alt_ellipsoidal,
        "estacion_gnss": data.estacion_gnss,
        "fecha_posicion": data.fecha_posicion,
        "fecha_emision": data.fecha_emision,
        "anio": data.anio,
        "tipo_orden": data.tipo_orden,
        "correlativo": data.correlativo,
        "solucion": getattr(report, "solution_type", "") or getattr(report, "solution_state", ""),
        "duracion_lectura": getattr(report, "duration", "") or getattr(report, "solution_duration", ""),
        "distancia_m": getattr(report, "distance_m", "") or "",
        "cq1d_m": getattr(report, "cq1d_m", "") or "",
        "cq2d_m": getattr(report, "cq2d_m", "") or "",
        "cq3d_m": getattr(report, "cq3d_m", "") or "",
        "m0_m": getattr(report, "m0_m", "") or "",
        "receptor_movil": getattr(report, "mobile_receiver", "") or "",
        "antena_movil": getattr(report, "mobile_antenna", "") or "",
        "altura_antena_movil": getattr(report, "mobile_antenna_height_m", "") or "",
        "informe_leica": report_filename,
        "certificado_pdf": pdf_name,
        "certificado_word": word_name,
        "origen": "Certificado CONPLANOS",
    }


def make_external_record(*, codigo: str, nombre: str, norte: float, este: float, zona: str, latitud: float, longitud: float, altura: str = "", fuente: str = "", observacion: str = "") -> dict[str, Any]:
    return {
        "fecha_registro": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
        "codigo": codigo,
        "nombre": nombre,
        "norte": norte,
        "este": este,
        "zona": zona,
        "latitud": latitud,
        "longitud": longitud,
        "altura": altura,
        "fuente": fuente,
        "tipo": "Punto externo",
        "observacion": observacion,
    }


def dms_to_decimal(value: str) -> float | None:
    """Convert Leica DMS text such as 13° 40' 51.24909'' S to decimal degrees."""
    if not value:
        return None
    import re
    s = str(value).strip().replace('º', '°').replace('’', "'").replace('”', '"').replace('″', '"')
    m = re.search(r"([+-]?\d+(?:\.\d+)?)\D+([0-9]+(?:\.\d+)?)\D+([0-9]+(?:\.\d+)?)", s)
    if not m:
        try:
            return float(s)
        except Exception:
            return None
    deg, minute, sec = map(float, m.groups())
    out = abs(deg) + minute / 60 + sec / 3600
    if re.search(r"[SW]\s*$", s, re.I) or deg < 0:
        out *= -1
    return out
