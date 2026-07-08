from paie.clients import Client
from paie.rapprochement import clients_dans_texte, extraire_texte, rapprocher
from paie.textes import normaliser
from tests.conftest import pdf_avec_texte

DUPE = Client("Dupé", "Jean-François", "jf@x.fr")
MARTIN = Client("MARTIN", "claire", "cm@x.fr")


def test_normaliser():
    assert normaliser("  Jean-François  DUPÉ ") == "JEAN FRANCOIS DUPE"


def test_nom_trouve_malgre_accents_et_ordre():
    texte = "BULLETIN DE PAIE\nSalarié : DUPE Jean-Francois\nPériode 06/2026"
    assert clients_dans_texte(texte, [DUPE, MARTIN]) == [DUPE]
    # ordre prénom puis nom
    assert clients_dans_texte("Mme claire Martin", [DUPE, MARTIN]) == [MARTIN]


def test_pas_de_faux_positif_sur_nom_seul():
    assert clients_dans_texte("M. MARTIN Bernard", [MARTIN]) == []


def test_extraction_pdf_et_rapprochement():
    pdf = pdf_avec_texte("Releve mensuel", "Client : Jean-Francois DUPE")
    texte = extraire_texte(pdf)
    assert clients_dans_texte(texte, [DUPE, MARTIN]) == [DUPE]


def test_rapprocher_repli_sur_nom_de_fichier():
    # texte vide (scan sans OCR) -> repli sur le nom du fichier
    docs = {"releve_martin_claire_juin.pdf": ""}
    resultat = rapprocher(docs, [DUPE, MARTIN])
    assert resultat[MARTIN.cle] == ["releve_martin_claire_juin.pdf"]
    assert resultat[DUPE.cle] == []
