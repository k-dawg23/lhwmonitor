"""Main window: Info and Monitor tabs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import QRunnable, QSettings, QThreadPool, QTimer, Qt, Signal, QObject
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
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
from lhwmonitor.export_log import write_snapshot_csv, write_snapshot_json, write_snapshot_ndjson
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


class _AlertsDialog(QDialog):
    def __init__(
        self,
        enabled: bool,
        cpu_temp_c: float | None,
        ram_percent: float | None,
        vram_percent: float | None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Alerts")

        lay = QVBoxLayout(self)
        form = QFormLayout()

        self.enabled_cb = QCheckBox("Enable alerts")
        self.enabled_cb.setChecked(enabled)
        form.addRow(self.enabled_cb)

        self.cpu_cb = QCheckBox("CPU temperature threshold")
        self.cpu_cb.setChecked(cpu_temp_c is not None)
        self.cpu_spin = QDoubleSpinBox()
        self.cpu_spin.setRange(0, 150)
        self.cpu_spin.setSuffix(" °C")
        self.cpu_spin.setDecimals(0)
        self.cpu_spin.setValue(float(cpu_temp_c or 90.0))
        self.cpu_spin.setEnabled(self.cpu_cb.isChecked())
        self.cpu_cb.toggled.connect(self.cpu_spin.setEnabled)
        row = QHBoxLayout()
        row.addWidget(self.cpu_cb)
        row.addWidget(self.cpu_spin)
        form.addRow(row)

        self.ram_cb = QCheckBox("RAM usage threshold")
        self.ram_cb.setChecked(ram_percent is not None)
        self.ram_spin = QDoubleSpinBox()
        self.ram_spin.setRange(0, 100)
        self.ram_spin.setSuffix(" %")
        self.ram_spin.setDecimals(0)
        self.ram_spin.setValue(float(ram_percent or 90.0))
        self.ram_spin.setEnabled(self.ram_cb.isChecked())
        self.ram_cb.toggled.connect(self.ram_spin.setEnabled)
        row = QHBoxLayout()
        row.addWidget(self.ram_cb)
        row.addWidget(self.ram_spin)
        form.addRow(row)

        self.vram_cb = QCheckBox("GPU VRAM usage threshold")
        self.vram_cb.setChecked(vram_percent is not None)
        self.vram_spin = QDoubleSpinBox()
        self.vram_spin.setRange(0, 100)
        self.vram_spin.setSuffix(" %")
        self.vram_spin.setDecimals(0)
        self.vram_spin.setValue(float(vram_percent or 90.0))
        self.vram_spin.setEnabled(self.vram_cb.isChecked())
        self.vram_cb.toggled.connect(self.vram_spin.setEnabled)
        row = QHBoxLayout()
        row.addWidget(self.vram_cb)
        row.addWidget(self.vram_spin)
        form.addRow(row)

        lay.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def result_config(self) -> tuple[bool, float | None, float | None, float | None]:
        enabled = bool(self.enabled_cb.isChecked())
        cpu = float(self.cpu_spin.value()) if self.cpu_cb.isChecked() else None
        ram = float(self.ram_spin.value()) if self.ram_cb.isChecked() else None
        vram = float(self.vram_spin.value()) if self.vram_cb.isChecked() else None
        return enabled, cpu, ram, vram


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
        self._fetch_inflight = False

        # Chart controls (defaults are conservative)
        self._cpu_chart_max_series = 12
        self._sensor_chart_max_series = 8
        self._thermal_chart_max_series = 8
        self._freq_chart_max_series = 8
        self._gpu_chart_max_series = 4
        self._chart_range_mode = "Auto"  # Auto|Fixed

        # Alerts (manual, non-continuous): thresholds only
        self._alerts_enabled = False
        self._alert_cpu_temp_c: float | None = 90.0
        self._alert_ram_percent: float | None = 90.0
        self._alert_vram_percent: float | None = 90.0
        self._load_alert_settings()

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
        save_act.setStatusTip("Save current Info + Monitor data as JSON, CSV, or NDJSON")
        save_act.triggered.connect(self._save_snapshot)

        alerts_act = QAction("Alerts…", self)
        alerts_act.setStatusTip("Configure simple threshold alerts (manual)")
        alerts_act.triggered.connect(self._open_alerts_dialog)

        quit_act = QAction("Quit", self)
        quit_act.setShortcut("Ctrl+Q")
        quit_act.setStatusTip("Quit lhwmonitor")
        quit_act.triggered.connect(self.close)

        file_menu = self.menuBar().addMenu("&File")
        file_menu.addAction(save_act)
        file_menu.addSeparator()
        file_menu.addAction(alerts_act)
        file_menu.addSeparator()
        file_menu.addAction(quit_act)

    def _settings(self) -> QSettings:
        return QSettings()

    def _load_alert_settings(self) -> None:
        s = self._settings()
        self._alerts_enabled = bool(s.value("alerts/enabled", False, type=bool))
        self._alert_cpu_temp_c = s.value("alerts/cpu_temp_c", 90.0, type=float)
        self._alert_ram_percent = s.value("alerts/ram_percent", 90.0, type=float)
        self._alert_vram_percent = s.value("alerts/vram_percent", 90.0, type=float)
        # Allow disabling thresholds by storing None marker
        if s.value("alerts/cpu_enabled", True, type=bool) is False:
            self._alert_cpu_temp_c = None
        if s.value("alerts/ram_enabled", True, type=bool) is False:
            self._alert_ram_percent = None
        if s.value("alerts/vram_enabled", True, type=bool) is False:
            self._alert_vram_percent = None

    def _save_alert_settings(self) -> None:
        s = self._settings()
        s.setValue("alerts/enabled", self._alerts_enabled)
        s.setValue("alerts/cpu_enabled", self._alert_cpu_temp_c is not None)
        s.setValue("alerts/ram_enabled", self._alert_ram_percent is not None)
        s.setValue("alerts/vram_enabled", self._alert_vram_percent is not None)
        if self._alert_cpu_temp_c is not None:
            s.setValue("alerts/cpu_temp_c", float(self._alert_cpu_temp_c))
        if self._alert_ram_percent is not None:
            s.setValue("alerts/ram_percent", float(self._alert_ram_percent))
        if self._alert_vram_percent is not None:
            s.setValue("alerts/vram_percent", float(self._alert_vram_percent))

    def _open_alerts_dialog(self) -> None:
        dlg = _AlertsDialog(
            self._alerts_enabled,
            self._alert_cpu_temp_c,
            self._alert_ram_percent,
            self._alert_vram_percent,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        enabled, cpu, ram, vram = dlg.result_config()
        self._alerts_enabled = enabled
        self._alert_cpu_temp_c = cpu
        self._alert_ram_percent = ram
        self._alert_vram_percent = vram
        self._save_alert_settings()
        state = "ON" if self._alerts_enabled else "OFF"
        self._status.setText(f"Alerts: {state}")

    def _save_snapshot(self) -> None:
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save snapshot",
            "",
            "JSON (*.json);;CSV (*.csv);;NDJSON (*.ndjson)",
        )
        if not path:
            return
        low = path.lower()
        if not low.endswith((".json", ".csv", ".ndjson")):
            uf = selected_filter.upper()
            if "CSV" in uf:
                path += ".csv"
            elif "NDJSON" in uf:
                path += ".ndjson"
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
            elif path.lower().endswith(".ndjson"):
                write_snapshot_ndjson(path, info, monitor, __version__)
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
            section = bundle.get(key, {})
            sec.body_layout().addWidget(self._build_info_section_widget(key, section))
            root_layout.addWidget(sec)
        root_layout.addStretch()

    def _build_info_section_widget(self, key: str, section: dict[str, Any]) -> QWidget:
        """Curated summary + optional raw details toggle for Info sections."""
        outer = QWidget()
        vbox = QVBoxLayout(outer)
        vbox.setContentsMargins(0, 0, 0, 0)

        summary = QWidget()
        summary_form = QFormLayout(summary)

        summary_pairs = self._curated_info_pairs(key, section)
        if not summary_pairs:
            summary_form.addRow(QLabel("(no data)"))
        else:
            for k, v in summary_pairs:
                summary_form.addRow(k, QLabel(v))
        vbox.addWidget(summary)

        raw_toggle = QCheckBox("Show raw details")
        vbox.addWidget(raw_toggle)

        raw = QWidget()
        raw_form = QFormLayout(raw)
        pairs = flatten_info(section)
        if not pairs:
            raw_form.addRow(QLabel("(no raw data)"))
        else:
            for label, value in pairs[:200]:
                raw_form.addRow(label, QLabel(value))
            if len(pairs) > 200:
                raw_form.addRow(QLabel(f"... and {len(pairs) - 200} more rows omitted"))
        raw.setVisible(False)
        raw_toggle.toggled.connect(raw.setVisible)
        vbox.addWidget(raw)

        return outer

    def _curated_info_pairs(self, key: str, section: dict[str, Any]) -> list[tuple[str, str]]:
        """Return a stable, small set of display rows for the Info tab."""
        out: list[tuple[str, str]] = []

        if key == "cpu":
            proc = section.get("proc_cpuinfo") if isinstance(section, dict) else None
            lscpu = section.get("lscpu") if isinstance(section, dict) else None
            if isinstance(proc, dict):
                for k in ("model_name", "vendor", "microcode"):
                    if proc.get(k):
                        out.append((k.replace("_", " ").title(), str(proc[k])))
            if isinstance(lscpu, dict):
                for k in ("Architecture", "CPU(s)", "Thread(s) per core", "Core(s) per socket", "Socket(s)"):
                    if lscpu.get(k):
                        out.append((k, str(lscpu[k])))
                for k in ("CPU max MHz", "CPU min MHz"):
                    if lscpu.get(k):
                        out.append((k, f"{lscpu[k]} MHz"))
            return out

        if key == "memory":
            if isinstance(section, dict):
                for k in ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree"):
                    if section.get(k):
                        out.append((k, str(section[k])))
            return out

        if key == "dmi":
            if isinstance(section, dict):
                if "available" in section:
                    out.append(("Available", str(section.get("available"))))
                for k in (
                    "system_manufacturer",
                    "system_product_name",
                    "baseboard_manufacturer",
                    "baseboard_product_name",
                    "bios_vendor",
                    "bios_version",
                    "bios_release_date",
                ):
                    if section.get(k):
                        out.append((k.replace("_", " ").title(), str(section[k])))
                if section.get("note"):
                    out.append(("Note", str(section["note"])))
            return out

        if key == "graphics":
            if isinstance(section, dict):
                lspci = section.get("lspci")
                if isinstance(lspci, list) and lspci:
                    out.append(("lspci", str(lspci[0])))
                nvsmi = section.get("nvidia_smi")
                if isinstance(nvsmi, dict):
                    if nvsmi.get("gpu"):
                        out.append(("NVIDIA GPU", str(nvsmi["gpu"])))
                    if nvsmi.get("driver"):
                        out.append(("NVIDIA driver", str(nvsmi["driver"])))
                gmem = section.get("gpu_memory")
                if isinstance(gmem, dict):
                    n = gmem.get("nvidia")
                    if isinstance(n, list) and n:
                        r0 = n[0]
                        if isinstance(r0, dict) and r0.get("dedicated_total_mib") is not None:
                            out.append(("VRAM total", f"{float(r0['dedicated_total_mib']):.0f} MiB"))
                        if isinstance(r0, dict) and r0.get("dedicated_used_mib") is not None:
                            out.append(("VRAM used", f"{float(r0['dedicated_used_mib']):.0f} MiB"))
                    a = gmem.get("amd")
                    if isinstance(a, list) and a:
                        r0 = a[0]
                        if isinstance(r0, dict) and r0.get("dedicated_total_mib") is not None:
                            out.append(("AMD VRAM total", f"{float(r0['dedicated_total_mib']):.0f} MiB"))
                        if isinstance(r0, dict) and r0.get("dedicated_used_mib") is not None:
                            out.append(("AMD VRAM used", f"{float(r0['dedicated_used_mib']):.0f} MiB"))
            return out

        return out

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

        controls.addWidget(QLabel("Chart range:"))
        self._range_mode = QComboBox()
        self._range_mode.addItems(["Auto", "Fixed (0–100 for %)"])
        self._range_mode.currentTextChanged.connect(self._on_range_mode_changed)
        controls.addWidget(self._range_mode)

        controls.addWidget(QLabel("CPU series:"))
        self._cpu_series = QSpinBox()
        self._cpu_series.setRange(1, 64)
        self._cpu_series.setValue(self._cpu_chart_max_series)
        self._cpu_series.valueChanged.connect(self._on_series_changed)
        controls.addWidget(self._cpu_series)

        controls.addWidget(QLabel("Sensor series:"))
        self._sensor_series = QSpinBox()
        self._sensor_series.setRange(1, 32)
        self._sensor_series.setValue(self._sensor_chart_max_series)
        self._sensor_series.valueChanged.connect(self._on_series_changed)
        controls.addWidget(self._sensor_series)

        controls.addWidget(QLabel("GPU series:"))
        self._gpu_series = QSpinBox()
        self._gpu_series.setRange(0, 16)
        self._gpu_series.setValue(self._gpu_chart_max_series)
        self._gpu_series.valueChanged.connect(self._on_series_changed)
        controls.addWidget(self._gpu_series)

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
            "Network": ("Network throughput", "KiB/s"),
            "Battery": ("Battery", "%"),
            "Disks": ("Disk temperature", "°C"),
        }
        for cat in ("Load", "Memory", "CPU", "Thermal", "Sensors", "Frequency", "Network", "Battery", "Disks"):
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

        # Apply initial fixed/auto range preference
        self._apply_chart_range_mode()

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
        if self._fetch_inflight and not force:
            return
        self._fetch_inflight = True
        self._pool.start(_MonitorRunnable(self._sampler, self._bridge))

    def _on_monitor_data(self, data: dict[str, Any]) -> None:
        self._fetch_inflight = False
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
        self._evaluate_alerts(data)

    def _evaluate_alerts(self, data: dict[str, Any]) -> None:
        if not self._alerts_enabled:
            return
        alerts: list[str] = []

        # CPU temperature (best-effort): use first thermal zone temp if present
        if self._alert_cpu_temp_c is not None:
            for z in data.get("thermal_zones") or []:
                zm = z.get("temp_millideg", "")
                if isinstance(zm, str) and zm.isdigit():
                    temp_c = int(zm) / 1000.0
                    if temp_c >= float(self._alert_cpu_temp_c):
                        alerts.append(f"CPU temp {temp_c:.1f}°C ≥ {self._alert_cpu_temp_c:.0f}°C")
                    break

        # RAM %
        if self._alert_ram_percent is not None:
            ram = data.get("ram") or {}
            p = ram.get("mem_used_percent")
            if p is not None and float(p) >= float(self._alert_ram_percent):
                alerts.append(f"RAM {float(p):.1f}% ≥ {self._alert_ram_percent:.0f}%")

        # VRAM %
        if self._alert_vram_percent is not None:
            for g in data.get("gpu_memory") or []:
                pct = g.get("dedicated_used_percent")
                if pct is None:
                    continue
                if float(pct) >= float(self._alert_vram_percent):
                    idx = str(g.get("gpu_index", ""))
                    alerts.append(f"VRAM GPU{idx} {float(pct):.1f}% ≥ {self._alert_vram_percent:.0f}%")
                    break

        if alerts:
            msg = "ALERT: " + " | ".join(alerts)
            if self._monitor_note:
                self._monitor_note.setText(msg + ("\n\n" + (data.get("sensors_note") or "") if data.get("sensors_note") else ""))
            self._status.setText(msg)

    def _on_range_mode_changed(self, text: str) -> None:
        self._chart_range_mode = "Fixed" if text.startswith("Fixed") else "Auto"
        self._apply_chart_range_mode()

    def _apply_chart_range_mode(self) -> None:
        # Fixed range for % charts helps reduce jumpiness.
        if self._chart_range_mode == "Fixed":
            self._monitor_charts["CPU"].set_fixed_y_range(0, 100)
            self._monitor_charts["Memory"].set_fixed_y_range(0, 100)
        else:
            self._monitor_charts["CPU"].set_auto_y_range()
            self._monitor_charts["Memory"].set_auto_y_range()

    def _on_series_changed(self) -> None:
        self._cpu_chart_max_series = int(self._cpu_series.value())
        self._sensor_chart_max_series = int(self._sensor_series.value())
        self._gpu_chart_max_series = int(self._gpu_series.value())

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
        _fill(self._monitor_tables["Network"], "Network")
        _fill(self._monitor_tables["Battery"], "Battery")
        _fill(self._monitor_tables["Disks"], "Disks")

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
            if self._gpu_chart_max_series <= 0 or i >= self._gpu_chart_max_series:
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
                if i >= self._cpu_chart_max_series:
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
            if len(sensor_samples) >= self._sensor_chart_max_series:
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

        # Network chart: show aggregate RX/TX across non-lo interfaces
        net_samples: dict[str, float | None] = {}
        net = data.get("net") or {}
        if isinstance(net, dict):
            ifaces = net.get("interfaces")
            if isinstance(ifaces, list):
                rx_sum = 0.0
                tx_sum = 0.0
                for r in ifaces:
                    if not isinstance(r, dict):
                        continue
                    iface = str(r.get("iface", ""))
                    if iface == "lo":
                        continue
                    rx_sum += float(r.get("rx_bytes_per_s", 0.0))
                    tx_sum += float(r.get("tx_bytes_per_s", 0.0))
                net_samples["RX"] = rx_sum / 1024.0
                net_samples["TX"] = tx_sum / 1024.0
        self._monitor_charts["Network"].record_tick(net_samples)

        # Battery chart: first battery capacity%
        bat_samples: dict[str, float | None] = {}
        power = data.get("power") or {}
        if isinstance(power, dict):
            bats = power.get("batteries")
            if isinstance(bats, list) and bats:
                b0 = bats[0]
                if isinstance(b0, dict) and b0.get("capacity_percent") is not None:
                    bat_samples[str(b0.get("name", "BAT"))] = float(b0["capacity_percent"])
        self._monitor_charts["Battery"].record_tick(bat_samples)

        # Disk chart: first temperature if present
        disk_samples: dict[str, float | None] = {}
        smart = data.get("smart") or {}
        if isinstance(smart, dict):
            devs = smart.get("devices")
            if isinstance(devs, list):
                for d in devs:
                    if not isinstance(d, dict):
                        continue
                    if d.get("temp_c") is not None:
                        disk_samples[str(d.get("device", "disk"))] = float(d["temp_c"])
                        break
        self._monitor_charts["Disks"].record_tick(disk_samples)

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
