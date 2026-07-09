from paie.acces import hacher, verifier


def test_bon_mot_de_passe():
    h = hacher("moovincab")
    assert verifier("moovincab", h)


def test_mauvais_mot_de_passe():
    h = hacher("moovincab")
    assert not verifier("moovincab ", h)
    assert not verifier("Moovincab", h)
    assert not verifier("", h)


def test_hachage_stocke_abime_ne_plante_pas():
    # caractères non-ASCII ou parasites dans le secret : False, pas d'exception
    assert not verifier("moovincab", "83fca841…")
    assert not verifier("moovincab", "")
    assert not verifier("moovincab", None)


def test_hachage_avec_guillemets_ou_espaces_tolere():
    h = hacher("moovincab")
    assert verifier("moovincab", f'  "{h}"  ')
    assert verifier("moovincab", h.upper())
