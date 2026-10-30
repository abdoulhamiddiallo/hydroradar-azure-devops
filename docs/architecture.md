# Architecture

## Source des données

API Hub'Eau Hydrométrie, ressource `observations_tr` : hauteurs (H, en mm) et débits (Q, en l/s)
mesurés toutes les 5 à 15 minutes par les stations du réseau hydrométrique. Un mois d'historique.

## Couches

| Couche | Contenu | Format |
|---|---|---|
| bronze | réponse brute de l'API, jamais modifiée | JSON compressé |
| argent | mesures nettoyées, en m et m3/s, partition par jour | Parquet |
| or | situation de chaque station, synthèse du département | CSV et JSON |

## Chargement incrémental

Le fichier `etat.json` garde la date de la dernière mesure chargée (le filigrane). Chaque passage
relit depuis ce filigrane moins 2 heures, puis fusionne sans doublon : rejouer un passage ne change rien.
Le filigrane n'avance que si la porte qualité accepte le lot.
