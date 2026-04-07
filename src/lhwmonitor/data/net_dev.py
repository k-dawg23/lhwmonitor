"""Network interface RX/TX rates from /proc/net/dev."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any


_prev: tuple[float, dict[str, tuple[int, int]]] | None = None


def _read_net_dev() -> dict[str, tuple[int, int]]:
    """Return iface -> (rx_bytes, tx_bytes)."""
    try:
        text = Path("/proc/net/dev").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    lines = [ln.strip() for ln in text.splitlines() if ":" in ln]
    out: dict[str, tuple[int, int]] = {}
    for ln in lines:
        iface, rest = ln.split(":", 1)
        parts = rest.split()
        if len(parts) < 16:
            continue
        try:
            rx = int(parts[0])
            tx = int(parts[8])
        except ValueError:
            continue
        out[iface.strip()] = (rx, tx)
    return out


def collect_net_rates_snapshot() -> dict[str, Any]:
    """Return per-interface rates (bytes/s) and a small summary.

    Uses a module-level previous sample. The UI prevents overlapping refreshes.
    """
    global _prev
    now = time.monotonic()
    cur = _read_net_dev()
    if not cur:
        return {"interfaces": [], "note": "No /proc/net/dev data."}
    if _prev is None:
        _prev = (now, cur)
        return {"interfaces": [], "note": "Calibrating network rates…"}
    prev_t, prev = _prev
    dt = max(1e-6, now - prev_t)
    rows: list[dict[str, Any]] = []
    for iface, (rx, tx) in cur.items():
        if iface not in prev:
            continue
        prx, ptx = prev[iface]
        rx_rate = max(0.0, (rx - prx) / dt)
        tx_rate = max(0.0, (tx - ptx) / dt)
        rows.append(
            {
                "iface": iface,
                "rx_bytes_per_s": rx_rate,
                "tx_bytes_per_s": tx_rate,
            }
        )
    rows.sort(key=lambda r: (r["iface"] != "lo", r["iface"]))
    _prev = (now, cur)
    return {"interfaces": rows}

