"""Envoi d'emails avec pièces jointes via SMTP (config dans .env)."""

import os
import smtplib
import ssl
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

import certifi


def config_manquante() -> list[str]:
    """Variables SMTP absentes de l'environnement (liste vide = config complète)."""
    requises = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]
    return [v for v in requises if not os.getenv(v)]


@contextmanager
def _session():
    """Connexion SMTP authentifiée (SSL sur 465, sinon STARTTLS)."""
    hote = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    utilisateur = os.environ["SMTP_USER"]
    mot_de_passe = os.environ["SMTP_PASSWORD"]
    # certifi : autorités de certification à jour (le Python de macOS
    # ne trouve pas toujours celles du système)
    contexte = ssl.create_default_context(cafile=certifi.where())

    if port == 465:
        smtp = smtplib.SMTP_SSL(hote, port, context=contexte, timeout=30)
    else:
        smtp = smtplib.SMTP(hote, port, timeout=30)
        smtp.starttls(context=contexte)
    try:
        smtp.login(utilisateur, mot_de_passe)
        yield smtp
    finally:
        try:
            smtp.quit()
        except Exception:
            pass


def tester_connexion() -> None:
    """Vérifie serveur + identifiants sans rien envoyer. Lève en cas d'échec."""
    with _session():
        pass


def _construire_message(destinataire: str, sujet: str, corps: str,
                        pieces_jointes: list[Path]) -> EmailMessage:
    expediteur = os.getenv("SMTP_FROM") or os.environ["SMTP_USER"]
    message = EmailMessage()
    message["From"] = expediteur
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    for piece in pieces_jointes:
        piece = Path(piece)
        message.add_attachment(
            piece.read_bytes(),
            maintype="application", subtype="pdf", filename=piece.name,
        )
    return message


def envoyer(destinataire: str, sujet: str, corps: str, pieces_jointes: list[Path]) -> None:
    """Envoie UN email (ouvre une connexion). Pour un test ou un envoi isolé."""
    message = _construire_message(destinataire, sujet, corps, pieces_jointes)
    with _session() as smtp:
        smtp.send_message(message)


@contextmanager
def session_envoi():
    """Ouvre UNE connexion SMTP réutilisable pour un envoi en lot.

    Évite de se reconnecter à chaque email (indispensable pour ~350 envois :
    plus rapide, et beaucoup moins de risque de blocage côté serveur).

        with session_envoi() as envoyer_un:
            for dest, sujet, corps, pj in lot:
                envoyer_un(dest, sujet, corps, pj)   # lève si échec
    """
    with _session() as smtp:
        def _envoyer_un(destinataire, sujet, corps, pieces_jointes):
            smtp.send_message(
                _construire_message(destinataire, sujet, corps, pieces_jointes))
        yield _envoyer_un
