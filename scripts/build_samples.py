# /// script
# requires-python = ">=3.12"
# dependencies = ["reportlab==4.4.9"]
# ///
"""Render the fictional invoices and their evidence as printable two-page packets."""

import json
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "invoice_review" / "data"
OUTPUT = ROOT / "samples"
WIDTH, HEIGHT = A4
LEFT, RIGHT = 22 * mm, WIDTH - 22 * mm
INK, TEAL, MUTED = "#142B39", "#076D67", "#485F68"


def put(canvas, x, y, content, size=12, colour=INK, bold=False, right=False):
    canvas.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    canvas.setFillColor(colors.HexColor(colour))
    draw = canvas.drawRightString if right else canvas.drawString
    draw(x, y, str(content))


def paragraph(canvas, text, y, size=12):
    style = ParagraphStyle("body", fontName="Helvetica", fontSize=size,
                           leading=size * 1.45, textColor=colors.HexColor(INK))
    body = Paragraph(escape(text), style)
    _, height = body.wrap(RIGHT - LEFT, HEIGHT)
    body.drawOn(canvas, LEFT, y - height)
    return y - height


def footer(canvas, invoice_id, page):
    put(canvas, LEFT, 15 * mm, "Fictional sample for an invoice review demonstration", 9, MUTED)
    put(canvas, RIGHT, 15 * mm, f"{invoice_id}   /   {page} of 2", 9, MUTED, right=True)


def amount(cents):
    return f"${cents // 100:,}.{cents % 100:02}"


def build(invoice, sources):
    invoice_id = invoice["source_id"]
    canvas = Canvas(str(OUTPUT / f"{invoice_id}.pdf"), pagesize=A4, invariant=True)
    canvas.setTitle(f"{invoice_id} | {invoice['supplier']} | Fictional invoice packet")
    canvas.setAuthor("Invoice Review")
    top = HEIGHT - 25 * mm
    put(canvas, LEFT, top, invoice["supplier"], 17, TEAL, bold=True)
    put(canvas, LEFT, top - 52, "Supplier invoice", 28, bold=True)
    put(canvas, RIGHT, top - 51, invoice_id, 16, right=True)
    put(canvas, LEFT, top - 88, f"Billed to    {invoice['buyer']}")
    put(canvas, LEFT, top - 111, f"Job           {invoice['job']}")
    label = date.fromisoformat(invoice["issued_on"]).strftime("%d %B %Y")
    put(canvas, LEFT, top - 134, f"Issued      {label}")
    y = top - 197
    put(canvas, LEFT, y, "Description", 11, MUTED, bold=True)
    put(canvas, RIGHT, y, "Amount (AUD ex GST)", 11, MUTED, bold=True, right=True)
    for line in invoice["lines"]:
        y -= 31
        put(canvas, LEFT, y, line["description"])
        put(canvas, RIGHT, y, amount(line["amount_cents"]), right=True)
    canvas.setStrokeColor(colors.HexColor("#A1B3BA"))
    canvas.line(LEFT, y - 19, RIGHT, y - 19)
    put(canvas, LEFT, y - 47, "Total excluding GST", 15, bold=True)
    put(canvas, RIGHT, y - 47, amount(invoice["total_cents"]), 15, bold=True, right=True)
    footer(canvas, invoice_id, 1)
    canvas.showPage()
    put(canvas, LEFT, top, invoice_id, 15, TEAL, bold=True)
    put(canvas, LEFT, top - 49, "Purchasing evidence", 28, bold=True)
    y = paragraph(canvas, f"Source excerpts for {invoice['job']}. Status reflects the recorded paperwork.", top - 69) - 37
    for source_id in invoice["evidence_ids"]:
        source = sources[source_id]
        put(canvas, LEFT, y, f"{source_id}    /    {source['status'].capitalize()}", 11, TEAL, bold=True)
        put(canvas, LEFT, y - 24, source["title"], 15, bold=True)
        y = paragraph(canvas, source["excerpt"], y - 34) - 35
    footer(canvas, invoice_id, 2)
    canvas.save()


def main():
    OUTPUT.mkdir(exist_ok=True)
    invoices = json.loads((DATA / "invoices.json").read_text(encoding="utf-8"))
    evidence = json.loads((DATA / "evidence.json").read_text(encoding="utf-8"))
    sources = {source["source_id"]: source for source in evidence}
    for invoice in invoices:
        build(invoice, sources)


if __name__ == "__main__":
    main()
