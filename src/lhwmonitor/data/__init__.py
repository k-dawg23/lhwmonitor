"""Data collection from /proc, /sys, and CLI tools."""

from lhwmonitor.data.info_bundle import collect_info_bundle
from lhwmonitor.data.monitor_snapshot import collect_monitor_snapshot

__all__ = ["collect_info_bundle", "collect_monitor_snapshot"]
