"""프로젝트 공통 경로와 상수.

숫자 상수는 코드에 반복해서 적지 않고 `data/route_config_busan_port_hjit.json`에서
읽어 사용한다. 이 모듈은 그 파일 위치와, 파일에 없는 서비스 UI 상수만 정의한다.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parents[1]

DATA_DIR = PROJECT_ROOT / "data"
MODEL_DIR = PROJECT_ROOT / "models"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

ENERGY_CSV = DATA_DIR / "ev_energy_consumption.csv"
VEHICLE_CSV = DATA_DIR / "vehicles_volvo_fh_electric_10.csv"
SERVICE_ROUTE_CSV = DATA_DIR / "busan_port_hjit_service_route.csv"
ROUTE_GRADE_CSV = DATA_DIR / "busan_port_hjit_route_grade.csv"
ROUTE_CONFIG_JSON = DATA_DIR / "route_config_busan_port_hjit.json"
ADAPTER_CONFIG_JSON = DATA_DIR / "model_adapter_config.json"

MODEL_PATH = MODEL_DIR / "energy_model.joblib"

# --- 머신러닝 ---
TARGET = "energy_consumption_kwhper100km"
BASE_FEATURES = [
    "speed_kmh", "payload_kg", "ambient_temp_C", "hvac_power_kw",
    "road_grade_pct", "battery_temp_C", "driving_style_index",
    "tire_pressure_bar", "trip_distance_km",
]
RANDOM_STATE = 42

# 파생변수 기준값 (데이터의 물리적 해석을 위한 실험용 기준)
COMFORTABLE_AMBIENT_TEMP_C = 25.0
OPTIMAL_BATTERY_TEMP_C = 30.0
OPTIMAL_TIRE_PRESSURE_BAR = 2.4

# --- 서비스 UI 상수 (route_config JSON에 담기 애매한 값) ---
CARGO_SET_WEIGHT_KG = 10.0
CARGO_MIN_SETS = 3
CARGO_MAX_SETS = 10
DEPARTURE_SOC_OPTIONS = tuple(range(50, 91, 5))
DEFAULT_SPEED_KMH = 100.0
FIXED_DEPARTURE_HOUR = 10  # 배차일 오전 10:00 출발

USABLE_VEHICLE_STATUS = "NORMAL"


@lru_cache(maxsize=1)
def route_config() -> dict:
    """노선 공통 설정값(총거리·SOC·충전 상수)을 반환한다."""
    return json.loads(ROUTE_CONFIG_JSON.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def adapter_config() -> dict:
    """학습 스케일 ↔ 실제 트럭 스케일 보정 설정(데모용)을 반환한다."""
    return json.loads(ADAPTER_CONFIG_JSON.read_text(encoding="utf-8"))


def simulation_constants() -> dict:
    return route_config()["simulation_constants"]
