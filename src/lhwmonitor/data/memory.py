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


def _kb_int(raw: dict[str, str], key: str) -> int | None:
    v = raw.get(key)
    if v is None or not str(v).strip():
        return None
    try:
        return int(str(v).split()[0])
    except ValueError:
        return None


def collect_system_ram_snapshot() -> dict[str, Any]:
    """Live RAM usage for Monitor tab (values in kB from /proc/meminfo unless noted)."""
    raw = read_meminfo()
    total = _kb_int(raw, "MemTotal")
    avail = _kb_int(raw, "MemAvailable")
    free = _kb_int(raw, "MemFree")
    swap_t = _kb_int(raw, "SwapTotal")
    swap_f = _kb_int(raw, "SwapFree")
    out: dict[str, Any] = {}
    if total is not None:
        out["mem_total_kb"] = total
    if avail is not None:
        out["mem_available_kb"] = avail
    if free is not None:
        out["mem_free_kb"] = free
    if total is not None and avail is not None:
        used = max(0, total - avail)
        out["mem_used_kb"] = used
        out["mem_used_percent"] = round(100.0 * used / total, 1) if total > 0 else 0.0
    if swap_t is not None:
        out["swap_total_kb"] = swap_t
    if swap_f is not None:
        out["swap_free_kb"] = swap_f
    if swap_t is not None and swap_f is not None and swap_t > 0:
        su = max(0, swap_t - swap_f)
        out["swap_used_kb"] = su
        out["swap_used_percent"] = round(100.0 * su / swap_t, 1)
    return out


def format_kb_gib(kb: int | float) -> str:
    gib = float(kb) / (1024 * 1024)
    return f"{gib:.2f} GiB"
