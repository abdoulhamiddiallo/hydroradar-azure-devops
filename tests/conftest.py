"""Données de test : un extrait RÉEL de Hub'Eau (Moselle, 29 octobre 2026, 20 h 25 à 21 h 30 UTC).

Les tests ne touchent jamais le réseau : ils sont rapides, reproductibles et passent hors ligne.
"""

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

DONNEES = Path(__file__).parent / "donnees"
MAINTENANT = datetime(2026, 10, 29, 21, 45, tzinfo=UTC)


@pytest.fixture
def stations_brutes() -> list[dict]:
    return json.loads((DONNEES / "stations_57.json").read_text(encoding="utf-8"))


@pytest.fixture
def observations_brutes() -> list[dict]:
    with open(DONNEES / "observations_57.csv", encoding="utf-8") as f:
        lignes = list(csv.DictReader(f))
    for ligne in lignes:  # le CSV ne connaît que du texte : on retrouve les types de l'API
        for champ in ("resultat_obs", "code_methode_obs", "code_qualification_obs"):
            ligne[champ] = int(ligne[champ])
    return lignes


@pytest.fixture
def maintenant() -> datetime:
    return MAINTENANT


class FauxClient:
    """Remplace ClientHubeau : même interface, réponses tirées des fichiers de test."""

    def __init__(self, stations, observations):
        self._stations, self._observations = stations, observations
        self.depuis_demande = None

    def stations(self, departement):
        return self._stations

    def observations(self, codes, depuis):
        self.depuis_demande = depuis
        return [o for o in self._observations if o["code_station"] in codes]


@pytest.fixture
def faux_client(stations_brutes, observations_brutes) -> FauxClient:
    return FauxClient(stations_brutes, observations_brutes)
