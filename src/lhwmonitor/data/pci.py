"""Graphics devices: lspci and optional nvidia-smi."""

from __future__ import annotations

import subprocess
from typing import Any


def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def lspci_vga() -> list[str]:
    code, out, _ = _run(["lspci", "-nn"])
    if code != 0:
        return []
    lines = []
    for line in out.splitlines():
        low = line.lower()
        if "vga" in low or "3d" in low or "display" in low:
            lines.append(line.strip())
    return lines


def nvidia_smi_brief() -> dict[str, str] | None:
    code, out, _ = _run(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"],
        timeout=5,
    )
    if code != 0 or not out.strip():
        return None
    first = out.strip().splitlines()[0]
    parts = [p.strip() for p in first.split(",")]
    if len(parts) >= 2:
        return {"gpu": parts[0], "driver": parts[1]}
    return {"gpu": first, "driver": ""}


def collect_graphics_info() -> dict[str, Any]:
    from lhwmonitor.data.gpu_mem import collect_gpu_memory_for_info

    return {
        "lspci": lspci_vga(),
        "nvidia_smi": nvidia_smi_brief(),
        "gpu_memory": collect_gpu_memory_for_info(),
    }
