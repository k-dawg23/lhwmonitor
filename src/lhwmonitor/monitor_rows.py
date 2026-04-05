"""Build Monitor tab table rows from a snapshot dict (shared UI + export)."""

from __future__ import annotations

from typing import Any

from lhwmonitor.data.memory import format_kb_gib


def cpu_usage_sort_key(name: str) -> tuple[int, int, str]:
    if name == "cpu":
        return (-1, 0, "")
    if name.startswith("cpu") and name[3:].isdigit():
        return (0, int(name[3:]), name)
    return (1, 0, name)


def _cpu_pad_width_from_indices(indices: list[int]) -> int:
    if not indices:
        return 2
    return max(2, len(str(max(indices))))


def cpu_pad_width_from_usage_keys(keys: list[str]) -> int:
    idx: list[int] = []
    for k in keys:
        if k.startswith("cpu") and k[3:].isdigit():
            idx.append(int(k[3:]))
    return _cpu_pad_width_from_indices(idx)


def cpu_pad_width_from_sys_cpu_names(names: list[str]) -> int:
    idx: list[int] = []
    for n in names:
        if n.startswith("cpu") and len(n) > 3 and n[3:].isdigit():
            idx.append(int(n[3:]))
    return _cpu_pad_width_from_indices(idx)


def label_cpu_usage(name: str, width: int) -> str:
    if name == "cpu":
        return "cpu"
    if name.startswith("cpu") and name[3:].isdigit():
        return f"cpu{int(name[3:]):0{width}d}"
    return name


def label_freq_cpu(cpu_name: str, width: int) -> str:
    if cpu_name.startswith("cpu") and len(cpu_name) > 3 and cpu_name[3:].isdigit():
        return f"cpu{int(cpu_name[3:]):0{width}d}"
    return cpu_name


def cpufreq_entry_sort_key(entry: dict[str, Any]) -> tuple[int, str]:
    c = entry.get("cpu", "")
    if isinstance(c, str) and c.startswith("cpu") and c[3:].isdigit():
        return (int(c[3:]), c)
    return (10**9, str(c))


def build_monitor_rows(data: dict[str, Any]) -> dict[str, list[tuple[str, str]]]:
    load_rows: list[tuple[str, str]] = []
    memory_rows: list[tuple[str, str]] = []
    cpu_rows: list[tuple[str, str]] = []
    thermal_rows: list[tuple[str, str]] = []
    sensor_rows: list[tuple[str, str]] = []
    freq_rows: list[tuple[str, str]] = []

    la = data.get("loadavg") or ""
    if la:
        parts = la.split()
        if len(parts) >= 3:
            load_rows.append(("1 min", parts[0]))
            load_rows.append(("5 min", parts[1]))
            load_rows.append(("15 min", parts[2]))

    ram = data.get("ram") or {}
    if ram.get("mem_total_kb") is not None:
        memory_rows.append(("RAM total", format_kb_gib(ram["mem_total_kb"])))
    if ram.get("mem_available_kb") is not None:
        memory_rows.append(("RAM available", format_kb_gib(ram["mem_available_kb"])))
    if ram.get("mem_used_kb") is not None:
        memory_rows.append(("RAM used (est.)", format_kb_gib(ram["mem_used_kb"])))
    if ram.get("mem_used_percent") is not None:
        memory_rows.append(("RAM used %", f"{ram['mem_used_percent']:.1f}%"))
    st = ram.get("swap_total_kb")
    if st is not None and st > 0:
        memory_rows.append(("Swap total", format_kb_gib(st)))
        if ram.get("swap_used_kb") is not None:
            memory_rows.append(("Swap used", format_kb_gib(ram["swap_used_kb"])))
        if ram.get("swap_used_percent") is not None:
            memory_rows.append(("Swap used %", f"{ram['swap_used_percent']:.1f}%"))

    for g in data.get("gpu_memory") or []:
        src = str(g.get("source", ""))
        idx = str(g.get("gpu_index", ""))
        name = str(g.get("name", ""))[:48]
        label = f"GPU {idx} ({src})"
        if name:
            label = f"{label} {name}"
        if g.get("dedicated_total_mib") is not None:
            memory_rows.append((f"{label} VRAM total", f"{g['dedicated_total_mib']:.0f} MiB"))
        if g.get("dedicated_used_mib") is not None:
            memory_rows.append((f"{label} VRAM used", f"{g['dedicated_used_mib']:.0f} MiB"))
        if g.get("dedicated_free_mib") is not None:
            memory_rows.append((f"{label} VRAM free", f"{g['dedicated_free_mib']:.0f} MiB"))
        if g.get("dedicated_used_percent") is not None:
            memory_rows.append((f"{label} VRAM used %", f"{g['dedicated_used_percent']:.1f}%"))
        if g.get("dynamic_used_mib") is not None:
            memory_rows.append((f"{label} dynamic (shared) used", f"{g['dynamic_used_mib']:.0f} MiB"))

    if not memory_rows:
        memory_rows.append(("(no data)", "—"))

    usage = data.get("cpu_usage")
    if usage is None:
        cpu_rows.append(("usage %", "(calibrating…)"))
    else:
        ukeys = list(usage.keys())
        pad = cpu_pad_width_from_usage_keys(ukeys)
        for name in sorted(ukeys, key=cpu_usage_sort_key):
            cpu_rows.append((label_cpu_usage(name, pad), f"{usage[name]:.1f}"))

    for z in data.get("thermal_zones") or []:
        zm = z.get("temp_millideg", "")
        label = z.get("type") or z.get("zone", "")
        temp = ""
        if zm.isdigit():
            temp = f"{int(zm) / 1000.0:.1f} °C"
        thermal_rows.append((label or z.get("zone", ""), temp or zm))

    for s in data.get("sensors") or []:
        chip = s.get("chip", "")
        lab = s.get("label", "")
        val = s.get("value", "")
        unit = s.get("unit", "")
        v = val + (f" {unit}" if unit else "")
        sensor_rows.append((f"{chip} — {lab}", v))

    freq_list = sorted(data.get("cpufreq") or [], key=cpufreq_entry_sort_key)
    fcpus = [str(f.get("cpu", "")) for f in freq_list]
    fpad = cpu_pad_width_from_sys_cpu_names(fcpus)
    for f in freq_list:
        cpu = f.get("cpu", "")
        mhz = f.get("mhz", "")
        gov = f.get("governor", "")
        extra = f" ({gov})" if gov else ""
        label = label_freq_cpu(str(cpu), fpad) if cpu else ""
        freq_rows.append((label, (mhz + " MHz" if mhz else "") + extra))

    return {
        "Load": load_rows,
        "Memory": memory_rows,
        "CPU": cpu_rows,
        "Thermal": thermal_rows,
        "Sensors": sensor_rows,
        "Frequency": freq_rows,
    }
