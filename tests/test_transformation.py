import pytest

from hydroradar.transformation import ContratRompu, normaliser_observations, normaliser_stations


def test_les_unites_sont_converties_en_metres_et_m3_par_seconde(observations_brutes):
    df = normaliser_observations(observations_brutes)
    metz = df[(df.code_station == "A743061001") & (df.date_obs == "2026-10-29T21:30:00Z")].iloc[0]
    assert metz.valeur_brute == 2162 and metz.valeur == 2.162 and metz.unite == "m"
    corny_q = df[(df.code_station == "A740000101") & (df.grandeur == "Q")].iloc[-1]
    assert corny_q.valeur == 21.7 and corny_q.unite == "m3/s"


def test_une_mesure_lue_deux_fois_ne_compte_qu_une_fois(observations_brutes):
    df = normaliser_observations(observations_brutes + observations_brutes[:10])
    assert len(df) == len(observations_brutes)


def test_la_methode_de_mesure_est_decodee(observations_brutes):
    df = normaliser_observations(observations_brutes)
    assert set(df.methode) == {"mesurée", "calculée"}


def test_un_schema_casse_arrete_tout():
    with pytest.raises(ContratRompu, match="Colonnes reçues"):
        normaliser_observations([{"code_station": "A1", "date": "2026-10-29"}])


def test_les_stations_ont_des_libelles_lisibles(stations_brutes):
    df = normaliser_stations(stations_brutes)
    assert len(df) == 7
    assert df.set_index("code_station").loc["A743061001", "commune"] == "Metz"
    assert df.set_index("code_station").loc["A841040101", "cours_eau"] == "(non renseigné)"
