#!/usr/bin/env python3
"""Capture PNG screenshots for docs (offscreen Qt; no display required).

Run from repo root:
  PYTHONPATH=src QT_QPA_PLATFORM=offscreen python scripts/capture_screenshots.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root = parent of scripts/
_ROOT = Path(__file__).resolve().parent.parent
_OUT = _ROOT / "screenshots"


def main() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _OUT.mkdir(parents=True, exist_ok=True)

    if str(_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(_ROOT / "src"))

    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from lhwmonitor.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    w = MainWindow()
    w.resize(920, 680)
    w.show()

    def shot_info() -> None:
        w.grab().save(str(_OUT / "01-info-tab.png"))

    def switch_monitor() -> None:
        tw = w.centralWidget()
        if tw is not None:
            tw.setCurrentIndex(1)

    def shot_monitor() -> None:
        w.grab().save(str(_OUT / "02-monitor-tab.png"))
        app.quit()

    QTimer.singleShot(1200, shot_info)
    QTimer.singleShot(1300, switch_monitor)
    QTimer.singleShot(2200, shot_monitor)
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
