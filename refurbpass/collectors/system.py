"""Collecte des informations matérielles (modèle, numéro de série, CPU, RAM, BIOS, OS)."""
from __future__ import annotations

import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import psutil

from refurbpass.collectors._util import UNKNOWN, clean_value, is_windows, run_powershell_json


@dataclass
class SystemInfo:
    model: str = UNKNOWN
    serial_number: str = UNKNOWN
    cpu: str = UNKNOWN
    ram: str = UNKNOWN
    os: str = UNKNOWN
    bios_version: str = UNKNOWN


_WINDOWS_SCRIPT = r"""
$cs  = Get-CimInstance Win32_ComputerSystem
$csp = Get-CimInstance Win32_ComputerSystemProduct
$bio = Get-CimInstance Win32_BIOS
$cpu = Get-CimInstance Win32_Processor | Select-Object -First 1
[pscustomobject]@{
    manufacturer = $cs.Manufacturer
    model        = $cs.Model
    version      = $csp.Version
    serial       = $bio.SerialNumber
    bios         = $bio.SMBIOSBIOSVersion
    cpu          = $cpu.Name
} | ConvertTo-Json -Compress
"""


def build_model_name(
    manufacturer: Optional[str], model: Optional[str], version: Optional[str]
) -> str:
    """Construit un nom de modèle lisible.

    Chez Lenovo, `Model` est un code (ex. 20L5...) et le vrai nom commercial
    (ThinkPad T480) se trouve dans `Version`.
    """
    man = clean_value(manufacturer)
    mod = clean_value(model)
    ver = clean_value(version)

    if man and man.lower().startswith("lenovo") and ver:
        mod = ver

    if man and mod and mod.lower().startswith(man.lower()):
        return mod
    return " ".join(p for p in (man, mod) if p) or UNKNOWN


def format_ram(total_bytes: int) -> str:
    return f"{round(total_bytes / (1024 ** 3))} Go"


def _windows_os_name() -> str:
    try:
        build = int(platform.version().split(".")[-1])
    except ValueError:
        return f"Windows {platform.release()}"
    # Windows 11 garde la version majeure 10 ; on le reconnaît au numéro de build.
    return "Windows 11" if build >= 22000 else f"Windows {platform.release()}"


def _read_text(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _linux_cpu_name() -> Optional[str]:
    text = _read_text(Path("/proc/cpuinfo"))
    if not text:
        return None
    for line in text.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return None


def _collect_windows(info: SystemInfo) -> None:
    data = run_powershell_json(_WINDOWS_SCRIPT)
    if not isinstance(data, dict):
        return
    info.model = build_model_name(data.get("manufacturer"), data.get("model"), data.get("version"))
    info.serial_number = clean_value(data.get("serial")) or UNKNOWN
    info.bios_version = clean_value(data.get("bios")) or UNKNOWN
    info.cpu = clean_value(data.get("cpu")) or info.cpu


def _collect_linux(info: SystemInfo, dmi: Path = Path("/sys/class/dmi/id")) -> None:
    info.model = build_model_name(
        _read_text(dmi / "sys_vendor"),
        _read_text(dmi / "product_name"),
        _read_text(dmi / "product_version"),
    )
    # product_serial n'est lisible que par root.
    info.serial_number = clean_value(_read_text(dmi / "product_serial")) or UNKNOWN
    info.bios_version = clean_value(_read_text(dmi / "bios_version")) or UNKNOWN
    info.cpu = _linux_cpu_name() or info.cpu


def collect_system_info() -> SystemInfo:
    """Ne plante jamais : les champs non détectés valent « Inconnu »."""
    info = SystemInfo()
    try:
        info.ram = format_ram(psutil.virtual_memory().total)
    except Exception:
        pass
    info.cpu = clean_value(platform.processor()) or UNKNOWN
    system = platform.system()
    try:
        if is_windows():
            info.os = _windows_os_name()
            _collect_windows(info)
        else:
            info.os = f"{system} {platform.release()}".strip()
            if system == "Linux":
                _collect_linux(info)
    except Exception:
        pass
    return info
