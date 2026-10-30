"""Builds the OKPELLA risk assessment PDF (v1.11 form design) from engine output."""
import io
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from engine import HAZARD_CATEGORIES, LEVEL_NAMES, LEVELS

BLUE_DEEP = colors.HexColor("#123a73")
RED = colors.HexColor("#c6303e")
INK_DIM = colors.HexColor("#5c7086")
LINE = colors.HexColor("#d7e3ee")
PAPER_DIM = colors.HexColor("#f2f6fc")
LEVEL_COLOURS = {"E": "#c6303e", "H": "#e0793a", "M": "#d9b23a", "L": "#4f9d63", "N": "#4a7fc9"}

ERP_TEXT = ("Stop whatever you are doing and call the following number:<br/>"
            "Safety Officers: 08056857344, 08152711025, 07085713676, 08056862447, 08056848737<br/>"
            "HSE Manager: 09053739601 &nbsp; Security Manager: 08110540298<br/>"
            "Extensions: HSE: 1539, 1540, 1165 &nbsp; Fire: 1539 &nbsp; Security: 1468")


def _fonts():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
    try:
        pdfmetrics.registerFont(TTFont("OkSans", os.path.join(here, "LiberationSans-Regular.ttf")))
        pdfmetrics.registerFont(TTFont("OkSans-Bold", os.path.join(here, "LiberationSans-Bold.ttf")))
        pdfmetrics.registerFontFamily("OkSans", normal="OkSans", bold="OkSans-Bold")
        return "OkSans", "OkSans-Bold"
    except Exception:  # noqa: BLE001  fonts missing: fall back to built-in Helvetica
        return "Helvetica", "Helvetica-Bold"


FONT, FONT_B = _fonts()
S = {
    "banner1": ParagraphStyle("b1", fontName=FONT_B, fontSize=14, textColor=colors.white, alignment=TA_CENTER, leading=17),
    "banner2": ParagraphStyle("b2", fontName=FONT, fontSize=9.5, textColor=colors.HexColor("#bcd2ee"), alignment=TA_CENTER),
    "k": ParagraphStyle("k", fontName=FONT_B, fontSize=8.5, textColor=INK_DIM, leading=11),
    "v": ParagraphStyle("v", fontName=FONT, fontSize=8.5, leading=11),
    "h3": ParagraphStyle("h3", fontName=FONT_B, fontSize=9, textColor=colors.white, leading=11),
    "hz": ParagraphStyle("hz", fontName=FONT_B, fontSize=9, leading=11.5),
    "ct": ParagraphStyle("ct", fontName=FONT, fontSize=8.3, textColor=INK_DIM, leading=10.8),
    "src": ParagraphStyle("src", fontName=FONT, fontSize=7, textColor=colors.HexColor("#8b99a8"), leading=9),
    "badge": ParagraphStyle("bd", fontName=FONT_B, fontSize=8, textColor=colors.white, alignment=TA_CENTER, leading=10),
    "excl": ParagraphStyle("ex", fontName=FONT_B, fontSize=6.8, textColor=colors.HexColor("#5f6b77"), leading=9),
    "body": ParagraphStyle("bo", fontName=FONT, fontSize=8.3, leading=11),
    "chip": ParagraphStyle("ch", fontName=FONT_B, fontSize=7.5, textColor=colors.white, alignment=TA_CENTER, leading=9),
    "empty": ParagraphStyle("em", fontName=FONT, fontSize=8.3, textColor=INK_DIM, alignment=TA_CENTER),
}


_SUB = {chr(0x2080 + i): "<sub>%d</sub>" % i for i in range(10)}
_SUP = {"\u2070": "0", "\u2074": "4", "\u2075": "5", "\u2076": "6", "\u2077": "7", "\u2078": "8", "\u2079": "9"}


def _markup(text):
    """Escape register text for the PDF. Unicode sub/superscript digits (e.g. O\u2082) are drawn as
    real sub/superscripts because the PDF font has no glyphs for them. The wording is unchanged."""
    out = escape(str(text or ""))
    for ch, rep in _SUB.items():
        out = out.replace(ch, rep)
    for ch, d in _SUP.items():
        out = out.replace(ch, "<super>%s</super>" % d)
    return out.replace("\n", "<br/>")


def _p(text, style):
    return Paragraph(_markup(text), S[style])


def _badge(level, faded=False):
    col = colors.HexColor(LEVEL_COLOURS.get(level, "#c7ccd1"))
    if faded:
        col = colors.HexColor("#c7ccd1")
    t = Table([[Paragraph(escape(level or "—"), S["badge"])]], colWidths=[9 * mm], rowHeights=[5 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), col), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    return t


def _card(h, included, width):
    title = _markup(h["hazard"])
    if not included:
        title = "<strike>%s</strike>" % title
    rows = [
        [Paragraph(title, S["hz"]), _badge(h["level"], faded=not included)],
        [_p(h["controls"], "ct"), ""],
        [Paragraph("Residual risk after controls:", S["ct"]), _badge(h["residual"], faded=not included)],
        [_p("%s · %s · Responsible: %s" % (h["id"], h["source"], h["responsible"] or "—"), "src"), ""],
    ]
    if not included:
        rows.append([Paragraph("REVIEWED AND EXCLUDED BY ASSESSOR AS NOT APPLICABLE", S["excl"]), ""])
    t = Table(rows, colWidths=[width - 14 * mm, 14 * mm])
    style = [
        ("BOX", (0, 0), (-1, -1), 0.6, LINE if included else colors.HexColor("#aab5c0")),
        ("SPAN", (0, 1), (1, 1)), ("SPAN", (0, 3), (1, 3)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5),
    ]
    if not included:
        style += [("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f1f3f6")), ("SPAN", (0, 4), (1, 4))]
    t.setStyle(TableStyle(style))
    return t


def _section_header(text, width):
    t = Table([[Paragraph(escape(text.upper()), S["h3"])]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE_DEEP),
                           ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return t


def build_pdf(header, hazards, included_ids, fingerprint, engine_version, generated):
    """
    header: dict with serial, department, location, area, equipment, equipment_type,
            motion_status, title, description, activities, assessed_by, reviewed_by
    hazards: engine hazard list (final order); included_ids: set of IDs left ticked.
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=16 * mm,
                            title="Risk Assessment %s" % header["serial"], author="OKPELLA Risk Assessment")
    W = doc.width
    story = []

    banner = Table([[Paragraph("OKPELLA CEMENT LIMITED, OKPELLA", S["banner1"])],
                    [Paragraph("RISK ASSESSMENT FORM", S["banner2"])]], colWidths=[W])
    banner.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLUE_DEEP),
                                ("LINEBELOW", (0, -1), (-1, -1), 2, RED),
                                ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    story += [banner, Spacer(1, 4 * mm)]

    kv = [("Assessment No.", header["serial"]), ("Department / Section", header["department"]),
          ("Location of work", header["location"]), ("Specific work area", header["area"]),
          ("Specific equipment", header["equipment"]), ("Equipment type", header["equipment_type"]),
          ("Motion / Status", header["motion_status"]), ("Title of work", header["title"]),
          ("Description", header["description"]), ("Activities", header["activities"])]
    t = Table([[_p(k, "k"), _p(v, "v")] for k, v in kv], colWidths=[42 * mm, W - 42 * mm])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
    story += [t, Spacer(1, 4 * mm)]

    inc = [h for h in hazards if h["id"] in included_ids]
    n_exc = len(hazards) - len(inc)
    chips = [("%d HAZARDS" % len(inc), BLUE_DEEP)]
    for lv in LEVELS:
        n = sum(1 for h in inc if h["level"] == lv)
        if n:
            chips.append(("%d %s" % (n, LEVEL_NAMES[lv]), colors.HexColor(LEVEL_COLOURS[lv])))
    if n_exc:
        chips.append(("%d EXCLUDED" % n_exc, colors.HexColor("#8c98a4")))
    ct = Table([[Paragraph(c[0], S["chip"]) for c in chips]], colWidths=[min(30 * mm, W / len(chips))] * len(chips),
               hAlign="LEFT")
    ct.setStyle(TableStyle([("BACKGROUND", (i, 0), (i, 0), c[1]) for i, c in enumerate(chips)] +
                           [("LINEAFTER", (0, 0), (-2, 0), 2, colors.white)]))
    story += [ct, Spacer(1, 3 * mm)]

    for n, cat in enumerate(HAZARD_CATEGORIES, 1):
        rows = [h for h in hazards if h["category"] == cat]
        head = [_section_header("%d. %s" % (n, cat), W), Spacer(1, 2 * mm)]
        if not rows:
            story += [KeepTogether(head + [_p("No hazards in this category for the current selection.", "empty")]),
                      Spacer(1, 2 * mm)]
        for j, h in enumerate(rows):
            card = _card(h, h["id"] in included_ids, W)
            story += [KeepTogether(head + [card]) if j == 0 else KeepTogether(card), Spacer(1, 2 * mm)]
        story.append(Spacer(1, 2 * mm))

    ppe = []
    for h in inc:
        for p in h["ppe"]:
            if p not in ppe:
                ppe.append(p)
    story.append(_section_header("PPE Required (compiled from included hazards)", W))
    pt = Table([[_p("; ".join(ppe) or "No PPE listed for the included hazards.", "body")]], colWidths=[W])
    pt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), PAPER_DIM)]))
    story += [Spacer(1, 2 * mm), pt, Spacer(1, 4 * mm)]

    erp = Table([[Paragraph("<b>Emergency Response Plan</b><br/>" + ERP_TEXT, S["body"])]], colWidths=[W])
    erp.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#e4eefb")),
                             ("LINEBEFORE", (0, 0), (0, -1), 3, RED)]))
    story += [KeepTogether(erp), Spacer(1, 4 * mm)]

    half = W / 2 - 3 * mm
    sig = Table([[_p("Assessed By", "k"), "", _p("Reviewed By", "k")],
                 [_p(header["assessed_by"], "v"), "", _p(header["reviewed_by"], "v")],
                 ["", "", ""],
                 [_p("Signature / Date", "src"), "", _p("Signature / Date", "src")]],
                colWidths=[half, 6 * mm, half], rowHeights=[None, None, 12 * mm, None])
    sig.setStyle(TableStyle([("LINEBELOW", (0, 2), (0, 2), 0.6, INK_DIM), ("LINEBELOW", (2, 2), (2, 2), 0.6, INK_DIM)]))
    story += [KeepTogether([_section_header("Authorization", W), Spacer(1, 2 * mm), sig])]

    def footer(canvas, d):
        canvas.saveState()
        canvas.setFont(FONT, 7)
        canvas.setFillColor(colors.HexColor("#8b99a8"))
        canvas.drawString(14 * mm, 10 * mm, "Assessment %s · Generated %s · Engine v%s · Register fingerprint %s"
                          % (header["serial"], generated, engine_version, fingerprint))
        canvas.drawString(14 * mm, 6.5 * mm, "Every hazard is quoted verbatim from OKPELLA_Master_Workbook "
                                             "(row ID shown on each card).")
        canvas.drawRightString(A4[0] - 14 * mm, 10 * mm, "Page %d" % d.page)
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
