"""Single refresh of Monitor tab metrics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from lhwmonitor.data.cpufreq import read_cpu_mhz
from lhwmonitor.data.proc_stat import CpuUsageSampler
from lhwmonitor.data.sensors_live import collect_sensors_rows
from lhwmonitor.data.thermal import read_thermal_zones


def read_loadavg() -> str:
    try:
        return Path("/proc/loadavg").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def collect_monitor_snapshot(sampler: CpuUsageSampler) -> dict[str, Any]:
    stat_text = ""
    try:
        stat_text = Path("/proc/stat").read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return {"error": str(e)}

    usage = sampler.update(stat_text)
    srows, snote = collect_sensors_rows()
    zones = read_thermal_zones()
    freqs = read_cpu_mhz()

    return {
        "cpu_usage": usage,
        "loadavg": read_loadavg(),
        "sensors": srows,
        "sensors_note": snote,
        "thermal_zones": zones,
        "cpufreq": freqs,
    }
