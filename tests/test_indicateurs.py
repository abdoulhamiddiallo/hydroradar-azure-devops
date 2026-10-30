import json

from hydroradar.cli import executer
from hydroradar.indicateurs import situation_stations
from hydroradar.transformation import normaliser_observations, normaliser_stations


def test_variation_sur_une_heure_et_tendance(observations_brutes, stations_brutes):
    situation = situation_stations(
        normaliser_observations(observations_brutes), normaliser_stations(stations_brutes)
    ).set_index("code_station")
    metz = situation.loc["A743061001"]
    assert metz.hauteur_m == 2.162
    assert metz.variation_1h_cm == 0.4  # 2,162 m à 21 h 30 contre 2,158 m à 20 h 30
    assert metz.tendance == "stable"
    # Sarrebourg transmet en retard : l'extrait ne remonte pas une heure avant sa dernière mesure.
    assert situation.loc["A902102050", "tendance"] == "indéterminée"


def test_execution_complete_de_bout_en_bout(tmp_path, faux_client, maintenant):
    rapport = executer("57", tmp_path, jours_initiaux=2, client=faux_client, maintenant=maintenant)
    assert rapport["statut"] == "ACCEPTE" and rapport["mesures_nouvelles"] == 134
    assert (tmp_path / "or" / "situation_stations.csv").exists()
    synthese = json.loads((tmp_path / "or" / "synthese.json").read_text(encoding="utf-8"))
    assert synthese["stations_suivies"] == 6

    # Deuxième passage : le filigrane fait repartir 2 h avant la dernière mesure, rien de neuf.
    rapport = executer("57", tmp_path, jours_initiaux=2, client=faux_client, maintenant=maintenant)
    assert rapport["mesures_nouvelles"] == 0
    assert faux_client.depuis_demande.isoformat() == "2026-10-29T19:30:00+00:00"
