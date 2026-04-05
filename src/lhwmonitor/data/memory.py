"""Memory info from /proc/meminfo."""

from __future__ import annotations

from pathlib import Path


def read_meminfo() -> dict[str, str]:
    path = Path("/proc/meminfo")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    out: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, rest = line.split(":", 1)
        key = k.strip()
        parts = rest.split()
        if parts:
            out[key] = parts[0] + (" " + " ".join(parts[1:]) if len(parts) > 1 else "")
        else:
            out[key] = ""
    return out


def collect_memory_info() -> dict[str, Any]:
    raw = read_meminfo()
    keys = ("MemTotal", "MemFree", "MemAvailable", "Buffers", "Cached", "SwapTotal", "SwapFree")
    return {k: raw.get(k, "") for k in keys if k in raw} or raw
