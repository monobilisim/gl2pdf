"""
renderer.py
-----------
ReportLab-based PDF renderer for SAST reports.
~25x faster than WeasyPrint for large reports.
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.flowables import Flowable, HRFlowable

from .parser import SastReport
from .template import _LABELS, SEVERITY_COLOR, SEVERITY_ORDER

# ── Font registration ─────────────────────────────────────────────────────────

_FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")


def _register_fonts() -> tuple[str, str, str]:
    try:
        pdfmetrics.registerFont(TTFont("DVSans",      str(_FONT_DIR / "DejaVuSans.ttf")))
        pdfmetrics.registerFont(TTFont("DVSans-Bold", str(_FONT_DIR / "DejaVuSans-Bold.ttf")))
        pdfmetrics.registerFont(TTFont("DVMono",      str(_FONT_DIR / "DejaVuSansMono.ttf")))
        from reportlab.pdfbase.pdfmetrics import registerFontFamily
        registerFontFamily("DVSans", normal="DVSans", bold="DVSans-Bold",
                           italic="DVSans", boldItalic="DVSans-Bold")
        return "DVSans", "DVSans-Bold", "DVMono"
    except Exception:
        return "Helvetica", "Helvetica-Bold", "Courier"


FONT_REG, FONT_BOLD, FONT_MONO = _register_fonts()

# ── Page geometry ─────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
MARGIN_L = 14 * mm
MARGIN_R = 14 * mm
MARGIN_T = 16 * mm
MARGIN_B = 18 * mm
CONTENT_W = PAGE_W - MARGIN_L - MARGIN_R

BRAND_COLOR = "#FA002A"


def _hex(h: str) -> HexColor:
    try:
        return HexColor(h)
    except Exception:
        return HexColor("#FA002A")


def _sev_color(sev: str) -> HexColor:
    return _hex(SEVERITY_COLOR.get(sev, "#95a5a6"))


def _row_bg() -> HexColor:
    return HexColor("#fff5f6")


# ── Localization ──────────────────────────────────────────────────────────────

def _L(lang: str, key: str) -> str:
    return _LABELS.get(lang, _LABELS["en"]).get(key, _LABELS["en"].get(key, key))


# ── Styles ────────────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    bc = _hex(BRAND_COLOR)
    return {
        "section_title": ParagraphStyle(
            "section_title", fontName=FONT_BOLD, fontSize=11,
            textColor=bc, spaceBefore=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body", fontName=FONT_REG, fontSize=8.5,
            textColor=HexColor("#1e293b"), leading=13, spaceAfter=7,
        ),
        "info_key": ParagraphStyle(
            "info_key", fontName=FONT_BOLD, fontSize=7.5,
            textColor=bc,
        ),
        "info_val": ParagraphStyle(
            "info_val", fontName=FONT_REG, fontSize=7.5,
            textColor=HexColor("#334155"),
        ),
        "td": ParagraphStyle(
            "td", fontName=FONT_REG, fontSize=7,
            textColor=HexColor("#1e293b"), wordWrap="CJK", leading=9,
        ),
        "td_mono": ParagraphStyle(
            "td_mono", fontName=FONT_MONO, fontSize=6.5,
            textColor=HexColor("#334155"), wordWrap="CJK", leading=8,
        ),
        "rec": ParagraphStyle(
            "rec", fontName=FONT_REG, fontSize=8,
            textColor=HexColor("#1e293b"), leading=13,
            leftIndent=10, spaceAfter=5,
        ),
    }


# ── Table style ───────────────────────────────────────────────────────────────

def _tbl_style() -> TableStyle:
    alt = _row_bg()
    bc = _hex(BRAND_COLOR)
    return TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), bc),
        ("TEXTCOLOR",     (0, 0), (-1, 0), white),
        ("FONTNAME",      (0, 0), (-1, 0), FONT_BOLD),
        ("FONTSIZE",      (0, 0), (-1, 0), 7),
        ("TOPPADDING",    (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("FONTNAME",      (0, 1), (-1, -1), FONT_REG),
        ("FONTSIZE",      (0, 1), (-1, -1), 7),
        ("TOPPADDING",    (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, alt]),
        ("LINEBELOW",     (0, 0), (-1, 0), 0.5, bc),
        ("INNERGRID",     (0, 1), (-1, -1), 0.25, HexColor("#e2e8f0")),
        ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#cbd5e1")),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ])


# ── Document with footer ──────────────────────────────────────────────────────

class _Doc(BaseDocTemplate):
    def __init__(self, buf, lang: str = "en", footer_label: str = "gl2pdf", **kw):
        super().__init__(buf, **kw)
        self._is_cover = True
        self._lang = lang
        self._footer_label = footer_label

    def handle_pageEnd(self):
        super().handle_pageEnd()
        if not self._is_cover:
            self._draw_footer()
        self._is_cover = False

    def _draw_footer(self):
        c = self.canv
        c.saveState()
        y_line = MARGIN_B - 5 * mm
        y_text = MARGIN_B - 8.5 * mm
        c.setStrokeColor(_hex(BRAND_COLOR))
        c.setLineWidth(0.4)
        c.line(MARGIN_L, y_line, PAGE_W - MARGIN_R, y_line)
        c.setFont(FONT_REG, 6.5)
        c.setFillColor(HexColor("#94a3b8"))
        c.drawString(MARGIN_L, y_text, self._footer_label)
        page_str = f"Page {self.page}"
        c.drawRightString(PAGE_W - MARGIN_R, y_text, page_str)
        c.restoreState()


# ── Cover flowable ────────────────────────────────────────────────────────────

class _Cover(Flowable):
    def __init__(self, report: SastReport, title: str, repo: str | None, lang: str, kicker: str | None = None):
        super().__init__()
        self.report = report
        self.title  = title
        self.repo   = repo
        self.lang   = lang
        self.kicker = kicker

    def wrap(self, aw, ah):
        return (PAGE_W, PAGE_H)

    def draw(self):
        c   = self.canv
        bc  = _hex(BRAND_COLOR)
        cx  = PAGE_W / 2

        # White background
        c.setFillColor(HexColor("#ffffff"))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        # Bottom accent stripe (6px)
        c.setFillColor(bc)
        c.rect(0, 0, PAGE_W, 6, fill=1, stroke=0)

        # Title
        cy = PAGE_H * 0.62
        if self.kicker:
            c.setFont(FONT_REG, 11)
            c.setFillColor(HexColor("#6b7280"))
            c.drawCentredString(cx, cy + 9 * mm, self.kicker)
        c.setFont(FONT_BOLD, 26)
        c.setFillColor(HexColor("#1a1a1a"))
        c.drawCentredString(cx, cy, self.title)
        cy -= 11 * mm

        # Repo
        if self.repo:
            c.setFont(FONT_REG, 12)
            c.setFillColor(HexColor("#555555"))
            c.drawCentredString(cx, cy, self.repo)
            cy -= 10 * mm

        cy -= 6 * mm

        # Meta info
        now = datetime.now().strftime("%d %B %Y %H:%M")
        lang = self.lang
        r = self.report
        meta = [
            f"{_L(lang,'analyzer')}: {r.scan.analyzer_name} v{r.scan.analyzer_version}",
            f"{_L(lang,'scanner')}: {r.scan.scanner_name} v{r.scan.scanner_version}",
            f"{_L(lang,'report_date')}: {now}",
        ]
        c.setFont(FONT_REG, 9)
        c.setFillColor(HexColor("#666666"))
        for line in meta:
            c.drawCentredString(cx, cy, line)
            cy -= 6.5 * mm

        cy -= 10 * mm

        # Severity pills
        sev_items = [(s, r.severity_counts.get(s, 0)) for s in SEVERITY_ORDER if r.severity_counts.get(s, 0) > 0]
        if sev_items:
            from reportlab.lib.colors import Color
            pill_gap = 10
            n_pills = len(sev_items)
            # Dynamic width: all pills + gaps must fit within CONTENT_W
            pill_w = min(60, (CONTENT_W - (n_pills - 1) * pill_gap) / n_pills)
            pill_h = 38
            # Font sizes scale with pill width
            count_fs = min(16, pill_w * 0.30)
            label_fs = min(7, pill_w * 0.13)
            total_w = n_pills * pill_w + (n_pills - 1) * pill_gap
            px = cx - total_w / 2
            # cy is currently the top edge of the pills
            pill_top = cy
            for sev, cnt in sev_items:
                sc = _sev_color(sev)
                # Background
                c.setFillColor(Color(sc.red, sc.green, sc.blue, 0.12))
                c.setStrokeColor(Color(sc.red, sc.green, sc.blue, 0.5))
                c.setLineWidth(0.8)
                c.roundRect(px, pill_top - pill_h, pill_w, pill_h, 5, fill=1, stroke=1)
                # Top color bar
                c.setFillColor(sc)
                c.setStrokeColor(sc)
                c.roundRect(px, pill_top - 4, pill_w, 4, 2, fill=1, stroke=0)
                # Count — slightly above the pill's center
                c.setFont(FONT_BOLD, count_fs)
                c.setFillColor(sc)
                c.drawCentredString(px + pill_w / 2, pill_top - pill_h * 0.45, str(cnt))
                # Label — bottom of the pill, with padding
                c.setFont(FONT_REG, label_fs)
                c.setFillColor(HexColor("#555555"))
                c.drawCentredString(px + pill_w / 2, pill_top - pill_h + 6, sev.upper())
                px += pill_w + pill_gap
            cy = pill_top - pill_h - 14 * mm

        # Confidentiality tag
        conf = _L(lang, "confidential")
        tag_w = min(len(conf) * 5.5 + 30, CONTENT_W * 0.8)
        tag_h = 18
        tag_x = cx - tag_w / 2
        c.setFillColor(bc)
        c.roundRect(tag_x, cy - 4, tag_w, tag_h, 3, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 7.5)
        c.setFillColor(white)
        c.drawCentredString(cx, cy + 3, conf)

        # Bottom note
        c.setFont(FONT_REG, 7)
        c.setFillColor(HexColor("#aaaaaa"))
        label = "gl2pdf"
        c.drawCentredString(cx, 14 * mm, label)
        text_width = c.stringWidth(label, FONT_REG, 7)
        c.linkURL(
            "https://github.com/monobilisim/gl2pdf",
            (cx - text_width / 2, 14 * mm - 1, cx + text_width / 2, 14 * mm + 7),
            relative=0,
        )


# ── Section helper ────────────────────────────────────────────────────────────

def _section(text: str, st: dict) -> list:
    return [
        Paragraph(text, st["section_title"]),
        HRFlowable(width=CONTENT_W, thickness=1,
                   color=st["section_title"].textColor, spaceAfter=6, spaceBefore=0),
    ]


# ── Exec summary ──────────────────────────────────────────────────────────────

def _exec_summary(report: SastReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec1"), st)

    now = datetime.now().strftime("%d %B %Y %H:%M")
    info = [
        (_L(lang, "source_file"),    str(report.source_file.name)),
        (_L(lang, "scan_type"),      _L(lang, "scan_type_val")),
        (_L(lang, "tool"),           f"{report.scan.analyzer_name} {report.scan.analyzer_version} / {report.scan.scanner_name} {report.scan.scanner_version}"),
        (_L(lang, "total_findings"), str(report.total)),
        (_L(lang, "report_date"),    now),
    ]
    info_rows = [[Paragraph(k, st["info_key"]), Paragraph(v, st["info_val"])] for k, v in info]
    bc = _hex(BRAND_COLOR)
    info_tbl = Table(info_rows, colWidths=[CONTENT_W * 0.28, CONTENT_W * 0.72])
    info_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), _row_bg()),
        ("LINEAFTER",     (0, 0), (0, -1),  1.5, bc),
        ("BOX",           (0, 0), (-1, -1), 0.5, bc),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 7))

    # Summary paragraph (strip HTML tags from template)
    raw_summary = _L(lang, "summary").format(
        source_file=report.source_file.name,
        scanner_name=report.scan.scanner_name,
        total=report.total,
    )
    # convert simple HTML tags to ReportLab markup
    summary = raw_summary.replace("<em>", "<i>").replace("</em>", "</i>").replace("<strong>", "<b>").replace("</strong>", "</b>")
    story.append(Paragraph(summary, st["body"]))

    # Severity cards
    sev_items = [(s, report.severity_counts.get(s, 0)) for s in SEVERITY_ORDER if report.severity_counts.get(s, 0) > 0]
    if sev_items:
        n = len(sev_items)
        cw = CONTENT_W / n
        card_cols = []
        for sev, cnt in sev_items:
            sc = _sev_color(sev)
            inner = Table(
                [[Paragraph(str(cnt), ParagraphStyle("cn", fontName=FONT_BOLD, fontSize=18,
                                                      textColor=sc, alignment=1))],
                 [Paragraph(sev.upper(), ParagraphStyle("cl", fontName=FONT_BOLD, fontSize=6,
                                                         textColor=HexColor("#64748b"), alignment=1))]],
                colWidths=[cw],
                style=TableStyle([
                    ("LEFTPADDING",   (0,0), (-1,-1), 2),
                    ("RIGHTPADDING",  (0,0), (-1,-1), 2),
                    ("TOPPADDING",    (0,0), (-1,-1), 4),
                    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
                ]),
            )
            card_cols.append(inner)
        cards = Table([card_cols], colWidths=[cw] * n)
        ts = TableStyle([
            ("BACKGROUND",    (0, 0), (-1, -1), HexColor("#f8fafc")),
            ("BOX",           (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("INNERGRID",     (0, 0), (-1, -1), 0.5, HexColor("#e2e8f0")),
            ("TOPPADDING",    (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ])
        for i, (sev, _) in enumerate(sev_items):
            ts.add("LINEABOVE", (i, 0), (i, 0), 3, _sev_color(sev))
        cards.setStyle(ts)
        story.append(cards)

    story.append(Spacer(1, 10))
    return story


# ── Top types ─────────────────────────────────────────────────────────────────

def _top_types(report: SastReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec2"), st)

    td = st["td"]
    rows = [["#", _L(lang, "col_vuln"), _L(lang, "col_count"), _L(lang, "col_ratio")]]
    for i, (name, cnt) in enumerate(report.top_names, 1):
        pct = cnt / report.total * 100 if report.total else 0
        rows.append([str(i), Paragraph(name, td), str(cnt), f"{pct:.1f}%"])

    cw = [CONTENT_W * r for r in [0.05, 0.65, 0.15, 0.15]]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    tbl.setStyle(_tbl_style())
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


# ── Top files ─────────────────────────────────────────────────────────────────

def _top_files(report: SastReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec3"), st)

    td_mono = st["td_mono"]
    rows = [["#", _L(lang, "col_file"), _L(lang, "col_findings")]]
    for i, (fname, cnt) in enumerate(report.top_files, 1):
        rows.append([str(i), Paragraph(fname, td_mono), str(cnt)])

    cw = [CONTENT_W * r for r in [0.05, 0.80, 0.15]]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style()
    ts.add("FONTNAME", (1, 1), (1, -1), FONT_MONO)
    ts.add("FONTSIZE", (1, 1), (1, -1), 6.5)
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


# ── Detail table ──────────────────────────────────────────────────────────────

def _detail(report: SastReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec4"), st)

    header = ["#", _L(lang, "col_severity"), _L(lang, "col_file_line"),
              _L(lang, "col_vuln"), _L(lang, "col_cwe"), _L(lang, "col_owasp")]
    rows = [header]
    td      = st["td"]
    td_mono = st["td_mono"]

    sorted_vulns = report.sorted_vulnerabilities()
    for i, v in enumerate(sorted_vulns, 1):
        cwe_str   = ", ".join(v.cwe[:2]) or "—"
        owasp_str = ", ".join(v.owasp[:1]) or "—"
        sev_style = ParagraphStyle(
            f"sev_{v.severity}", fontName=FONT_BOLD, fontSize=7,
            textColor=white, alignment=1,
            backColor=_sev_color(v.severity),
            borderPadding=(2, 4, 2, 4),
        )
        rows.append([
            str(i),
            Paragraph(v.severity, sev_style),
            Paragraph(f"{v.file}:{v.start_line}", td_mono),
            Paragraph(v.name, td),
            Paragraph(cwe_str, td),
            Paragraph(owasp_str, td),
        ])

    cw = [CONTENT_W * r for r in [0.04, 0.10, 0.24, 0.36, 0.14, 0.12]]
    tbl = Table(rows, colWidths=cw, repeatRows=1, splitByRow=1)
    ts = _tbl_style()
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


# ── Recommendations ───────────────────────────────────────────────────────────

def _recommendations(report: SastReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec5"), st)

    name_counts = dict(report.top_names)
    items = [_L(lang, "rec_priority")]

    rfi = next((k for k in name_counts if "Remote File Inclusion" in k or "include/require" in k.lower()), None)
    if rfi:
        raw = _L(lang, "rec_rfi").format(count=name_counts[rfi])
        items.append(raw)

    ev = next((k for k in name_counts if "Eval" in k or "eval" in k.lower()), None)
    if ev:
        raw = _L(lang, "rec_eval").format(count=name_counts[ev])
        items.append(raw)

    hk = next((k for k in name_counts if "weak hash" in k.lower() or "hash" in k.lower()), None)
    if hk:
        items.append(_L(lang, "rec_hash"))

    rk = next((k for k in name_counts if "regular expression" in k.lower()), None)
    if rk:
        items.append(_L(lang, "rec_regex"))

    cmd = next((k for k in name_counts if "OS Command" in k or "command injection" in k.lower()), None)
    if cmd:
        raw = _L(lang, "rec_cmd").format(count=name_counts[cmd])
        items.append(raw)

    items.append(_L(lang, "rec_cicd"))

    def _strip_html(s: str) -> str:
        import re
        # convert <li> items and strip HTML
        s = s.replace("<li>", "").replace("</li>", "")
        s = re.sub(r"<strong>(.*?)</strong>", r"\1", s)
        s = re.sub(r"<em>(.*?)</em>", r"\1", s)
        s = re.sub(r"<code>(.*?)</code>", r"\1", s)
        s = re.sub(r"<[^>]+>", "", s)
        return s.strip()

    for idx, item in enumerate(items, 1):
        story.append(Paragraph(f"{idx}.  {_strip_html(item)}", st["rec"]))

    story.append(Spacer(1, 16))
    now = datetime.now().strftime("%d %B %Y %H:%M")
    story.append(Paragraph(
        f'<link href="https://github.com/monobilisim/gl2pdf">gl2pdf</link>  |  {now}',
        ParagraphStyle("fn", fontName=FONT_REG, fontSize=7,
                       textColor=HexColor("#94a3b8"), alignment=1),
    ))
    return story


# ── Build story ───────────────────────────────────────────────────────────────

def _build_story(report: SastReport, title: str | None, repo: str | None, lang: str) -> list:
    if lang not in _LABELS:
        lang = "en"
    cover_title = title or _L(lang, "default_title")
    kicker = _L(lang, "kicker") if title else None
    st = _styles()

    story = []
    story.append(NextPageTemplate("cover"))
    story.append(_Cover(report, cover_title, repo, lang, kicker))
    story.append(NextPageTemplate("normal"))
    story.append(PageBreak())

    story += _exec_summary(report, lang, st)
    story.append(PageBreak())
    story += _top_types(report, lang, st)
    story.append(PageBreak())
    story += _top_files(report, lang, st)
    story.append(PageBreak())
    story += _detail(report, lang, st)
    story.append(PageBreak())
    story += _recommendations(report, lang, st)

    return story


def _make_doc(buf, lang: str) -> _Doc:
    footer_label = _L(lang, "page_footer")
    doc = _Doc(buf, lang=lang, footer_label=footer_label,
               pagesize=A4,
               leftMargin=MARGIN_L, rightMargin=MARGIN_R,
               topMargin=MARGIN_T, bottomMargin=MARGIN_B)
    cover_frame  = Frame(0, 0, PAGE_W, PAGE_H, id="cover",
                         leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    normal_frame = Frame(MARGIN_L, MARGIN_B, CONTENT_W,
                         PAGE_H - MARGIN_T - MARGIN_B, id="main",
                         leftPadding=0, rightPadding=0,
                         topPadding=0, bottomPadding=0)
    doc.addPageTemplates([
        PageTemplate(id="cover",  frames=[cover_frame]),
        PageTemplate(id="normal", frames=[normal_frame]),
    ])
    return doc


# ── Public API ────────────────────────────────────────────────────────────────

def render_bytes_sast(
    report: SastReport,
    title: str | None = None,
    repo: str | None = None,
    lang: str = "en",
) -> bytes:
    """Render SAST report to PDF bytes using ReportLab."""
    buf = io.BytesIO()
    doc = _make_doc(buf, lang)
    doc.build(_build_story(report, title, repo, lang))
    return buf.getvalue()


def render_sast(
    report: SastReport,
    output_path: Path,
    title: str | None = None,
    repo: str | None = None,
    lang: str = "en",
) -> Path:
    """Render SAST report to PDF file using ReportLab. Returns output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_bytes_sast(report, title=title, repo=repo, lang=lang))
    return output_path.resolve()
