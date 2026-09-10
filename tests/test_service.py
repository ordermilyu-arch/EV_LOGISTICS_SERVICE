"""서비스 로직 스모크 테스트.

실행: python -m pytest -q   (또는 python tests/test_service.py)
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd
import pytest

from ev_logistics.assignments import load_assignments, save_dispatch
from ev_logistics.dispatch import create_dispatch, validate_employee_id
from ev_logistics.model import load_energy_model
from ev_logistics.route import available_chargers, load_service_route
from ev_logistics.simulation import run_service_simulation
from ev_logistics.vehicles import load_vehicles, usable_vehicles


def test_employee_id_validation():
    assert validate_employee_id(" 12345678 ") == "12345678"
    for bad in ["", "1234567", "123456789", "1234abcd"]:
        with pytest.raises(ValueError):
            validate_employee_id(bad)


def test_dispatch_is_deterministic():
    a = create_dispatch("12345678", "2026-08-28")
    b = create_dispatch("12345678", "2026-08-28")
    assert a == b
    assert 50 <= a["battery_soc_pct"] <= 90
    assert 3 <= a["default_cargo_set_count"] <= 10


def test_route_and_chargers():
    route = load_service_route()
    chargers = available_chargers(route)
    assert len(route) == 16
    assert len(chargers) == 14  # 16 - 2 OUT_OF_SERVICE
    assert chargers["max_verified_power_kw"].notna().all()


def test_all_vehicles_usable_in_sample_data():
    vehicles = load_vehicles()
    assert len(vehicles) == 10
    assert len(usable_vehicles(vehicles)) == 10


def test_model_metrics_reasonable():
    bundle = load_energy_model()
    assert bundle["metrics"]["R2"] > 0.9
    assert len(bundle["features"]) == 16


def test_end_to_end_simulation_feasible():
    result = run_service_simulation("12345678", "2026-08-28")
    sim = result["simulation"]
    assert sim["feasible"] is True
    assert result["total_energy_kwh"] > 0
    assert len(result["segments"]) == 17
    assert all(leg["도착 SOC(%)"] >= 10 for leg in sim["legs"])


def test_save_dispatch_roundtrip():
    dispatch = create_dispatch("12345678", "2026-08-28")
    vehicles = load_vehicles()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "a.csv"
        message, row = save_dispatch(
            dispatch, vehicles.iloc[0]["vehicle_id"], 5, assignment_path=path
        )
        assert "배정" in message
        saved = load_assignments(path)
        assert len(saved) == 1
        assert saved.iloc[0]["employee_id"] == "12345678"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
