"""Petits utilitaires partagés par les collecteurs."""
from __future__ import annotations

import json
import platform
import subprocess
from typing import Any, Optional

UNKNOWN = "Inconnu"

# Valeurs « bidon » que beaucoup de BIOS renvoient quand le fabricant n'a rien rempli.
_PLACEHOLDERS = {
    "",
    "to be filled by o.e.m.",
    "to be filled by oem",
    "default string",
    "system product name",
    "system serial number",
    "system version",
    "o.e.m.",
    "oem",
    "none",
    "not specified",
    "not applicable",
    "unknown",
    "n/a",
    "0",
}


def is_windows() -> bool:
    return platform.system() == "Windows"


def clean_value(value: Any) -> Optional[str]:
    """Renvoie la valeur nettoyée, ou None si elle est vide ou bidon."""
    if value is None:
        return None
    text = str(value).strip()
    return None if text.lower() in _PLACEHOLDERS else text


def run_powershell_json(script: str, timeout: int = 25) -> Optional[Any]:
    """Exécute un script PowerShell qui affiche du JSON et renvoie l'objet décodé.

    Renvoie None en cas d'échec (PowerShell absent, erreur, sortie illisible).
    """
    prefix = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    try:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                prefix + script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None

    output = (proc.stdout or "").strip()
    if proc.returncode != 0 or not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None
