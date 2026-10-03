# RefurbPass

Outil en ligne de commande qui analyse un PC (portable ou fixe) et génère un **certificat de santé en PDF** à remettre au client : état réel de la batterie, état des disques (SMART), identité de la machine, score sur 100 et QR code.

Pensé pour les ateliers de reconditionnement.

## Ce que l'outil mesure

| Composant | Source | Ce qui est lu |
|---|---|---|
| Machine | WMI (Windows) / DMI (Linux) | Marque et modèle, n° de série, BIOS, CPU, RAM, OS |
| Batterie | WMI `BatteryStaticData` / `BatteryFullChargedCapacity`, repli `powercfg` (Windows), `/sys/class/power_supply` (Linux) | Capacité à pleine charge **comparée à la capacité d'origine**, nombre de cycles |
| Disques | `smartctl` (smartmontools) | Tous les disques : statut SMART, heures de fonctionnement, secteurs réalloués et instables, usure SSD / NVMe |

La batterie est notée sur son **usure** (capacité actuelle / capacité d'origine), pas sur son niveau de charge du moment.

## Calcul du score

Pondération : batterie 30 %, disque 40 %, système 30 %.

- Un composant **non mesuré** (PC fixe sans batterie, smartctl absent, droits insuffisants) n'entre **pas** dans le calcul : le score est recalculé sur les poids disponibles. Il n'est jamais gonflé par défaut.
- Le composant « Système » n'a pas encore de test réel (stabilité, RAM, CPU) : il apparaît « Non mesuré » sur le certificat et n'influence pas le score.
- Avec plusieurs disques, c'est le **moins bon** qui compte.
- Si rien n'a pu être mesuré, le certificat indique « Score non calculable » (et non 0/100).

Barème disque (heuristique, à affiner) : SMART en échec, secteurs réalloués (≥ 1, ≥ 10, ≥ 100), secteurs instables, usure SSD, erreurs d'intégrité NVMe, plus de 40 000 h de fonctionnement.

## Installation

Pré-requis :

- Python 3.11 ou plus
- [smartmontools](https://www.smartmontools.org/) 7.0 ou plus, `smartctl` dans le `PATH`
- Sous Windows : un terminal lancé **en administrateur**, sinon `smartctl` ne peut pas lire les disques

```bash
cd refurbpass
python -m venv .venv
.venv\Scripts\activate        # Windows (PowerShell / cmd)
# source .venv/bin/activate   # Linux / macOS
pip install -e .
```

## Utilisation

```bash
refurbpass run --shop "Mon Atelier" --output rapport_client.pdf
```

(équivalent : `python -m refurbpass.cli run ...`)

- `--shop` : nom de l'atelier affiché sur le certificat
- `--output` : fichier PDF à générer (les dossiers manquants sont créés)

## Tests

```bash
pip install -e ".[dev]"
pytest
```

Les tests couvrent le scoring, l'analyse des sorties SMART, la lecture de batterie et la génération du PDF avec des données simulées. Les appels WMI / PowerShell propres à Windows ne sont pas testables sans le matériel : **à vérifier sur de vraies machines**.

## Dépannage

**`pytest.exe` ou `refurbpass.exe` bloqué par Windows** (« stratégie de contrôle d'application ») : passer par Python, `python -m pytest` et `python -m refurbpass.cli run ...`.

**« Lecture SMART impossible (relancer le terminal en administrateur) »** : ouvrir PowerShell avec « Exécuter en tant qu'administrateur » puis relancer la commande.

**Disque « Non mesuré »** : `smartctl` est absent du `PATH`, ou son option JSON n'est pas disponible (smartmontools trop ancien).

## Limites connues

- Pas de test de stabilité (stress CPU / RAM, températures) : prévu pour une prochaine version.
- Les seuils du barème disque et batterie sont des heuristiques, pas une norme.
- Disques derrière un contrôleur RAID ou boîtier USB : `smartctl` peut ne pas y accéder.
- Le QR code encode un identifiant de rapport ; il ne pointe pas encore vers une page en ligne.
- Testé sous Linux ; la collecte Windows (WMI, `powercfg`) est écrite mais à valider sur machines réelles.

## Licence

MIT
