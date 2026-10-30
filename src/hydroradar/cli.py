"""Point d'entrée : extraction incrémentale, quarantaine, porte qualité, couches argent et or.

hydroradar --departement 57 --dossier C:\\HydroRadar\\dev --jours-initiaux 2
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hydroradar import __version__
from hydroradar.client import ClientHubeau, ErreurSource
from hydroradar.indicateurs import situation_stations, synthese
from hydroradar.qualite import mettre_en_quarantaine, porte_qualite
from hydroradar.stockage import (
    debut_extraction,
    ecrire_etat,
    fusionner_observations,
    lire_observations,
    sauver_brut,
    sauver_stations,
)
from hydroradar.transformation import normaliser_observations, normaliser_stations

DANS_AZURE = os.environ.get("TF_BUILD") == "True"  # variable posée par l'agent Azure Pipelines


def _ecrire_json(chemin: Path, contenu: dict) -> None:
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(contenu, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def executer(
    departement: str,
    dossier: Path,
    jours_initiaux: int,
    client: ClientHubeau | None = None,
    maintenant: datetime | None = None,
) -> dict:
    maintenant = maintenant or datetime.now(UTC)
    client = client or ClientHubeau()

    stations = normaliser_stations(client.stations(departement))
    if stations.empty:
        raise ErreurSource(f"Aucune station en service pour le département {departement}")
    sauver_stations(dossier, stations)

    debut = debut_extraction(dossier, maintenant, jours_initiaux)
    brut = client.observations(stations["code_station"].tolist(), debut)
    sauver_brut(dossier, brut, maintenant)

    lot = normaliser_observations(brut)
    valides, quarantaine = mettre_en_quarantaine(lot)
    rapport = porte_qualite(valides, quarantaine, len(stations), maintenant)
    rapport.update(
        version=__version__,
        departement=departement,
        debut_extraction=debut.isoformat(),
        mesures_lues=len(brut),
        mesures_nouvelles=0,
    )
    (dossier / "controle").mkdir(parents=True, exist_ok=True)
    quarantaine.to_csv(dossier / "controle" / "quarantaine.csv", index=False, sep=";", encoding="utf-8-sig")

    if rapport["statut"] == "ACCEPTE":
        rapport["mesures_nouvelles"] = fusionner_observations(dossier, valides)
        # Le filigrane n'avance QUE si le lot est accepté : un lot refusé sera relu au prochain passage.
        ecrire_etat(dossier, valides["date_obs"].max().to_pydatetime())
        recentes = lire_observations(dossier, maintenant - timedelta(hours=25))
        situation = situation_stations(recentes, stations)
        (dossier / "or").mkdir(parents=True, exist_ok=True)
        situation.to_csv(
            dossier / "or" / "situation_stations.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig"
        )
        _ecrire_json(dossier / "or" / "synthese.json", synthese(situation, rapport))

    _ecrire_json(dossier / "controle" / "rapport_qualite.json", rapport)
    return rapport


def _afficher(rapport: dict, dossier: Path) -> None:
    print(f"HydroRadar {rapport['version']} · département {rapport['departement']} · dossier {dossier}")
    print(
        f"Extraction depuis {rapport['debut_extraction']} : {rapport['mesures_lues']} mesures lues, "
        f"{rapport['lignes_quarantaine']} en quarantaine, {rapport['mesures_nouvelles']} nouvelles."
    )
    print(f"Stations actives : {rapport['stations_actives']} / {rapport['stations_referentiel']}")
    for r in rapport["regles"]:
        print(f"  [{'OK' if r['ok'] else 'KO'}] {r['regle']} = {r['valeur']} (attendu {r['seuil']})")
    print(f"Porte qualité : {rapport['statut']}")


def _commandes_azure(rapport: dict) -> None:
    """Commandes de journalisation : l'agent lit ces lignes spéciales sur la sortie standard."""
    print(f"##vso[task.setvariable variable=mesuresNouvelles]{rapport['mesures_nouvelles']}")
    couverture = rapport["regles"][1]["valeur"]
    if rapport["statut"] == "ACCEPTE" and couverture < 0.8:
        print(f"##vso[task.logissue type=warning]Couverture faible : {couverture:.0%} des stations")
    if rapport["statut"] == "ACCEPTE":
        print("##vso[build.addbuildtag]qualite-acceptee")
    else:
        echecs = ", ".join(r["regle"] for r in rapport["regles"] if not r["ok"])
        print(f"##vso[task.logissue type=error]Porte qualité refusée : {echecs}")


def main(argv: list[str] | None = None) -> int:
    if not sys.stdout.isatty():
        sys.stdout.reconfigure(encoding="utf-8")  # accents lisibles dans les journaux du pipeline
    parser = argparse.ArgumentParser(prog="hydroradar", description=__doc__.splitlines()[0])
    parser.add_argument("--departement", default=os.environ.get("HYDRORADAR_DEPARTEMENT", "57"))
    parser.add_argument("--dossier", type=Path, default=Path(os.environ.get("HYDRORADAR_DOSSIER", "donnees")))
    parser.add_argument("--jours-initiaux", type=int, default=int(os.environ.get("HYDRORADAR_JOURS", "2")))
    parser.add_argument("--version", action="version", version=f"hydroradar {__version__}")
    args = parser.parse_args(argv)

    rapport = executer(args.departement, args.dossier, args.jours_initiaux)
    _afficher(rapport, args.dossier)
    if DANS_AZURE:
        _commandes_azure(rapport)
    return 0 if rapport["statut"] == "ACCEPTE" else 1


if __name__ == "__main__":
    sys.exit(main())
