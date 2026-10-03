"""Collecte de l'état des disques via smartmontools (smartctl).

Nécessite smartctl >= 7.0 (sortie JSON) et, sous Windows, un terminal
lancé en administrateur.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Attributs SMART qui indiquent la vie restante (valeur normalisée, 100 = neuf)
_SSD_LIFE_LEFT_IDS = (177, 231, 233, 202)


@dataclass
class DiskReport:
    name: str
    device: str
    kind: str  # "SSD NVMe", "SSD", "HDD", "Inconnu"
    smart_passed: Optional[bool] = None
    power_on_hours: Optional[int] = None
    reallocated_sectors: Optional[int] = None
    pending_sectors: Optional[int] = None
    wear_used_pct: Optional[int] = None
    health: float = 1.0  # 0.0 à 1.0
    issues: List[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{self.name} ({self.kind})"]
        if self.power_on_hours is not None:
            parts.append(f"{self.power_on_hours} h")
        if self.wear_used_pct is not None:
            parts.append(f"usure {self.wear_used_pct} %")
        if self.reallocated_sectors is not None:
            parts.append(f"{self.reallocated_sectors} secteurs réalloués")
        if self.smart_passed is not None:
            parts.append("SMART OK" if self.smart_passed else "SMART EN ÉCHEC")
        return ", ".join(parts)


@dataclass
class DiskInfo:
    status: str  # "OK" ou "Unavailable"
    health: Optional[float] = None  # le pire disque
    disks: List[DiskReport] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    details: str = ""


def _attributes(data: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    table = data.get("ata_smart_attributes", {}).get("table", [])
    return {a["id"]: a for a in table if isinstance(a, dict) and "id" in a}


def _raw(attrs: Dict[int, Dict[str, Any]], attr_id: int) -> Optional[int]:
    attr = attrs.get(attr_id)
    if not attr:
        return None
    try:
        return int(attr.get("raw", {}).get("value"))
    except (TypeError, ValueError):
        return None


def evaluate_disk(data: Dict[str, Any], device: str) -> DiskReport:
    """Transforme la sortie JSON de `smartctl -a -j` en rapport noté (fonction pure)."""
    name = data.get("model_name") or data.get("device", {}).get("name") or device
    nvme_log = data.get("nvme_smart_health_information_log")
    attrs = _attributes(data)

    if nvme_log is not None or data.get("device", {}).get("type") == "nvme":
        kind = "SSD NVMe"
    elif data.get("rotation_rate") == 0:
        kind = "SSD"
    elif data.get("rotation_rate"):
        kind = "HDD"
    else:
        kind = "Inconnu"

    report = DiskReport(name=name, device=device, kind=kind)
    issues = report.issues
    health = 1.0

    passed = data.get("smart_status", {}).get("passed")
    if isinstance(passed, bool):
        report.smart_passed = passed
        if not passed:
            health = min(health, 0.1)
            issues.append(f"{name} : diagnostic SMART en échec, disque à remplacer")

    hours = data.get("power_on_time", {}).get("hours")
    if hours is None and nvme_log:
        hours = nvme_log.get("power_on_hours")
    if hours is not None:
        report.power_on_hours = int(hours)

    if nvme_log:
        used = nvme_log.get("percentage_used")
        if used is not None:
            report.wear_used_pct = max(0, min(100, int(used)))
        if nvme_log.get("critical_warning"):
            health = min(health, 0.3)
            issues.append(f"{name} : alerte critique signalée par le disque")
        media_errors = nvme_log.get("media_errors") or 0
        if media_errors > 0:
            health -= 0.3
            issues.append(f"{name} : {media_errors} erreurs d'intégrité des données")
    else:
        if kind != "HDD":
            for attr_id in _SSD_LIFE_LEFT_IDS:
                attr = attrs.get(attr_id)
                if attr and isinstance(attr.get("value"), int):
                    report.wear_used_pct = max(0, min(100, 100 - attr["value"]))
                    break

    if report.wear_used_pct is not None:
        health = min(health, max(0.0, 1 - report.wear_used_pct / 100))
        if report.wear_used_pct >= 80:
            issues.append(f"{name} : SSD usé à {report.wear_used_pct} %, remplacement conseillé")
        elif report.wear_used_pct >= 50:
            issues.append(f"{name} : SSD usé à {report.wear_used_pct} %, à surveiller")

    realloc = _raw(attrs, 5)
    if realloc is not None:
        report.reallocated_sectors = realloc
        if realloc >= 100:
            health -= 0.5
        elif realloc >= 10:
            health -= 0.3
        elif realloc > 0:
            health -= 0.1
        if realloc > 0:
            issues.append(f"{name} : {realloc} secteurs réalloués, à surveiller")

    pending = (_raw(attrs, 197) or 0) + (_raw(attrs, 198) or 0)
    if _raw(attrs, 197) is not None or _raw(attrs, 198) is not None:
        report.pending_sectors = pending
    if pending > 0:
        health -= 0.3
        issues.append(f"{name} : {pending} secteurs instables ou illisibles")

    if report.power_on_hours is not None and report.power_on_hours >= 40000:
        health -= 0.08
        issues.append(f"{name} : très sollicité ({report.power_on_hours} h de fonctionnement)")

    report.health = round(max(0.0, min(1.0, health)), 3)
    return report


def parse_scan(output: str) -> List[Tuple[str, List[str]]]:
    """Lit la sortie de `smartctl --scan` : liste de (périphérique, arguments)."""
    devices = []
    for line in output.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        tokens = line.split()
        devices.append((tokens[0], tokens[1:]))
    return devices


def _run(cmd: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def collect_disk_info() -> DiskInfo:
    """Ne plante jamais : renvoie Unavailable avec la raison si smartctl échoue."""
    smartctl = shutil.which("smartctl")
    if not smartctl:
        return DiskInfo("Unavailable", details="smartmontools (smartctl) non installé")

    try:
        scan = _run([smartctl, "--scan"])
        devices = parse_scan(scan.stdout)
        if not devices:
            return DiskInfo("Unavailable", details="Aucun disque détecté par smartctl")

        reports: List[DiskReport] = []
        denied = False
        for device, args in devices:
            proc = _run([smartctl, "-a", "-j", device, *args])
            try:
                data = json.loads(proc.stdout)
            except json.JSONDecodeError:
                continue
            # bits 0-1 : erreur de ligne de commande / impossible d'ouvrir le périphérique
            has_smart = any(
                k in data
                for k in ("smart_status", "ata_smart_attributes", "nvme_smart_health_information_log")
            )
            if not has_smart:
                if proc.returncode & 3:
                    denied = True
                continue
            reports.append(evaluate_disk(data, device))

        if not reports:
            hint = (
                " (relancer le terminal en administrateur)"
                if denied
                else ""
            )
            return DiskInfo("Unavailable", details=f"Lecture SMART impossible{hint}")

        issues = [issue for r in reports for issue in r.issues]
        return DiskInfo(
            status="OK",
            health=min(r.health for r in reports),
            disks=reports,
            issues=issues,
            details=" ; ".join(r.summary() for r in reports),
        )
    except Exception as exc:
        return DiskInfo("Unavailable", details=f"Erreur smartctl : {exc}")
