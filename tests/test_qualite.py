from datetime import timedelta

import pandas as pd

from hydroradar.qualite import mettre_en_quarantaine, porte_qualite
from hydroradar.transformation import normaliser_observations


def test_une_hauteur_negative_est_normale(observations_brutes):
    # La Petite Seille à Château-Salins mesure -0,27 m : l'eau est sous le zéro de l'échelle.
    valides, quarantaine = mettre_en_quarantaine(normaliser_observations(observations_brutes))
    assert (valides[valides.code_station == "A764201001"].query("grandeur == 'H'").valeur < 0).all()
    assert quarantaine.empty


def test_un_debit_negatif_part_en_quarantaine(observations_brutes):
    i = next(i for i, o in enumerate(observations_brutes) if o["grandeur_hydro"] == "Q")
    observations_brutes[i] = {**observations_brutes[i], "resultat_obs": -500}
    valides, quarantaine = mettre_en_quarantaine(normaliser_observations(observations_brutes))
    assert list(quarantaine.motif) == ["débit négatif"]
    assert len(valides) == len(observations_brutes) - 1


def test_un_saut_de_hauteur_impossible_part_en_quarantaine(observations_brutes):
    i = next(
        i
        for i, o in enumerate(observations_brutes)
        if o["code_station"] == "A743061001" and o["date_obs"].endswith("21:00:00Z")
    )
    observations_brutes[i] = {**observations_brutes[i], "resultat_obs": 9000}  # +6,8 m en 5 minutes
    _, quarantaine = mettre_en_quarantaine(normaliser_observations(observations_brutes))
    assert "saut de hauteur aberrant" in set(quarantaine.motif)


def test_la_porte_accepte_le_lot_reel(observations_brutes, maintenant):
    valides, quarantaine = mettre_en_quarantaine(normaliser_observations(observations_brutes))
    rapport = porte_qualite(valides, quarantaine, nb_stations_referentiel=7, maintenant=maintenant)
    assert rapport["statut"] == "ACCEPTE"
    assert rapport["stations_actives"] == 6  # la station minière de Neufchef n'a rien transmis


def test_la_porte_refuse_un_lot_perime(observations_brutes, maintenant):
    valides, quarantaine = mettre_en_quarantaine(normaliser_observations(observations_brutes))
    rapport = porte_qualite(valides, quarantaine, 7, maintenant + timedelta(hours=5))
    assert rapport["statut"] == "REFUSE"
    assert [r["regle"] for r in rapport["regles"] if not r["ok"]] == ["fraicheur_minutes"]


def test_la_porte_refuse_un_lot_vide(maintenant):
    vide = normaliser_observations([])
    rapport = porte_qualite(vide, pd.DataFrame(columns=vide.columns), 7, maintenant)
    assert rapport["statut"] == "REFUSE"
