"""Tests for /proc/stat parsing."""

from lhwmonitor.data.proc_stat import CpuUsageSampler, parse_proc_stat_cores


SAMPLE_STAT = """cpu  4705 0 3443 8174123 405703 4059 0 0 0 0
cpu0 2350 0 1720 4085000 202800 2000 0 0 0 0
cpu1 2355 0 1723 4089123 202903 2059 0 0 0 0
intr 10290482
ctxt 201049170
"""


def test_parse_proc_stat_cores_keys() -> None:
    m = parse_proc_stat_cores(SAMPLE_STAT)
    assert "cpu" in m and "cpu0" in m and "cpu1" in m


def test_cpu_usage_sampler_second_tick() -> None:
    s = CpuUsageSampler()
    assert s.update(SAMPLE_STAT) is None
    assert s.update(SAMPLE_STAT) is not None
