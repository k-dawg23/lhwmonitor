"""Battery / power supply information from /sys/class/power_supply."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _read_text(p: Path) -> str | None:
    try:
        return p.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def collect_power_supply_snapshot() -> dict[str, Any]:
    base = Path("/sys/class/power_supply")
    if not base.is_dir():
        return {"batteries": [], "note": "No /sys/class/power_supply."}
    bats: list[dict[str, Any]] = []
    for dev in sorted(base.glob("BAT*")):
        cap = _read_text(dev / "capacity")
        status = _read_text(dev / "status")
        energy_now = _read_text(dev / "energy_now") or _read_text(dev / "charge_now")
        energy_full = _read_text(dev / "energy_full") or _read_text(dev / "charge_full")
        power_now = _read_text(dev / "power_now") or _read_text(dev / "current_now")
        bats.append(
            {
                "name": dev.name,
                "capacity_percent": int(cap) if cap and cap.isdigit() else None,
                "status": status,
                "energy_now": energy_now,
                "energy_full": energy_full,
                "power_now": power_now,
            }
        )
    if not bats:
        return {"batteries": [], "note": "No batteries detected (BAT*)."}
    return {"batteries": bats}

