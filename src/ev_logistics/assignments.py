"""일일 차량 배정 기록 저장과 차량 중복 처리.

실행 세션마다의 기록은 프로젝트를 오염시키지 않도록 `outputs/` 아래에 쓴다
(`data/`가 아니다). 저장 컬럼은 이후 서비스 계산에 필요한 값만 포함한다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CARGO_SET_WEIGHT_KG, OUTPUT_DIR
from .vehicles import load_vehicles, usable_vehicles

ASSIGNMENT_COLUMNS = [
    "assignment_date", "employee_id", "assignment_status", "vehicle_id",
    "vehicle_display_name", "cargo_set_count", "cargo_set_weight_kg",
    "cargo_weight_kg", "vehicle_empty_weight_kg", "total_vehicle_weight_kg",
    "battery_soc_pct", "payload_kg", "project_max_payload_kg",
    "tire_pressure_bar", "battery_usable_kwh", "max_dc_charge_kw",
    "default_soc_pct", "weather_type", "ambient_temp_C", "hvac_mode",
    "hvac_power_kw",
]


def new_session_assignment_path(output_dir: Path = OUTPUT_DIR) -> Path:
    """이번 실행 세션 전용 빈 기록 파일을 만들고 경로를 반환한다."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    path = output_dir / f"daily_vehicle_assignments_{stamp}.csv"
    pd.DataFrame(columns=ASSIGNMENT_COLUMNS).to_csv(
        path, index=False, encoding="utf-8-sig"
    )
    return path


def load_assignments(assignment_path: Path) -> pd.DataFrame:
    """저장 파일이 없으면 같은 컬럼의 빈 DataFrame을 반환한다."""
    path = Path(assignment_path)
    if not path.exists():
        return pd.DataFrame(columns=ASSIGNMENT_COLUMNS)
    saved = pd.read_csv(
        path,
        dtype={"assignment_date": str, "employee_id": str, "vehicle_id": str},
    )
    for column in ASSIGNMENT_COLUMNS:
        if column not in saved.columns:
            saved[column] = np.nan
    return saved[ASSIGNMENT_COLUMNS]


def has_available_vehicle(dispatch: dict, assignment_path: Path) -> bool:
    """현재 사원이 차량을 점유하지 않는다는 전제로 빈 차량이 있는지 확인한다."""
    saved = load_assignments(assignment_path)
    saved = saved.loc[~(
        (saved["assignment_date"] == dispatch["assignment_date"])
        & (saved["employee_id"] == dispatch["employee_id"])
    )]
    used = set(saved.loc[
        saved["assignment_date"] == dispatch["assignment_date"], "vehicle_id"
    ])
    fleet = usable_vehicles(load_vehicles())
    return not fleet["vehicle_id"].isin(used).all()


def save_dispatch(
    dispatch: dict,
    requested_vehicle_id: str,
    cargo_set_count: int,
    assignment_path: Path,
    overwrite_confirmed: bool = False,
) -> tuple[str, pd.Series]:
    """배차를 저장하고 (상태 메시지, 저장된 행)을 반환한다.

    - 같은 날짜에 같은 사원의 기존 행은 갱신 대상으로 먼저 제거
    - 요청 차량이 비어 있으면 그 차량을, 아니면 seed 기반으로 다른 빈 차량을 배정
    - `NORMAL`이 아닌 차량은 후보에서 제외
    - 모든 차량이 사용 중이면 `overwrite_confirmed`에 따라 덮어쓰기 또는 예비차량 저장
    """
    if cargo_set_count < 0:
        raise ValueError("화물 박스 수는 0 이상이어야 합니다.")

    saved = load_assignments(assignment_path)
    same_employee = (
        (saved["assignment_date"] == dispatch["assignment_date"])
        & (saved["employee_id"] == dispatch["employee_id"])
    )
    saved = saved.loc[~same_employee].copy()

    vehicles = load_vehicles()
    fleet = usable_vehicles(vehicles)
    requested = fleet.loc[fleet["vehicle_id"].eq(requested_vehicle_id)]
    if requested.empty:
        raise ValueError("선택한 차량을 사용할 수 없습니다(고장·점검 또는 미존재).")

    max_payload = float(requested.iloc[0]["project_max_payload_kg"])
    if cargo_set_count * CARGO_SET_WEIGHT_KG > max_payload:
        raise ValueError(f"화물량은 선택 차량 적재 한도({max_payload:g}kg) 이하여야 합니다.")

    used = set(saved.loc[
        (saved["assignment_date"] == dispatch["assignment_date"])
        & saved["vehicle_id"].isin(set(fleet["vehicle_id"])), "vehicle_id"
    ])
    available = fleet.loc[~fleet["vehicle_id"].isin(used)]

    if available.empty:
        if overwrite_confirmed:
            selected = fleet.iloc[dispatch["seed"] % len(fleet)]
            saved = saved.loc[~(
                (saved["assignment_date"] == dispatch["assignment_date"])
                & (saved["vehicle_id"] == selected["vehicle_id"])
            )].copy()
            status = "OVERWRITTEN"
            message = f'기존 배정 덮어쓰기: {selected["display_name"]}'
        else:
            selected, status = None, "RESERVE"
            message = "차량 배정 취소: 예비차량으로 저장했습니다."
    else:
        matches = available.loc[available["vehicle_id"].eq(requested_vehicle_id)]
        selected = (
            matches.iloc[0] if not matches.empty
            else available.iloc[dispatch["seed"] % len(available)]
        )
        status = "ASSIGNED"
        message = f'차량 배정 완료: {selected["display_name"]}'

    empty_weight = (
        float(selected["project_combination_empty_weight_kg"])
        if selected is not None else np.nan
    )
    row = {
        "assignment_date": dispatch["assignment_date"],
        "employee_id": dispatch["employee_id"],
        "assignment_status": status,
        "vehicle_id": selected["vehicle_id"] if selected is not None else "RESERVE_VEHICLE",
        "vehicle_display_name": selected["display_name"] if selected is not None else "예비차량",
        "cargo_set_count": cargo_set_count,
        "cargo_set_weight_kg": CARGO_SET_WEIGHT_KG,
        "cargo_weight_kg": cargo_set_count * CARGO_SET_WEIGHT_KG,
        "vehicle_empty_weight_kg": empty_weight,
        "total_vehicle_weight_kg": (
            empty_weight + cargo_set_count * CARGO_SET_WEIGHT_KG
            if selected is not None else np.nan
        ),
        "battery_soc_pct": dispatch["battery_soc_pct"],
        "payload_kg": cargo_set_count * CARGO_SET_WEIGHT_KG,
        "project_max_payload_kg": selected["project_max_payload_kg"] if selected is not None else np.nan,
        "tire_pressure_bar": selected["tire_pressure_bar"] if selected is not None else np.nan,
        "battery_usable_kwh": selected["battery_usable_kwh"] if selected is not None else np.nan,
        "max_dc_charge_kw": selected["max_dc_charge_kw"] if selected is not None else np.nan,
        "default_soc_pct": selected["default_soc_pct"] if selected is not None else np.nan,
        "weather_type": dispatch["weather_type"],
        "ambient_temp_C": dispatch["ambient_temp_C"],
        "hvac_mode": dispatch["hvac_mode"],
        "hvac_power_kw": dispatch["hvac_power_kw"],
    }
    updated = pd.concat(
        [saved, pd.DataFrame([row])], ignore_index=True
    )[ASSIGNMENT_COLUMNS]
    Path(assignment_path).parent.mkdir(parents=True, exist_ok=True)
    updated.to_csv(assignment_path, index=False, encoding="utf-8-sig")
    return message, updated.iloc[-1]
