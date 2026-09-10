"""학습 데이터(승용 EV 스케일) ↔ 서비스 입력(대형 전기트럭 스케일) 보정.

이 보정은 미니 프로젝트 시연용이다. 실제 물류 서비스 수준의 정확도를 주장하려면
대형 전기트럭 실측 데이터로 다시 학습해야 한다.
"""

from __future__ import annotations

import numpy as np

from .config import adapter_config


def adapt_model_input(
    payload_kg: float,
    tire_pressure_bar: float,
    adapter: dict | None = None,
) -> tuple[float, float]:
    """실제 트럭 화물량·타이어 공기압을 학습 데이터 범위로 선형 변환한다."""
    adapter = adapter or adapter_config()
    service = adapter["service_domain"]
    training = adapter["training_domain"]
    model_payload = np.interp(
        payload_kg,
        [service["payload_kg"]["min"], service["payload_kg"]["max"]],
        [training["payload_kg"]["min"], training["payload_kg"]["max"]],
    )
    model_tire = np.interp(
        tire_pressure_bar,
        [service["tire_pressure_bar"]["min"], service["tire_pressure_bar"]["max"]],
        [training["tire_pressure_bar"]["min"], training["tire_pressure_bar"]["max"]],
    )
    return float(model_payload), float(model_tire)


def output_calibration_factor(adapter: dict | None = None) -> float:
    """모델 raw 출력을 서비스 표시값(kWh/100km)으로 바꾸는 보정계수."""
    adapter = adapter or adapter_config()
    return float(adapter["output_mapping"]["output_calibration_factor"])


def demo_warning(adapter: dict | None = None) -> str:
    adapter = adapter or adapter_config()
    return adapter["warning"]
