from datetime import UTC, datetime

import pytest

from hydroradar.client import ClientHubeau, ErreurSource


class Reponse:
    def __init__(self, status_code, corps):
        self.status_code, self._corps, self.text = status_code, corps, str(corps)

    def json(self):
        return self._corps


class FausseSession:
    """Rejoue une suite de réponses HTTP et garde la trace des appels."""

    def __init__(self, reponses):
        self.reponses, self.appels = list(reponses), []

    def get(self, url, params=None, timeout=None):
        self.appels.append((url, params))
        return self.reponses.pop(0)


def test_la_pagination_suit_le_lien_next_jusqu_au_bout():
    session = FausseSession(
        [
            Reponse(206, {"data": [{"n": 1}, {"n": 2}], "next": "https://x/page2"}),
            Reponse(206, {"data": [{"n": 3}], "next": "https://x/page3"}),
            Reponse(200, {"data": [], "next": None}),
        ]
    )
    lignes = ClientHubeau(session=session, url_base="https://x").stations("57")
    assert [ligne["n"] for ligne in lignes] == [1, 2, 3]
    # Le curseur est dans l'URL « next » : les paramètres ne sont envoyés qu'au premier appel.
    assert session.appels[0][1]["code_departement"] == "57"
    assert session.appels[1] == ("https://x/page2", None)


def test_une_erreur_http_leve_erreur_source():
    session = FausseSession([Reponse(503, {"message": "indisponible"})])
    with pytest.raises(ErreurSource, match="HTTP 503"):
        ClientHubeau(session=session, url_base="https://x").stations("57")


def test_les_stations_sont_demandees_par_lots_de_50():
    session = FausseSession([Reponse(200, {"data": [], "next": None}) for _ in range(3)])
    codes = [f"A{i:09d}" for i in range(120)]
    client = ClientHubeau(session=session, url_base="https://x")
    client.observations(codes, datetime(2026, 10, 29, tzinfo=UTC))
    assert len(session.appels) == 3
    premier = session.appels[0][1]
    assert premier["code_entite"].count(",") == 49
    assert premier["date_debut_obs"] == "2026-10-29T00:00:00Z"
    assert premier["sort"] == "asc"


def test_le_user_agent_porte_la_vraie_version():
    from hydroradar import __version__
    from hydroradar.client import creer_session

    assert creer_session().headers["User-Agent"].startswith(f"HydroRadar/{__version__} ")
