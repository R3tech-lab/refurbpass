"""Collecte de la santé réelle de la batterie.

Santé = capacité à pleine charge actuelle / capacité d'origine (et non le
pourcentage de charge du moment).
"""
from __future__ import annotations

import tempfile
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import psutil

from refurbpass.collectors._util import is_windows, run_powershell_json

# status : "OK" (mesure obtenue), "NotApplicable" (PC fixe), "Unavailable" (échec de mesure)


@dataclass
class BatteryInfo:
    status: str
    health: Optional[float] = None  # 0.0 à 1.0
    design_capacity: Optional[int] = None
    full_capacity: Optional[int] = None
    unit: str = "mWh"
    cycles: Optional[int] = None
    details: str = ""


def compute_health(design: Optional[float], full: Optional[float]) -> Optional[float]:
    """Capacité actuelle / capacité d'origine, plafonnée à 1.0."""
    if not design or not full or design <= 0 or full <= 0:
        return None
    return round(min(full / design, 1.0), 3)


def parse_powercfg_xml(xml_bytes: bytes) -> Optional[Tuple[int, int, Optional[int]]]:
    """Lit un rapport `powercfg /batteryreport /xml` : (design, full, cycles)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None

    def local(tag: str) -> str:
        return tag.split("}")[-1]

    for battery in root.iter():
        if local(battery.tag) != "Battery":
            continue
        values = {local(child.tag): (child.text or "").strip() for child in battery}
        try:
            design = int(values["DesignCapacity"])
            full = int(values["FullChargeCapacity"])
        except (KeyError, ValueError):
            continue
        try:
            # 0 = information non fournie par la batterie, pas « batterie neuve »
            cycles: Optional[int] = int(values["CycleCount"]) or None
        except (KeyError, ValueError):
            cycles = None
        return design, full, cycles
    return None


def read_linux_battery(
    base: Path = Path("/sys/class/power_supply"),
) -> Optional[Tuple[int, int, Optional[int], str]]:
    """Renvoie (design, full, cycles, unité) ou None s'il n'y a pas de batterie."""
    batteries = sorted(p for p in base.glob("BAT*") if p.is_dir())
    if not batteries:
        return None
    bat = batteries[0]

    def number(name: str) -> Optional[int]:
        try:
            return int((bat / name).read_text().strip())
        except (OSError, ValueError):
            return None

    design = number("energy_full_design")
    full = number("energy_full")
    unit = "mWh"
    if not design or not full:
        design = number("charge_full_design")
        full = number("charge_full")
        unit = "mAh"
    if not design or not full:
        return 0, 0, number("cycle_count"), unit
    return design // 1000, full // 1000, number("cycle_count"), unit


_WINDOWS_SCRIPT = r"""
$d = Get-CimInstance -Namespace root\wmi -ClassName BatteryStaticData -ErrorAction SilentlyContinue | Select-Object -First 1
$f = Get-CimInstance -Namespace root\wmi -ClassName BatteryFullChargedCapacity -ErrorAction SilentlyContinue | Select-Object -First 1
$c = Get-CimInstance -Namespace root\wmi -ClassName BatteryCycleCount -ErrorAction SilentlyContinue | Select-Object -First 1
[pscustomobject]@{
    design = $d.DesignedCapacity
    full   = $f.FullChargedCapacity
    cycles = $c.CycleCount
} | ConvertTo-Json -Compress
"""


def _windows_measure() -> Optional[Tuple[int, int, Optional[int]]]:
    data = run_powershell_json(_WINDOWS_SCRIPT)
    if isinstance(data, dict):
        try:
            design, full = int(data.get("design") or 0), int(data.get("full") or 0)
        except (TypeError, ValueError):
            design = full = 0
        if design > 0 and full > 0:
            cycles = data.get("cycles")
            return design, full, int(cycles) if cycles else None

    # Repli : rapport powercfg au format XML.
    try:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "battery.xml"
            subprocess.run(
                ["powercfg", "/batteryreport", "/output", str(out), "/xml"],
                capture_output=True,
                timeout=30,
            )
            if out.exists():
                return parse_powercfg_xml(out.read_bytes())
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _build_info(design: int, full: int, cycles: Optional[int], unit: str = "mWh") -> BatteryInfo:
    health = compute_health(design, full)
    if health is None:
        return BatteryInfo(
            status="Unavailable",
            details="Capacité d'origine ou actuelle non lisible sur cette machine",
            cycles=cycles,
        )
    details = (
        f"{full} {unit} à pleine charge sur {design} {unit} d'origine "
        f"({round(health * 100)} %)"
    )
    if cycles:
        details += f", {cycles} cycles"
    return BatteryInfo("OK", health, design, full, unit, cycles, details)


def collect_battery_info() -> BatteryInfo:
    """Ne plante jamais : renvoie NotApplicable (PC fixe) ou Unavailable en cas d'échec."""
    try:
        if is_windows():
            if psutil.sensors_battery() is None:
                return BatteryInfo("NotApplicable", details="Aucune batterie (PC fixe)")
            measured = _windows_measure()
            if measured is None:
                return BatteryInfo(
                    "Unavailable", details="Mesure impossible (WMI et powercfg ont échoué)"
                )
            return _build_info(*measured)

        linux = read_linux_battery()
        if linux is None:
            return BatteryInfo("NotApplicable", details="Aucune batterie (PC fixe)")
        design, full, cycles, unit = linux
        return _build_info(design, full, cycles, unit)
    except Exception as exc:
        return BatteryInfo("Unavailable", details=f"Erreur : {exc}")
