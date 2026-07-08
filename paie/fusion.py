"""Fusion de plusieurs PDF en un seul document."""

import re
from pathlib import Path

from pypdf import PdfWriter


def nom_fichier_sur(texte: str) -> str:
    """Transforme un libellé en nom de fichier sûr : « DUPÉ Jean » -> « DUPE_Jean »."""
    import unicodedata

    decompose = unicodedata.normalize("NFKD", texte)
    ascii_ = "".join(c for c in decompose if not unicodedata.combining(c))
    propre = re.sub(r"[^A-Za-z0-9]+", "_", ascii_).strip("_")
    return propre or "document"


def fusionner(sources: list, destination: Path) -> Path:
    """Concatène les PDF `sources` (chemins ou objets fichiers) dans `destination`."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for source in sources:
        if hasattr(source, "seek"):
            source.seek(0)
        writer.append(source)
    with open(destination, "wb") as f:
        writer.write(f)
    writer.close()
    return destination
