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
    "informe_leica", "certificado_pdf", "certificado_word",
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


def _worksheet():
    import gspread
    from google.oauth2.service_account import Credentials

    sheet_id, account = _get_config()
    if not sheet_id or not account:
        raise RuntimeError("Google Sheets aún no está configurado en Streamlit Secrets.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
    creds = Credentials.from_service_account_info(dict(account), scopes=scopes)
    client = gspread.authorize(creds)
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet("Puntos")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Puntos", rows=1000, cols=len(HEADERS))
    values = ws.get_all_values()
    if not values:
        ws.append_row(HEADERS)
    elif values[0][:len(HEADERS)] != HEADERS:
        # Only add headers to a completely empty sheet; never overwrite user data.
        if not any(values[0]):
            ws.update("A1", [HEADERS])
    return ws


def append_point(record: dict[str, Any]) -> None:
    ws = _worksheet()
    row = [record.get(h, "") for h in HEADERS]
    ws.append_row(row, value_input_option="USER_ENTERED")


def load_points() -> list[dict[str, str]]:
    ws = _worksheet()
    rows = ws.get_all_records()
    return [dict(r) for r in rows]


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
