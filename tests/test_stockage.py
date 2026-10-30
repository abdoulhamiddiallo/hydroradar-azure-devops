from datetime import timedelta

import pandas as pd

from hydroradar.stockage import (
    debut_extraction,
    ecrire_etat,
    fusionner_observations,
    lire_observations,
)
from hydroradar.transformation import normaliser_observations


def test_le_premier_passage_remonte_de_n_jours(tmp_path, maintenant):
    assert debut_extraction(tmp_path, maintenant, jours_initiaux=2) == maintenant - timedelta(days=2)


def test_ensuite_on_repart_du_filigrane_moins_le_recouvrement(tmp_path, maintenant):
    ecrire_etat(tmp_path, maintenant - timedelta(minutes=15))
    assert debut_extraction(tmp_path, maintenant, 2) == maintenant - timedelta(hours=2, minutes=15)


def test_on_ne_remonte_jamais_au_dela_de_29_jours(tmp_path, maintenant):
    assert debut_extraction(tmp_path, maintenant, jours_initiaux=90) == maintenant - timedelta(days=29)


def test_le_chargement_est_idempotent(tmp_path, observations_brutes):
    lot = normaliser_observations(observations_brutes)
    assert fusionner_observations(tmp_path, lot) == len(lot)
    assert fusionner_observations(tmp_path, lot) == 0  # rejouer le même lot n'ajoute rien
    relu = lire_observations(tmp_path, pd.Timestamp("2026-10-29", tz="UTC"))
    assert len(relu) == len(lot)


def test_les_partitions_sont_journalieres(tmp_path, observations_brutes):
    fusionner_observations(tmp_path, normaliser_observations(observations_brutes))
    partitions = [p.name for p in (tmp_path / "argent" / "observations").iterdir()]
    assert partitions == ["date=2026-10-29"]
