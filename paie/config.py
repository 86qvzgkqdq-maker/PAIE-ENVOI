"""Lecture/écriture de la configuration email (fichier .env local)."""

import os
import socket
import subprocess
from pathlib import Path

# Serveurs SMTP des fournisseurs courants, repérés par le domaine de l'adresse.
FOURNISSEURS = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
    "me.com": ("smtp.mail.me.com", 587),
    "mac.com": ("smtp.mail.me.com", 587),
    "outlook.com": ("smtp.office365.com", 587),
    "outlook.fr": ("smtp.office365.com", 587),
    "hotmail.com": ("smtp.office365.com", 587),
    "hotmail.fr": ("smtp.office365.com", 587),
    "live.com": ("smtp.office365.com", 587),
    "live.fr": ("smtp.office365.com", 587),
    "yahoo.com": ("smtp.mail.yahoo.com", 465),
    "yahoo.fr": ("smtp.mail.yahoo.com", 465),
    "orange.fr": ("smtp.orange.fr", 465),
    "wanadoo.fr": ("smtp.orange.fr", 465),
    "free.fr": ("smtp.free.fr", 465),
    "sfr.fr": ("smtp.sfr.fr", 465),
    "laposte.net": ("smtp.laposte.net", 465),
}

# Fournisseurs qui exigent un « mot de passe d'application »
# (généré dans les réglages du compte, différent du mot de passe habituel).
MDP_APPLICATION = {"smtp.gmail.com", "smtp.mail.me.com", "smtp.mail.yahoo.com"}


def detecter_smtp(email: str) -> tuple[str, int] | None:
    """(serveur, port) déduits du domaine de l'adresse, ou None si inconnu."""
    if "@" not in email:
        return None
    domaine = email.rsplit("@", 1)[1].strip().lower()
    return FOURNISSEURS.get(domaine)


# Hébergeurs de messagerie d'entreprise, reconnus par leurs serveurs MX.
HEBERGEURS_MX = [
    ("google.com", ("smtp.gmail.com", 587, "Google Workspace")),
    ("googlemail.com", ("smtp.gmail.com", 587, "Google Workspace")),
    ("outlook.com", ("smtp.office365.com", 587, "Microsoft 365")),
    ("ovh.net", ("ssl0.ovh.net", 465, "OVH")),
    ("ionos", ("smtp.ionos.fr", 465, "Ionos (1&1)")),
    ("kundenserver.de", ("smtp.ionos.fr", 465, "Ionos (1&1)")),
    ("gandi.net", ("mail.gandi.net", 465, "Gandi")),
    ("infomaniak", ("mail.infomaniak.com", 465, "Infomaniak")),
    ("zoho.eu", ("smtp.zoho.eu", 465, "Zoho")),
    ("zoho.com", ("smtp.zoho.eu", 465, "Zoho")),
    # Viaduc (registrar FR) : MX en marque blanche « mymail.eu.com »,
    # mais le certificat TLS n'est valable que pour smtp.viaduc.fr
    ("mymail.eu.com", ("smtp.viaduc.fr", 587, "Viaduc")),
]


def parser_mx(sortie_dig: str) -> list[str]:
    """Noms des serveurs MX dans la sortie de `dig +short MX`."""
    hotes = []
    for ligne in sortie_dig.splitlines():
        champs = ligne.split()
        if champs and "." in champs[-1]:
            hotes.append(champs[-1].rstrip(".").lower())
    return hotes


def _mx(domaine: str) -> list[str]:
    try:
        resultat = subprocess.run(
            ["dig", "+short", "MX", domaine],
            capture_output=True, text=True, timeout=10,
        )
    except Exception:
        return []
    return parser_mx(resultat.stdout)


def smtp_depuis_mx(mx_hotes: list[str]) -> tuple[str, int, str] | None:
    """Réglages SMTP si les MX désignent un hébergeur connu."""
    for mx in mx_hotes:
        for motif, reglages in HEBERGEURS_MX:
            if motif in mx:
                return reglages
    return None


def _sonder(hotes: list[str], ports=(587, 465)) -> tuple[str, int] | None:
    """Premier couple (hôte, port) qui accepte une connexion TCP."""
    for hote in hotes:
        for port in ports:
            try:
                with socket.create_connection((hote, port), timeout=3):
                    return hote, port
            except OSError:
                continue
    return None


def detecter_smtp_entreprise(email: str) -> tuple[str, int, str] | None:
    """Détection pour une adresse sur domaine d'entreprise.

    1. fournisseur grand public connu ; 2. hébergeur identifié par les
    serveurs MX du domaine ; 3. sondage de smtp.<domaine> / mail.<domaine>.
    Retour : (serveur, port, libellé de la source) ou None.
    """
    if "@" not in email:
        return None
    domaine = email.rsplit("@", 1)[1].strip().lower()

    connu = detecter_smtp(email)
    if connu:
        return (*connu, "fournisseur connu")

    mx_hotes = _mx(domaine)
    via_mx = smtp_depuis_mx(mx_hotes)
    if via_mx:
        return via_mx

    candidats = [f"smtp.{domaine}", f"mail.{domaine}"] + mx_hotes[:2]
    trouve = _sonder(candidats)
    if trouve:
        return (trouve[0], trouve[1], "serveur du domaine répondant")
    return None


def enregistrer_env(chemin: Path, valeurs: dict[str, str]) -> None:
    """Met à jour le .env avec `valeurs`, en préservant les autres lignes.

    Applique aussi les valeurs à os.environ pour prise d'effet immédiate.
    """
    lignes = chemin.read_text().splitlines() if chemin.exists() else []
    restantes = dict(valeurs)
    sortie = []
    for ligne in lignes:
        cle = ligne.split("=", 1)[0].strip()
        if "=" in ligne and cle in restantes:
            sortie.append(f"{cle}={restantes.pop(cle)}")
        else:
            sortie.append(ligne)
    for cle, valeur in restantes.items():
        sortie.append(f"{cle}={valeur}")
    chemin.write_text("\n".join(sortie) + "\n")
    chemin.chmod(0o600)  # identifiants : lisible par l'utilisateur seul
    for cle, valeur in valeurs.items():
        os.environ[cle] = str(valeur)
