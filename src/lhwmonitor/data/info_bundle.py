"""Aggregate static Info tab data."""

from __future__ import annotations

from typing import Any

from lhwmonitor.data.cpu import collect_cpu_info
from lhwmonitor.data.dmi import collect_dmi_info
from lhwmonitor.data.memory import collect_memory_info
from lhwmonitor.data.pci import collect_graphics_info


def collect_info_bundle() -> dict[str, Any]:
    return {
        "cpu": collect_cpu_info(),
        "memory": collect_memory_info(),
        "graphics": collect_graphics_info(),
        "dmi": collect_dmi_info(),
    }
