"""Normalisation de texte pour le rapprochement par nom/prénom."""

import re
import unicodedata


def normaliser(texte: str) -> str:
    """Majuscules, sans accents, sans ponctuation, espaces uniques.

    « Jean-François  DUPÉ » -> « JEAN FRANCOIS DUPE »
    """
    if not texte:
        return ""
    decompose = unicodedata.normalize("NFKD", str(texte))
    sans_accents = "".join(c for c in decompose if not unicodedata.combining(c))
    lettres = re.sub(r"[^A-Za-z]+", " ", sans_accents)
    return " ".join(lettres.upper().split())
