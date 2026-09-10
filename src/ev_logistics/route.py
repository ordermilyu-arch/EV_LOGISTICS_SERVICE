"""고정 노선(부산항 신선대 → HJIT)의 휴게소·충전기·구간 경사 처리."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .config import ROUTE_GRADE_CSV, SERVICE_ROUTE_CSV, route_config


def load_service_route(
    service_route_csv: Path = SERVICE_ROUTE_CSV,
    route_grade_csv: Path = ROUTE_GRADE_CSV,
) -> pd.DataFrame:
    """휴게소 CSV를 순서·누적거리로 정렬하고 구간 경사 정보를 결합한다."""
    route = pd.read_csv(service_route_csv)
    grade = pd.read_csv(route_grade_csv)
    route = route.merge(
        grade[[
            "point_name", "latitude", "longitude", "elevation_m",
            "segment_average_grade_pct", "grade_data_quality",
        ]],
        left_on="rest_area_name_ko", right_on="point_name", how="left",
        validate="one_to_one",
    ).drop(columns="point_name")
    route["trip_distance_from_start_km"] = pd.to_numeric(
        route["trip_distance_from_start_km"], errors="coerce"
    )
    route["max_verified_power_kw"] = pd.to_numeric(
        route["max_verified_power_kw"], errors="coerce"
    )
    return route.sort_values(
        ["sequence", "trip_distance_from_start_km"]
    ).reset_index(drop=True)


def load_route_grade(route_grade_csv: Path = ROUTE_GRADE_CSV) -> pd.DataFrame:
    return pd.read_csv(route_grade_csv)


def available_chargers(route_rows: pd.DataFrame) -> pd.DataFrame:
    """프로젝트 규칙을 모두 만족하는 실제 충전 후보만 반환한다.

    - `ev_charger_available == 1`
    - `service_usable_for_charging == 1`
    - 확인된 충전 출력(`max_verified_power_kw`)이 있음
    - `service_charger_status`가 `OUT_OF_SERVICE`가 아님
    """
    status = route_rows["service_charger_status"].astype(str).str.upper()
    usable = route_rows.loc[
        (route_rows["ev_charger_available"] == 1)
        & (route_rows["service_usable_for_charging"] == 1)
        & route_rows["max_verified_power_kw"].notna()
        & (status != "OUT_OF_SERVICE")
    ].copy()
    return usable.sort_values("trip_distance_from_start_km").reset_index(drop=True)


def charger_status_view(route_rows: pd.DataFrame) -> pd.DataFrame:
    """모든 휴게소와 충전 후보 제외 사유를 화면 표시용으로 정리한다."""
    view = route_rows.copy()

    def reason(row: pd.Series) -> str:
        if row["ev_charger_available"] != 1:
            return "EV 충전기 없음"
        if row["service_usable_for_charging"] != 1:
            return "서비스 사용 불가"
        if pd.isna(row["max_verified_power_kw"]):
            return "충전 출력 미확인"
        if str(row["service_charger_status"]).upper() == "OUT_OF_SERVICE":
            return "운영 불가"
        return "추천 가능"

    view["추천 상태"] = view.apply(reason, axis=1)
    return view


def build_route_grade_view(
    grade_rows: pd.DataFrame,
    segment_predictions: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """노선 순서에 맞춘 구간별 거리·고도·경사 표시표를 생성한다."""
    ordered = grade_rows.sort_values("sequence").reset_index(drop=True).copy()
    view = ordered.loc[ordered["sequence"] > 0].copy()
    view["출발지"] = ordered["point_name"].shift(1).loc[view.index]
    view["출발 고도(m)"] = ordered["elevation_m"].shift(1).loc[view.index]
    view["고도차(m)"] = view["elevation_m"] - view["출발 고도(m)"]
    view["경사각도(°)"] = np.degrees(
        np.arctan(view["segment_average_grade_pct"] / 100.0)
    )
    view["구간 유형"] = np.select(
        [
            view["segment_average_grade_pct"] > 0.01,
            view["segment_average_grade_pct"] < -0.01,
        ],
        ["오르막", "내리막"],
        default="평지",
    )
    if segment_predictions is not None:
        view = view.merge(
            segment_predictions[[
                "sequence", "predicted_kwh_per_100km", "predicted_energy_kwh",
            ]],
            on="sequence", how="left", validate="one_to_one",
        )
    view = view.rename(columns={
        "sequence": "순서",
        "point_name": "도착지",
        "segment_distance_km": "구간거리(km)",
        "elevation_m": "도착 고도(m)",
        "segment_average_grade_pct": "평균경사(%)",
        "predicted_kwh_per_100km": "예상 소비율(kWh/100km)",
        "predicted_energy_kwh": "구간 소비에너지(kWh)",
    })
    columns = [
        "순서", "출발지", "도착지", "구간거리(km)",
        "출발 고도(m)", "도착 고도(m)", "고도차(m)",
        "평균경사(%)", "경사각도(°)", "구간 유형",
    ]
    numeric_columns = [
        "구간거리(km)", "출발 고도(m)", "도착 고도(m)",
        "고도차(m)", "평균경사(%)", "경사각도(°)",
    ]
    if segment_predictions is not None:
        columns.extend(["예상 소비율(kWh/100km)", "구간 소비에너지(kWh)"])
        numeric_columns.extend(["예상 소비율(kWh/100km)", "구간 소비에너지(kWh)"])
    view[numeric_columns] = view[numeric_columns].round(3)
    return view[columns]


def route_summary() -> dict:
    """화면 요약용 노선 상수."""
    config = route_config()
    return {
        "route_name": config["route_name"],
        "start_name": config["start"]["name"],
        "destination_name": config["destination"]["name"],
        "total_route_distance_km": float(config["total_route_distance_km"]),
    }
