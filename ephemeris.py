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


def _rapid_candidates_for_day(d: date) -> list[EphCandidate]:
    """Return Rapid orbit candidates from public/official sources.

    ESA publishes its IGS Analysis Center Rapid orbit directly from its public
    GNSS products service, while the IGS combined Rapid product is archived at
    CDDIS.  We check both instead of relying only on the combined CDDIS file.
    """
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"
    esa_name = f"ESA0OPSRAP_{stamp}_01D_15M_ORB.SP3.gz"
    esa_url = f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}"
    igs_name = f"IGS0OPSRAP_{stamp}_01D_15M_ORB.SP3.gz"
    igs_url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}"
    return [
        EphCandidate(d, "ESA", "ESA Rapid · 15 min", esa_name, esa_url, "15 min", "GPS/Galileo/GLONASS", "Rapid", 30),
        EphCandidate(d, "IGS", "IGS Rapid combinado · 15 min", igs_name, igs_url, "15 min", "GPS", "Rapid", 31),
    ]


def _ultra_starts_for_target(target: date) -> list[datetime]:
    """Generate 6-hour Ultra-Rapid release epochs that can cover target.

    The previous implementation searched only around *today*. That made a
    historical request such as 20/09/2026 fail on 24/09/2026 even though an
    archived Ultra-Rapid product for 20/09 was available. Search around the
    requested date instead.
    """
    target_start = datetime.combine(target, time(0, tzinfo=UTC))
    # A 48-hour Ultra-Rapid file covers the target if its start is between
    # target-48h and target+23h45. Include a small margin of releases.
    return [target_start + timedelta(hours=6 * i) for i in range(-8, 5)]


def _ultra_candidates_for_start(start: datetime, requested_day: date) -> list[EphCandidate]:
    """Return ESA and IGS Ultra-Rapid candidates for one release epoch."""
    sdate = start.date()
    w = gps_week(sdate)
    stamp = f"{sdate.year:04d}{doy(sdate):03d}{start.hour:02d}00"
    coverage_start = start
    coverage_end = start + timedelta(hours=48) - timedelta(minutes=15)

    day_start = datetime.combine(requested_day, time(0, tzinfo=UTC))
    day_end = day_start + timedelta(days=1) - timedelta(minutes=15)
    overlap_start = max(coverage_start, day_start)
    overlap_end = min(coverage_end, day_end)
    if overlap_start > overlap_end:
        return []

    if overlap_start >= coverage_start and overlap_end <= coverage_start + timedelta(hours=24):
        note = "Cobertura observada para la fecha solicitada"
    elif overlap_start >= coverage_start + timedelta(hours=24):
        note = "Cobertura predicha para la fecha solicitada"
    else:
        note = "Cobertura mixta: observada + predicha"

    esa_name = f"ESA0OPSULT_{stamp}_02D_15M_ORB.SP3.gz"
    esa_url = f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}"
    igs_name = f"IGS0OPSULT_{stamp}_02D_15M_ORB.SP3.gz"
    igs_url = f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}"
    return [
        EphCandidate(requested_day, "ESA", "ESA Ultra-Rapid · 15 min", esa_name, esa_url, "15 min", "GPS/Galileo/GLONASS", "Ultra-Rapid", 40, coverage_start=coverage_start, coverage_end=coverage_end, note=note),
        EphCandidate(requested_day, "IGS", "IGS Ultra-Rapid · 15 min", igs_name, igs_url, "15 min", "GPS", "Ultra-Rapid", 41, coverage_start=coverage_start, coverage_end=coverage_end, note=note),
    ]


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

    # Rapid: check all official Rapid candidates for the exact requested day.
    # If ESA is available it is preferred here because its public archive is
    # directly downloadable; IGS combined remains a verified fallback.
    rapids = _rapid_candidates_for_day(target)
    if check:
        for p in rapids:
            p.status = _url_status(p.url)
    alternatives.extend(rapids)
    available_rapids = [p for p in rapids if p.status == "Disponible"]
    if available_rapids:
        available_rapids.sort(key=lambda p: p.priority)
        return available_rapids[0], alternatives

    # Ultra-Rapid: search releases around the REQUESTED day, not around today.
    # Each product contains 48 hours, so historical dates can be served from
    # archived Ultra-Rapid files even several days after the observation.
    ultras: list[EphCandidate] = []
    seen_urls: set[str] = set()
    for start in _ultra_starts_for_target(target):
        for cand in _ultra_candidates_for_start(start, target):
            if cand.url in seen_urls:
                continue
            seen_urls.add(cand.url)
            if check:
                cand.status = _url_status(cand.url)
            ultras.append(cand)

    alternatives.extend(ultras)
    available_ultras = [p for p in ultras if p.status == "Disponible"]
    if available_ultras:
        # Prefer a file that covers the COMPLETE requested UTC day. If several
        # do, use the newest release; within the same release prefer ESA over
        # the CDDIS combined fallback. If no file covers the whole day, use the
        # one with the greatest overlap and then the newest release.
        day_start = datetime.combine(target, time(0, tzinfo=UTC))
        day_end = day_start + timedelta(days=1) - timedelta(minutes=15)

        def ultra_score(p: EphCandidate):
            overlap_start = max(p.coverage_start or day_start, day_start)
            overlap_end = min(p.coverage_end or day_end, day_end)
            overlap_minutes = max(0.0, (overlap_end - overlap_start).total_seconds() / 60.0)
            full_day = 1 if overlap_minutes >= (24 * 60 - 15) else 0
            return (full_day, overlap_minutes, p.coverage_start or datetime.min.replace(tzinfo=UTC), -p.priority)

        available_ultras.sort(key=ultra_score, reverse=True)
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
