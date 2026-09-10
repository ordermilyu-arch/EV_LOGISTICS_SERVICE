"""에너지 소비 모델을 학습하고 models/energy_model.joblib로 저장한다.

실행: python scripts/train_model.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ev_logistics.config import MODEL_PATH
from ev_logistics.model import train_energy_model


def main() -> None:
    bundle = train_energy_model(save=True)
    metrics = bundle["metrics"]
    print(f"저장 완료: {MODEL_PATH}")
    print(
        f"R2={metrics['R2']:.4f}  MAE={metrics['MAE']:.4f}  RMSE={metrics['RMSE']:.4f}"
    )
    print(f"피처 {len(bundle['features'])}개")


if __name__ == "__main__":
    main()
