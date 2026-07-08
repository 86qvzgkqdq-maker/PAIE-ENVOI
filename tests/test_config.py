import os

from paie.config import (detecter_smtp, enregistrer_env, parser_mx,
                         smtp_depuis_mx)


def test_detection_fournisseurs_courants():
    assert detecter_smtp("jean@gmail.com") == ("smtp.gmail.com", 587)
    assert detecter_smtp("jean@ORANGE.FR") == ("smtp.orange.fr", 465)
    assert detecter_smtp("jean@entreprise-inconnue.fr") is None
    assert detecter_smtp("pas-un-email") is None


def test_parser_mx():
    sortie = "10 mx1.mail.ovh.net.\n20 mx2.mail.OVH.net.\n"
    assert parser_mx(sortie) == ["mx1.mail.ovh.net", "mx2.mail.ovh.net"]
    assert parser_mx("") == []


def test_hebergeur_identifie_par_mx():
    # entreprise sous Google Workspace
    assert smtp_depuis_mx(["aspmx.l.google.com"]) == ("smtp.gmail.com", 587, "Google Workspace")
    # entreprise sous Microsoft 365
    assert smtp_depuis_mx(["entreprise-fr.mail.protection.outlook.com"]) == (
        "smtp.office365.com", 587, "Microsoft 365")
    # entreprise chez OVH
    assert smtp_depuis_mx(["mx1.mail.ovh.net"]) == ("ssl0.ovh.net", 465, "OVH")
    # hébergeur inconnu
    assert smtp_depuis_mx(["mail.hebergeur-obscur.fr"]) is None


def test_enregistrer_cree_le_fichier(tmp_path, monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    env = tmp_path / ".env"
    enregistrer_env(env, {"SMTP_HOST": "smtp.x.fr", "SMTP_USER": "a@x.fr"})
    contenu = env.read_text()
    assert "SMTP_HOST=smtp.x.fr" in contenu
    assert "SMTP_USER=a@x.fr" in contenu
    assert os.environ["SMTP_HOST"] == "smtp.x.fr"  # prise d'effet immédiate
    assert oct(env.stat().st_mode & 0o777) == "0o600"


def test_enregistrer_preserve_les_autres_lignes(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# commentaire\nAUTRE_CLE=garde\nSMTP_HOST=ancien\n")
    enregistrer_env(env, {"SMTP_HOST": "nouveau"})
    lignes = env.read_text().splitlines()
    assert "# commentaire" in lignes
    assert "AUTRE_CLE=garde" in lignes
    assert "SMTP_HOST=nouveau" in lignes
    assert "SMTP_HOST=ancien" not in lignes
