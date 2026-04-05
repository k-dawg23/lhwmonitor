"""Parse /proc/stat for CPU usage (needs consecutive samples)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class _CpuJiffies:
    idle_sum: int
    total: int


def _parse_cpu_line(parts: list[str]) -> _CpuJiffies | None:
    if len(parts) < 5:
        return None
    try:
        nums = [int(x) for x in parts[1:]]
    except ValueError:
        return None
    while len(nums) < 10:
        nums.append(0)
    user, nice, system, idle, iowait = nums[0], nums[1], nums[2], nums[3], nums[4]
    irq, softirq, steal = nums[5], nums[6], nums[7]
    guest, guest_nice = nums[8], nums[9]
    idle_sum = idle + iowait
    total = user + nice + system + idle + iowait + irq + softirq + steal + guest + guest_nice
    return _CpuJiffies(idle_sum=idle_sum, total=total)


def parse_proc_stat_cores(stat_text: str) -> dict[str, _CpuJiffies]:
    """Map cpu, cpu0, ... -> jiffies."""
    out: dict[str, _CpuJiffies] = {}
    for line in stat_text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        name = parts[0]
        if not name.startswith("cpu"):
            continue
        j = _parse_cpu_line(parts)
        if j is not None:
            out[name] = j
    return out


def jiffies_to_usage_percent(
    prev: dict[str, _CpuJiffies], cur: dict[str, _CpuJiffies]
) -> dict[str, float]:
    """Return 0-100 usage per key present in both."""
    result: dict[str, float] = {}
    for key in cur:
        if key not in prev:
            continue
        a, b = prev[key], cur[key]
        dt = b.total - a.total
        if dt <= 0:
            continue
        didle = b.idle_sum - a.idle_sum
        idle_frac = max(0.0, min(1.0, didle / dt))
        result[key] = round((1.0 - idle_frac) * 100.0, 1)
    return result


class CpuUsageSampler:
    """Holds previous /proc/stat snapshot to compute CPU usage."""

    def __init__(self) -> None:
        self._prev: dict[str, _CpuJiffies] | None = None

    def update(self, stat_text: str) -> dict[str, float] | None:
        cur = parse_proc_stat_cores(stat_text)
        if self._prev is None:
            self._prev = cur
            return None
        usage = jiffies_to_usage_percent(self._prev, cur)
        self._prev = cur
        return usage
