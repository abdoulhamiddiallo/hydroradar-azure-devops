"""Quarantaine ligne par ligne, puis porte qualité sur le lot entier."""

from __future__ import annotations

from datetime import datetime, timedelta

import pandas as pd

from hydroradar.transformation import CLE

SEUIL_VOLUME = 100  # mesures valides minimum dans un lot
SEUIL_COUVERTURE = 0.5  # part des stations du référentiel qui doivent avoir transmis
SEUIL_FRAICHEUR = timedelta(hours=3)  # âge maximal de la mesure la plus récente
SEUIL_QUARANTAINE = 0.02  # part maximale de lignes écartées
SAUT_MAX_HAUTEUR_M = 3.0  # variation de hauteur impossible entre deux mesures rapprochées
ECART_SAUT = pd.Timedelta(minutes=30)


def mettre_en_quarantaine(lot: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Sépare les mesures publiables des mesures suspectes, en notant le motif de chaque rejet.

    Attention, piège du métier : une hauteur NÉGATIVE est normale (elle est mesurée par rapport
    au zéro de l'échelle). Seul un débit négatif est physiquement impossible.
    """
    df = lot.sort_values(CLE).copy()
    motif = pd.Series("", index=df.index, dtype="object")
    motif[df["valeur"].isna()] = "valeur absente"
    motif[~df["grandeur"].isin(["H", "Q"])] = "grandeur inconnue"
    motif[(df["grandeur"] == "Q") & (df["valeur"] < 0)] = "débit négatif"

    hauteurs = df["grandeur"] == "H"
    meme_serie = df["code_station"].eq(df["code_station"].shift()) & df["grandeur"].eq(df["grandeur"].shift())
    ecart = df["date_obs"].diff()
    saut = df["valeur"].diff().abs()
    aberrant = hauteurs & meme_serie & (ecart <= ECART_SAUT) & (saut > SAUT_MAX_HAUTEUR_M)
    motif[aberrant & (motif == "")] = "saut de hauteur aberrant"

    rejet = motif != ""
    quarantaine = df[rejet].assign(motif=motif[rejet])
    return df[~rejet].reset_index(drop=True), quarantaine.reset_index(drop=True)


def porte_qualite(
    valides: pd.DataFrame,
    quarantaine: pd.DataFrame,
    nb_stations_referentiel: int,
    maintenant: datetime,
) -> dict:
    """Cinq règles bloquantes. Une seule en échec et le lot entier est refusé."""
    total = len(valides) + len(quarantaine)
    stations_actives = valides["code_station"].nunique() if total else 0
    couverture = stations_actives / nb_stations_referentiel if nb_stations_referentiel else 0.0
    derniere = valides["date_obs"].max() if len(valides) else None
    age = (pd.Timestamp(maintenant) - derniere) if derniere is not None else None
    taux_quarantaine = len(quarantaine) / total if total else 0.0
    doublons = int(valides.duplicated(CLE).sum())

    regles = [
        ("volume", len(valides), f">= {SEUIL_VOLUME}", len(valides) >= SEUIL_VOLUME),
        ("couverture", round(couverture, 3), f">= {SEUIL_COUVERTURE}", couverture >= SEUIL_COUVERTURE),
        (
            "fraicheur_minutes",
            None if age is None else round(age.total_seconds() / 60),
            f"<= {int(SEUIL_FRAICHEUR.total_seconds() // 60)}",
            age is not None and age <= SEUIL_FRAICHEUR,
        ),
        ("unicite_doublons", doublons, "== 0", doublons == 0),
        (
            "taux_quarantaine",
            round(taux_quarantaine, 4),
            f"<= {SEUIL_QUARANTAINE}",
            taux_quarantaine <= SEUIL_QUARANTAINE,
        ),
    ]
    return {
        "horodatage": pd.Timestamp(maintenant).isoformat(),
        "lignes_valides": len(valides),
        "lignes_quarantaine": len(quarantaine),
        "stations_referentiel": nb_stations_referentiel,
        "stations_actives": int(stations_actives),
        "derniere_mesure": None if derniere is None else derniere.isoformat(),
        "regles": [{"regle": r, "valeur": v, "seuil": s, "ok": bool(ok)} for r, v, s, ok in regles],
        "statut": "ACCEPTE" if all(ok for *_, ok in regles) else "REFUSE",
    }
