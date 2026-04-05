"""Main window: Info and Monitor tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QRunnable, QThreadPool, QTimer, Qt, Signal, QObject
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
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
    QVBoxLayout,
    QWidget,
)

from lhwmonitor import __version__
from lhwmonitor.data.info_bundle import collect_info_bundle
from lhwmonitor.data.monitor_snapshot import collect_monitor_snapshot
from lhwmonitor.data.proc_stat import CpuUsageSampler


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
        self._monitor_table: QTableWidget | None = None
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
            box = QGroupBox(title)
            form = QFormLayout()
            section = bundle.get(key, {})
            pairs = _flatten_info(section)
            if not pairs:
                form.addRow(QLabel("(no data)"))
            else:
                for label, value in pairs[:200]:
                    form.addRow(label, QLabel(value))
                if len(pairs) > 200:
                    form.addRow(QLabel(f"... and {len(pairs) - 200} more rows omitted"))
            box.setLayout(form)
            root_layout.addWidget(box)
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

        self._monitor_table = QTableWidget(0, 3)
        self._monitor_table.setHorizontalHeaderLabels(["Category", "Item", "Value"])
        self._monitor_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self._monitor_table)
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
            return
        if self._monitor_note:
            note = data.get("sensors_note") or ""
            self._monitor_note.setText(note)
        self._fill_monitor_table(data)

    def _fill_monitor_table(self, data: dict[str, Any]) -> None:
        table = self._monitor_table
        if table is None:
            return
        rows: list[tuple[str, str, str]] = []

        la = data.get("loadavg") or ""
        if la:
            parts = la.split()
            if len(parts) >= 3:
                rows.append(("Load", "1 min", parts[0]))
                rows.append(("Load", "5 min", parts[1]))
                rows.append(("Load", "15 min", parts[2]))

        usage = data.get("cpu_usage")
        if usage is None:
            rows.append(("CPU", "usage %", "(calibrating…)"))
        else:
            for name in sorted(usage.keys(), key=lambda x: (x != "cpu", x)):
                rows.append(("CPU", name, f"{usage[name]:.1f}"))

        for z in data.get("thermal_zones") or []:
            zm = z.get("temp_millideg", "")
            label = z.get("type") or z.get("zone", "")
            temp = ""
            if zm.isdigit():
                temp = f"{int(zm) / 1000.0:.1f} °C"
            rows.append(("Thermal", label or z.get("zone", ""), temp or zm))

        for s in data.get("sensors") or []:
            chip = s.get("chip", "")
            lab = s.get("label", "")
            val = s.get("value", "")
            unit = s.get("unit", "")
            item = f"{lab}"
            v = val + (f" {unit}" if unit else "")
            rows.append(("Sensors", f"{chip} — {item}", v))

        for f in data.get("cpufreq") or []:
            cpu = f.get("cpu", "")
            mhz = f.get("mhz", "")
            gov = f.get("governor", "")
            extra = f" ({gov})" if gov else ""
            rows.append(("Frequency", cpu, (mhz + " MHz" if mhz else "") + extra))

        table.setRowCount(len(rows))
        for i, (c, it, v) in enumerate(rows):
            table.setItem(i, 0, QTableWidgetItem(c))
            table.setItem(i, 1, QTableWidgetItem(it))
            table.setItem(i, 2, QTableWidgetItem(v))

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
