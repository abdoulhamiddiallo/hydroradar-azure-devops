"""Client de l'API Hub'Eau Hydrométrie : reprises automatiques et pagination par curseur.

Documentation officielle : https://hubeau.eaufrance.fr/page/api-hydrometrie
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from hydroradar import __version__

URL_BASE = "https://hubeau.eaufrance.fr/api/v2/hydrometrie"

# Projection : on ne demande que les colonnes utiles (réponse trois fois plus légère).
CHAMPS_OBSERVATIONS = (
    "code_station",
    "grandeur_hydro",
    "date_obs",
    "resultat_obs",
    "code_methode_obs",
    "code_qualification_obs",
)
TAILLE_PAGE = 5000  # l'API accepte jusqu'à 20 000 lignes par page
STATIONS_PAR_REQUETE = 50  # on découpe la liste des stations pour garder des URL courtes


class ErreurSource(RuntimeError):
    """L'API a répondu autre chose qu'un succès, après toutes les reprises."""


def creer_session() -> requests.Session:
    """Session HTTP qui réessaie seule sur les erreurs passagères (429, 5xx) avec attente croissante."""
    session = requests.Session()
    reprises = Retry(
        total=5,
        backoff_factor=2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
    )
    session.mount("https://", HTTPAdapter(max_retries=reprises))
    session.headers["User-Agent"] = f"HydroRadar/{__version__} (projet Azure DevOps)"
    return session


class ClientHubeau:
    def __init__(self, session: requests.Session | None = None, url_base: str = URL_BASE, delai: int = 60):
        self.session = session or creer_session()
        self.url_base = url_base.rstrip("/")
        self.delai = delai

    def _pages(self, chemin: str, params: dict) -> Iterator[dict]:
        """Parcourt toutes les pages d'une ressource : on suit le lien « next » jusqu'au bout."""
        url: str | None = f"{self.url_base}/{chemin}"
        while url:
            reponse = self.session.get(url, params=params, timeout=self.delai)
            # 206 (Partial Content) = « il reste des pages » : c'est un succès pour Hub'Eau.
            if reponse.status_code not in (200, 206):
                raise ErreurSource(f"HTTP {reponse.status_code} sur {url} : {reponse.text[:200]}")
            corps = reponse.json()
            yield from corps.get("data") or []
            url = corps.get("next")
            params = None  # l'URL « next » contient déjà tous les paramètres et le curseur

    def stations(self, departement: str) -> list[dict]:
        """Référentiel des stations hydrométriques en service d'un département."""
        params = {"code_departement": departement, "en_service": "true", "format": "json", "size": 1000}
        return list(self._pages("referentiel/stations", params))

    def observations(self, codes_stations: list[str], depuis: datetime) -> list[dict]:
        """Observations temps réel (pas de 5 à 15 minutes) depuis une date, pour une liste de stations."""
        resultat: list[dict] = []
        for i in range(0, len(codes_stations), STATIONS_PAR_REQUETE):
            lot = codes_stations[i : i + STATIONS_PAR_REQUETE]
            params = {
                "code_entite": ",".join(lot),
                "date_debut_obs": depuis.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fields": ",".join(CHAMPS_OBSERVATIONS),
                "size": TAILLE_PAGE,
                "sort": "asc",
                "format": "json",
            }
            resultat.extend(self._pages("observations_tr", params))
        return resultat
