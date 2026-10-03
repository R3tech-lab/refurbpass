"""Génération du certificat PDF avec ReportLab (Python pur : pas de GTK à installer)."""
from __future__ import annotations

import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

STATUS_LABELS = {
    "OK": "Bon",
    "Warning": "À surveiller",
    "Critical": "Critique",
    "Unavailable": "Non mesuré",
    "NotApplicable": "Sans objet",
}
STATUS_COLORS = {
    "OK": "#27ae60",
    "Warning": "#f39c12",
    "Critical": "#e74c3c",
    "Unavailable": "#95a5a6",
    "NotApplicable": "#95a5a6",
}

DARK = colors.HexColor("#2c3e50")
GREY = colors.HexColor("#7f8c8d")
LIGHT = colors.HexColor("#f8f9fa")
LINE = colors.HexColor("#eeeeee")


def new_report_id() -> str:
    return f"{datetime.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2).upper()}"


def build_qr(text: str, size: float = 70) -> Drawing:
    """QR code vectoriel de `size` points de côté."""
    widget = QrCodeWidget(text)
    x0, y0, x1, y1 = widget.getBounds()
    width, height = x1 - x0, y1 - y0
    drawing = Drawing(size, size, transform=[size / width, 0, 0, size / height, 0, 0])
    drawing.add(widget)
    return drawing


def _score_color(score: Optional[int]) -> str:
    if score is None:
        return "#95a5a6"
    return "#27ae60" if score >= 80 else "#f39c12" if score >= 60 else "#e74c3c"


def _styles() -> dict:
    base = {"fontName": "Helvetica", "textColor": colors.HexColor("#333333")}
    return {
        "shop": ParagraphStyle("shop", fontName="Helvetica-Bold", fontSize=20, textColor=DARK, leading=24),
        "grey": ParagraphStyle("grey", fontSize=9, textColor=GREY, leading=12, fontName="Helvetica"),
        "qrid": ParagraphStyle("qrid", fontSize=7, textColor=GREY, leading=9,
                               fontName="Helvetica", alignment=TA_CENTER),
        "label": ParagraphStyle("label", fontName="Helvetica-Bold", fontSize=8, textColor=GREY, leading=10),
        "cell": ParagraphStyle("cell", fontSize=9.5, leading=12, **base),
        "h3": ParagraphStyle("h3", fontName="Helvetica-Bold", fontSize=13, textColor=DARK,
                             spaceBefore=14, spaceAfter=6),
        "score_label": ParagraphStyle("score_label", fontSize=11, textColor=GREY, alignment=TA_CENTER,
                                      fontName="Helvetica", leading=14),
        "note": ParagraphStyle("note", fontSize=8, textColor=GREY, leading=10, fontName="Helvetica",
                               spaceBefore=6),
        "wp_title": ParagraphStyle("wp_title", fontName="Helvetica-Bold", fontSize=11,
                                   textColor=colors.HexColor("#c0392b"), spaceAfter=4),
        "wp": ParagraphStyle("wp", fontSize=9.5, leading=13, leftIndent=10, **base),
        "footer": ParagraphStyle("footer", fontSize=8, textColor=colors.HexColor("#bdc3c7"),
                                 alignment=TA_CENTER, fontName="Helvetica"),
    }


def _p(text: Any, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(str(text)), style)


class ReportGenerator:
    def __init__(self, shop_name: str):
        self.shop_name = shop_name

    def build_story(self, system_info: Any, global_health: Any, report_id: str) -> list:
        s = _styles()
        story: list = []
        width = A4[0] - 36 * mm

        # --- En-tête : atelier + date, QR code à droite ---
        left = [
            _p(self.shop_name, s["shop"]),
            _p(f"Date du rapport : {datetime.now():%d/%m/%Y %H:%M}", s["grey"]),
        ]
        right = [build_qr(f"RefurbPass-ID:{report_id}"), _p(report_id, s["qrid"])]
        header = Table([[left, right]], colWidths=[width - 34 * mm, 34 * mm])
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (1, 0), (1, 0), "CENTER"),
            ("LINEBELOW", (0, 0), (-1, 0), 2, DARK),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (0, 0), 0),
        ]))
        story += [header, Spacer(1, 14)]

        # --- Score global ---
        score = global_health.overall_score
        score_text = "—" if score is None else f"{score}/100"
        story.append(Paragraph(
            f'<font color="{_score_color(score)}">{score_text}</font>',
            ParagraphStyle("score", fontName="Helvetica-Bold", fontSize=54, leading=60, alignment=TA_CENTER),
        ))
        story.append(_p(
            "Score non calculable : aucun composant mesuré" if score is None else "Score global de santé",
            s["score_label"],
        ))

        # --- Informations appareil ---
        story.append(_p("Informations appareil", s["h3"]))
        rows = [
            [_p("MODÈLE", s["label"]), _p(system_info.model, s["cell"]),
             _p("OS", s["label"]), _p(system_info.os, s["cell"])],
            [_p("CPU", s["label"]), _p(system_info.cpu, s["cell"]),
             _p("RAM", s["label"]), _p(system_info.ram, s["cell"])],
            [_p("N° DE SÉRIE", s["label"]), _p(system_info.serial_number, s["cell"]),
             _p("BIOS", s["label"]), _p(system_info.bios_version, s["cell"])],
        ]
        device = Table(rows, colWidths=[26 * mm, 60 * mm, 16 * mm, width - 102 * mm])
        device.setStyle(TableStyle([
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ("BACKGROUND", (0, 0), (0, -1), LIGHT),
            ("BACKGROUND", (2, 0), (2, -1), LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(device)

        # --- Détail des composants ---
        story.append(_p("Détail des composants", s["h3"]))
        data = [[_p(h, s["label"]) for h in ("COMPOSANT", "STATUT", "DÉTAILS", "SCORE")]]
        for comp in global_health.component_scores:
            color = STATUS_COLORS.get(comp.status, "#333333")
            label = STATUS_LABELS.get(comp.status, comp.status)
            shown = "—" if comp.status in ("Unavailable", "NotApplicable") else f"{comp.score}/100"
            data.append([
                _p(comp.name, s["cell"]),
                Paragraph(f'<font color="{color}"><b>{escape(label)}</b></font>', s["cell"]),
                _p(comp.details, s["cell"]),
                _p(shown, s["cell"]),
            ])
        comps = Table(data, colWidths=[28 * mm, 28 * mm, width - 28 * mm - 28 * mm - 22 * mm, 22 * mm],
                      repeatRows=1)
        comps.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
            ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(comps)
        story.append(_p("Le score global est calculé uniquement sur les composants effectivement mesurés.",
                        s["note"]))

        # --- Points d'attention ---
        if global_health.summary_weak_points:
            cell = [_p("Points d'attention", s["wp_title"])]
            cell += [_p(f"•  {wp}", s["wp"]) for wp in global_health.summary_weak_points]
            box = Table([[cell]], colWidths=[width])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fdf2f2")),
                ("LINEBEFORE", (0, 0), (0, -1), 3, colors.HexColor("#e74c3c")),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]))
            story += [Spacer(1, 12), box]

        story += [Spacer(1, 28), _p("Certificat de santé généré par RefurbPass", s["footer"])]
        return story

    def generate(self, system_info: Any, global_health: Any, output_path: str) -> str:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        report_id = new_report_id()
        doc = SimpleDocTemplate(
            str(output), pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
            title=f"Certificat de santé - {self.shop_name}", author=self.shop_name,
        )
        doc.build(self.build_story(system_info, global_health, report_id))
        return str(output)
