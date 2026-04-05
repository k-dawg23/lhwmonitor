"""Main window: Info and Monitor tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QRunnable, QThreadPool, QTimer, Qt, Signal, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
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
from lhwmonitor.data.monitor_snapshot import collect_monitor_snapshot
from lhwmonitor.data.proc_stat import CpuUsageSampler
from lhwmonitor.export_log import write_snapshot_csv, write_snapshot_json
from lhwmonitor.info_flatten import flatten_info
from lhwmonitor.monitor_rows import (
    build_monitor_rows,
    cpu_pad_width_from_sys_cpu_names,
    cpu_pad_width_from_usage_keys,
    cpu_usage_sort_key,
    cpufreq_entry_sort_key,
    label_cpu_usage,
    label_freq_cpu,
)
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
        self._setup_file_menu()

    def _setup_file_menu(self) -> None:
        save_act = QAction("Save snapshot…", self)
        save_act.setShortcut("Ctrl+S")
        save_act.setStatusTip("Save current Info + Monitor data as JSON or CSV")
        save_act.triggered.connect(self._save_snapshot)
        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(save_act)

    def _save_snapshot(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save snapshot",
            "",
            "JSON (*.json);;CSV (*.csv)",
        )
        if not path:
            return
        low = path.lower()
        if not low.endswith(".json") and not low.endswith(".csv"):
            if "CSV" in selected_filter.upper():
                path += ".csv"
            else:
                path += ".json"
        try:
            info = collect_info_bundle()
            monitor = collect_monitor_snapshot(self._sampler)
        except Exception as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        try:
            if path.lower().endswith(".csv"):
                write_snapshot_csv(path, info, monitor, __version__)
            else:
                write_snapshot_json(path, info, monitor, __version__)
        except OSError as e:
            QMessageBox.warning(self, "Save failed", str(e))
            return
        self._status.setText(f"Saved: {path}")

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
            pairs = flatten_info(section)
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
        rows = build_monitor_rows(data)

        def _fill(table: QTableWidget, key: str) -> None:
            r = rows[key]
            table.setRowCount(len(r))
            for i, (a, b) in enumerate(r):
                table.setItem(i, 0, QTableWidgetItem(a))
                table.setItem(i, 1, QTableWidgetItem(b))

        _fill(self._monitor_tables["Load"], "Load")
        _fill(self._monitor_tables["Memory"], "Memory")
        _fill(self._monitor_tables["CPU"], "CPU")
        _fill(self._monitor_tables["Thermal"], "Thermal")
        _fill(self._monitor_tables["Sensors"], "Sensors")
        _fill(self._monitor_tables["Frequency"], "Frequency")

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
            pad_u = cpu_pad_width_from_usage_keys(ukeys)
            for i, name in enumerate(sorted(ukeys, key=cpu_usage_sort_key)):
                if i >= 16:
                    break
                cpu_samples[label_cpu_usage(name, pad_u)] = float(usage[name])
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
        freqs = sorted(data.get("cpufreq") or [], key=cpufreq_entry_sort_key)
        mhz_list: list[float] = []
        for f in freqs:
            mhz = f.get("mhz", "")
            if mhz.isdigit():
                mhz_list.append(float(mhz))
        if mhz_list:
            freq_samples["average"] = sum(mhz_list) / len(mhz_list)
        fpad = cpu_pad_width_from_sys_cpu_names([str(f.get("cpu", "")) for f in freqs])
        for i, f in enumerate(freqs[:8]):
            cpu = f.get("cpu", "")
            mhz = f.get("mhz", "")
            if cpu and mhz.isdigit():
                label = label_freq_cpu(str(cpu), fpad)
                freq_samples[label] = float(mhz)
        self._monitor_charts["Frequency"].record_tick(freq_samples)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
