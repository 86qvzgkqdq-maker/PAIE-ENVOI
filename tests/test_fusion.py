from pypdf import PdfReader

from paie.fusion import fusionner, nom_fichier_sur
from tests.conftest import pdf_avec_texte


def test_nom_fichier_sur():
    assert nom_fichier_sur("DUPÉ Jean-François") == "DUPE_Jean_Francois"
    assert nom_fichier_sur("Juin 2026") == "Juin_2026"


def test_fusion_concatene_les_pages(tmp_path):
    bulletin = pdf_avec_texte("BULLETIN DE PAIE", "DUPE Jean-Francois")
    releve = pdf_avec_texte("RELEVE THESEE", "DUPE Jean-Francois")
    destination = tmp_path / "sortie" / "DUPE_Jean_Francois.pdf"

    fusionner([bulletin, releve], destination)

    lecteur = PdfReader(destination)
    assert len(lecteur.pages) == 2
    assert "BULLETIN" in lecteur.pages[0].extract_text()
    assert "THESEE" in lecteur.pages[1].extract_text()
