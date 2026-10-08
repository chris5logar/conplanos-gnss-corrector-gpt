"""CONPLANOS CAD export — CPimp v2.5.2 defaults translated to DXF.

The supplied AutoLISP is not executed. Its point/layer/color and path defaults are
reproduced on the server; coordinates come from the CSV semantic column mapping.
Coordinates: DXF X = Easting, Y = Northing, Z = Elevation. GNSS base is not a boundary vertex.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal
import io
import math
import re

import ezdxf

POINT_LAYER = "Pun_TODOS"
POLYGON_LAYER = "pol_TODOS"
TEXT_HEIGHT = 0.04
POINT_MARKER_MODE = 36
POINT_MARKER_SIZE = 1.0
DEFAULT_CONNECTION_MODE = "4"
CONNECTION_MODES = {
    "1": "Orden ID Codigo",
    "2": "Orden ID Global",
    "3": "Cercanos",
    "4": "Linderos (Pista en U)",
    "5": "Ninguno",
}
COLORS = [1, 5, 6, 250, 3, 4, 30, 40, 94, 114, 134, 150,
          164, 194, 214, 224, 12, 22, 42, 52, 62, 82, 102]


def _num(value: str) -> float:
    return float(Decimal(str(value).strip().replace(",", ".")))


def _distance(a, b):
    return math.hypot(a["e"] - b["e"], a["n"] - b["n"])


def _id_key(point):
    text = str(point["name"])
    m = re.search(r"\d+", text)
    return (int(m.group()) if m else float("inf"), text.casefold())


def _nearest_path(points):
    if not points:
        return []
    span_e = max(p["e"] for p in points) - min(p["e"] for p in points)
    span_n = max(p["n"] for p in points) - min(p["n"] for p in points)
    start = (max(points, key=lambda p: p["n"]) if span_n > span_e
             else min(points, key=lambda p: p["e"]))
    result = [start]
    remaining = [p for p in points if p is not start]
    while remaining:
        choice = min(remaining, key=lambda p: _distance(result[-1], p))
        result.append(choice)
        remaining.remove(choice)
    return result


def _two_opt_cycle(points):
    """A bounded 2-opt boundary route, keeping the same starting point."""
    path = list(points)
    n = len(path)
    if n < 4:
        return path
    for _ in range(min(20, n)):
        improvement = False
        for i in range(n-1):
            for j in range(i+2, n):
                if i == 0 and j == n-1:
                    continue
                a, b = path[i], path[(i+1) % n]
                c, d = path[j], path[(j+1) % n]
                old = _distance(a, b) + _distance(c, d)
                new = _distance(a, c) + _distance(b, d)
                if new < old - 1e-5:
                    path[i+1:j+1] = reversed(path[i+1:j+1])
                    improvement = True
        if not improvement:
            break
    return path


def create_cpimp_dxf(csv_info, corrected_rows: list[dict[str, str]],
                     connection_mode: str = DEFAULT_CONNECTION_MODE,
                     text_height: float = TEXT_HEIGHT) -> bytes:
    """Build a valid DXF from semantically identified E/N/H columns, not fixed positions."""
    if connection_mode not in CONNECTION_MODES:
        raise ValueError("Modo de conexión CAD inválido.")
    if not 0 < text_height <= 100:
        raise ValueError("Altura de texto CAD inválida.")
    columns = csv_info.columns
    for required in ("name", "e", "n", "h"):
        if required not in columns:
            raise ValueError(f"No se pudo identificar {required} para DXF.")
    name_col, east_col, north_col, height_col = (columns[x] for x in ("name", "e", "n", "h"))
    code_col = columns.get("code")
    points = []
    # Exclude the RTK base; it is not a polygon vertex and must not distort the boundary.
    for row_num, row in enumerate(corrected_rows[1:], start=3):
        try:
            e = _num(row[east_col]); n = _num(row[north_col]); h = _num(row[height_col])
            if not all(math.isfinite(v) for v in (e, n, h)):
                raise ValueError("Coordenada no finita")
        except (ValueError, TypeError, KeyError) as exc:
            raise ValueError(f"Coordenadas CAD inválidas en fila CSV {row_num}: {exc}") from exc
        points.append({
            "name": str(row.get(name_col) or row_num-2),
            "e": e, "n": n, "h": h,
            "code": str(row.get(code_col) or "PUNTO").strip() if code_col else "PUNTO",
        })
    if not points:
        raise ValueError("No hay puntos móviles para dibujar en CAD.")

    doc = ezdxf.new("R2010")
    doc.header["$PDMODE"] = POINT_MARKER_MODE
    doc.header["$PDSIZE"] = POINT_MARKER_SIZE
    doc.layers.add(POINT_LAYER, color=8)
    doc.layers.add(POLYGON_LAYER, color=8)
    ms = doc.modelspace()
    groups = defaultdict(list)
    for pt in points:
        groups[pt["code"] or "PUNTO"].append(pt)
    for index, (code, group) in enumerate(groups.items()):
        aci = COLORS[index % len(COLORS)]
        for pt in group:
            xyz = (pt["e"], pt["n"], pt["h"])
            ms.add_point(xyz, dxfattribs={"layer": POINT_LAYER, "color": aci})
            ms.add_text(pt["name"], dxfattribs={
                "height": text_height, "layer": POINT_LAYER, "color": 250,
                "insert": (pt["e"] + text_height * 0.5,
                           pt["n"] + text_height * 0.5, pt["h"]),
            })
            ms.add_text(code, dxfattribs={
                "height": text_height, "layer": POINT_LAYER, "color": 250,
                "insert": (pt["e"] + text_height * 0.5,
                           pt["n"] - text_height * 0.5, pt["h"]),
            })
        if connection_mode in ("1", "3", "4") and len(group) > 1:
            order = (sorted(group, key=_id_key) if connection_mode == "1"
                     else _nearest_path(group))
            if connection_mode == "4":
                order = _two_opt_cycle(order)
            ms.add_lwpolyline(
                [(p["e"], p["n"]) for p in order],
                close=(connection_mode == "4" and len(order) >= 3),
                dxfattribs={
                    "layer": POLYGON_LAYER, "color": aci,
                    "elevation": order[0]["h"],
                },
            )
    if connection_mode == "2" and len(points) > 1:
        ordered = sorted(points, key=_id_key)
        ms.add_lwpolyline(
            [(p["e"], p["n"]) for p in ordered],
            dxfattribs={"layer": POLYGON_LAYER, "color": 250,
                         "elevation": ordered[0]["h"]},
        )
    sink = io.StringIO()
    doc.write(sink)
    return sink.getvalue().encode("utf-8")
