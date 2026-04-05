"""CPU frequency from cpufreq sysfs."""

from __future__ import annotations

from pathlib import Path


def read_cpu_mhz() -> list[dict[str, str]]:
    """Per-logical-cpu scaling_cur_freq in kHz -> MHz string."""
    cpus = sorted(Path("/sys/devices/system/cpu").glob("cpu[0-9]*"))
    out: list[dict[str, str]] = []
    for cpu in cpus:
        cur = cpu / "cpufreq" / "scaling_cur_freq"
        gov = cpu / "cpufreq" / "scaling_governor"
        khz = ""
        g = ""
        try:
            if cur.is_file():
                khz = cur.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        try:
            if gov.is_file():
                g = gov.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            pass
        mhz = ""
        if khz.isdigit():
            mhz = f"{int(khz) / 1000.0:.0f}"
        out.append({"cpu": cpu.name, "mhz": mhz, "khz": khz, "governor": g})
    return out
