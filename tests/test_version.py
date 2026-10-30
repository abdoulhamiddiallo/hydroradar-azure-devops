from outils.version import calculer


def test_un_tag_donne_la_version_exacte():
    assert calculer("0.1.0", "refs/tags/v1.0.0", "812") == "1.0.0"


def test_une_branche_donne_une_version_de_developpement():
    assert calculer("0.1.0", "refs/heads/main", "812") == "0.1.0.dev812"
