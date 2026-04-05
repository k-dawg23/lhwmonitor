"""DMI / SMBIOS via dmidecode when permitted."""

from __future__ import annotations

import subprocess
from typing import Any


def _dmidecode_string(t: str) -> str | None:
    try:
        p = subprocess.run(
            ["dmidecode", "-s", t],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return None
    if p.returncode != 0:
        return None
    s = (p.stdout or "").strip()
    return s or None


def collect_dmi_info() -> dict[str, Any]:
    """May be empty if not root or restricted."""
    keys = [
        "system-manufacturer",
        "system-product-name",
        "system-version",
        "baseboard-manufacturer",
        "baseboard-product-name",
        "bios-vendor",
        "bios-version",
        "bios-release-date",
    ]
    out: dict[str, Any] = {"available": False}
    found = False
    for k in keys:
        v = _dmidecode_string(k)
        if v:
            found = True
            out[k.replace("-", "_")] = v
    out["available"] = found
    if not found:
        out["note"] = "Run as root or install dmidecode for motherboard/BIOS details."
    return out
