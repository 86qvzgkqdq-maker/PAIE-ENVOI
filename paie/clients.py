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
    """Repère les colonnes nom / prénom / email d'après les en-têtes.

    Les en-têtes exacts (« Nom ») priment sur les approchants (« Nom
    complet »), pour ne pas confondre les deux si les deux existent.
    """
    normes = [normaliser(e or "").lower() for e in entetes]
    colonnes = {}
    # 1) correspondances exactes
    for i, e in enumerate(normes):
        if e == "prenom" and "prenom" not in colonnes:
            colonnes["prenom"] = i
        elif e == "nom" and "nom" not in colonnes:
            colonnes["nom"] = i
        elif e in ("email", "e mail", "mail", "courriel", "adresse mail",
                   "adresse email") and "email" not in colonnes:
            colonnes["email"] = i
    # 2) repli : l'en-tête contient le mot
    for i, e in enumerate(normes):
        if not e or i in colonnes.values():
            continue
        if "prenom" in e and "prenom" not in colonnes:
            colonnes["prenom"] = i
        elif ("mail" in e or "courriel" in e) and "email" not in colonnes:
            colonnes["email"] = i
        elif "nom" in e and "prenom" not in e and "nom" not in colonnes:
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

    # la ligne d'en-têtes n'est pas forcément la première (titre au-dessus…) :
    # on la cherche dans les 10 premières lignes
    colonnes = None
    for _ in range(10):
        try:
            candidate = next(lignes)
        except StopIteration:
            break
        reperees = _reperer_colonnes(candidate)
        if {"nom", "prenom", "email"} <= set(reperees):
            colonnes = reperees
            break
    if colonnes is None:
        raise ErreurColonnes(
            "Ligne d'en-têtes introuvable dans l'Excel : il faut une ligne "
            "avec les colonnes Nom, Prénom et Email (la casse et les accents "
            "sont ignorés), dans les 10 premières lignes du fichier."
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
