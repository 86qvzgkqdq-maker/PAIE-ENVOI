"""Rapprochement des PDF avec les clients par nom + prénom."""

from pypdf import PdfReader

from .clients import Client
from .textes import normaliser


def extraire_texte(fichier, max_pages: int = 3) -> str:
    """Texte des premières pages d'un PDF (chemin ou objet fichier)."""
    try:
        lecteur = PdfReader(fichier)
    except Exception:
        return ""
    morceaux = []
    for page in lecteur.pages[:max_pages]:
        try:
            morceaux.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(morceaux)


def clients_dans_texte(texte: str, clients: list[Client]) -> list[Client]:
    """Clients dont « NOM PRENOM » ou « PRENOM NOM » apparaît dans le texte."""
    texte_norm = f" {normaliser(texte)} "
    trouves = []
    for client in clients:
        nom, prenom = normaliser(client.nom), normaliser(client.prenom)
        if not nom or not prenom:
            continue
        if f" {nom} {prenom} " in texte_norm or f" {prenom} {nom} " in texte_norm:
            trouves.append(client)
    return trouves


def rapprocher(documents: dict[str, str], clients: list[Client]) -> dict[str, list[str]]:
    """Associe chaque client aux documents où son nom apparaît.

    documents : {nom_de_fichier: texte extrait (ou nom de fichier si vide)}
    Retour : {cle_client: [noms_de_fichiers]}

    Si le texte d'un PDF est vide (scan sans OCR), on se rabat sur le
    nom du fichier lui-même.
    """
    resultat: dict[str, list[str]] = {c.cle: [] for c in clients}
    for nom_fichier, texte in documents.items():
        contenu = texte if texte and texte.strip() else nom_fichier
        for client in clients_dans_texte(contenu, clients):
            resultat[client.cle].append(nom_fichier)
    return resultat
