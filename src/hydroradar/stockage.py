"""Stockage en couches (bronze, argent, or) et chargement incrémental par filigrane.

Arborescence produite sous le dossier de l'environnement (dev ou prod) :

    bronze/AAAA-MM-JJ/observations_HHMMSS.json.gz   réponse brute de l'API, jamais modifiée
    argent/stations.parquet                         dimension des stations
    argent/observations/date=AAAA-MM-JJ/part.parquet  faits nettoyés, une partition par jour
    or/situation_stations.csv, or/synthese.json     indicateurs prêts à consommer
    controle/rapport_qualite.json, quarantaine.csv  traçabilité de la porte qualité
    etat.json                                       filigrane : dernière mesure chargée
"""

from __future__ import annotations

import gzip
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from hydroradar.transformation import CLE

RECOUVREMENT = timedelta(hours=2)  # on relit 2 h en arrière : les stations transmettent parfois en retard
PROFONDEUR_MAX = timedelta(days=29)  # l'API temps réel ne garde qu'un mois d'historique


def lire_etat(dossier: Path) -> datetime | None:
    fichier = dossier / "etat.json"
    if not fichier.exists():
        return None
    return datetime.fromisoformat(json.loads(fichier.read_text(encoding="utf-8"))["derniere_obs"])


def ecrire_etat(dossier: Path, derniere_obs: datetime) -> None:
    dossier.mkdir(parents=True, exist_ok=True)
    contenu = {"derniere_obs": derniere_obs.isoformat()}
    (dossier / "etat.json").write_text(json.dumps(contenu, indent=2), encoding="utf-8")


def debut_extraction(dossier: Path, maintenant: datetime, jours_initiaux: int) -> datetime:
    """Premier passage : N jours d'historique. Ensuite : depuis le filigrane, moins le recouvrement."""
    plancher = maintenant - PROFONDEUR_MAX
    filigrane = lire_etat(dossier)
    debut = maintenant - timedelta(days=jours_initiaux) if filigrane is None else filigrane - RECOUVREMENT
    return max(debut, plancher)


def sauver_brut(dossier: Path, brut: list[dict], maintenant: datetime) -> Path:
    cible = dossier / "bronze" / maintenant.strftime("%Y-%m-%d") / f"observations_{maintenant:%H%M%S}.json.gz"
    cible.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(cible, "wt", encoding="utf-8") as f:
        json.dump(brut, f, ensure_ascii=False)
    return cible


def sauver_stations(dossier: Path, stations: pd.DataFrame) -> None:
    cible = dossier / "argent" / "stations.parquet"
    cible.parent.mkdir(parents=True, exist_ok=True)
    stations.to_parquet(cible, index=False)


def lire_stations(dossier: Path) -> pd.DataFrame:
    return pd.read_parquet(dossier / "argent" / "stations.parquet")


def _partition(dossier: Path, jour: str) -> Path:
    return dossier / "argent" / "observations" / f"date={jour}" / "part.parquet"


def fusionner_observations(dossier: Path, lot: pd.DataFrame) -> int:
    """Upsert par partition journalière. Renvoie le nombre de mesures réellement nouvelles.

    Rejouer deux fois le même lot ne crée aucun doublon : le chargement est idempotent.
    """
    if lot.empty:
        return 0
    nouvelles = 0
    jours = lot["date_obs"].dt.strftime("%Y-%m-%d")
    for jour, morceau in lot.groupby(jours):
        fichier = _partition(dossier, jour)
        if fichier.exists():
            existant = pd.read_parquet(fichier)
            cles_existantes = pd.MultiIndex.from_frame(existant[CLE])
            nouvelles += int((~pd.MultiIndex.from_frame(morceau[CLE]).isin(cles_existantes)).sum())
            morceau = pd.concat([existant, morceau], ignore_index=True)
        else:
            nouvelles += len(morceau)
        morceau = morceau.drop_duplicates(CLE, keep="last").sort_values(CLE)
        fichier.parent.mkdir(parents=True, exist_ok=True)
        morceau.to_parquet(fichier, index=False)
    return nouvelles


def lire_observations(dossier: Path, depuis: datetime) -> pd.DataFrame:
    """Relit les partitions utiles uniquement (élagage de partitions), puis filtre à la minute près."""
    racine = dossier / "argent" / "observations"
    premier_jour = depuis.strftime("%Y-%m-%d")
    fichiers = sorted(p for p in racine.glob("date=*/part.parquet") if p.parent.name[5:] >= premier_jour)
    if not fichiers:
        return pd.DataFrame(columns=CLE + ["valeur"])
    df = pd.concat((pd.read_parquet(f) for f in fichiers), ignore_index=True)
    return df[df["date_obs"] >= pd.Timestamp(depuis)].reset_index(drop=True)
