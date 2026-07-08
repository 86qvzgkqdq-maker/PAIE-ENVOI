import io

import pytest
from fpdf import FPDF
from openpyxl import Workbook


def pdf_avec_texte(*lignes: str) -> io.BytesIO:
    """Petit PDF d'une page contenant les lignes de texte données."""
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("helvetica", size=12)
    for ligne in lignes:
        pdf.cell(text=ligne)
        pdf.ln()
    return io.BytesIO(pdf.output())


@pytest.fixture
def excel_clients(tmp_path):
    """Fichier Excel de 3 clients avec en-têtes accentués."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Nom", "Prénom", "E-mail"])
    ws.append(["Dupé", "Jean-François", "jf.dupe@exemple.fr"])
    ws.append(["MARTIN", "claire", "claire.martin@exemple.fr"])
    ws.append(["N'Guessan", "Aya", "aya.nguessan@exemple.fr"])
    ws.append(["SansEmail", "Paul", None])  # ignorée : email manquant
    chemin = tmp_path / "clients.xlsx"
    wb.save(chemin)
    return chemin
