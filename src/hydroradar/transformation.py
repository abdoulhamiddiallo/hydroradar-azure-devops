"""Transformation : contrat de schéma, typage, unités et dédoublonnage."""

from __future__ import annotations

import pandas as pd

COLONNES_OBLIGATOIRES = ("code_station", "grandeur_hydro", "date_obs", "resultat_obs")
CLE = ["code_station", "grandeur", "date_obs"]

# Hub'Eau publie les hauteurs en millimètres et les débits en litres par seconde.
UNITES = {"H": ("m", 1000.0), "Q": ("m3/s", 1000.0)}

# Nomenclature Sandre 507 : méthode d'obtention de la mesure.
METHODES = {0: "mesurée", 4: "reconstituée", 8: "calculée", 12: "interpolée"}

COLONNES_OBSERVATIONS = ["code_station", "grandeur", "date_obs", "valeur", "unite", "valeur_brute", "methode"]


class ContratRompu(ValueError):
    """La source ne respecte plus le schéma attendu : on arrête tout plutôt que publier du faux."""


def verifier_contrat(brut: list[dict]) -> None:
    if not brut:
        return
    recues = set().union(*(ligne.keys() for ligne in brut[:100]))
    manquantes = [c for c in COLONNES_OBLIGATOIRES if c not in recues]
    if manquantes:
        raise ContratRompu(f"Colonnes manquantes : {manquantes}. Colonnes reçues : {sorted(recues)}")


def normaliser_stations(brut: list[dict]) -> pd.DataFrame:
    """Dimension « stations » : une ligne par station, libellés lisibles, coordonnées WGS 84."""
    colonnes = {
        "code_station": "code_station",
        "libelle_station": "station",
        "libelle_cours_eau": "cours_eau",
        "libelle_commune": "commune",
        "code_departement": "departement",
        "type_station": "type_station",
        "longitude_station": "longitude",
        "latitude_station": "latitude",
    }
    df = pd.DataFrame(brut, columns=list(colonnes)).rename(columns=colonnes)
    df["cours_eau"] = df["cours_eau"].fillna("(non renseigné)")
    df["commune"] = df["commune"].str.title()
    return df.drop_duplicates("code_station").sort_values("code_station").reset_index(drop=True)


def normaliser_observations(brut: list[dict]) -> pd.DataFrame:
    """Format long : une ligne par station, grandeur (H ou Q) et date de mesure."""
    verifier_contrat(brut)
    if not brut:
        return pd.DataFrame(columns=COLONNES_OBSERVATIONS)

    df = pd.DataFrame(brut).rename(columns={"grandeur_hydro": "grandeur", "resultat_obs": "valeur_brute"})
    df["date_obs"] = pd.to_datetime(df["date_obs"], utc=True)
    df["valeur_brute"] = pd.to_numeric(df["valeur_brute"], errors="coerce")
    df["unite"] = df["grandeur"].map(lambda g: UNITES.get(g, ("?", 1.0))[0])
    diviseur = df["grandeur"].map(lambda g: UNITES.get(g, ("?", 1.0))[1])
    df["valeur"] = (df["valeur_brute"] / diviseur).round(3)
    methode = df.get("code_methode_obs", pd.Series(index=df.index, dtype="float"))
    df["methode"] = methode.map(METHODES).fillna("inconnue")

    # Idempotence : une même mesure lue deux fois (fenêtre de recouvrement) ne compte qu'une fois.
    df = df.drop_duplicates(CLE, keep="last")
    return df[COLONNES_OBSERVATIONS].sort_values(CLE).reset_index(drop=True)
