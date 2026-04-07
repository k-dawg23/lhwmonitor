"""Disk SMART summary via smartctl (opt-in, may require root)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def _run(cmd: list[str], timeout: float = 8.0) -> tuple[int, str, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
        return p.returncode, p.stdout or "", p.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:
        return -1, "", str(e)


def _list_block_devices() -> list[str]:
    """Return candidate /dev names (sda, nvme0n1, ...)."""
    out: list[str] = []
    for p in sorted(Path("/sys/block").glob("*")):
        name = p.name
        if name.startswith(("loop", "ram", "dm-")):
            continue
        out.append(name)
    return out


def _parse_smart_summary(text: str) -> dict[str, Any]:
    d: dict[str, Any] = {}
    m = re.search(r"Device Model:\\s*(.+)", text)
    if not m:
        m = re.search(r"Model Number:\\s*(.+)", text)
    if m:
        d["model"] = m.group(1).strip()
    m = re.search(r"Serial Number:\\s*(.+)", text)
    if m:
        d["serial"] = m.group(1).strip()
    m = re.search(r"SMART overall-health self-assessment test result:\\s*(.+)", text)
    if m:
        d["health"] = m.group(1).strip()
    # Common SATA attribute line
    m = re.search(r"Temperature_Celsius\\s+0x[0-9a-fA-F]+\\s+\\d+\\s+\\d+\\s+\\d+\\s+\\S+\\s+\\S+\\s+\\S+\\s+(\\d+)", text)
    if m:
        d["temp_c"] = int(m.group(1))
    # NVMe: "Temperature: 35 Celsius"
    m = re.search(r"Temperature:\\s*(\\d+)\\s*Celsius", text)
    if m:
        d["temp_c"] = int(m.group(1))
    return d


def collect_smart_snapshot() -> dict[str, Any]:
    """Opt-in snapshot.

    Enable by setting environment variable `LHW_MONITOR_ENABLE_SMART=1`.
    """
    if os.environ.get("LHW_MONITOR_ENABLE_SMART") != "1":
        return {"enabled": False, "devices": [], "note": "SMART disabled (set LHW_MONITOR_ENABLE_SMART=1)."}
    if not shutil.which("smartctl"):
        return {"enabled": True, "devices": [], "note": "`smartctl` not found (install smartmontools)."}

    devs: list[dict[str, Any]] = []
    for name in _list_block_devices():
        path = f"/dev/{name}"
        code, out, err = _run(["smartctl", "-a", path], timeout=10)
        if code != 0 and not out:
            # Permission issues are common; surface a short note.
            devs.append({"device": path, "error": (err or "smartctl failed").strip()})
            continue
        summary = _parse_smart_summary(out)
        summary["device"] = path
        devs.append(summary)
    return {"enabled": True, "devices": devs}

