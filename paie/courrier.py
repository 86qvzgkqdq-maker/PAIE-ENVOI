"""Envoi d'emails avec pièces jointes.

Deux modes, choisis automatiquement d'après les variables d'environnement :

- **API Brevo (HTTPS)** si `BREVO_API_KEY` est défini. Indispensable chez les
  hébergeurs qui bloquent le SMTP sortant (Render, etc.). Expéditeur = `SMTP_FROM`
  (une adresse validée dans Brevo).
- **SMTP classique** sinon (usage local, serveur dédié…), config `SMTP_*`.
"""

import base64
import json
import os
import smtplib
import ssl
import urllib.error
import urllib.request
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path

import certifi

BREVO_URL = "https://api.brevo.com/v3"


def _mode_brevo() -> bool:
    return bool(os.getenv("BREVO_API_KEY"))


def config_manquante() -> list[str]:
    """Variables manquantes (liste vide = config complète)."""
    if _mode_brevo():
        manque = []
        if not os.getenv("BREVO_API_KEY"):
            manque.append("BREVO_API_KEY")
        if not (os.getenv("SMTP_FROM") or os.getenv("SMTP_USER")):
            manque.append("SMTP_FROM")  # l'expéditeur validé dans Brevo
        return manque
    requises = ["SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"]
    return [v for v in requises if not os.getenv(v)]


def _expediteur() -> str:
    return os.getenv("SMTP_FROM") or os.environ["SMTP_USER"]


# ----------------------------------------------------------------- mode Brevo
def _brevo_requete(chemin: str, methode: str = "GET", corps: dict | None = None):
    req = urllib.request.Request(
        BREVO_URL + chemin, method=methode,
        data=json.dumps(corps).encode() if corps is not None else None,
        headers={"api-key": os.environ["BREVO_API_KEY"],
                 "content-type": "application/json", "accept": "application/json"},
    )
    contexte = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(req, timeout=30, context=contexte) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:200]
        raise RuntimeError(f"Brevo {e.code} : {detail}") from None


def _brevo_envoyer(destinataire, sujet, corps, pieces_jointes):
    payload = {
        "sender": {"email": _expediteur()},
        "to": [{"email": destinataire}],
        "subject": sujet,
        "textContent": corps,
        "attachment": [
            {"content": base64.b64encode(Path(p).read_bytes()).decode(),
             "name": Path(p).name}
            for p in pieces_jointes
        ],
    }
    _brevo_requete("/smtp/email", "POST", payload)


# ----------------------------------------------------------------- mode SMTP
@contextmanager
def _session():
    """Connexion SMTP authentifiée (SSL sur 465, sinon STARTTLS)."""
    hote = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    utilisateur = os.environ["SMTP_USER"]
    mot_de_passe = os.environ["SMTP_PASSWORD"]
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


def _construire_message(destinataire, sujet, corps, pieces_jointes) -> EmailMessage:
    message = EmailMessage()
    message["From"] = _expediteur()
    message["To"] = destinataire
    message["Subject"] = sujet
    message.set_content(corps)
    for piece in pieces_jointes:
        piece = Path(piece)
        message.add_attachment(piece.read_bytes(), maintype="application",
                               subtype="pdf", filename=piece.name)
    return message


# ----------------------------------------------------------------- API publique
def tester_connexion() -> None:
    """Vérifie la config sans rien envoyer. Lève en cas d'échec."""
    if _mode_brevo():
        _brevo_requete("/account")          # 401 si clé invalide
        return
    with _session():
        pass


def envoyer(destinataire: str, sujet: str, corps: str, pieces_jointes: list) -> None:
    """Envoie UN email (test ou envoi isolé)."""
    if _mode_brevo():
        _brevo_envoyer(destinataire, sujet, corps, pieces_jointes)
        return
    with _session() as smtp:
        smtp.send_message(_construire_message(destinataire, sujet, corps, pieces_jointes))


@contextmanager
def session_envoi():
    """Contexte d'envoi en lot. Réutilise une connexion SMTP, ou enchaîne les
    appels API Brevo. Usage :

        with session_envoi() as envoyer_un:
            for dest, sujet, corps, pj in lot:
                envoyer_un(dest, sujet, corps, pj)   # lève si échec
    """
    if _mode_brevo():
        yield lambda d, s, c, pj: _brevo_envoyer(d, s, c, pj)
    else:
        with _session() as smtp:
            yield lambda d, s, c, pj: smtp.send_message(
                _construire_message(d, s, c, pj))
