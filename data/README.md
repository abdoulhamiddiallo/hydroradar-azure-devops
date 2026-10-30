# 🗂️ Dictionnaire des données HydroRadar

Toutes les données viennent de l'API publique **Hub'Eau Hydrométrie** (Office français de la biodiversité et BRGM, Licence Ouverte Etalab). Le dossier [`exemples/`](exemples) contient les sorties **réelles** produites par HydroRadar sur l'extrait du **29 octobre 2026, de 20 h 25 à 21 h 30 UTC**, en Moselle (département 57). C'est le même extrait que celui des tests unitaires ([`tests/donnees/`](../tests/donnees)).

## 1. La source

| Ressource Hub'Eau | Utilisation | Unités publiées |
|---|---|---|
| `referentiel/stations` | liste des stations d'un département | coordonnées WGS 84 |
| `observations_tr` | hauteurs (`H`) et débits (`Q`) en temps réel, une mesure toutes les 5 à 15 minutes, un mois d'historique | `H` en **millimètres**, `Q` en **litres par seconde** |

Particularités prises en compte par le code :

| Comportement de l'API | Réponse d'HydroRadar |
|---|---|
| HTTP **206** tant qu'il reste des pages, curseur dans le champ `next` | pagination par curseur jusqu'à HTTP 200 ([`client.py`](../src/hydroradar/client.py)) |
| erreurs passagères 429 et 5xx | 5 reprises avec attente croissante |
| le paramètre `fields` réduit la réponse | seules les colonnes utiles sont demandées |
| filtre `code_entite` limité en longueur | stations demandées par lots de 50 |
| stations qui transmettent en retard | relecture de **2 heures** avant le filigrane |

## 2. Organisation des couches

```text
donnees/<environnement>/<département>/
├── etat.json                                     filigrane : dernière mesure chargée
├── bronze/AAAA-MM-JJ/observations_HHMMSS.json.gz réponse brute, jamais modifiée
├── argent/
│   ├── stations.parquet                          dimension stations
│   └── observations/date=AAAA-MM-JJ/part.parquet faits nettoyés, une partition par jour
├── or/
│   ├── situation_stations.csv                    une ligne par station
│   └── synthese.json                             résumé du département
└── controle/
    ├── rapport_qualite.json                      verdict de la porte qualité
    └── quarantaine.csv                           lignes écartées et leur motif
```

| Couche | Rôle | Format | Règle d'écriture |
|---|---|---|---|
| **bronze** | preuve de ce que l'API a renvoyé | JSON compressé | ajout seul, jamais de modification |
| **argent** | faits typés, en unités du système international | Parquet partitionné par jour | fusion sans doublon (upsert) par partition |
| **or** | indicateurs prêts à lire | CSV `;` et virgule décimale, JSON | réécrit à chaque passage accepté |
| **contrôle** | traçabilité de la qualité | JSON, CSV | réécrit à chaque passage, accepté ou refusé |

## 3. Schéma de chaque fichier

### `argent/observations/date=AAAA-MM-JJ/part.parquet`

Clé unique : `code_station`, `grandeur`, `date_obs`.

| Colonne | Type | Description | Exemple |
|---|---|---|---|
| `code_station` | texte | identifiant Sandre de la station | `A743061001` |
| `grandeur` | texte | `H` hauteur ou `Q` débit | `H` |
| `date_obs` | horodatage UTC | instant de la mesure | `2026-10-29 21:30:00+00:00` |
| `valeur` | décimal | valeur convertie : mètres pour `H`, m³/s pour `Q` | `2.162` |
| `unite` | texte | `m` ou `m3/s` | `m` |
| `valeur_brute` | entier | valeur publiée par l'API (mm ou l/s) | `2162` |
| `methode` | texte | nomenclature Sandre 507 : mesurée, calculée, reconstituée, interpolée | `mesurée` |

### `argent/stations.parquet`

| Colonne | Type | Description |
|---|---|---|
| `code_station` | texte | identifiant Sandre |
| `station` | texte | libellé officiel |
| `cours_eau` | texte | rivière, ou `(non renseigné)` |
| `commune` | texte | commune, en casse titre |
| `departement` | texte | code du département |
| `type_station` | texte | `STD` standard, `DEB` débitmètre, `H` hauteur seule |
| `longitude`, `latitude` | décimal | WGS 84 |

### `or/situation_stations.csv`

| Colonne | Description |
|---|---|
| `code_station`, `station`, `cours_eau`, `commune`, `latitude`, `longitude` | identité de la station |
| `derniere_mesure` | dernière mesure reçue |
| `hauteur_m`, `debit_m3s` | dernières valeurs connues |
| `variation_1h_cm`, `variation_24h_cm` | écart de hauteur avec la mesure d'il y a 1 h et 24 h (tolérance de 30 minutes) |
| `hauteur_max_24h_m` | plus haute hauteur sur la période |
| `tendance` | `en hausse` ou `en baisse` au-delà de 2 cm par heure, sinon `stable` ; `indéterminée` sans référence |

### `or/synthese.json`

Nombre de stations suivies, répartition des tendances, plus forte hausse sur une heure, dernière mesure et statut qualité.

### `controle/rapport_qualite.json` et `controle/quarantaine.csv`

Le rapport contient les cinq règles avec leur valeur, leur seuil et leur verdict, puis le statut `ACCEPTE` ou `REFUSE`. La quarantaine reprend les colonnes de la couche argent, plus `motif`.

## 4. Les deux niveaux de contrôle

**Quarantaine, ligne par ligne.** Une ligne suspecte est écartée avec son motif, sans bloquer les lignes saines.

| Motif | Condition |
|---|---|
| `valeur absente` | pas de valeur numérique |
| `grandeur inconnue` | ni `H` ni `Q` |
| `débit négatif` | `Q` inférieur à 0, physiquement impossible |
| `saut de hauteur aberrant` | plus de 3 m d'écart avec la mesure précédente de la même station, à moins de 30 minutes |

> **Piège du métier.** Une hauteur **négative** est normale : elle est mesurée par rapport au zéro de l'échelle limnimétrique. La Petite Seille à Château-Salins était à **-0,27 m** le 29 octobre. Seul un débit négatif est rejeté.

**Porte qualité, sur le lot entier.** Une seule règle en échec et le lot est refusé : rien n'est écrit en argent ni en or, et le filigrane **n'avance pas**. Le passage suivant relira donc les mêmes mesures.

| Règle | Seuil | Extrait du 29 oct. | Exécution réelle complète (57) |
|---|---|---|---|
| `volume` | au moins 100 mesures valides | 134 | **31 840** |
| `couverture` | au moins 50 % des stations ont transmis | 0,857 | **0,787** (37 sur 47) |
| `fraicheur_minutes` | dernière mesure de moins de 180 min | 15 | **13** |
| `unicite_doublons` | aucun doublon sur la clé | 0 | **0** |
| `taux_quarantaine` | au plus 2 % de lignes écartées | 0 | **0** |

Sous 80 % de couverture, le lot reste accepté, mais le pipeline affiche un avertissement **« Couverture faible »** dans Azure DevOps.

## 5. Chargement incrémental

| Situation | Début de l'extraction |
|---|---|
| premier passage (pas de `etat.json`) | maintenant moins `--jours-initiaux` jours (2 par défaut) |
| passages suivants | filigrane moins **2 heures** de recouvrement |

Les mesures relues par le recouvrement sont dédoublonnées sur la clé unique : rejouer un passage ne change rien (**idempotence**). Le filigrane n'est écrit qu'après une porte qualité acceptée.

## 6. Réconciliation de l'exemple

| Contrôle | Valeur |
|---|---|
| mesures dans le fichier bronze | 134 |
| mesures en argent | 134 (74 hauteurs, 60 débits) |
| lignes en quarantaine | 0 |
| stations du référentiel | 7 |
| stations ayant transmis | 6 (la station minière de Neufchef n'a rien transmis sur la période) |
| stations en or | 6, dont 5 `stable` et 1 `indéterminée` (Sarrebourg transmet avec retard) |

Lecture des fichiers Parquet :

```python
import pandas as pd

pd.read_parquet("data/exemples/argent/observations")  # toutes les partitions d'un coup
```

Les fichiers `apercu_*.csv` sont les mêmes tables au format CSV, pour une lecture directe sur GitHub.
