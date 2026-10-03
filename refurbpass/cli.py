"""Interface en ligne de commande de RefurbPass."""
from __future__ import annotations

import argparse
import sys
from typing import List, Optional

from refurbpass import __version__
from refurbpass.collectors.battery import collect_battery_info
from refurbpass.collectors.disk import collect_disk_info
from refurbpass.collectors.system import collect_system_info
from refurbpass.report.pdf import ReportGenerator
from refurbpass.scoring import calculate_score


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="refurbpass",
        description="Analyse de santé d'un PC et certificat PDF.",
    )
    parser.add_argument("--version", action="version", version=f"RefurbPass {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Analyser cette machine et générer le certificat PDF")
    run.add_argument("--shop", default="Atelier de Reconditionnement",
                     help="Nom de l'atelier affiché sur le certificat")
    run.add_argument("--output", default="rapport_sante.pdf",
                     help="Fichier PDF à générer")
    return parser


def run_analysis(shop: str, output: str) -> int:
    print("Collecte des informations système...")
    system = collect_system_info()

    print("Analyse de la batterie...")
    battery = collect_battery_info()

    print("Analyse des disques (SMART)...")
    disks = collect_disk_info()

    health = calculate_score(
        battery_health=battery.health,
        disk_health=disks.health,
        system_stability=None,  # pas de test de stabilité dans cette version
        disk_issues=disks.issues,
        details={
            "battery": battery.details,
            "disk": disks.details,
        },
        not_applicable=["battery"] if battery.status == "NotApplicable" else [],
    )

    print(f"Génération du certificat : {output}")
    try:
        ReportGenerator(shop_name=shop).generate(system, health, output)
    except Exception as exc:
        print(f"Erreur lors de la génération du PDF : {exc}", file=sys.stderr)
        return 1

    if health.overall_score is None:
        print("\nTerminé. Score non calculable : aucun composant n'a pu être mesuré.")
    else:
        print(f"\nTerminé. Score global : {health.overall_score}/100")
    for point in health.summary_weak_points:
        print(f"  - {point}")
    if disks.status == "Unavailable":
        print(f"  ! Disque non évalué : {disks.details}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return run_analysis(args.shop, args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
