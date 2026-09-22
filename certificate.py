from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date, datetime
from pathlib import Path
from typing import Optional
import re
import io
import zipfile
import tempfile

from PIL import Image, ImageDraw, ImageFont
from lxml import etree


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NS = {"w": W_NS}


@dataclass
class CertificateData:
    codigo: str = ""
    solicitante: str = ""
    norte: str = ""
    este: str = ""
    zona: str = ""
    latitud: str = ""
    longitud: str = ""
    alt_ellipsoidal: str = ""
    estacion_gnss: str = ""
    fecha_posicion: str = ""
    fecha_emision: str = ""
    anio: str = ""
    tipo_orden: str = "C"
    correlativo: str = ""
    lugar_emision: str = "Cusco"


def today_defaults() -> CertificateData:
    d = date.today()
    return CertificateData(
        fecha_emision=d.strftime("%d/%m/%Y"),
        anio=str(d.year),
    )


def extract_certificate_data(report, defaults: Optional[CertificateData] = None) -> CertificateData:
    data = CertificateData(**asdict(defaults or today_defaults()))

    data.norte = f"{report.mobile_n:.4f}" if report.mobile_n is not None else ""
    data.este = f"{report.mobile_e:.4f}" if report.mobile_e is not None else ""
    data.latitud = report.mobile_lat or ""
    data.longitud = report.mobile_lon or ""
    data.alt_ellipsoidal = (
        f"{report.mobile_h_ellip:.4f}" if report.mobile_h_ellip is not None else ""
    )

    if report.start:
        try:
            dt = datetime.strptime(report.start, "%d/%m/%Y %H:%M:%S")
            data.fecha_posicion = dt.strftime("%d/%m/%Y")
            data.anio = str(dt.year)
        except Exception:
            data.fecha_posicion = report.start.split(" ")[0]

    z = getattr(report, "utm_zone", None)
    if z:
        data.zona = f"{z} Sur"

    if report.reference_name:
        station = report.reference_name
        if data.anio and not re.search(r"\b\d{4}\b", station):
            station = f"{station} - {data.anio}"
        data.estacion_gnss = station

    if getattr(report, "point_code", None):
        data.codigo = report.point_code

    return data


def make_plaque(code: str, output_path: str | Path) -> Path:
    """Genera una ilustración de placa cuando no se dispone de fotografía."""
    output_path = Path(output_path)
    size = 700
    img = Image.new("RGB", (size, size), (155, 75, 44))
    draw = ImageDraw.Draw(img)
    font_file = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    bold = ImageFont.truetype(font_file, 52) if Path(font_file).exists() else None
    small = ImageFont.truetype(font_file, 29) if Path(font_file).exists() else None
    cx = cy = size // 2

    draw.ellipse((65, 65, 635, 635), fill=(233, 221, 164), outline=(70, 90, 110), width=9)
    draw.ellipse((98, 98, 602, 602), outline=(70, 90, 110), width=6)

    def centered(text, y, font):
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text((cx - (bbox[2] - bbox[0]) / 2, y), text, fill=(55, 85, 105), font=font)

    centered("PUNTO GEODÉSICO", 105, small)
    centered("CONPLANOS", 205, bold)
    centered(code or "PG-XXXX", 310, bold)
    centered("GENERADO", 535, small)
    img.save(output_path, "PNG", optimize=True)
    return output_path


def _fill_text_node(tree, token_map):
    """Replace whole placeholder tokens in a Word document XML tree."""
    for t in tree.xpath("//w:t", namespaces=NS):
        if not t.text:
            continue
        text = t.text
        for old, new in token_map.items():
            if old in text:
                text = text.replace(old, new)
        t.text = text


def generate_certificate_docx(data, image_path, template_path, output_path) -> Path:
    """
    Patches the provided editable template at the OOXML level so the
    original header/footer/branding/layout and image placement remain intact.
    """
    token_map = {
        "{{CODIGO}}": data.codigo,
        "{{SOLICITANTE}}": data.solicitante,
        "{{NORTE}}": data.norte,
        "{{ESTE}}": data.este,
        "{{ZONA}}": data.zona,
        "{{LATITUD}}": data.latitud,
        "{{LONGITUD}}": data.longitud,
        "{{ALT_ELIP}}": data.alt_ellipsoidal,
        "{{TIPO_ORDEN}}": data.tipo_orden,
        "{{ESTACION_GNSS}}": data.estacion_gnss,
        "{{FECHA_POSICION}}": data.fecha_posicion,
        "{{CORRELATIVO}}": data.correlativo,
        "{{LUGAR_EMISION}}": data.lugar_emision,
        "{{FECHA_EMISION}}": data.fecha_emision,
    }

    output_path = Path(output_path)
    # Convert photo/generated plaque to PNG.
    with Image.open(image_path) as im:
        png_buf = io.BytesIO()
        im.convert("RGB").save(png_buf, "PNG")
        png_bytes = png_buf.getvalue()

    parser = etree.XMLParser(remove_blank_text=False)

    with zipfile.ZipFile(template_path, "r") as zin, zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            payload = zin.read(item.filename)
            if item.filename == "word/document.xml":
                root = etree.fromstring(payload, parser)
                _fill_text_node(root, token_map)
                payload = etree.tostring(
                    root, xml_declaration=True, encoding="UTF-8", standalone="yes"
                )
            elif item.filename == "word/media/image3.png":
                payload = png_bytes
            zout.writestr(item, payload)

    return output_path


def _fit_font(text, max_width, max_size=9.5, min_size=6.5, fontname="times-bold"):
    try:
        import fitz
        for size in [max_size - i * 0.5 for i in range(int((max_size-min_size)/0.5)+1)]:
            if fitz.get_text_length(text, fontname=fontname, fontsize=size) <= max_width:
                return size
    except Exception:
        return min_size
    return min_size


def _draw_centered(page, text, rect, fontsize=9, fontname="times-roman"):
    import fitz
    if not text:
        return
    width = fitz.get_text_length(text, fontname=fontname, fontsize=fontsize)
    x = rect.x0 + max(0, (rect.width - width) / 2)
    y = rect.y0 + rect.height * 0.72
    page.insert_text((x, y), text, fontsize=fontsize, fontname=fontname, color=(0,0,0))


def _replace_rect(page, old_text, new_text, *, center=False, fontsize=9, pad=1.5):
    import fitz
    rects = page.search_for(old_text)
    if not rects:
        return False
    rect = rects[0]
    cover = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
    page.draw_rect(cover, color=(1,1,1), fill=(1,1,1), overlay=True)
    if center:
        _draw_centered(page, new_text, cover, fontsize=fontsize)
    else:
        page.insert_text((cover.x0, cover.y1-2), new_text, fontsize=fontsize, fontname="times-roman", color=(0,0,0))
    return True


def _replace_paragraph_area(page, area, lines):
    import fitz
    page.draw_rect(area, color=(1,1,1), fill=(1,1,1), overlay=True)
    x = area.x0 + 6
    y = area.y0 + 14
    for text, bold in lines:
        page.insert_text(
            (x, y),
            text,
            fontsize=8.0,
            fontname="times-bold" if bold else "times-roman",
            color=(0,0,0),
        )
        y += 15


def generate_certificate_pdf(data, photo_or_plaque, template_pdf_path, output_path) -> Path:
    """Uses the supplied one-page PDF as the exact visual template."""
    import fitz
    doc = fitz.open(template_pdf_path)
    page = doc[0]

    def replace_found(old_text, new_text, *, font="times-roman", size=9.0, center=False, pad=1.0, rect_override=None):
        rects = page.search_for(old_text) if rect_override is None else [rect_override]
        if not rects:
            return False
        rect = fitz.Rect(rects[0])
        cover = fitz.Rect(rect.x0-pad, rect.y0-pad, rect.x1+pad, rect.y1+pad)
        page.draw_rect(cover, color=(1,1,1), fill=(1,1,1), overlay=True)
        if center:
            width = fitz.get_text_length(new_text, fontname=font, fontsize=size)
            x = cover.x0 + max(0, (cover.width-width)/2)
        else:
            x = cover.x0 + 1
        y = cover.y0 + cover.height*0.78
        page.insert_text((x,y), new_text, fontsize=size, fontname=font, color=(0,0,0), overlay=True)
        return True

    # Main value cells.
    replace_found("PG2625", data.codigo, font="times-roman", size=9.0, center=True)
    applicant_size = 9.0
    while applicant_size > 6.2 and fitz.get_text_length(
        data.solicitante, fontname="times-bold", fontsize=applicant_size
    ) > 330:
        applicant_size -= 0.4
    replace_found(
        "SERVIO NUÑEZ PERALTA BACA Y ESPOSA",
        data.solicitante,
        font="times-bold",
        size=applicant_size,
        center=True,
        pad=0.8,
        rect_override=fitz.Rect(60, 331, 535, 346),
    )
    replace_found("8507508.5251 m", f"{data.norte} m", size=8.8, pad=0.8)
    replace_found("13°29'07.70966'' S", data.latitud, size=8.2, pad=0.8)
    replace_found("797795.1174 m", f"{data.este} m", size=8.8, pad=0.8)
    replace_found("72°14'57.70438'' O", data.longitud, size=8.2, pad=0.8)
    replace_found("18 Sur", data.zona, size=8.8, pad=0.8)
    replace_found("3387.4337 m", f"{data.alt_ellipsoidal} m", size=8.8, pad=0.8)

    station = data.estacion_gnss

    # General data: replace only the existing text rectangles.
    replace_found('- TIPO ORDEN: “C”', f'- TIPO ORDEN: "{data.tipo_orden}"', font="times-bold", size=7.5, pad=0.8)
    replace_found('- ESTACIÓN GNSS BASE: CUSCO (CS01) - 2026', f'- ESTACIÓN GNSS BASE: {station}', font="times-bold", size=7.5, pad=0.8)
    replace_found('- FECHA DE POSICIONAMIENTO: 23/08/2026', f'- FECHA DE POSICIONAMIENTO: {data.fecha_posicion}', font="times-bold", size=7.5, pad=0.8)
    replace_found('- NUM. CORRELATIVO CP-2026-1025', f'- NUM. CORRELATIVO {data.correlativo}', font="times-bold", size=7.5, pad=0.8)

    # Replace point image while preserving the original image position.
    image_rect = fitz.Rect(384.02, 426.95, 497.06, 540.30)
    page.draw_rect(image_rect, color=(1,1,1), fill=(1,1,1), overlay=True)
    page.insert_image(image_rect, filename=str(photo_or_plaque), keep_proportion=True, overlay=True)

    # Issuance date.
    footer_rects = page.search_for("Cusco, 3 de setiembre de 2026")
    rect = footer_rects[0] if footer_rects else fitz.Rect(395, 645, 540, 664)
    page.draw_rect(rect, color=(1,1,1), fill=(1,1,1), overlay=True)
    footer = f"{data.lugar_emision}, {data.fecha_emision}"
    page.insert_text((rect.x0, rect.y0+9.5), footer, fontsize=9.2, fontname="times-roman", color=(0,0,0), overlay=True)

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    return Path(output_path)

