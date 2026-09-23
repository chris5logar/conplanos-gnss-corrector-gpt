from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

GPS_EPOCH = date(1980, 1, 6)

@dataclass
class EphCandidate:
    day: date
    source: str
    label: str
    filename: str
    url: str
    sampling: str
    constellation: str
    status: str = "No comprobado"
    note: str = ""


def gps_week_day(d: date) -> tuple[int, int]:
    days = (d - GPS_EPOCH).days
    return days // 7, days % 7


def gps_week(d: date) -> int:
    return gps_week_day(d)[0]


def doy(d: date) -> int:
    return d.timetuple().tm_yday


def _url_status(url: str, timeout: float = 6.0) -> str:
    try:
        req = Request(url, method="HEAD", headers={"User-Agent": "CONPLANOS-GNSS/7.0"})
        with urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            return "Disponible" if 200 <= code < 300 else f"HTTP {code}"
    except Exception as exc:
        # Some servers reject HEAD but accept GET. Avoid downloading the file;
        # use a range request as a lightweight fallback.
        try:
            req = Request(
                url,
                method="GET",
                headers={"User-Agent": "CONPLANOS-GNSS/7.0", "Range": "bytes=0-64"},
            )
            with urlopen(req, timeout=timeout) as r:
                code = getattr(r, "status", 200)
                return "Disponible" if 200 <= code < 400 else f"HTTP {code}"
        except Exception as exc2:
            msg = str(exc2).lower()
            if "401" in msg or "403" in msg or "unauthorized" in msg or "forbidden" in msg:
                return "Requiere acceso Earthdata"
            return "No disponible / sin respuesta"


def candidates_for_day(d: date) -> list[EphCandidate]:
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"

    # ESA publishes final SP3 at 5-minute sampling from its official
    # Navigation Support Office archive. This is the preferred public link.
    esa_name = f"ESA0OPSFIN_{stamp}_01D_05M_ORB.SP3.gz"
    esa_url = f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}"

    # Official IGS combined final orbit, 15-minute sampling.
    igs_name = f"IGS0OPSFIN_{stamp}_01D_15M_ORB.SP3.gz"
    igs_url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}"

    # Other IGS Analysis Centers with final 5-minute SP3 products.
    centers = [
        ("CODE", "COD0OPSFIN"),
        ("GFZ", "GFZ0OPSFIN"),
        ("GRG", "GRG0OPSFIN"),
        ("JPL", "JPL0OPSFIN"),
    ]

    out = [
        EphCandidate(d, "ESA", "ESA Final · 5 min", esa_name, esa_url, "5 min", "GPS/Galileo/GLONASS/QZSS"),
        EphCandidate(d, "IGS", "IGS Final combinado · 15 min", igs_name, igs_url, "15 min", "GPS"),
    ]
    for label, prefix in centers:
        name = f"{prefix}_{stamp}_01D_05M_ORB.SP3.gz"
        out.append(EphCandidate(d, label, f"{label} Final · 5 min", name, f"https://cddis.nasa.gov/archive/gnss/products/{w}/{name}", "5 min", "Según AC"))
    return out


def find_products(target: date, check: bool = True) -> list[EphCandidate]:
    products: list[EphCandidate] = []
    for delta in (-1, 0, 1):
        d = target + timedelta(days=delta)
        day_products = candidates_for_day(d)
        if check:
            for p in day_products:
                p.status = _url_status(p.url)
        products.extend(day_products)
    return products


def group_by_day(products: list[EphCandidate]) -> dict[date, list[EphCandidate]]:
    out: dict[date, list[EphCandidate]] = {}
    for p in products:
        out.setdefault(p.day, []).append(p)
    return out
