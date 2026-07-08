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


def historique(chemin_db: Path, limite: int = 200) -> list[tuple]:
    with _connexion(chemin_db) as conn:
        return conn.execute(
            "SELECT horodatage, periode, client, email, fichier, statut, erreur"
            " FROM envois ORDER BY id DESC LIMIT ?",
            (limite,),
        ).fetchall()
