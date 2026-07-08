"""Protection de l'app par mot de passe (hachage stocké dans .env)."""

import hashlib
import hmac


def hacher(mot_de_passe: str) -> str:
    return hashlib.sha256(mot_de_passe.encode("utf-8")).hexdigest()


def verifier(mot_de_passe: str, hachage_attendu: str) -> bool:
    return hmac.compare_digest(hacher(mot_de_passe), hachage_attendu)
