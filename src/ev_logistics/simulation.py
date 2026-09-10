"""구간별 에너지 예측 → SOC 시뮬레이션 → 충전 계획 → ETA 통합.

전체 노선을 하나의 평균값으로 처리하지 않고, 17개 구간의 거리와 평균경사를
모델에 개별 입력해 구간별 소비율·소비에너지를 예측한 뒤 누적한다.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import numpy as np
import pandas as pd

from .adapter import adapt_model_input, output_calibration_factor
from .config import (
    CARGO_SET_WEIGHT_KG,
    DEFAULT_SPEED_KMH,
    FIXED_DEPARTURE_HOUR,
    OPTIMAL_BATTERY_TEMP_C,
    adapter_config,
    route_config,
)
from .dispatch import create_dispatch
from .features import create_ev_features
from .model import load_energy_model
from .route import available_chargers, load_route_grade, load_service_route, route_summary
from .vehicles import get_vehicle, load_vehicles


def predict_route_segments(
    model: object,
    grade_rows: pd.DataFrame,
    payload_kg: float,
    tire_pressure_bar: float,
    speed_kmh: float,
    dispatch: dict,
    adapter: dict | None = None,
) -> pd.DataFrame:
    """각 노선 구간의 거리와 경사를 반영해 소비전력을 개별 예측한다."""
    adapter = adapter or adapter_config()
    model_payload, model_tire = adapt_model_input(payload_kg, tire_pressure_bar, adapter)
    segments = grade_rows.loc[grade_rows["segment_distance_km"] > 0].copy()
    segments["start_distance_km"] = (
        segments["trip_distance_from_start_km"] - segments["segment_distance_km"]
    )
    model_input = pd.DataFrame({
        "speed_kmh": float(speed_kmh),
        "payload_kg": model_payload,
        "ambient_temp_C": float(dispatch["ambient_temp_C"]),
        "hvac_power_kw": float(dispatch["hvac_power_kw"]),
        "road_grade_pct": segments["segment_average_grade_pct"].to_numpy(),
        "battery_temp_C": OPTIMAL_BATTERY_TEMP_C,
        "driving_style_index": float(dispatch["driving_style_index"]),
        "tire_pressure_bar": model_tire,
        "trip_distance_km": segments["segment_distance_km"].to_numpy(),
    })
    raw_predictions = model.predict(create_ev_features(model_input))
    factor = output_calibration_factor(adapter)
    segments["predicted_kwh_per_100km"] = raw_predictions * factor
    segments["predicted_energy_kwh"] = (
        segments["predicted_kwh_per_100km"] * segments["segment_distance_km"] / 100.0
    )
    return segments.reset_index(drop=True)


def simulate_route(
    segment_predictions: pd.DataFrame,
    battery_usable_kwh: float,
    departure_soc_pct: float,
    route_rows: pd.DataFrame,
    departure_time: datetime,
    config: dict | None = None,
) -> dict[str, object]:
    """충전 후보를 순서대로 검토하며 SOC와 ETA를 계산한다.

    필요한 경우에만 충전하며, 충전 정차가 발생하면 다음 운행을 위해 목표 SOC까지
    채운다. 어느 구간에서든 안전 SOC를 지킬 수 없으면 ``feasible=False``.
    """
    config = config or route_config()
    constants = config["simulation_constants"]
    reserve_kwh = battery_usable_kwh * constants["minimum_reserve_soc_pct"] / 100
    max_charge_kwh = battery_usable_kwh * constants["maximum_charge_target_soc_pct"] / 100
    efficiency = constants["charging_efficiency"]
    speed = constants["simulation_average_speed_kmh"]
    overhead = constants["charging_stop_overhead_minutes"]

    chargers = available_chargers(route_rows)
    points = [
        {"name": route_summary()["start_name"], "distance_km": 0.0, "power_kw": None},
        *[
            {
                "name": row["rest_area_name_ko"],
                "distance_km": float(row["trip_distance_from_start_km"]),
                "power_kw": float(row["max_verified_power_kw"]),
            }
            for _, row in chargers.iterrows()
        ],
        {
            "name": route_summary()["destination_name"],
            "distance_km": route_summary()["total_route_distance_km"],
            "power_kw": None,
        },
    ]
    current_soc_kwh = battery_usable_kwh * departure_soc_pct / 100
    elapsed = timedelta(0)
    legs: list[dict] = []
    charges: list[dict] = []

    def energy_between(start_km: float, end_km: float) -> float:
        """경계가 겹치는 모든 노선 구간의 예측 소비에너지를 합산한다."""
        energy_kwh = 0.0
        for _, segment in segment_predictions.iterrows():
            overlap_km = max(
                0.0,
                min(end_km, float(segment["trip_distance_from_start_km"]))
                - max(start_km, float(segment["start_distance_km"])),
            )
            energy_kwh += overlap_km * float(segment["predicted_kwh_per_100km"]) / 100.0
        return energy_kwh

    for index in range(1, len(points)):
        previous, point = points[index - 1], points[index]
        distance = point["distance_km"] - previous["distance_km"]
        energy = energy_between(previous["distance_km"], point["distance_km"])
        if current_soc_kwh - energy < reserve_kwh:
            if previous["power_kw"] is None:
                return {"feasible": False, "legs": legs, "charges": charges, "arrival_time": None}
            if max_charge_kwh - energy < reserve_kwh:
                return {"feasible": False, "legs": legs, "charges": charges, "arrival_time": None}
            charge_from_grid_kwh = max(0.0, (max_charge_kwh - current_soc_kwh) / efficiency)
            charge_minutes = charge_from_grid_kwh / previous["power_kw"] * 60
            current_soc_kwh = max_charge_kwh
            elapsed += timedelta(minutes=charge_minutes + overhead)
            charges.append({
                "휴게소": previous["name"],
                "충전량(kWh)": charge_from_grid_kwh,
                "충전출력(kW)": previous["power_kw"],
                "충전시간(분)": int(round(charge_minutes)),
                "총 정차시간(분)": int(round(charge_minutes + overhead)),
            })
        arrival_soc_kwh = current_soc_kwh - energy
        elapsed += timedelta(hours=distance / speed)
        legs.append({
            "구간": f'{previous["name"]} → {point["name"]}',
            "거리(km)": distance,
            "소비에너지(kWh)": energy,
            "도착 SOC(%)": arrival_soc_kwh / battery_usable_kwh * 100,
        })
        current_soc_kwh = arrival_soc_kwh

    return {
        "feasible": True,
        "legs": legs,
        "charges": charges,
        "arrival_time": departure_time + elapsed,
        "total_minutes": elapsed.total_seconds() / 60,
    }


def run_service_simulation(
    employee_id: str,
    assignment_date: date | datetime | str | None = None,
    vehicle_id: str | None = None,
    cargo_set_count: int | None = None,
    speed_kmh: float = DEFAULT_SPEED_KMH,
    hvac_control: str = "자동(날씨 기준)",
) -> dict:
    """배차 → 예측 → 시뮬레이션을 한 번에 실행해 결과 딕셔너리 하나를 반환한다."""
    from .dispatch import apply_hvac_control

    dispatch = create_dispatch(employee_id, assignment_date)
    dispatch = apply_hvac_control(dispatch, hvac_control)

    vehicles = load_vehicles()
    if vehicle_id is None:
        vehicle_id = vehicles.iloc[dispatch["seed"] % len(vehicles)]["vehicle_id"]
    vehicle = get_vehicle(vehicles, vehicle_id)

    if cargo_set_count is None:
        cargo_set_count = dispatch["default_cargo_set_count"]
    payload_kg = cargo_set_count * CARGO_SET_WEIGHT_KG
    max_payload = float(vehicle["project_max_payload_kg"])
    if payload_kg > max_payload:
        raise ValueError(f"화물량({payload_kg:g}kg)이 차량 적재 한도({max_payload:g}kg)를 초과합니다.")

    model_bundle = load_energy_model()
    grade_rows = load_route_grade()
    route_rows = load_service_route()

    segments = predict_route_segments(
        model=model_bundle["model"],
        grade_rows=grade_rows,
        payload_kg=payload_kg,
        tire_pressure_bar=float(vehicle["tire_pressure_bar"]),
        speed_kmh=speed_kmh,
        dispatch=dispatch,
    )
    total_energy_kwh = float(segments["predicted_energy_kwh"].sum())
    total_distance_km = route_summary()["total_route_distance_km"]

    departure_time = datetime.combine(
        date.fromisoformat(dispatch["assignment_date"]),
        time(FIXED_DEPARTURE_HOUR, 0),
    )
    simulation = simulate_route(
        segment_predictions=segments,
        battery_usable_kwh=float(vehicle["battery_usable_kwh"]),
        departure_soc_pct=dispatch["battery_soc_pct"],
        route_rows=route_rows,
        departure_time=departure_time,
    )
    return {
        "dispatch": dispatch,
        "vehicle": vehicle.to_dict(),
        "cargo_set_count": cargo_set_count,
        "payload_kg": payload_kg,
        "speed_kmh": speed_kmh,
        "metrics": model_bundle["metrics"],
        "segments": segments,
        "predicted_kwh_per_100km": total_energy_kwh / total_distance_km * 100.0,
        "total_energy_kwh": total_energy_kwh,
        "departure_time": departure_time,
        "simulation": simulation,
    }
