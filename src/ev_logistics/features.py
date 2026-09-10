"""에너지 소비 모델용 물리 기반 파생변수 생성."""

from __future__ import annotations

import pandas as pd

from .config import (
    COMFORTABLE_AMBIENT_TEMP_C,
    OPTIMAL_BATTERY_TEMP_C,
    OPTIMAL_TIRE_PRESSURE_BAR,
)


def create_ev_features(data: pd.DataFrame) -> pd.DataFrame:
    """전기차 소비량에 의미가 있는 비선형·상호작용 변수를 추가한다.

    원본 열은 그대로 두고 7개 파생변수를 덧붙인 새 DataFrame을 반환한다.
    """
    result = data.copy()
    result["speed_squared"] = result["speed_kmh"] ** 2
    result["ambient_temp_deviation"] = (
        result["ambient_temp_C"] - COMFORTABLE_AMBIENT_TEMP_C
    ).abs()
    result["battery_temp_deviation"] = (
        result["battery_temp_C"] - OPTIMAL_BATTERY_TEMP_C
    ).abs()
    result["tire_pressure_deviation"] = (
        result["tire_pressure_bar"] - OPTIMAL_TIRE_PRESSURE_BAR
    ).abs()
    result["payload_grade"] = result["payload_kg"] * result["road_grade_pct"]
    result["hvac_temp_interaction"] = (
        result["hvac_power_kw"] * result["ambient_temp_deviation"]
    )
    result["speed_driving_interaction"] = (
        result["speed_kmh"] * result["driving_style_index"]
    )
    return result
