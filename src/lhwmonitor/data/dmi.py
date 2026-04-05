"""DMI / SMBIOS via dmidecode when permitted."""

from __future__ import annotations

import shutil
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


def _probe_dmidecode() -> tuple[bool, str | None]:
    """Return (ok_to_query, error_message_if_not).

    If dmidecode is missing or the first query fails (e.g. permission), callers skip field reads.
    """
    if not shutil.which("dmidecode"):
        return False, (
            "The `dmidecode` program was not found. Install it (e.g. `sudo apt install dmidecode`) "
            "to see motherboard and BIOS details here."
        )
    try:
        p = subprocess.run(
            ["dmidecode", "-s", "system-manufacturer"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError as e:
        return False, f"Could not run dmidecode: {e}"

    if p.returncode == 0:
        return True, None

    err = (p.stderr or "").strip()
    out = (p.stdout or "").strip()
    detail = err or out or f"exit code {p.returncode}"
    lower = detail.lower()
    if "permission" in lower or "root" in lower or "/dev/mem" in lower:
        return False, (
            "DMI is not readable without elevated privileges on this system. "
            "Run lhwmonitor as root if you need these details.\n\n"
            "If `sudo lhwmonitor` reports “command not found”, sudo is using a different PATH than your "
            "shell. Use either:\n"
            "  sudo env PATH=\"$PATH\" lhwmonitor\n"
            "or:\n"
            "  sudo $(command -v lhwmonitor)\n\n"
            f"(dmidecode said: {detail})"
        )
    return False, f"dmidecode failed: {detail}"


def collect_dmi_info() -> dict[str, Any]:
    """May be empty if not root, missing binary, or restricted."""
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

    ok, probe_err = _probe_dmidecode()
    if not ok:
        out["note"] = probe_err or "DMI unavailable."
        return out

    found = False
    for k in keys:
        v = _dmidecode_string(k)
        if v:
            found = True
            out[k.replace("-", "_")] = v
    out["available"] = found
    if not found:
        out["note"] = (
            "dmidecode ran but returned no DMI strings. If this persists as root, check kernel/firmware "
            "restrictions."
        )
    return out
