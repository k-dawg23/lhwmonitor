# lhwmonitor — project history

This document summarizes major phases of development from the first prototype through the latest release. Version numbers refer to tags and `pyproject.toml` / `lhwmonitor.__version__`.

---

## Phase 1 — v0.1.0: foundation

**Goals:** Linux-only desktop utility modeled on CPU-Z (static hardware) and HWMonitor (live sensors).

**Delivered:**

- **Python 3.11+** app using **PySide6 (Qt 6)** with two tabs: **Info** and **Monitor**.
- **Info:** CPU (`lscpu`, `/proc/cpuinfo`), memory (`/proc/meminfo`), optional DMI (`dmidecode`), graphics (`lspci`, optional `nvidia-smi`).
- **Monitor:** load averages, CPU usage from `/proc/stat` (two-sample calibration), thermal zones, `lm-sensors` output, CPU frequencies from sysfs.
- **UI:** collapsible sections (expand/collapse with +/−), monitor refresh interval and pause, background collection via `QThreadPool`.
- **Packaging:** `pyproject.toml`, console entry point `lhwmonitor`.

**Out of scope for v0.1.0:** Web UI, heavy logging infrastructure, SMART disks (noted for later).

---

## Phase 2 — v0.1.1: usability and system integration

**Goals:** Clearer presentation, DMI messaging, repository hygiene.

**Delivered:**

- **Collapsible sections** on both Info and Monitor for Processor, Memory, System (DMI), Graphics, Load, CPU, Thermal, Sensors, Frequency.
- **DMI / `sudo`:** Improved detection and user-facing notes when `dmidecode` needs root or when `sudo` cannot find `lhwmonitor` (PATH); README guidance (`sudo env PATH="$PATH" lhwmonitor`).
- **README:** Version line, optional **python3-venv** note for Debian/Ubuntu.
- **Git:** Planning notes `INFO.md` / `MONITOR.md` removed from tracking (local-only), **MIT License** documented in README.

---

## Phase 3 — v0.2.0: real-time charts

**Goals:** Visual trends in the Monitor tab.

**Delivered:**

- **Qt Charts** (`PySide6.QtCharts`) — rolling **line charts** under each Monitor section (Load, CPU, Thermal, Sensors, Frequency) with a bounded history (e.g. 180 samples).
- **CPU / frequency ordering:** Numeric sort for logical CPUs; zero-padded labels (`cpu00`, `cpu01`, …) so ordering stays correct beyond nine cores.
- **Refactor:** Chart widget in `monitor_trend_chart.py`.

---

## Phase 4 — v0.2.1: memory and GPU metrics

**Goals:** RAM and GPU memory visibility on Info and Monitor.

**Delivered:**

- **Info → Graphics:** GPU VRAM via **NVIDIA** (`nvidia-smi`) and **AMD** (`rocm-smi` when available); optional **dynamic/shared** system RAM usage for NVIDIA via `nvidia-smi -q` on Info refresh.
- **Monitor:** New **Memory** section — system RAM (totals, used %, swap when present), per-GPU VRAM lines; **Memory** trend chart (RAM % and GPU VRAM % series).
- **Modules:** `gpu_mem.py`, extended `memory.py` (`collect_system_ram_snapshot`), snapshot includes `ram` and `gpu_memory`.

---

## Phase 5 — v0.2.2: manual export (“logs”)

**Goals:** Save snapshots in usable formats without continuous background logging.

**Delivered:**

- **File → Save snapshot…** (**Ctrl+S**): export current **Info** bundle + **Monitor** snapshot.
- **JSON:** Full structured document (version, UTC timestamp, `info`, `monitor`) for scripting and archival.
- **CSV:** Flattened rows (`Section`, `Item`, `Value`) for spreadsheets; includes meta rows and Info/Monitor sections.
- **Refactor:** `export_log.py`, `info_flatten.py`, `monitor_rows.py` shared between UI tables and export.
- **Explicitly deferred:** Automatic / continuous logging (called out in README for a future version).

---

## Current direction

Future work may include scheduled or continuous logging, additional hardware sources (e.g. disk SMART), and further charting — driven by issues and releases after **v0.2.2**.

---

## Screenshots in the repository

Example captures of the running UI are stored under [`screenshots/`](screenshots/) and linked from [`README.md`](README.md). Regenerate them with:

```bash
PYTHONPATH=src QT_QPA_PLATFORM=offscreen python scripts/capture_screenshots.py
```
