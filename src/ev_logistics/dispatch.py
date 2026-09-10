"""사원번호·배차일 기반 결정적 배차 생성.

같은 (사원번호, 배차일)은 SHA-256 seed를 거쳐 항상 같은 차량·SOC·운전성향·날씨를
만든다. 데모와 테스트에서 결과를 재현할 수 있게 하는 것이 목적이다.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime

from .config import CARGO_MAX_SETS, CARGO_MIN_SETS, DEPARTURE_SOC_OPTIONS


def validate_employee_id(employee_id: str) -> str:
    """숫자 8자리 사원번호만 허용하고 표준 문자열로 반환한다."""
    normalized = str(employee_id).strip()
    if not normalized:
        raise ValueError("사원번호를 입력해주세요.")
    if not normalized.isdigit():
        raise ValueError("사원번호는 숫자만 입력할 수 있습니다.")
    if len(normalized) != 8:
        raise ValueError("사원번호는 숫자 8자리여야 합니다.")
    return normalized


def normalize_assignment_date(value: date | datetime | str | None) -> str:
    """날짜 입력을 seed에 쓸 YYYY-MM-DD 문자열로 통일한다."""
    if value is None:
        return date.today().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    try:
        return date.fromisoformat(str(value).strip()).isoformat()
    except ValueError as error:
        raise ValueError("배차 날짜는 YYYY-MM-DD 형식이어야 합니다.") from error


def make_assignment_seed(employee_id: str, assignment_date: str) -> int:
    """실행 환경이 달라도 같은 입력에 같은 seed가 나오도록 한다."""
    digest = hashlib.sha256(f"{employee_id}:{assignment_date}".encode()).digest()
    return int.from_bytes(digest[:8], byteorder="big")


def create_dispatch(employee_id: str, assignment_date: date | datetime | str | None) -> dict:
    """차량 배정 전 단계의 배차 조건(날씨·HVAC·SOC·운전성향·기본 화물량)을 만든다."""
    normalized_id = validate_employee_id(employee_id)
    normalized_date = normalize_assignment_date(assignment_date)
    seed = make_assignment_seed(normalized_id, normalized_date)
    rng = random.Random(seed)

    battery_soc_pct = float(rng.choice(DEPARTURE_SOC_OPTIONS))
    driving_style_index = round(rng.random(), 2)
    weather_type = rng.choice(["cold", "normal", "hot"])
    if weather_type == "cold":
        ambient_temp_c, hvac_mode = round(rng.uniform(-10, 5), 1), "HEATING"
        hvac_power_kw = round(rng.uniform(2, 5), 2)
    elif weather_type == "hot":
        ambient_temp_c, hvac_mode = round(rng.uniform(30, 40), 1), "COOLING"
        hvac_power_kw = round(rng.uniform(2, 5), 2)
    else:
        ambient_temp_c, hvac_mode, hvac_power_kw = round(rng.uniform(15, 25), 1), "OFF", 0.0

    default_cargo_sets = CARGO_MIN_SETS + seed % (CARGO_MAX_SETS - CARGO_MIN_SETS + 1)

    return {
        "employee_id": normalized_id,
        "assignment_date": normalized_date,
        "seed": seed,
        "battery_soc_pct": battery_soc_pct,
        "driving_style_index": driving_style_index,
        "weather_type": weather_type,
        "ambient_temp_C": ambient_temp_c,
        "hvac_mode": hvac_mode,
        "hvac_power_kw": hvac_power_kw,
        "default_cargo_set_count": int(default_cargo_sets),
    }


def apply_hvac_control(dispatch: dict, control: str) -> dict:
    """날씨 기본값을 유지하거나 사용자가 HVAC를 강제로 켜고 끈다."""
    controlled = dispatch.copy()
    if control == "강제 OFF":
        controlled["hvac_mode"] = "OFF"
        controlled["hvac_power_kw"] = 0.0
    elif control == "강제 ON" and controlled["hvac_mode"] == "OFF":
        controlled["hvac_mode"] = (
            "HEATING" if controlled["ambient_temp_C"] < 25 else "COOLING"
        )
        controlled["hvac_power_kw"] = 2.5
    return controlled


def driving_style_label(index: float) -> str:
    if index < 0.34:
        return "Eco / Smooth Driving"
    if index < 0.67:
        return "Normal Driving"
    return "Aggressive Driving"
