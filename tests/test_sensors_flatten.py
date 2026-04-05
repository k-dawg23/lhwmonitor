"""Tests for sensors JSON flattening."""

from lhwmonitor.data.sensors_live import _flatten_sensors_json


def test_flatten_nested_temps() -> None:
    data = {
        "coretemp-isa-0000": {
            "Adapter": "ISA adapter",
            "Package id 0": {"temp1_input": 45.0},
            "Core 0": {"temp2_input": 43.0},
        }
    }
    rows = _flatten_sensors_json(data)
    assert any("45.0" in r["value"] for r in rows)
