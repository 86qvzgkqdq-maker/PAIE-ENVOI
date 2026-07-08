from paie.acces import hacher, verifier


def test_bon_mot_de_passe():
    h = hacher("moovincab")
    assert verifier("moovincab", h)


def test_mauvais_mot_de_passe():
    h = hacher("moovincab")
    assert not verifier("moovincab ", h)
    assert not verifier("Moovincab", h)
    assert not verifier("", h)
