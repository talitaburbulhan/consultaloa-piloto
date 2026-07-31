from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .schemas import SearchResponse


def search_pdf(response: SearchResponse) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Consulta documental das LOAs",
    )
    styles = getSampleStyleSheet()
    evidence_style = ParagraphStyle(
        "Evidence",
        parent=styles["BodyText"],
        borderColor=colors.HexColor("#1f5742"),
        leftIndent=8,
        fontSize=9,
        leading=13,
    )
    story = [
        Paragraph("LOA - Pesquisa com evidências", styles["Title"]),
        Spacer(1, 6 * mm),
        Paragraph(f"<b>Consulta:</b> {escape(response.query)}", styles["BodyText"]),
        Spacer(1, 5 * mm),
    ]
    if response.summary:
        story.extend([Paragraph(escape(response.summary), styles["BodyText"]), Spacer(1, 4 * mm)])
    for index, item in enumerate(response.evidence, start=1):
        reference = (
            f"<b>Evidência {index}</b> - {escape(item.document)} ({item.year}), "
            f"página PDF {item.pdf_page}"
        )
        if item.printed_page:
            reference += f", impressa {escape(item.printed_page)}"
        story.extend(
            [
                Paragraph(reference, styles["Heading3"]),
                Paragraph(escape(item.original_text).replace("\n", "<br/>"), evidence_style),
                Spacer(1, 5 * mm),
            ]
        )
    story.extend(
        [
            Paragraph("Nota editorial", styles["Heading2"]),
            Paragraph(
                "Este relatório reproduz evidências do acervo documental. "
                "A conclusão editorial pertence ao jornalista.",
                styles["BodyText"],
            ),
        ]
    )
    document.build(story)
    return output.getvalue()
