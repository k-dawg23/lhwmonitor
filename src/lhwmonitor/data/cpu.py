"""CPU identification from lscpu and /proc/cpuinfo."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return default


def read_proc_cpuinfo() -> dict[str, str]:
    text = _read_text(Path("/proc/cpuinfo"))
    out: dict[str, str] = {}
    model_parts: list[str] = []
    for line in text.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        k, v = k.strip(), v.strip()
        if k == "model name":
            model_parts.append(v)
        elif k == "vendor_id" and "vendor" not in out:
            out["vendor"] = v
        elif k == "cpu family" and "cpu_family" not in out:
            out["cpu_family"] = v
        elif k == "model" and "model_num" not in out:
            out["model_num"] = v
        elif k == "stepping" and "stepping" not in out:
            out["stepping"] = v
        elif k == "microcode" and "microcode" not in out:
            out["microcode"] = v
    if model_parts:
        out["model_name"] = model_parts[0]
    return out


def read_lscpu_json() -> dict[str, Any] | None:
    try:
        raw = subprocess.run(
            ["lscpu", "-J"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if raw.returncode != 0 or not raw.stdout.strip():
        return None
    try:
        return json.loads(raw.stdout)
    except json.JSONDecodeError:
        return None


def read_lscpu_text() -> dict[str, str]:
    try:
        raw = subprocess.run(
            ["lscpu"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return {}
    if raw.returncode != 0:
        return {}
    kv: dict[str, str] = {}
    for line in raw.stdout.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        kv[k.strip()] = v.strip()
    return kv


def _flatten_lscpu_j(data: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    if "lscpu" not in data:
        return out
    for block in data["lscpu"]:
        if not isinstance(block, dict):
            continue
        field = block.get("field")
        data_v = block.get("data")
        if isinstance(field, str) and data_v is not None:
            out[field] = str(data_v).strip()
    return out


def collect_cpu_info() -> dict[str, Any]:
    """Return CPU section for Info tab."""
    info: dict[str, Any] = {"source": "lscpu+proc"}
    j = read_lscpu_json()
    if j:
        flat = _flatten_lscpu_j(j)
        info["lscpu"] = flat
        for key in (
            "Architecture",
            "CPU(s)",
            "On-line CPU(s) list",
            "Model name",
            "Thread(s) per core",
            "Core(s) per socket",
            "Socket(s)",
            "CPU max MHz",
            "CPU min MHz",
            "CPU(s) scaling MHz",
            "Caches (sum of all)",
        ):
            if key in flat:
                info[key.lower().replace(" ", "_").replace("(", "").replace(")", "")] = flat[key]
    else:
        info["lscpu_text"] = read_lscpu_text()

    cpuinfo = read_proc_cpuinfo()
    info["proc_cpuinfo"] = cpuinfo
    return info
