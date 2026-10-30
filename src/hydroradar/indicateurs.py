"""Couche « or » : situation de chaque station et synthèse du département."""

from __future__ import annotations

import pandas as pd

SEUIL_TENDANCE_CM = 2.0  # au-delà de 2 cm en une heure, la rivière monte ou baisse
TOLERANCE = pd.Timedelta(minutes=30)  # on accepte une mesure de référence jusqu'à 30 min plus ancienne


def _valeur_au(serie: pd.Series, instant: pd.Timestamp) -> float | None:
    """Dernière valeur connue à un instant donné, si elle n'est pas trop ancienne."""
    avant = serie[serie.index <= instant]
    if avant.empty or instant - avant.index[-1] > TOLERANCE:
        return None
    return float(avant.iloc[-1])


def _tendance(variation_cm: float | None) -> str:
    if variation_cm is None:
        return "indéterminée"
    if variation_cm >= SEUIL_TENDANCE_CM:
        return "en hausse"
    if variation_cm <= -SEUIL_TENDANCE_CM:
        return "en baisse"
    return "stable"


def situation_stations(observations: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    """Une ligne par station : dernière hauteur et dernier débit, variations sur 1 h et 24 h, tendance."""
    lignes = []
    for code, groupe in observations.groupby("code_station"):
        hauteur = groupe[groupe["grandeur"] == "H"].set_index("date_obs")["valeur"].sort_index()
        debit = groupe[groupe["grandeur"] == "Q"].set_index("date_obs")["valeur"].sort_index()
        derniere = groupe["date_obs"].max()
        h = float(hauteur.iloc[-1]) if len(hauteur) else None
        h_1h = _valeur_au(hauteur, hauteur.index[-1] - pd.Timedelta(hours=1)) if len(hauteur) else None
        h_24h = _valeur_au(hauteur, hauteur.index[-1] - pd.Timedelta(hours=24)) if len(hauteur) else None
        var_1h = None if h is None or h_1h is None else round((h - h_1h) * 100, 1)
        var_24h = None if h is None or h_24h is None else round((h - h_24h) * 100, 1)
        lignes.append(
            {
                "code_station": code,
                "derniere_mesure": derniere,
                "hauteur_m": h,
                "debit_m3s": float(debit.iloc[-1]) if len(debit) else None,
                "variation_1h_cm": var_1h,
                "variation_24h_cm": var_24h,
                "hauteur_max_24h_m": float(hauteur.max()) if len(hauteur) else None,
                "tendance": _tendance(var_1h),
            }
        )
    colonnes = ["code_station", "station", "cours_eau", "commune", "latitude", "longitude"]
    situation = pd.DataFrame(lignes)
    if situation.empty:
        return situation
    return (
        stations[colonnes]
        .merge(situation, on="code_station", how="inner")
        .sort_values("variation_1h_cm", ascending=False, na_position="last")
        .reset_index(drop=True)
    )


def synthese(situation: pd.DataFrame, rapport: dict) -> dict:
    """Résumé lisible du département, publié avec les données."""
    tendances = situation["tendance"].value_counts().to_dict() if len(situation) else {}
    hausse = situation.dropna(subset=["variation_1h_cm"]).head(1)
    return {
        "stations_suivies": int(len(situation)),
        "tendances": {k: int(v) for k, v in tendances.items()},
        "plus_forte_hausse_1h": None
        if hausse.empty
        else {
            "station": hausse.iloc[0]["station"],
            "cours_eau": hausse.iloc[0]["cours_eau"],
            "variation_1h_cm": float(hausse.iloc[0]["variation_1h_cm"]),
        },
        "derniere_mesure": rapport.get("derniere_mesure"),
        "statut_qualite": rapport.get("statut"),
    }
