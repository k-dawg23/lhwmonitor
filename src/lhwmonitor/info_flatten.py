"""Flatten nested info dicts for display and export."""

from __future__ import annotations

from typing import Any


def flatten_info(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k in sorted(obj.keys(), key=str):
            p = f"{prefix}{k}" if not prefix else f"{prefix} / {k}"
            rows.extend(flatten_info(obj[k], p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            rows.extend(flatten_info(item, f"{prefix}[{i}]"))
    else:
        rows.append((prefix or "value", str(obj)))
    return rows
