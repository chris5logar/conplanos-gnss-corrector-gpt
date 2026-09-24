from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

GPS_EPOCH = date(1980, 1, 6)
UTC = timezone.utc
LIMA = ZoneInfo("America/Lima")


@dataclass
class EphCandidate:
    day: date                 # requested observation day covered by this product
    source: str
    label: str
    filename: str
    url: str
    sampling: str
    constellation: str
    kind: str                 # Final / Rapid / Ultra-Rapid
    priority: int
    status: str = "No comprobado"
    note: str = ""
    coverage_start: datetime | None = None
    coverage_end: datetime | None = None


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_lima() -> datetime:
    return datetime.now(LIMA)


def today_lima() -> date:
    return now_lima().date()


def gps_week_day(d: date) -> tuple[int, int]:
    days = (d - GPS_EPOCH).days
    return days // 7, days % 7


def gps_week(d: date) -> int:
    return gps_week_day(d)[0]


def doy(d: date) -> int:
    return d.timetuple().tm_yday


def _looks_like_gzip(blob: bytes) -> bool:
    return blob[:2] == b"\x1f\x8b"


def _url_status(url: str, timeout: float = 8.0) -> str:
    """Verify the actual product, not just an HTTP 200 landing/error page.

    Some GNSS archives return an HTML page with HTTP 200 when a file is absent
    or authentication is required. We therefore validate both the response
    headers and the first bytes of the requested .gz file.
    """
    try:
        req = Request(
            url,
            method="GET",
            headers={
                "User-Agent": "CONPLANOS-GNSS/10.3",
                "Range": "bytes=0-127",
                "Accept": "application/gzip, application/octet-stream, */*",
            },
        )
        with urlopen(req, timeout=timeout) as r:
            code = getattr(r, "status", 200)
            ctype = (r.headers.get("Content-Type") or "").lower()
            blob = r.read(128)

            if code not in (200, 206):
                if code in (401, 403):
                    return "Requiere acceso Earthdata"
                return f"HTTP {code}"

            if _looks_like_gzip(blob):
                return "Disponible"

            # A valid GNSS .SP3.gz may be served as octet-stream, but an HTML
            # login/error page is never a valid product.
            if "text/html" in ctype or blob.lstrip().lower().startswith((b"<!doctype html", b"<html", b"<head")):
                return "No disponible / respuesta HTML"
            return "No confirmado: contenido no es SP3.gz"
    except Exception as exc:
        msg = str(exc).lower()
        if any(token in msg for token in ("401", "403", "unauthorized", "forbidden")):
            return "Requiere acceso Earthdata"
        return "No disponible / sin respuesta"


def _final_candidates_for_day(d: date) -> list[EphCandidate]:
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"

    esa_name = f"ESA0OPSFIN_{stamp}_01D_05M_ORB.SP3.gz"
    esa_url = f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}"

    igs_name = f"IGS0OPSFIN_{stamp}_01D_15M_ORB.SP3.gz"
    igs_url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}"

    out = [
        EphCandidate(d, "ESA", "ESA Final · 5 min", esa_name, esa_url, "5 min", "GPS/Galileo/GLONASS/QZSS", "Final", 10),
        EphCandidate(d, "IGS", "IGS Final combinado · 15 min", igs_name, igs_url, "15 min", "GPS", "Final", 11),
    ]

    centers = [
        ("CODE", "COD0OPSFIN"),
        ("GFZ", "GFZ0OPSFIN"),
        ("GRG", "GRG0OPSFIN"),
        ("JPL", "JPL0OPSFIN"),
    ]
    for label, prefix in centers:
        name = f"{prefix}_{stamp}_01D_05M_ORB.SP3.gz"
        url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{name}"
        out.append(EphCandidate(d, label, f"{label} Final · 5 min", name, url, "5 min", "Según AC", "Final", 20 + centers.index((label, prefix))))
    return out


def _rapid_candidate(d: date) -> EphCandidate:
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"
    name = f"IGS0OPSRAP_{stamp}_01D_15M_ORB.SP3.gz"
    url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{name}"
    return EphCandidate(d, "IGS", "IGS Rapid combinado · 15 min", name, url, "15 min", "GPS", "Rapid", 30)


def _ultra_starts_around_now() -> list[datetime]:
    now = now_utc()
    base_hour = (now.hour // 6) * 6
    base = datetime.combine(now.date(), time(base_hour, tzinfo=UTC))
    # Search recent releases first. The newest available file that covers the
    # requested date is the most relevant ultra-rapid product.
    return [base - timedelta(hours=6 * i) for i in range(0, 10)]


def _ultra_candidate_for_start(start: datetime, requested_day: date) -> EphCandidate:
    sdate = start.date()
    w = gps_week(sdate)
    stamp = f"{sdate.year:04d}{doy(sdate):03d}{start.hour:02d}00"
    name = f"IGS0OPSULT_{stamp}_02D_15M_ORB.SP3.gz"
    url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{name}"
    coverage_start = start
    coverage_end = start + timedelta(hours=48) - timedelta(minutes=15)

    day_start = datetime.combine(requested_day, time(0, tzinfo=UTC))
    day_end = day_start + timedelta(days=1) - timedelta(minutes=15)
    overlap_start = max(coverage_start, day_start)
    overlap_end = min(coverage_end, day_end)

    if overlap_start > overlap_end:
        note = "No cubre la fecha solicitada"
    elif overlap_start >= coverage_start and overlap_end <= coverage_start + timedelta(hours=24):
        note = "Cobertura observada para la fecha solicitada"
    elif overlap_start >= coverage_start + timedelta(hours=24):
        note = "Cobertura predicha para la fecha solicitada"
    else:
        note = "Cobertura mixta: observada + predicha"

    return EphCandidate(
        requested_day,
        "IGS",
        "IGS Ultra-Rapid · 15 min",
        name,
        url,
        "15 min",
        "GPS",
        "Ultra-Rapid",
        40,
        coverage_start=coverage_start,
        coverage_end=coverage_end,
        note=note,
    )


def find_best_for_day(target: date, check: bool = True) -> tuple[EphCandidate | None, list[EphCandidate]]:
    """Return the best currently verifiable product for the requested day.

    Priority: Final -> Rapid -> Ultra-Rapid. Only a real product response is
    accepted; URL patterns alone are never treated as availability.
    """
    alternatives: list[EphCandidate] = []

    # Final products: exact file for the requested day.
    finals = _final_candidates_for_day(target)
    if check:
        for p in finals:
            p.status = _url_status(p.url)
    alternatives.extend(finals)
    available_finals = [p for p in finals if p.status == "Disponible"]
    if available_finals:
        available_finals.sort(key=lambda p: p.priority)
        return available_finals[0], alternatives

    # Rapid: exact day. The server check determines whether it has really been released.
    rapid = _rapid_candidate(target)
    if check:
        rapid.status = _url_status(rapid.url)
    alternatives.append(rapid)
    if rapid.status == "Disponible":
        return rapid, alternatives

    # Ultra-Rapid: find an actually available 48-hour file that covers the target day.
    ultras: list[EphCandidate] = []
    for start in _ultra_starts_around_now():
        cand = _ultra_candidate_for_start(start, target)
        day_start = datetime.combine(target, time(0, tzinfo=UTC))
        day_end = day_start + timedelta(days=1) - timedelta(minutes=15)
        if cand.coverage_start and cand.coverage_start <= day_end and cand.coverage_end and cand.coverage_end >= day_start:
            if check:
                cand.status = _url_status(cand.url)
            ultras.append(cand)

    alternatives.extend(ultras)
    available_ultras = [p for p in ultras if p.status == "Disponible"]
    if available_ultras:
        available_ultras.sort(key=lambda p: p.coverage_start or datetime.min.replace(tzinfo=UTC), reverse=True)
        return available_ultras[0], alternatives

    return None, alternatives


def find_products(target: date, check: bool = True) -> list[EphCandidate]:
    """Return one recommended real product per day for target-1, target, target+1."""
    out: list[EphCandidate] = []
    for delta in (-1, 0, 1):
        d = target + timedelta(days=delta)
        best, alternatives = find_best_for_day(d, check=check)
        if best is not None:
            out.append(best)
        else:
            # Preserve an explicit marker so the UI can explain that nothing
            # has been released/verified yet rather than inventing a URL.
            out.append(
                EphCandidate(
                    d,
                    "—",
                    "Sin producto verificado",
                    "",
                    "",
                    "",
                    "",
                    "Sin disponibilidad",
                    99,
                    status="Sin producto",
                    note="No se verificó ningún Final, Rapid o Ultra-Rapid disponible que cubra esta fecha en este momento.",
                )
            )
    return out


def group_by_day(products: list[EphCandidate]) -> dict[date, list[EphCandidate]]:
    out: dict[date, list[EphCandidate]] = {}
    for p in products:
        out.setdefault(p.day, []).append(p)
    return out
