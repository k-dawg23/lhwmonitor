"""Main window: Info and Monitor tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QRunnable, QThreadPool, QTimer, Qt, Signal, QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from lhwmonitor import __version__
from lhwmonitor.data.info_bundle import collect_info_bundle
from lhwmonitor.data.memory import format_kb_gib
from lhwmonitor.data.monitor_snapshot import collect_monitor_snapshot
from lhwmonitor.data.proc_stat import CpuUsageSampler
from lhwmonitor.ui.monitor_trend_chart import RollingTrendChart


class _MonitorBridge(QObject):
    """Cross-thread signal for monitor snapshot dict."""

    result = Signal(dict)


class _MonitorRunnable(QRunnable):
    def __init__(self, sampler: CpuUsageSampler, bridge: _MonitorBridge) -> None:
        super().__init__()
        self._sampler = sampler
        self._bridge = bridge

    def run(self) -> None:
        try:
            data = collect_monitor_snapshot(self._sampler)
            self._bridge.result.emit(data)
        except Exception as e:
            self._bridge.result.emit({"error": str(e)})


class _CollapsibleSection(QWidget):
    """Section with + / − toggle to show or hide body content."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._body = QWidget()
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(8, 0, 0, 0)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        header = QHBoxLayout()
        self._btn = QToolButton()
        self._btn.setText("−")
        self._btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self._btn.setCheckable(True)
        self._btn.setChecked(True)
        self._btn.setFixedWidth(28)
        self._btn.setToolTip("Click to expand or hide this section")
        title_lbl = QLabel(f"<b>{title}</b>")
        header.addWidget(self._btn)
        header.addWidget(title_lbl)
        header.addStretch()
        outer.addLayout(header)
        outer.addWidget(self._body)
        self._btn.toggled.connect(self._on_toggled)

    def _on_toggled(self, expanded: bool) -> None:
        self._body.setVisible(expanded)
        self._btn.setText("−" if expanded else "+")

    def body_layout(self) -> QVBoxLayout:
        return self._body_layout


def _flatten_info(obj: Any, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k in sorted(obj.keys(), key=str):
            p = f"{prefix}{k}" if not prefix else f"{prefix} / {k}"
            rows.extend(_flatten_info(obj[k], p))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            rows.extend(_flatten_info(item, f"{prefix}[{i}]"))
    else:
        rows.append((prefix or "value", str(obj)))
    return rows


def _cpu_usage_sort_key(name: str) -> tuple[int, int, str]:
    """Aggregate `cpu` first, then cpu0, cpu1, … by numeric index."""
    if name == "cpu":
        return (-1, 0, "")
    if name.startswith("cpu") and name[3:].isdigit():
        return (0, int(name[3:]), name)
    return (1, 0, name)


def _cpu_pad_width_from_indices(indices: list[int]) -> int:
    if not indices:
        return 2
    return max(2, len(str(max(indices))))


def _cpu_pad_width_from_usage_keys(keys: list[str]) -> int:
    idx: list[int] = []
    for k in keys:
        if k.startswith("cpu") and k[3:].isdigit():
            idx.append(int(k[3:]))
    return _cpu_pad_width_from_indices(idx)


def _cpu_pad_width_from_sys_cpu_names(names: list[str]) -> int:
    idx: list[int] = []
    for n in names:
        if n.startswith("cpu") and len(n) > 3 and n[3:].isdigit():
            idx.append(int(n[3:]))
    return _cpu_pad_width_from_indices(idx)


def _label_cpu_usage(name: str, width: int) -> str:
    if name == "cpu":
        return "cpu"
    if name.startswith("cpu") and name[3:].isdigit():
        return f"cpu{int(name[3:]):0{width}d}"
    return name


def _label_freq_cpu(cpu_name: str, width: int) -> str:
    if cpu_name.startswith("cpu") and len(cpu_name) > 3 and cpu_name[3:].isdigit():
        return f"cpu{int(cpu_name[3:]):0{width}d}"
    return cpu_name


def _cpufreq_entry_sort_key(entry: dict[str, Any]) -> tuple[int, str]:
    c = entry.get("cpu", "")
    if isinstance(c, str) and c.startswith("cpu") and c[3:].isdigit():
        return (int(c[3:]), c)
    return (10**9, str(c))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"lhwmonitor v{__version__}")
        self.resize(920, 640)

        self._sampler = CpuUsageSampler()
        self._bridge = _MonitorBridge()
        self._bridge.result.connect(self._on_monitor_data, Qt.QueuedConnection)
        self._pool = QThreadPool.globalInstance()

        self._info_root: QWidget | None = None
        self._monitor_tables: dict[str, QTableWidget] = {}
        self._monitor_charts: dict[str, RollingTrendChart] = {}
        self._monitor_note: QLabel | None = None
        self._paused = False

        tabs = QTabWidget()
        tabs.addTab(self._make_info_tab(), "Info")
        tabs.addTab(self._make_monitor_tab(), "Monitor")
        self.setCentralWidget(tabs)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status = QLabel("Ready")
        sb.addWidget(self._status, 1)

        self._timer = QTimer(self)
        self._timer.timeout.connect(lambda: self._request_monitor_fetch(False))
        self._timer.setInterval(2000)

        self._reload_info()
        self._request_monitor_fetch()
        self._timer.start()

    def _make_info_tab(self) -> QWidget:
        outer = QWidget()
        layout = QVBoxLayout(outer)

        btn_row = QHBoxLayout()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self._reload_info)
        btn_row.addWidget(refresh)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._info_root = QWidget()
        scroll.setWidget(self._info_root)
        layout.addWidget(scroll)
        return outer

    def _reload_info(self) -> None:
        if self._info_root is None:
            return
        try:
            bundle = collect_info_bundle()
        except Exception as e:
            QMessageBox.warning(self, "Info", f"Failed to read hardware info:\n{e}")
            return
        root_layout = self._info_root.layout()
        if root_layout is not None:
            while root_layout.count():
                item = root_layout.takeAt(0)
                w = item.widget()
                if w is not None:
                    w.deleteLater()
        else:
            root_layout = QVBoxLayout(self._info_root)

        for title, key in (
            ("Processor", "cpu"),
            ("Memory", "memory"),
            ("System (DMI)", "dmi"),
            ("Graphics", "graphics"),
        ):
            sec = _CollapsibleSection(title)
            inner = QWidget()
            form = QFormLayout(inner)
            section = bundle.get(key, {})
            pairs = _flatten_info(section)
            if not pairs:
                form.addRow(QLabel("(no data)"))
            else:
                for label, value in pairs[:200]:
                    form.addRow(label, QLabel(value))
                if len(pairs) > 200:
                    form.addRow(QLabel(f"... and {len(pairs) - 200} more rows omitted"))
            sec.body_layout().addWidget(inner)
            root_layout.addWidget(sec)
        root_layout.addStretch()

    def _make_monitor_tab(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)

        controls = QHBoxLayout()
        self._pause_cb = QCheckBox("Pause")
        self._pause_cb.toggled.connect(self._on_pause)
        controls.addWidget(self._pause_cb)
        controls.addWidget(QLabel("Interval (s):"))
        self._interval = QSpinBox()
        self._interval.setRange(1, 60)
        self._interval.setValue(2)
        self._interval.valueChanged.connect(self._on_interval_changed)
        controls.addWidget(self._interval)
        refresh = QPushButton("Refresh now")
        refresh.clicked.connect(lambda: self._request_monitor_fetch(True))
        controls.addWidget(refresh)
        controls.addStretch()
        layout.addLayout(controls)

        self._monitor_note = QLabel("")
        self._monitor_note.setWordWrap(True)
        layout.addWidget(self._monitor_note)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)

        chart_titles = {
            "Load": ("Load average", "Load"),
            "Memory": ("Memory utilization", "%"),
            "CPU": ("CPU usage", "%"),
            "Thermal": ("Thermal zones", "°C"),
            "Sensors": ("Temperature sensors (°C)", "°C"),
            "Frequency": ("CPU frequency", "MHz"),
        }
        for cat in ("Load", "Memory", "CPU", "Thermal", "Sensors", "Frequency"):
            sec = _CollapsibleSection(cat)
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(["Item", "Value"])
            table.horizontalHeader().setStretchLastSection(True)
            table.setMinimumHeight(80)
            sec.body_layout().addWidget(table)
            ctitle, ylabel = chart_titles[cat]
            chart = RollingTrendChart(ctitle, ylabel, max_points=180)
            sec.body_layout().addWidget(chart)
            vbox.addWidget(sec)
            self._monitor_tables[cat] = table
            self._monitor_charts[cat] = chart

        vbox.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)
        return w

    def _on_pause(self, checked: bool) -> None:
        self._paused = checked
        self._set_status()

    def _on_interval_changed(self, v: int) -> None:
        self._timer.setInterval(max(1, v) * 1000)
        self._set_status()

    def _set_status(self) -> None:
        extra = "paused" if self._paused else f"every {self._interval.value()}s"
        self._status.setText(f"Monitor: {extra} | Last: {getattr(self, '_last_ts', '—')}")

    def _request_monitor_fetch(self, force: bool = False) -> None:
        if self._paused and not force:
            return
        self._pool.start(_MonitorRunnable(self._sampler, self._bridge))

    def _on_monitor_data(self, data: dict[str, Any]) -> None:
        self._last_ts = datetime.now().strftime("%H:%M:%S")
        self._set_status()
        if "error" in data:
            if self._monitor_note:
                self._monitor_note.setText(data["error"])
            for t in self._monitor_tables.values():
                t.setRowCount(0)
            for c in self._monitor_charts.values():
                c.reset()
            return
        if self._monitor_note:
            note = data.get("sensors_note") or ""
            self._monitor_note.setText(note)
        self._fill_monitor_tables(data)

    def _fill_monitor_tables(self, data: dict[str, Any]) -> None:
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
            pad = _cpu_pad_width_from_usage_keys(ukeys)
            for name in sorted(ukeys, key=_cpu_usage_sort_key):
                cpu_rows.append((_label_cpu_usage(name, pad), f"{usage[name]:.1f}"))

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

        freq_list = sorted(data.get("cpufreq") or [], key=_cpufreq_entry_sort_key)
        fcpus = [str(f.get("cpu", "")) for f in freq_list]
        fpad = _cpu_pad_width_from_sys_cpu_names(fcpus)
        for f in freq_list:
            cpu = f.get("cpu", "")
            mhz = f.get("mhz", "")
            gov = f.get("governor", "")
            extra = f" ({gov})" if gov else ""
            label = _label_freq_cpu(str(cpu), fpad) if cpu else ""
            freq_rows.append((label, (mhz + " MHz" if mhz else "") + extra))

        def _fill(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
            table.setRowCount(len(rows))
            for i, (a, b) in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(a))
                table.setItem(i, 1, QTableWidgetItem(b))

        _fill(self._monitor_tables["Load"], load_rows)
        _fill(self._monitor_tables["Memory"], memory_rows)
        _fill(self._monitor_tables["CPU"], cpu_rows)
        _fill(self._monitor_tables["Thermal"], thermal_rows)
        _fill(self._monitor_tables["Sensors"], sensor_rows)
        _fill(self._monitor_tables["Frequency"], freq_rows)

        self._update_monitor_charts(data)

    def _update_monitor_charts(self, data: dict[str, Any]) -> None:
        la = data.get("loadavg") or ""
        load_samples: dict[str, float | None] = {}
        if la:
            parts = la.split()
            if len(parts) >= 3:
                load_samples["1 min"] = float(parts[0])
                load_samples["5 min"] = float(parts[1])
                load_samples["15 min"] = float(parts[2])
        self._monitor_charts["Load"].record_tick(load_samples)

        ram = data.get("ram") or {}
        mem_samples: dict[str, float | None] = {}
        if ram.get("mem_used_percent") is not None:
            mem_samples["RAM %"] = float(ram["mem_used_percent"])
        for i, g in enumerate(data.get("gpu_memory") or []):
            if i >= 8:
                break
            pct = g.get("dedicated_used_percent")
            idx = str(g.get("gpu_index", ""))
            src = str(g.get("source", "?"))[:4]
            if pct is not None:
                mem_samples[f"GPU{idx} ({src}) VRAM %"] = float(pct)
        self._monitor_charts["Memory"].record_tick(mem_samples)

        usage = data.get("cpu_usage")
        cpu_samples: dict[str, float | None] = {}
        if usage is not None:
            ukeys = list(usage.keys())
            pad_u = _cpu_pad_width_from_usage_keys(ukeys)
            for i, name in enumerate(sorted(ukeys, key=_cpu_usage_sort_key)):
                if i >= 16:
                    break
                cpu_samples[_label_cpu_usage(name, pad_u)] = float(usage[name])
        self._monitor_charts["CPU"].record_tick(cpu_samples)

        thermal_samples: dict[str, float | None] = {}
        for i, z in enumerate(data.get("thermal_zones") or []):
            if i >= 8:
                break
            zm = z.get("temp_millideg", "")
            label = (z.get("type") or z.get("zone") or f"zone{i}")[:32]
            if zm.isdigit():
                thermal_samples[label] = int(zm) / 1000.0
        self._monitor_charts["Thermal"].record_tick(thermal_samples)

        sensor_samples: dict[str, float | None] = {}
        for s in data.get("sensors") or []:
            if len(sensor_samples) >= 8:
                break
            unit = (s.get("unit") or "").lower()
            lab = (s.get("label") or "").lower()
            if "°c" not in unit and "temp" not in lab and "°c" not in lab:
                continue
            raw = str(s.get("value", "")).strip().split()
            if not raw:
                continue
            try:
                v = float(raw[0])
            except ValueError:
                continue
            chip = (s.get("chip") or "chip")[:14]
            name = f"{chip}:{(s.get('label') or '?')[:22]}"
            sensor_samples[name] = v
        self._monitor_charts["Sensors"].record_tick(sensor_samples)

        freq_samples: dict[str, float | None] = {}
        freqs = sorted(data.get("cpufreq") or [], key=_cpufreq_entry_sort_key)
        mhz_list: list[float] = []
        for f in freqs:
            mhz = f.get("mhz", "")
            if mhz.isdigit():
                mhz_list.append(float(mhz))
        if mhz_list:
            freq_samples["average"] = sum(mhz_list) / len(mhz_list)
        fpad = _cpu_pad_width_from_sys_cpu_names([str(f.get("cpu", "")) for f in freqs])
        for i, f in enumerate(freqs[:8]):
            cpu = f.get("cpu", "")
            mhz = f.get("mhz", "")
            if cpu and mhz.isdigit():
                label = _label_freq_cpu(str(cpu), fpad)
                freq_samples[label] = float(mhz)
        self._monitor_charts["Frequency"].record_tick(freq_samples)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
