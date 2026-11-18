"""Journal des envois dans SQLite (data/journal.db)."""

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS envois (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    horodatage TEXT NOT NULL,
    periode TEXT NOT NULL,
    client TEXT NOT NULL,
    email TEXT NOT NULL,
    fichier TEXT NOT NULL,
    statut TEXT NOT NULL,
    erreur TEXT
);
"""


def _connexion(chemin_db: Path) -> sqlite3.Connection:
    chemin_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(chemin_db)
    conn.execute(SCHEMA)
    return conn


def consigner(chemin_db: Path, periode: str, client: str, email: str,
              fichier: str, statut: str, erreur: str = "") -> None:
    with _connexion(chemin_db) as conn:
        conn.execute(
            "INSERT INTO envois (horodatage, periode, client, email, fichier, statut, erreur)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), periode, client,
             email, fichier, statut, erreur),
        )


def deja_envoyes(chemin_db: Path, periode: str) -> set[str]:
    """Emails déjà servis avec succès pour cette période (anti double envoi)."""
    with _connexion(chemin_db) as conn:
        lignes = conn.execute(
            "SELECT DISTINCT email FROM envois WHERE periode = ? AND statut = 'envoyé'",
            (periode,),
        ).fetchall()
    return {l[0] for l in lignes}


def dernier_envoi(chemin_db: Path, periode: str) -> str:
    """Horodatage du dernier email envoyé avec succès pour cette période (ou '')."""
    with _connexion(chemin_db) as conn:
        r = conn.execute(
            "SELECT MAX(horodatage) FROM envois WHERE periode = ? AND statut = 'envoyé'",
            (periode,),
        ).fetchone()
    return r[0] if r and r[0] else ""


def resume(chemin_db: Path) -> list[tuple]:
    """Agrégat par période / communication :
    (periode, nb_envoyés, nb_échecs, premier_horodatage, dernier_horodatage)."""
    with _connexion(chemin_db) as conn:
        return conn.execute(
            "SELECT periode,"
            " SUM(CASE WHEN statut='envoyé' THEN 1 ELSE 0 END),"
            " SUM(CASE WHEN statut='échec' THEN 1 ELSE 0 END),"
            " MIN(horodatage), MAX(horodatage)"
            " FROM envois GROUP BY periode ORDER BY MAX(horodatage) DESC",
        ).fetchall()


def historique(chemin_db: Path, limite: int = 200) -> list[tuple]:
    with _connexion(chemin_db) as conn:
        return conn.execute(
            "SELECT horodatage, periode, client, email, fichier, statut, erreur"
            " FROM envois ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()
