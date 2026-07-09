"""Protection de l'app par mot de passe (hachage stocké dans .env)."""

import hashlib
import hmac


def hacher(mot_de_passe: str) -> str:
    return hashlib.sha256(mot_de_passe.encode("utf-8")).hexdigest()


def verifier(mot_de_passe: str, hachage_attendu: str) -> bool:
    # comparaison en bytes : jamais de TypeError, même si le hachage stocké
    # contient des caractères parasites (copier-coller malheureux) — dans ce
    # cas la comparaison échoue simplement
    attendu = str(hachage_attendu or "").strip().strip("\"'").lower()
    return hmac.compare_digest(
        hacher(mot_de_passe).encode("utf-8"),
        attendu.encode("utf-8", errors="replace"),
    )
