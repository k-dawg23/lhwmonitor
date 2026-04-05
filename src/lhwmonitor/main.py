"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from lhwmonitor import __version__
from lhwmonitor.ui.main_window import MainWindow


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("lhwmonitor")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("lhwmonitor")
    win = MainWindow()
    win.show()
    raise SystemExit(app.exec())


if __name__ == "__main__":
    main()
