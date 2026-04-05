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

        for cat in ("Load", "CPU", "Thermal", "Sensors", "Frequency"):
            sec = _CollapsibleSection(cat)
            table = QTableWidget(0, 2)
            table.setHorizontalHeaderLabels(["Item", "Value"])
            table.horizontalHeader().setStretchLastSection(True)
            table.setMinimumHeight(80)
            sec.body_layout().addWidget(table)
            vbox.addWidget(sec)
            self._monitor_tables[cat] = table

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
            return
        if self._monitor_note:
            note = data.get("sensors_note") or ""
            self._monitor_note.setText(note)
        self._fill_monitor_tables(data)

    def _fill_monitor_tables(self, data: dict[str, Any]) -> None:
        load_rows: list[tuple[str, str]] = []
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

        usage = data.get("cpu_usage")
        if usage is None:
            cpu_rows.append(("usage %", "(calibrating…)"))
        else:
            for name in sorted(usage.keys(), key=lambda x: (x != "cpu", x)):
                cpu_rows.append((name, f"{usage[name]:.1f}"))

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

        for f in data.get("cpufreq") or []:
            cpu = f.get("cpu", "")
            mhz = f.get("mhz", "")
            gov = f.get("governor", "")
            extra = f" ({gov})" if gov else ""
            freq_rows.append((cpu, (mhz + " MHz" if mhz else "") + extra))

        def _fill(table: QTableWidget, rows: list[tuple[str, str]]) -> None:
            table.setRowCount(len(rows))
            for i, (a, b) in enumerate(rows):
                table.setItem(i, 0, QTableWidgetItem(a))
                table.setItem(i, 1, QTableWidgetItem(b))

        _fill(self._monitor_tables["Load"], load_rows)
        _fill(self._monitor_tables["CPU"], cpu_rows)
        _fill(self._monitor_tables["Thermal"], thermal_rows)
        _fill(self._monitor_tables["Sensors"], sensor_rows)
        _fill(self._monitor_tables["Frequency"], freq_rows)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
