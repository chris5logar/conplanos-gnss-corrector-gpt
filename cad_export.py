"""Exportación CAD CONPLANOS. Parámetros de CPimp v2.5.2 (modo 4 por defecto)."""
from __future__ import annotations

import io
import math

TEXT_HEIGHT = 0.04
POINT_LAYER = "Pun_TODOS"
POLYGON_LAYER = "pol_TODOS"
ACI_PALETTE = (1, 5, 6, 250, 3, 4, 30, 40, 94, 114, 134, 150, 164, 194, 214, 224, 12, 22, 42, 52, 62, 82, 102)


def _distance(a, b):
    return math.hypot(a["e"] - b["e"], a["n"] - b["n"])


def _optimize_path(points):
    """2-opt de rutas abiertas, coherente con el menú CPimp Linderos."""
    pts = list(points)
    if len(pts) < 4:
        return pts
    changed = True
    while changed:
        changed = False
        for i in range(len(pts) - 2):
            for j in range(i + 2, len(pts) - 1):
                before = _distance(pts[i], pts[i + 1]) + _distance(pts[j], pts[j + 1])
                after = _distance(pts[i], pts[j]) + _distance(pts[i + 1], pts[j + 1])
                if after < before - 0.00001:
                    pts[i + 1:j + 1] = reversed(pts[i + 1:j + 1])
                    changed = True
    return pts


def _linderos(points):
    """Pista en U: extremo norte si extensión N-S domina, extremo oeste en otro caso."""
    pts = list(points)
    if len(pts) < 2:
        return pts
    span_e = max(p["e"] for p in pts) - min(p["e"] for p in pts)
    span_n = max(p["n"] for p in pts) - min(p["n"] for p in pts)
    start = max(pts, key=lambda p: p["n"]) if span_n > span_e else min(pts, key=lambda p: p["e"])
    route = [start]
    remaining = [p for p in pts if p is not start]
    while remaining:
        neighbor = min(remaining, key=lambda p: _distance(route[-1], p))
        route.append(neighbor)
        remaining.remove(neighbor)
    return _optimize_path(route)


def export_corrected_dxf(csv_info, *, text_height=TEXT_HEIGHT, connection_mode="Linderos") -> bytes:
    """Puntos XYZ y polilíneas 2D en X=ESTE/Y=NORTE. Excluye la base (fila 1).

    Respeta columnas semánticas del CSV original; no asume posiciones fijas.
    CPimp v2.5.2: capas Pun_TODOS/pol_TODOS, texto 0.04, opción 4 Linderos,
    colores por código y polilíneas abiertas.
    """
    try:
        import ezdxf
    except ImportError as exc:
        raise RuntimeError("Se requiere ezdxf para exportar CAD.") from exc

    from core import _decimal
    cols = csv_info.columns
    required = ("e", "n", "h", "name")
    if any(not cols.get(x) for x in required):
        raise ValueError("No se identificaron E, N, H o nombre en el CSV corregido.")

    groups = {}
    for line_number, row in enumerate(csv_info.rows[1:], start=3):
        try:
            e = float(_decimal(row[cols["e"]]))
            n = float(_decimal(row[cols["n"]]))
            h = float(_decimal(row[cols["h"]]))
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Fila CSV {line_number}: coordenadas no válidas para CAD.") from exc
        if not all(math.isfinite(v) for v in (e, n, h)):
            raise ValueError(f"Fila CSV {line_number}: coordenadas no finitas.")
        name = str(row.get(cols["name"], "")).strip() or str(line_number - 2)
        code_col = cols.get("code")
        code = str(row.get(code_col, "") or "").strip() if code_col else ""
        code = code or "PUNTO"
        groups.setdefault(code, []).append({"e": e, "n": n, "h": h, "name": name, "code": code})

    doc = ezdxf.new("R2010")
    doc.layers.new(POINT_LAYER, dxfattribs={"color": 8})
    doc.layers.new(POLYGON_LAYER, dxfattribs={"color": 8})
    msp = doc.modelspace()
    # CPimp establece PDMODE=36 y PDSIZE=1.
    doc.header["$PDMODE"] = 36
    doc.header["$PDSIZE"] = 1.0
    for color_idx, (code, points) in enumerate(groups.items()):
        color = ACI_PALETTE[color_idx % len(ACI_PALETTE)]
        for p in points:
            xyz = (p["e"], p["n"], p["h"])
            msp.add_point(xyz, dxfattribs={"layer": POINT_LAYER, "color": color})
            # Coincide con los desplazamientos CPimp: +0.5h/+0.5h y +0.5h/-0.5h.
            msp.add_text(p["name"], dxfattribs={"layer": POINT_LAYER, "color": 250,
                "height": text_height, "insert": (p["e"] + text_height * 0.5,
                                              p["n"] + text_height * 0.5, p["h"])})
            msp.add_text(code, dxfattribs={"layer": POINT_LAYER, "color": 250,
                "height": text_height, "insert": (p["e"] + text_height * 0.5,
                                              p["n"] - text_height * 0.5, p["h"])})
        if len(points) > 1 and connection_mode != "Ninguno":
            if connection_mode == "Linderos":
                ordered = _linderos(points)
            elif connection_mode == "Orden ID Codigo":
                ordered = sorted(points, key=lambda p: (0, int(p["name"])) if p["name"].isdigit() else (1, p["name"]))
            else:
                ordered = list(points)
            # CPimp default: polilínea abierta (no cerramos el predio sin autorización).
            msp.add_lwpolyline([(p["e"], p["n"]) for p in ordered],
                               format="xy", close=False,
                               dxfattribs={"layer": POLYGON_LAYER, "color": color,
                                           "elevation": ordered[0]["h"]})
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
