"""Lecture du fichier Excel des clients (Nom, Prénom, Email)."""

from dataclasses import dataclass

from openpyxl import load_workbook

from .textes import normaliser


@dataclass
class Client:
    nom: str
    prenom: str
    email: str

    @property
    def affichage(self) -> str:
        return f"{self.nom.upper()} {self.prenom}"

    @property
    def cle(self) -> str:
        return normaliser(f"{self.nom} {self.prenom}")


class ErreurColonnes(ValueError):
    """Le fichier Excel ne contient pas les colonnes attendues."""


def _reperer_colonnes(entetes) -> dict:
    """Repère les colonnes nom / prénom / email d'après les en-têtes."""
    colonnes = {}
    for i, entete in enumerate(entetes):
        e = normaliser(entete or "").lower()
        if not e:
            continue
        if "prenom" in e and "prenom" not in colonnes:
            colonnes["prenom"] = i
        elif ("mail" in e or "courriel" in e) and "email" not in colonnes:
            colonnes["email"] = i
        elif "nom" in e and "nom" not in colonnes:
            colonnes["nom"] = i
    return colonnes


def charger_clients(fichier) -> list[Client]:
    """Charge les clients depuis un .xlsx (chemin ou objet fichier).

    Les colonnes sont repérées par leurs en-têtes (nom, prénom, email —
    accents et casse indifférents). Les lignes sans nom ou sans email
    sont ignorées.
    """
    wb = load_workbook(fichier, read_only=True, data_only=True)
    ws = wb.active
    lignes = ws.iter_rows(values_only=True)
    try:
        entetes = next(lignes)
    except StopIteration:
        raise ErreurColonnes("Le fichier Excel est vide.")

    colonnes = _reperer_colonnes(entetes)
    manquantes = {"nom", "prenom", "email"} - set(colonnes)
    if manquantes:
        raise ErreurColonnes(
            "Colonnes introuvables dans l'Excel : "
            + ", ".join(sorted(manquantes))
            + ". En-têtes attendus : Nom, Prénom, Email (la casse et les accents sont ignorés)."
        )

    clients = []
    for ligne in lignes:
        def val(cle):
            v = ligne[colonnes[cle]] if colonnes[cle] < len(ligne) else None
            return str(v).strip() if v is not None else ""

        nom, prenom, email = val("nom"), val("prenom"), val("email")
        if nom and prenom and email:
            clients.append(Client(nom=nom, prenom=prenom, email=email))
    wb.close()
    return clients
