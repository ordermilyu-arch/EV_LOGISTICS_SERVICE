"""에너지 소비 예측 모델 학습·저장·재사용.

노트북 실험(0828 분석 노트북)에서 가장 좋았던
Feature Engineering + StandardScaler + LinearRegression 조합을 사용한다.
"""

from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .config import BASE_FEATURES, ENERGY_CSV, MODEL_PATH, RANDOM_STATE, TARGET
from .features import create_ev_features


def train_energy_model(
    energy_csv: Path = ENERGY_CSV,
    model_path: Path = MODEL_PATH,
    save: bool = True,
) -> dict:
    """CSV로 모델을 학습하고 {'model', 'metrics', 'features'} 번들을 반환한다."""
    data = pd.read_csv(energy_csv).dropna(subset=BASE_FEATURES + [TARGET])
    engineered = create_ev_features(data)
    features = [column for column in engineered.columns if column != TARGET]

    x_train, x_test, y_train, y_test = train_test_split(
        engineered[features], data[TARGET],
        test_size=0.2, random_state=RANDOM_STATE,
    )
    model = make_pipeline(StandardScaler(), LinearRegression())
    model.fit(x_train, y_train)
    predictions = model.predict(x_test)
    metrics = {
        "R2": float(r2_score(y_test, predictions)),
        "MAE": float(mean_absolute_error(y_test, predictions)),
        "RMSE": float(np.sqrt(mean_squared_error(y_test, predictions))),
    }
    bundle = {"model": model, "metrics": metrics, "features": features}
    if save:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(bundle, model_path)
    return bundle


def load_energy_model(
    model_path: Path = MODEL_PATH,
    energy_csv: Path = ENERGY_CSV,
) -> dict:
    """저장된 모델을 불러오고, 없으면 학습해서 저장한 뒤 반환한다."""
    if model_path.exists():
        return joblib.load(model_path)
    return train_energy_model(energy_csv=energy_csv, model_path=model_path, save=True)
