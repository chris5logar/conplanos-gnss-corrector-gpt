from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed
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


def _url_status(url: str, timeout: float = 4.5) -> str:
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
    """Final orbit candidates from open ESA/GFZ archives plus IGS/CDDIS."""
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"
    esa_name = f"ESA0OPSFIN_{stamp}_01D_05M_ORB.SP3.gz"
    gfz_name = f"GFZ0OPSFIN_{stamp}_01D_15M_ORB.SP3.gz"
    igs_name = f"IGS0OPSFIN_{stamp}_01D_15M_ORB.SP3.gz"
    return [
        EphCandidate(d, "ESA", "ESA Final · 5 min", esa_name,
                     f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}",
                     "5 min", "GPS/Galileo/GLONASS/QZSS", "Final", 10),
        EphCandidate(d, "GFZ", "GFZ Final · 15 min", gfz_name,
                     f"https://isdc-data.gfz.de/gnss/products/final/w{w}/{gfz_name}",
                     "15 min", "GPS/Galileo/GLONASS", "Final", 11),
        EphCandidate(d, "IGS", "IGS Final combinado · 15 min", igs_name,
                     f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}",
                     "15 min", "GPS", "Final", 12),
    ]


def _rapid_candidates_for_day(d: date) -> list[EphCandidate]:
    """Rapid orbit candidates from multiple public/official archives.

    ESA and GFZ publish open Rapid orbit files. IGS combined Rapid is also
    checked as a fallback, but it may require Earthdata access from some
    environments.  ESA/GFZ Rapid use 5-minute orbit sampling; IGS combined
    Rapid uses 15-minute sampling.
    """
    w = gps_week(d)
    stamp = f"{d.year:04d}{doy(d):03d}0000"
    return [
        EphCandidate(
            d, "ESA", "ESA Rapid · 5 min",
            f"ESA0OPSRAP_{stamp}_01D_05M_ORB.SP3.gz",
            f"https://navigation-office.esa.int/products/gnss-products/{w}/ESA0OPSRAP_{stamp}_01D_05M_ORB.SP3.gz",
            "5 min", "GPS/Galileo/GLONASS", "Rapid", 30,
        ),
        EphCandidate(
            d, "GFZ", "GFZ Rapid · 5 min",
            f"GFZ0OPSRAP_{stamp}_01D_05M_ORB.SP3.gz",
            f"https://isdc-data.gfz.de/gnss/products/rapid/w{w}/GFZ0OPSRAP_{stamp}_01D_05M_ORB.SP3.gz",
            "5 min", "GPS/Galileo/GLONASS", "Rapid", 31,
        ),
        EphCandidate(
            d, "IGS", "IGS Rapid combinado · 15 min",
            f"IGS0OPSRAP_{stamp}_01D_15M_ORB.SP3.gz",
            f"https://cddis.nasa.gov/archive/gnss/products/{w}/IGS0OPSRAP_{stamp}_01D_15M_ORB.SP3.gz",
            "15 min", "GPS", "Rapid", 32,
        ),
    ]


def _ultra_candidates_for_start(start: datetime, requested_day: date) -> list[EphCandidate]:
    """Return ESA, GFZ and IGS Ultra-Rapid candidates for one release epoch."""
    sdate = start.date()
    w = gps_week(sdate)
    stamp = f"{sdate.year:04d}{doy(sdate):03d}{start.hour:02d}{start.minute:02d}"
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

    # ESA and IGS issue every 6 h. GFZ issues its Ultra-Rapid approximately
    # every 3 h, so GFZ is generated separately by _ultra_starts_for_target.
    esa_name = f"ESA0OPSULT_{stamp}_02D_05M_ORB.SP3.gz"
    igs_name = f"IGS0OPSULT_{stamp}_02D_15M_ORB.SP3.gz"
    gfz_name = f"GFZ0OPSULT_{stamp}_02D_05M_ORB.SP3.gz"
    return [
        EphCandidate(requested_day, "ESA", "ESA Ultra-Rapid · 5 min", esa_name,
                     f"https://navigation-office.esa.int/products/gnss-products/{w}/{esa_name}",
                     "5 min", "GPS/Galileo/GLONASS", "Ultra-Rapid", 40,
                     coverage_start=coverage_start, coverage_end=coverage_end, note=note),
        EphCandidate(requested_day, "GFZ", "GFZ Ultra-Rapid · 5 min", gfz_name,
                     f"https://isdc-data.gfz.de/gnss/products/ultra/w{w}/{gfz_name}",
                     "5 min", "GPS/Galileo/GLONASS", "Ultra-Rapid", 41,
                     coverage_start=coverage_start, coverage_end=coverage_end, note=note),
        EphCandidate(requested_day, "IGS", "IGS Ultra-Rapid · 15 min", igs_name,
                     f"https://cddis.nasa.gov/archive/gnss/products/{w}/{igs_name}",
                     "15 min", "GPS", "Ultra-Rapid", 42,
                     coverage_start=coverage_start, coverage_end=coverage_end, note=note),
    ]


def _ultra_starts_for_target(target: date) -> list[datetime]:
    """Generate a compact set of release epochs that can cover target.

    For a 48-hour product, releases from target-24h through target+18h can
    cover the target day. ESA/IGS issue every 6 h; GFZ issues approximately
    every 3 h. We therefore test a 3-hour grid, but only 15 epochs total.
    """
    target_start = datetime.combine(target, time(0, tzinfo=UTC))
    return [target_start + timedelta(hours=3 * i) for i in range(-8, 7)]


def _verify_batch(candidates: list[EphCandidate]) -> None:
    """Verify a batch concurrently to avoid serial 4.5 s network delays."""
    if not candidates:
        return
    with ThreadPoolExecutor(max_workers=min(18, len(candidates))) as ex:
        futures = {ex.submit(_url_status, p.url): p for p in candidates}
        for fut in as_completed(futures):
            p = futures[fut]
            try:
                p.status = fut.result()
            except Exception as exc:
                p.status = f"No disponible / error: {exc}"


def _select_ultra(available_ultras: list[EphCandidate], target: date) -> EphCandidate | None:
    if not available_ultras:
        return None
    day_start = datetime.combine(target, time(0, tzinfo=UTC))
    day_end = day_start + timedelta(days=1) - timedelta(minutes=15)

    def score(p: EphCandidate):
        overlap_start = max(p.coverage_start or day_start, day_start)
        overlap_end = min(p.coverage_end or day_end, day_end)
        overlap_minutes = max(0.0, (overlap_end - overlap_start).total_seconds() / 60.0)
        full_day = 1 if overlap_minutes >= (24 * 60 - 15) else 0
        # Prefer complete coverage, then greatest overlap, then newest issue,
        # then ESA/GFZ before IGS when release time is identical.
        source_rank = {"ESA": 3, "GFZ": 2, "IGS": 1}.get(p.source, 0)
        return (full_day, overlap_minutes, p.coverage_start or datetime.min.replace(tzinfo=UTC), source_rank)

    return max(available_ultras, key=score)


def find_best_for_day(target: date, check: bool = True) -> tuple[EphCandidate | None, list[EphCandidate]]:
    """Return the best currently verifiable product for the requested day.

    Priority is strict: Final -> Rapid -> Ultra-Rapid. Each priority tier is
    checked in parallel across several official/public archives, which makes
    the search much faster and avoids depending on one server.
    """
    alternatives: list[EphCandidate] = []

    # 1) FINAL: exact day. These are intentionally checked first.
    finals = _final_candidates_for_day(target)
    if check:
        _verify_batch(finals)
    else:
        for p in finals:
            p.status = "No comprobado"
    alternatives.extend(finals)
    available = [p for p in finals if p.status == "Disponible"]
    if available:
        return min(available, key=lambda p: p.priority), alternatives

    # 2) RAPID: check ESA + GFZ + IGS in parallel.
    rapids = _rapid_candidates_for_day(target)
    if check:
        _verify_batch(rapids)
    else:
        for p in rapids:
            p.status = "No comprobado"
    alternatives.extend(rapids)
    available = [p for p in rapids if p.status == "Disponible"]
    if available:
        return min(available, key=lambda p: p.priority), alternatives

    # 3) ULTRA-RAPID: historical/current releases covering the requested day.
    # We check ESA, GFZ and IGS from release epochs around the target day.
    ultras: list[EphCandidate] = []
    seen: set[str] = set()
    for start in _ultra_starts_for_target(target):
        for cand in _ultra_candidates_for_start(start, target):
            if cand.url not in seen:
                seen.add(cand.url)
                ultras.append(cand)

    if check:
        _verify_batch(ultras)
    else:
        for p in ultras:
            p.status = "No comprobado"
    alternatives.extend(ultras)
    available = [p for p in ultras if p.status == "Disponible"]
    best = _select_ultra(available, target)
    if best:
        return best, alternatives

    return None, alternatives
