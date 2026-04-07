"""Rolling multi-series line charts for the Monitor tab (Qt Charts)."""

from __future__ import annotations

from collections import deque
from typing import Mapping

from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

_PALETTE: list[QColor] = [
    QColor(0, 114, 178),
    QColor(213, 94, 0),
    QColor(0, 158, 115),
    QColor(204, 121, 167),
    QColor(86, 180, 233),
    QColor(230, 159, 0),
    QColor(240, 228, 66),
    QColor(80, 80, 80),
]


class RollingTrendChart(QWidget):
    """Line chart that appends one shared X tick per monitor refresh."""

    def __init__(
        self,
        title: str,
        y_axis_title: str,
        max_points: int = 180,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._max_points = max_points
        self._x = 0
        self._points: dict[str, deque[tuple[float, float]]] = {}
        self._series: dict[str, QLineSeries] = {}
        self._color_idx = 0
        self._fixed_y: tuple[float, float] | None = None

        self._chart = QChart()
        self._chart.setTitle(title)
        self._chart.legend().setVisible(True)
        self._chart.legend().setAlignment(Qt.AlignmentFlag.AlignBottom)
        self._chart.setAnimationOptions(QChart.AnimationOption.NoAnimation)

        self._axis_x = QValueAxis()
        self._axis_x.setTitleText("Sample #")
        self._axis_x.setLabelFormat("%d")
        self._chart.addAxis(self._axis_x, Qt.AlignmentFlag.AlignBottom)

        self._axis_y = QValueAxis()
        self._axis_y.setTitleText(y_axis_title)
        self._chart.addAxis(self._axis_y, Qt.AlignmentFlag.AlignLeft)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setMinimumHeight(200)
        self._view.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.MinimumExpanding,
        )

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self._view)

    def _next_color(self) -> QColor:
        c = _PALETTE[self._color_idx % len(_PALETTE)]
        self._color_idx += 1
        return c

    def _ensure_series(self, name: str) -> QLineSeries:
        if name in self._series:
            return self._series[name]
        s = QLineSeries()
        s.setName(name)
        s.setColor(self._next_color())
        self._chart.addSeries(s)
        s.attachAxis(self._axis_x)
        s.attachAxis(self._axis_y)
        self._series[name] = s
        self._points[name] = deque(maxlen=self._max_points)
        return s

    def record_tick(self, samples: Mapping[str, float | None]) -> None:
        """Append one time step; `samples` maps series name to value (skip None)."""
        self._x += 1
        t = float(self._x)
        for name, val in samples.items():
            if val is None:
                continue
            self._ensure_series(name)
            self._points[name].append((t, float(val)))
        self._redraw()

    def _redraw(self) -> None:
        all_x: list[float] = []
        all_y: list[float] = []
        for name, series in self._series.items():
            series.clear()
            pts = self._points.get(name)
            if not pts:
                continue
            for x, y in pts:
                series.append(x, y)
                all_x.append(x)
                all_y.append(y)
        if not all_x or not all_y:
            return
        xmin, xmax = min(all_x), max(all_x)
        if xmin == xmax:
            xmin -= 0.5
            xmax += 0.5
        self._axis_x.setRange(xmin, xmax)
        if self._fixed_y is not None:
            self._axis_y.setRange(self._fixed_y[0], self._fixed_y[1])
            return
        ymin, ymax = min(all_y), max(all_y)
        if ymin == ymax:
            ymin -= 0.5
            ymax += 0.5
        pad_y = (ymax - ymin) * 0.08 + 1e-6
        self._axis_y.setRange(ymin - pad_y, ymax + pad_y)

    def set_fixed_y_range(self, ymin: float, ymax: float) -> None:
        self._fixed_y = (float(ymin), float(ymax))
        self._redraw()

    def set_auto_y_range(self) -> None:
        self._fixed_y = None
        self._redraw()

    def reset(self) -> None:
        """Clear history (e.g. after error or pause resume)."""
        self._x = 0
        self._points.clear()
        self._color_idx = 0
        for s in list(self._series.values()):
            self._chart.removeSeries(s)
        self._series.clear()
