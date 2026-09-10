"""차량 CSV 로드와 차량 조회.

10대 모두 같은 Volvo FH Electric이며, 차량 간 차이는 `tire_pressure_bar`만 사용한다.
`vehicle_status`가 `NORMAL`이 아닌 차량은 배정 대상에서 제외한다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import USABLE_VEHICLE_STATUS, VEHICLE_CSV

REQUIRED_COLUMNS = {
    "vehicle_id", "project_max_payload_kg", "tire_pressure_bar",
    "battery_usable_kwh", "max_dc_charge_kw", "default_soc_pct",
    "project_combination_empty_weight_kg", "vehicle_status",
}


def load_vehicles(vehicle_csv: Path = VEHICLE_CSV) -> pd.DataFrame:
    """차량 CSV를 읽고 화면 표시용 `display_name`(예: `3호차 (Volvo FH)`)을 붙인다."""
    if not Path(vehicle_csv).exists():
        raise FileNotFoundError(f"차량 데이터 파일을 찾을 수 없습니다: {vehicle_csv}")
    vehicles = pd.read_csv(vehicle_csv, dtype={"vehicle_id": str})
    missing = REQUIRED_COLUMNS.difference(vehicles.columns)
    if missing:
        raise ValueError(f"차량 CSV에 필요한 컬럼이 없습니다: {sorted(missing)}")
    vehicles["display_name"] = (
        vehicles["vehicle_id"].str.extract(r"(\d+)$")[0].astype(int)
        .map(lambda number: f"{number}호차 (Volvo FH)")
    )
    return vehicles


def usable_vehicles(vehicles: pd.DataFrame) -> pd.DataFrame:
    """고장·점검 중이 아닌(`vehicle_status == NORMAL`) 차량만 반환한다."""
    return vehicles.loc[
        vehicles["vehicle_status"].astype(str).str.upper() == USABLE_VEHICLE_STATUS
    ].reset_index(drop=True)


def get_vehicle(vehicles: pd.DataFrame, vehicle_id: str) -> pd.Series:
    """`vehicle_id`로 차량 한 대를 조회한다."""
    match = vehicles.loc[vehicles["vehicle_id"].eq(str(vehicle_id))]
    if match.empty:
        raise ValueError(f"차량을 찾을 수 없습니다: {vehicle_id}")
    return match.iloc[0]
