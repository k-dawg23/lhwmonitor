"""lm-sensors: `sensors -j` or fallback to text."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any


def _run_sensors_json() -> dict[str, Any] | None:
    try:
        p = subprocess.run(
            ["sensors", "-j"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except OSError:
        return None
    if p.returncode != 0 or not (p.stdout or "").strip():
        return None
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return None


def _flatten_sensors_json(data: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for chip_name, chip in data.items():
        if chip_name == "Adapter" or not isinstance(chip, dict):
            continue
        adapter = ""
        if "Adapter" in chip and isinstance(chip["Adapter"], str):
            adapter = chip["Adapter"]
        for key, val in chip.items():
            if key == "Adapter":
                continue
            if isinstance(val, dict):
                for subk, subv in val.items():
                    if isinstance(subv, (int, float)):
                        rows.append(
                            {
                                "chip": chip_name,
                                "adapter": adapter,
                                "label": f"{key}/{subk}",
                                "value": f"{float(subv):.1f}",
                                "unit": _guess_unit(subk),
                            }
                        )
            elif isinstance(val, (int, float)):
                rows.append(
                    {
                        "chip": chip_name,
                        "adapter": adapter,
                        "label": key,
                        "value": f"{float(val):.1f}",
                        "unit": _guess_unit(key),
                    }
                )
    return rows


def _guess_unit(name: str) -> str:
    n = name.lower()
    if "temp" in n:
        return "°C"
    if "fan" in n or "rpm" in n:
        return "RPM"
    if "volt" in n or "in" in n:
        return "V"
    return ""


def _parse_sensors_text(text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    chip = ""
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith(":") and not line.startswith(" "):
            chip = line[:-1].strip()
            continue
        m = re.match(r"^([^:]+):\s*\+?([0-9.]+)\s*([°CF°]*|[RV][P]?M|V)?", line)
        if m:
            label, val, unit = m.group(1).strip(), m.group(2), (m.group(3) or "").strip()
            rows.append(
                {
                    "chip": chip,
                    "adapter": "",
                    "label": label,
                    "value": val,
                    "unit": unit,
                }
            )
    return rows


def _run_sensors_text() -> str:
    try:
        p = subprocess.run(
            ["sensors"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except OSError:
        return ""
    return p.stdout or ""


def collect_sensors_rows() -> tuple[list[dict[str, str]], str | None]:
    """Return rows and optional error/note."""
    j = _run_sensors_json()
    if j:
        rows = _flatten_sensors_json(j)
        if rows:
            return rows, None
    txt = _run_sensors_text()
    if txt.strip():
        return _parse_sensors_text(txt), None
    return [], "lm-sensors not available or no chips. Install lm-sensors and run sensors-detect."
