from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def write_pdf(path: str, text: str):
    c = canvas.Canvas(path, pagesize=letter)
    width, height = letter

    y = height - 50  # top margin

    for line in text.split("\n"):
        if y < 50:
            c.showPage()
            y = height - 50
        c.drawString(50, y, line)
        y -= 14

    c.save()
