"""Génère un jeu de fichiers d'essai dans exemples/ (clients fictifs).

Usage : .venv/bin/python scripts/generer_exemples.py
Nécessite fpdf2 (requirements-dev.txt).
"""

from pathlib import Path

from fpdf import FPDF
from openpyxl import Workbook

DOSSIER = Path(__file__).resolve().parent.parent / "exemples"

CLIENTS = [
    ("Dupé", "Jean-François", "jf.dupe@exemple.fr"),
    ("MARTIN", "Claire", "claire.martin@exemple.fr"),
    ("N'Guessan", "Aya", "aya.nguessan@exemple.fr"),
]


def pdf(chemin: Path, *lignes: str) -> None:
    doc = FPDF()
    doc.add_page()
    doc.set_font("helvetica", size=12)
    for ligne in lignes:
        doc.cell(text=ligne)
        doc.ln()
    chemin.write_bytes(doc.output())


def main() -> None:
    DOSSIER.mkdir(exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.append(["Nom", "Prénom", "Email"])
    for nom, prenom, email in CLIENTS:
        ws.append([nom, prenom, email])
    wb.save(DOSSIER / "clients.xlsx")

    for i, (nom, prenom, _) in enumerate(CLIENTS, 1):
        pdf(DOSSIER / f"bulletin_{i}.pdf",
            "BULLETIN DE PAIE", f"Salarie : {nom.upper()} {prenom}",
            "Periode : 06/2026")
        pdf(DOSSIER / f"releve_{i}.pdf",
            "RELEVE MENSUEL - THESEE", f"Client : {prenom} {nom.upper()}",
            "Periode : 06/2026")

    print(f"Fichiers d'essai créés dans {DOSSIER}")


if __name__ == "__main__":
    main()
