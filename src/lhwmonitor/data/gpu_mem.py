"""GPU memory via vendor tools (NVIDIA, AMD) when available."""

from __future__ import annotations

import re
import shutil
import subprocess
from typing import Any


def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def nvidia_smi_gpu_memory_rows() -> list[dict[str, Any]]:
    """Per-GPU VRAM from nvidia-smi (MiB). Dedicated = framebuffer; dynamic = shared system RAM if reported."""
    if not shutil.which("nvidia-smi"):
        return []
    code, out, _ = _run(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits",
        ],
        timeout=8,
    )
    if code != 0 or not out.strip():
        return []
    rows: list[dict[str, Any]] = []
    for line in out.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 5:
            continue
        try:
            idx, name = parts[0], parts[1]
            total_m = float(parts[2])
            used_m = float(parts[3])
            free_m = float(parts[4])
        except (ValueError, IndexError):
            continue
        used_pct = round(100.0 * used_m / total_m, 1) if total_m > 0 else 0.0
        row: dict[str, Any] = {
            "source": "nvidia-smi",
            "gpu_index": idx,
            "name": name,
            "dedicated_total_mib": total_m,
            "dedicated_used_mib": used_m,
            "dedicated_free_mib": free_m,
            "dedicated_used_percent": used_pct,
        }
        rows.append(row)
    return rows


def _nvidia_shared_memory_mib(gpu_index: str) -> float | None:
    """Parse 'Shared Memory' / system RAM used by GPU from nvidia-smi -q (MiB), if present."""
    code, out, _ = _run(["nvidia-smi", "-i", gpu_index, "-q", "-d", "MEMORY"], timeout=8)
    if code != 0 or not out:
        return None
    # Typical: "Shared Memory Usage" block or "System Memory Usage"
    for pat in (
        r"Shared Memory[^\n]*\n[^\n]*Used\s*:\s*(\d+)\s*MiB",
        r"System Memory Usage[^\n]*\n[^\n]*Used\s*:\s*(\d+)\s*MiB",
        r"Shared\s*:\s*(\d+)\s*MiB",
    ):
        m = re.search(pat, out, re.IGNORECASE | re.MULTILINE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def rocm_smi_gpu_memory_rows() -> list[dict[str, Any]]:
    """AMD VRAM via rocm-smi when available."""
    if not shutil.which("rocm-smi"):
        return []
    code, out, _ = _run(["rocm-smi", "--showmeminfo", "vram"], timeout=10)
    if code != 0 or not out:
        return []
    rows: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in out.splitlines():
        m = re.match(r"GPU\[(\d+)\]", line.strip())
        if m:
            if current:
                rows.append(_finalize_rocm_row(current))
            current = {"gpu_index": m.group(1), "source": "rocm-smi"}
            continue
        if not current:
            continue
        m = re.search(r"VRAM Total Memory \(B\):\s*(\d+)", line)
        if m:
            current["total_bytes"] = int(m.group(1))
        m = re.search(r"VRAM Total Used Memory \(B\):\s*(\d+)", line)
        if m:
            current["used_bytes"] = int(m.group(1))
    if current:
        rows.append(_finalize_rocm_row(current))
    return rows


def _finalize_rocm_row(d: dict[str, Any]) -> dict[str, Any]:
    total_b = d.get("total_bytes", 0)
    used_b = d.get("used_bytes", 0)
    total_m = total_b / (1024 * 1024) if total_b else 0.0
    used_m = used_b / (1024 * 1024) if used_b else 0.0
    free_m = max(0.0, total_m - used_m)
    pct = round(100.0 * used_m / total_m, 1) if total_m > 0 else 0.0
    return {
        "source": "rocm-smi",
        "gpu_index": str(d.get("gpu_index", "")),
        "name": f"GPU {d.get('gpu_index', '')}",
        "dedicated_total_mib": round(total_m, 1),
        "dedicated_used_mib": round(used_m, 1),
        "dedicated_free_mib": round(free_m, 1),
        "dedicated_used_percent": pct,
    }


def collect_gpu_memory_for_info() -> dict[str, Any]:
    """Static Info tab: all sources we can query (includes slow dynamic/shared query for NVIDIA)."""
    nvidia = nvidia_smi_gpu_memory_rows()
    for row in nvidia:
        dyn = _nvidia_shared_memory_mib(str(row["gpu_index"]))
        if dyn is not None:
            row["dynamic_used_mib"] = dyn
    amd = rocm_smi_gpu_memory_rows()
    out: dict[str, Any] = {}
    if nvidia:
        out["nvidia"] = nvidia
    if amd:
        out["amd"] = amd
    if not out:
        out["note"] = "No GPU memory data (install NVIDIA or AMD drivers/tools, or use a supported GPU)."
    return out


def collect_gpu_memory_for_monitor() -> list[dict[str, Any]]:
    """Single refresh: combined list for Monitor tab (NVIDIA first, then AMD)."""
    return nvidia_smi_gpu_memory_rows() + rocm_smi_gpu_memory_rows()
