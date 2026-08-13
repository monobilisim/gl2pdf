"""
cq_renderer.py
--------------
ReportLab-based PDF renderer for Code Quality reports.
Handles 121K+ issues without memory issues (splitByRow=1).
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
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

from .cq_parser import CqReport, SEVERITY_ORDER
from .cq_template import _LABELS, SEVERITY_COLOR

# Reuse font registration from renderer
from .renderer import FONT_REG, FONT_BOLD, FONT_MONO, _hex, PAGE_W, PAGE_H


def _esc(text: str) -> str:
    """Escape special XML/HTML chars for ReportLab Paragraph."""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
from .renderer import MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B, CONTENT_W

BRAND_COLOR = "#FA002A"


def _sev_color(sev: str) -> HexColor:
    return _hex(SEVERITY_COLOR.get(sev, "#95a5a6"))


def _row_bg() -> HexColor:
    return HexColor("#fff5f6")


def _L(lang: str, key: str) -> str:
    return _LABELS.get(lang, _LABELS["en"]).get(key, _LABELS["en"].get(key, key))


# ── Styles ────────────────────────────────────────────────────────────────────

def _styles() -> dict[str, ParagraphStyle]:
    bc = _hex(BRAND_COLOR)
    return {
        "section_title": ParagraphStyle(
            "cq_section_title", fontName=FONT_BOLD, fontSize=11,
            textColor=bc, spaceBefore=12, spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "cq_body", fontName=FONT_REG, fontSize=8.5,
            textColor=HexColor("#1e293b"), leading=13, spaceAfter=7,
        ),
        "info_key": ParagraphStyle(
            "cq_info_key", fontName=FONT_BOLD, fontSize=7.5, textColor=bc,
        ),
        "info_val": ParagraphStyle(
            "cq_info_val", fontName=FONT_REG, fontSize=7.5,
            textColor=HexColor("#334155"),
        ),
        "td": ParagraphStyle(
            "cq_td", fontName=FONT_REG, fontSize=7,
            textColor=HexColor("#1e293b"), wordWrap="CJK", leading=9,
        ),
        "td_mono": ParagraphStyle(
            "cq_td_mono", fontName=FONT_MONO, fontSize=6.5,
            textColor=HexColor("#334155"), wordWrap="CJK", leading=8,
        ),
        "rec": ParagraphStyle(
            "cq_rec", fontName=FONT_REG, fontSize=8,
            textColor=HexColor("#1e293b"), leading=13,
            leftIndent=10, spaceAfter=5,
        ),
    }


# ── Table style ───────────────────────────────────────────────────────────────

def _tbl_style() -> TableStyle:
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
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [white, _row_bg()]),
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
        c.drawRightString(PAGE_W - MARGIN_R, y_text, f"Page {self.page}")
        c.restoreState()


# ── Cover ─────────────────────────────────────────────────────────────────────

class _Cover(Flowable):
    def __init__(self, report: CqReport, title: str, repo: str | None, lang: str, kicker: str | None = None):
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

        c.setFillColor(HexColor("#ffffff"))
        c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        c.setFillColor(bc)
        c.rect(0, 0, PAGE_W, 6, fill=1, stroke=0)

        cy = PAGE_H * 0.62
        if self.kicker:
            c.setFont(FONT_REG, 11)
            c.setFillColor(HexColor("#6b7280"))
            c.drawCentredString(cx, cy + 9 * mm, self.kicker)
        c.setFont(FONT_BOLD, 26)
        c.setFillColor(HexColor("#1a1a1a"))
        c.drawCentredString(cx, cy, self.title)
        cy -= 11 * mm

        if self.repo:
            c.setFont(FONT_REG, 12)
            c.setFillColor(HexColor("#555555"))
            c.drawCentredString(cx, cy, self.repo)
            cy -= 10 * mm

        cy -= 6 * mm

        now = datetime.now().strftime("%d %B %Y %H:%M")
        lang = self.lang
        r = self.report
        meta = [
            f"{_L(lang,'source_file')}: {r.source_file.name}",
            f"{_L(lang,'report_date')}: {now}",
        ]
        c.setFont(FONT_REG, 9)
        c.setFillColor(HexColor("#666666"))
        for line in meta:
            c.drawCentredString(cx, cy, line)
            cy -= 6.5 * mm

        cy -= 10 * mm

        sev_items = [(s, r.severity_counts.get(s, 0)) for s in SEVERITY_ORDER if r.severity_counts.get(s, 0) > 0]
        if sev_items:
            from reportlab.lib.colors import Color
            pill_gap = 10
            n_pills = len(sev_items)
            pill_w = min(60, (CONTENT_W - (n_pills - 1) * pill_gap) / n_pills)
            pill_h = 38
            count_fs = min(16, pill_w * 0.30)
            label_fs = min(7, pill_w * 0.13)
            total_w = n_pills * pill_w + (n_pills - 1) * pill_gap
            px = cx - total_w / 2
            pill_top = cy
            for sev, cnt in sev_items:
                sc = _sev_color(sev)
                c.setFillColor(Color(sc.red, sc.green, sc.blue, 0.12))
                c.setStrokeColor(Color(sc.red, sc.green, sc.blue, 0.5))
                c.setLineWidth(0.8)
                c.roundRect(px, pill_top - pill_h, pill_w, pill_h, 5, fill=1, stroke=1)
                c.setFillColor(sc)
                c.setStrokeColor(sc)
                c.roundRect(px, pill_top - 4, pill_w, 4, 2, fill=1, stroke=0)
                c.setFont(FONT_BOLD, count_fs)
                c.setFillColor(sc)
                c.drawCentredString(px + pill_w / 2, pill_top - pill_h * 0.45, str(cnt))
                c.setFont(FONT_REG, label_fs)
                c.setFillColor(HexColor("#555555"))
                c.drawCentredString(px + pill_w / 2, pill_top - pill_h + 6, sev.upper())
                px += pill_w + pill_gap
            cy = pill_top - pill_h - 14 * mm

        conf = _L(lang, "confidential")
        tag_w = min(len(conf) * 5.5 + 30, CONTENT_W * 0.8)
        tag_h = 18
        tag_x = cx - tag_w / 2
        c.setFillColor(bc)
        c.roundRect(tag_x, cy - 4, tag_w, tag_h, 3, fill=1, stroke=0)
        c.setFont(FONT_BOLD, 7.5)
        c.setFillColor(white)
        c.drawCentredString(cx, cy + 3, conf)

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

def _exec_summary(report: CqReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec1"), st)

    now = datetime.now().strftime("%d %B %Y %H:%M")
    info = [
        (_L(lang, "source_file"),  str(report.source_file.name)),
        (_L(lang, "total_issues"), str(report.total)),
        (_L(lang, "report_date"),  now),
    ]
    if report.primary_analyzer:
        info.append((_L(lang, "analyzer"), report.primary_analyzer))
    if report.analyzer_versions:
        info.append((_L(lang, "analyzer_version"), ", ".join(report.analyzer_versions)))
    if report.identifier_count:
        info.append((_L(lang, "rules"), str(report.identifier_count)))
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

    raw_summary = _L(lang, "summary").format(
        source_file=report.source_file.name,
        total=report.total,
    )
    summary = raw_summary.replace("<em>", "<i>").replace("</em>", "</i>").replace("<strong>", "<b>").replace("</strong>", "</b>")
    story.append(Paragraph(summary, st["body"]))

    sev_items = [(s, report.severity_counts.get(s, 0)) for s in SEVERITY_ORDER if report.severity_counts.get(s, 0) > 0]
    if sev_items:
        n = len(sev_items)
        cw = CONTENT_W / n
        card_cols = []
        for sev, cnt in sev_items:
            sc = _sev_color(sev)
            inner = Table(
                [[Paragraph(str(cnt), ParagraphStyle("cq_cn", fontName=FONT_BOLD, fontSize=18,
                                                      textColor=sc, alignment=1))],
                 [Paragraph(sev.upper(), ParagraphStyle("cq_cl", fontName=FONT_BOLD, fontSize=6,
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


# ── Top checks ────────────────────────────────────────────────────────────────

def _top_checks(report: CqReport, lang: str, st: dict) -> list:
    is_phpstan = (report.primary_analyzer or "").lower() == "phpstan"
    story = _section(_L(lang, "sec2_phpstan") if is_phpstan else _L(lang, "sec2"), st)

    td_mono = st["td_mono"]
    label = _L(lang, "col_message") if is_phpstan else _L(lang, "col_check")
    rows = [["#", label, _L(lang, "col_count"), _L(lang, "col_ratio")]]
    source_rows = report.top_descriptions if is_phpstan else report.top_checks
    for i, (check, cnt) in enumerate(source_rows, 1):
        pct = cnt / report.total * 100 if report.total else 0
        rows.append([str(i), Paragraph(_esc(check), td_mono), str(cnt), f"{pct:.1f}%"])

    cw = [CONTENT_W * r for r in [0.05, 0.65, 0.15, 0.15]]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style()
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


def _rule_summary(report: CqReport, lang: str, st: dict) -> list:
    is_phpstan = (report.primary_analyzer or "").lower() == "phpstan"
    if not is_phpstan or not report.top_identifiers:
        return []

    story = _section(_L(lang, "sec_rules"), st)

    td_mono = st["td_mono"]
    rows = [["#", _L(lang, "col_identifier"), _L(lang, "col_count"), _L(lang, "col_ratio")]]
    for i, (identifier, cnt) in enumerate(report.top_identifiers, 1):
        pct = cnt / report.total * 100 if report.total else 0
        rows.append([str(i), Paragraph(_esc(identifier), td_mono), str(cnt), f"{pct:.1f}%"])

    cw = [CONTENT_W * r for r in [0.05, 0.65, 0.15, 0.15]]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    tbl.setStyle(_tbl_style())
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


# ── Top files ─────────────────────────────────────────────────────────────────

def _top_files(report: CqReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec3"), st)

    td_mono = st["td_mono"]
    rows = [["#", _L(lang, "col_file"), _L(lang, "col_findings")]]
    for i, (fname, cnt) in enumerate(report.top_files, 1):
        rows.append([str(i), Paragraph(_esc(fname), td_mono), str(cnt)])

    cw = [CONTENT_W * r for r in [0.05, 0.80, 0.15]]
    tbl = Table(rows, colWidths=cw, repeatRows=1)
    ts = _tbl_style()
    tbl.setStyle(ts)
    story.append(tbl)
    story.append(Spacer(1, 8))
    return story


# ── Detail table ──────────────────────────────────────────────────────────────

_CHUNK_SIZE = 800  # rows per table chunk for performance


def _make_chunk_tbl(header: list, data_rows: list, cw: list, first_chunk: bool) -> Table:
    """Build one Table chunk. Header repeated only on first chunk.
    Severity column uses Paragraph with backColor — no TableStyle coloring needed."""
    rows = ([header] + data_rows) if first_chunk else data_rows
    repeat = 1 if first_chunk else 0
    tbl = Table(rows, colWidths=cw, repeatRows=repeat, splitByRow=1)
    tbl.setStyle(_tbl_style())
    return tbl


def _detail(report: CqReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec4"), st)

    header = ["#", _L(lang, "col_severity"), _L(lang, "col_file_line"),
              _L(lang, "col_check"), _L(lang, "col_description")]
    cw = [CONTENT_W * r for r in [0.04, 0.10, 0.22, 0.25, 0.39]]

    td      = st["td"]
    td_mono = st["td_mono"]

    all_data: list[list] = []
    for i, issue in enumerate(report.sorted_issues(), 1):
        sev_style = ParagraphStyle(
            f"sev_{issue.severity}", fontName=FONT_BOLD, fontSize=7,
            textColor=white, alignment=1,
            backColor=_sev_color(issue.severity),
            borderPadding=(2, 4, 2, 4),
        )
        all_data.append([
            str(i),
            Paragraph(issue.severity.upper(), sev_style),
            Paragraph(_esc(f"{issue.path}:{issue.line}"), td_mono),
            Paragraph(_esc(issue.check_name), td_mono),
            Paragraph(_esc(issue.description), td),
        ])

    # Split into chunks to avoid massive single-table layout overhead
    for chunk_idx in range(0, len(all_data), _CHUNK_SIZE):
        chunk = all_data[chunk_idx:chunk_idx + _CHUNK_SIZE]
        tbl = _make_chunk_tbl(header, chunk, cw, first_chunk=(chunk_idx == 0))
        story.append(tbl)

    story.append(Spacer(1, 8))
    return story


# ── Recommendations ───────────────────────────────────────────────────────────

def _recommendations(report: CqReport, lang: str, st: dict) -> list:
    story = _section(_L(lang, "sec5"), st)

    name_counts = dict(report.top_checks)
    is_phpstan = (report.primary_analyzer or "").lower() == "phpstan"
    items = [_L(lang, "rec_priority")]

    if is_phpstan:
        items.append(_L(lang, "rec_phpstan"))
        items.append(_L(lang, "rec_phpstan_level"))
        items.append(_L(lang, "rec_legacy"))
        for idx, item in enumerate(items, 1):
            story.append(Paragraph(f"{idx}.  {item}", st["rec"]))

        story.append(Spacer(1, 16))
        now = datetime.now().strftime("%d %B %Y %H:%M")
        story.append(Paragraph(
            f'<link href="https://github.com/monobilisim/gl2pdf">gl2pdf</link>  |  {now}',
            ParagraphStyle("fn", fontName=FONT_REG, fontSize=7,
                           textColor=HexColor("#94a3b8"), alignment=1),
        ))
        return story

    # Tab indentation
    tab_key = next((k for k in name_counts if "TabIndent" in k or "tab" in k.lower()), None)
    if tab_key:
        items.append(_L(lang, "rec_tabs").format(count=name_counts[tab_key]))

    # Operator / control structure spacing
    spacing_key = next((k for k in name_counts if "Spacing" in k or "spacing" in k.lower()), None)
    if spacing_key:
        items.append(_L(lang, "rec_spacing").format(count=name_counts[spacing_key]))

    # Line length
    line_key = next((k for k in name_counts if "LineLength" in k or "line_length" in k.lower()), None)
    if line_key:
        items.append(_L(lang, "rec_line_len").format(count=name_counts[line_key]))

    items.append(_L(lang, "rec_formatter"))
    items.append(_L(lang, "rec_phpcs"))

    for idx, item in enumerate(items, 1):
        story.append(Paragraph(f"{idx}.  {item}", st["rec"]))

    story.append(Spacer(1, 16))
    now = datetime.now().strftime("%d %B %Y %H:%M")
    story.append(Paragraph(
        f'<link href="https://github.com/monobilisim/gl2pdf">gl2pdf</link>  |  {now}',
        ParagraphStyle("fn", fontName=FONT_REG, fontSize=7,
                       textColor=HexColor("#94a3b8"), alignment=1),
    ))
    return story


# ── Build story ───────────────────────────────────────────────────────────────

def _build_story(report: CqReport, title: str | None, repo: str | None, lang: str) -> list:
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
    story += _top_checks(report, lang, st)
    story += _rule_summary(report, lang, st)
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

def render_bytes_cq(
    report: CqReport,
    title: str | None = None,
    repo: str | None = None,
    lang: str = "en",
) -> bytes:
    """Render Code Quality report to PDF bytes using ReportLab."""
    buf = io.BytesIO()
    doc = _make_doc(buf, lang)
    doc.build(_build_story(report, title, repo, lang))
    return buf.getvalue()


def render_cq(
    report: CqReport,
    output_path: Path,
    title: str | None = None,
    repo: str | None = None,
    lang: str = "en",
) -> Path:
    """Render Code Quality report to PDF file using ReportLab. Returns output_path."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(render_bytes_cq(report, title=title, repo=repo, lang=lang))
    return output_path.resolve()
