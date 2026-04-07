"""Manual snapshot export (JSON and CSV). Continuous logging may be added later."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from lhwmonitor.info_flatten import flatten_info
from lhwmonitor.monitor_rows import build_monitor_rows

INFO_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Processor", "cpu"),
    ("Memory", "memory"),
    ("System (DMI)", "dmi"),
    ("Graphics", "graphics"),
)


def build_snapshot_document(
    info_bundle: dict[str, Any],
    monitor_snapshot: dict[str, Any],
    app_version: str,
) -> dict[str, Any]:
    return {
        "lhwmonitor_version": app_version,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "export_kind": "manual_snapshot",
        "info": info_bundle,
        "monitor": monitor_snapshot,
    }


def write_snapshot_json(
    path: str | Path,
    info_bundle: dict[str, Any],
    monitor_snapshot: dict[str, Any],
    app_version: str,
) -> None:
    doc = build_snapshot_document(info_bundle, monitor_snapshot, app_version)
    p = Path(path)
    p.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_snapshot_ndjson(
    path: str | Path,
    info_bundle: dict[str, Any],
    monitor_snapshot: dict[str, Any],
    app_version: str,
) -> None:
    """Write one NDJSON record (single-line JSON object)."""
    doc = build_snapshot_document(info_bundle, monitor_snapshot, app_version)
    p = Path(path)
    p.write_text(json.dumps(doc, ensure_ascii=False) + "\n", encoding="utf-8")


def write_snapshot_csv(
    path: str | Path,
    info_bundle: dict[str, Any],
    monitor_snapshot: dict[str, Any],
    app_version: str,
) -> None:
    """CSV with proper quoting (stdlib csv)."""
    p = Path(path)
    with p.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["Section", "Item", "Value"])
        w.writerow(["meta", "lhwmonitor_version", app_version])
        w.writerow(["meta", "exported_at", datetime.now(timezone.utc).isoformat()])
        snote = monitor_snapshot.get("sensors_note")
        if snote:
            w.writerow(["meta", "sensors_note", str(snote)])
        for title, key in INFO_SECTIONS:
            section = info_bundle.get(key, {})
            for label, val in flatten_info(section):
                w.writerow([f"Info: {title}", label, val])
        rows_by_sec = build_monitor_rows(monitor_snapshot)
        for sec_name in ("Load", "Memory", "CPU", "Thermal", "Sensors", "Frequency"):
            for item, val in rows_by_sec.get(sec_name, ()):
                w.writerow([f"Monitor: {sec_name}", item, val])
