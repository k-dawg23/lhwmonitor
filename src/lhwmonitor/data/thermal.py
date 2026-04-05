"""Thermal zones from sysfs."""

from __future__ import annotations

from pathlib import Path


def read_thermal_zones() -> list[dict[str, str]]:
    base = Path("/sys/class/thermal")
    if not base.is_dir():
        return []
    zones: list[dict[str, str]] = []
    for z in sorted(base.glob("thermal_zone*")):
        tfile = z / "type"
        tempf = z / "temp"
        typ = ""
        try:
            typ = tfile.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        temp_millideg = ""
        try:
            temp_millideg = tempf.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        if typ or temp_millideg:
            zones.append(
                {
                    "zone": z.name,
                    "type": typ,
                    "temp_millideg": temp_millideg,
                }
            )
    return zones
