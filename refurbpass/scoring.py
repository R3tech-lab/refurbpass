"""Calcul du score de santé global (module pur, testable sans matériel)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


@dataclass
class ComponentHealth:
    name: str
    score: int  # 0 à 100
    status: str  # "OK", "Warning", "Critical", "Unavailable", "NotApplicable"
    details: str
    weak_points: List[str]


@dataclass
class GlobalHealth:
    overall_score: Optional[int]  # None si aucun composant n'a pu être mesuré
    component_scores: List[ComponentHealth]
    summary_weak_points: List[str]


WEIGHTS = {"battery": 30, "disk": 40, "system": 30}


def _status(score: int, ok_above: int, warning_above: int) -> str:
    return "OK" if score > ok_above else "Warning" if score > warning_above else "Critical"


def calculate_score(
    battery_health: Optional[float],  # 0.0 à 1.0
    disk_health: Optional[float],  # 0.0 à 1.0
    system_stability: Optional[float] = None,  # 0.0 à 1.0, None tant qu'aucun test réel
    *,
    disk_issues: Optional[List[str]] = None,
    details: Optional[Dict[str, str]] = None,
    not_applicable: Iterable[str] = (),
) -> GlobalHealth:
    """Score pondéré : batterie 30 %, disque 40 %, système 30 %.

    Un composant non mesuré (None) n'entre pas dans le calcul : le score est
    recalculé sur les poids disponibles, il n'est jamais gonflé par défaut.

    `details` : texte à afficher par composant ("battery", "disk", "system").
    `not_applicable` : composants sans objet (ex. {"battery"} sur un PC fixe).
    """
    details = details or {}
    not_applicable = set(not_applicable)
    components: List[ComponentHealth] = []
    weak_points: List[str] = []
    weighted = 0.0
    weight_total = 0.0

    def add(key, name, value, ok_above, warning_above, default_detail, generic, unavailable_detail):
        nonlocal weighted, weight_total
        if value is None:
            status = "NotApplicable" if key in not_applicable else "Unavailable"
            components.append(
                ComponentHealth(name, 0, status, details.get(key, unavailable_detail), [])
            )
            return
        score = round(value * 100)
        status = _status(score, ok_above, warning_above)
        points = generic(score, status)
        components.append(
            ComponentHealth(name, score, status, details.get(key, default_detail(score)), points)
        )
        weighted += score * WEIGHTS[key] / 100
        weight_total += WEIGHTS[key] / 100
        weak_points.extend(points)

    def battery_points(score, status):
        if status == "Warning":
            return [f"Batterie à {score}% de sa capacité d'origine : remplacement conseillé"]
        if status == "Critical":
            return [f"Batterie très usée ({score}% de sa capacité d'origine) : remplacement urgent"]
        return []

    def disk_points(score, status):
        if disk_issues:
            return list(disk_issues)
        if status == "Warning":
            return [f"Usure disque détectée ({score}%) : à surveiller"]
        if status == "Critical":
            return [f"Disque en fin de vie ({score}%) : remplacement immédiat"]
        return []

    def system_points(score, status):
        if status == "Warning":
            return ["Quelques anomalies détectées sur le système"]
        if status == "Critical":
            return ["Instabilité matérielle majeure détectée"]
        return []

    add("battery", "Batterie", battery_health, 80, 60,
        lambda s: f"Capacité : {s}% de l'origine", battery_points, "Mesure indisponible")
    add("disk", "Disque", disk_health, 90, 70,
        lambda s: f"Santé SMART : {s}%", disk_points, "SMART indisponible")
    add("system", "Système", system_stability, 90, 70,
        lambda s: "Stabilité matérielle", system_points,
        "Test de stabilité non réalisé dans cette version")

    final = int(weighted / weight_total) if weight_total else None
    return GlobalHealth(final, components, weak_points)
