"""발표자료용 분석 차트 PNG를 docs/presentation_assets/에 생성한다.

실행: python scripts/export_presentation_assets.py
사전조건: models/energy_model.joblib (없으면 scripts/train_model.py 먼저 실행)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ev_logistics.config import (
    ADAPTER_CONFIG_JSON,
    ENERGY_CSV,
    ROUTE_GRADE_CSV,
    SERVICE_ROUTE_CSV,
    VEHICLE_CSV,
    adapter_config,
)
from ev_logistics.features import create_ev_features
from ev_logistics.model import load_energy_model

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "presentation_assets"
OUT.mkdir(parents=True, exist_ok=True)

BLUE, CYAN, GREEN = "#1670C0", "#2DB5D2", "#239970"
NAVY, ORANGE, RED, GRAY = "#0E1F35", "#E58A2B", "#D9534F", "#667585"

plt.rcParams.update({
    "font.family": "NanumGothic",
    "axes.unicode_minus": False,
    "figure.facecolor": "white",
    "axes.facecolor": "#F7FAFC",
    "axes.edgecolor": "#D1DDE8",
    "axes.titleweight": "bold",
    "axes.titlesize": 16,
    "font.size": 11,
})


def save(fig, name: str) -> None:
    fig.tight_layout()
    fig.savefig(OUT / name, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)


bundle = load_energy_model()
model, metrics = bundle["model"], bundle["metrics"]

# 1. 모델 성능
fig, axes = plt.subplots(1, 3, figsize=(12, 3.8))
values = [float(metrics["R2"]) * 100, float(metrics["MAE"]), float(metrics["RMSE"])]
for ax, value, label, unit, color in zip(
    axes, values,
    ["R² explanatory power", "MAE", "RMSE"],
    ["%", "kWh/100km", "kWh/100km"],
    [GREEN, CYAN, BLUE],
):
    ax.bar([label], [value], color=color, width=.55)
    ax.text(0, value, f"{value:.2f}\n{unit}", ha="center", va="bottom",
            fontsize=14, fontweight="bold", color=NAVY)
    ax.set_title(label)
    ax.spines[["top", "right"]].set_visible(False)
    ax.set_ylim(0, value * 1.28 if value else 1)
fig.suptitle("Saved Energy Model Performance", fontsize=19, fontweight="bold", color=NAVY)
save(fig, "01_model_performance.png")

# 2. 표준화 회귀계수 영향도
estimator = model[-1]
feature_names = bundle.get("features") or list(model.feature_names_in_)
coefficients = pd.Series(np.abs(estimator.coef_), index=feature_names).nlargest(12).sort_values()
fig, ax = plt.subplots(figsize=(9.5, 5.5))
ax.barh(coefficients.index, coefficients.values, color=BLUE)
ax.set_title("Top Feature Influence | Absolute Standardized Coefficients")
ax.set_xlabel("Absolute coefficient")
ax.spines[["top", "right"]].set_visible(False)
save(fig, "02_feature_influence.png")

# 3. 노선 고도·경사 프로파일
grade = pd.read_csv(ROUTE_GRADE_CSV)
fig, ax1 = plt.subplots(figsize=(12, 5.5))
ax1.plot(grade["trip_distance_from_start_km"], grade["elevation_m"], marker="o", color=BLUE, linewidth=2.3)
ax1.fill_between(grade["trip_distance_from_start_km"], grade["elevation_m"], alpha=.16, color=BLUE)
ax1.set_xlabel("Distance from Busan Port (km)")
ax1.set_ylabel("Elevation (m)", color=BLUE)
ax1.tick_params(axis="y", labelcolor=BLUE)
ax2 = ax1.twinx()
ax2.bar(grade["trip_distance_from_start_km"], grade["segment_average_grade_pct"], width=7, alpha=.45,
        color=np.where(grade["segment_average_grade_pct"] >= 0, GREEN, ORANGE))
ax2.axhline(0, color=GRAY, linewidth=.8)
ax2.set_ylabel("Segment average grade (%)", color=GRAY)
ax1.set_title("Busan Port → HJIT | Elevation and Segment Grade")
save(fig, "03_route_elevation_grade.png")

# 4. 구간별 에너지 예측 (대표 조건)
adapter = adapter_config()
service, training = adapter["service_domain"], adapter["training_domain"]
payload = float(np.interp(80.0, [service["payload_kg"]["min"], service["payload_kg"]["max"]],
                          [training["payload_kg"]["min"], training["payload_kg"]["max"]]))
tire = float(np.interp(9.1, [service["tire_pressure_bar"]["min"], service["tire_pressure_bar"]["max"]],
                       [training["tire_pressure_bar"]["min"], training["tire_pressure_bar"]["max"]]))
segments = grade[grade["segment_distance_km"] > 0].copy()
inputs = pd.DataFrame({
    "speed_kmh": 100.0, "payload_kg": payload, "ambient_temp_C": 20.0, "hvac_power_kw": 0.0,
    "road_grade_pct": segments["segment_average_grade_pct"].to_numpy(),
    "battery_temp_C": 30.0, "driving_style_index": 0.5, "tire_pressure_bar": tire,
    "trip_distance_km": segments["segment_distance_km"].to_numpy(),
})
rates = model.predict(create_ev_features(inputs)) * float(adapter["output_mapping"]["output_calibration_factor"])
segments["energy_kwh"] = rates * segments["segment_distance_km"].to_numpy() / 100
fig, ax = plt.subplots(figsize=(12, 5.5))
labels = [f"{int(row.sequence)}. {row.point_name}" for row in segments.itertuples()]
ax.bar(range(len(segments)), segments["energy_kwh"],
       color=np.where(segments["segment_average_grade_pct"] >= 0, BLUE, CYAN))
ax.set_xticks(range(len(segments)), labels, rotation=65, ha="right", fontsize=8)
ax.set_ylabel("Predicted segment energy (kWh)")
ax.set_title("Segment-by-Segment Energy Prediction | 100km/h, 80kg Payload")
ax.spines[["top", "right"]].set_visible(False)
save(fig, "04_segment_energy.png")

# 5. 충전소 이용 가능 여부와 확인 출력
route = pd.read_csv(SERVICE_ROUTE_CSV)
power = pd.to_numeric(route["max_verified_power_kw"], errors="coerce").fillna(0)
usable = route["service_usable_for_charging"].eq(1)
fig, ax = plt.subplots(figsize=(12, 5.5))
ax.scatter(route["trip_distance_from_start_km"], power, s=110,
           c=np.where(usable, GREEN, RED), edgecolor="white", linewidth=1.2)
for row, p in zip(route.itertuples(), power):
    offset = -18 if p >= 340 else 8
    ax.annotate(row.rest_area_name_ko, (row.trip_distance_from_start_km, p),
                xytext=(0, offset), textcoords="offset points", ha="center", fontsize=7, rotation=35)
ax.set_xlabel("Distance from Busan Port (km)")
ax.set_ylabel("Verified charger power (kW)")
ax.set_title("Rest-Area Charging Availability and Verified Power")
ax.set_ylim(-18, max(390, float(power.max()) * 1.08))
ax.spines[["top", "right"]].set_visible(False)
ax.text(.01, .97, "Green: usable  |  Red: excluded / unverified", transform=ax.transAxes, va="top", color=GRAY)
save(fig, "05_charging_stations.png")

# 6. 차량 fleet 요약
vehicles = pd.read_csv(VEHICLE_CSV)
fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
names = [f"{i + 1}" for i in range(len(vehicles))]
axes[0].bar(names, vehicles["tire_pressure_bar"], color=BLUE)
axes[0].set_title("Fleet Tire Pressure"); axes[0].set_xlabel("Vehicle number"); axes[0].set_ylabel("bar")
axes[0].set_ylim(8.4, 9.5)
axes[1].bar(names, vehicles["default_soc_pct"], color=GREEN)
axes[1].set_title("Vehicle Default SOC Reference"); axes[1].set_xlabel("Vehicle number"); axes[1].set_ylabel("%")
axes[1].set_ylim(0, 100)
for ax in axes:
    ax.spines[["top", "right"]].set_visible(False)
fig.suptitle("Volvo FH Electric Fleet Data", fontsize=18, fontweight="bold", color=NAVY)
save(fig, "06_vehicle_fleet.png")

# 7. 데이터셋 스키마 요약
energy = pd.read_csv(ENERGY_CSV)
summary = pd.DataFrame({
    "Feature": ["Speed", "Payload", "Ambient temp", "HVAC power", "Road grade",
                "Battery temp", "Driving style", "Tire pressure", "Trip distance"],
    "Column": ["speed_kmh", "payload_kg", "ambient_temp_C", "hvac_power_kw", "road_grade_pct",
               "battery_temp_C", "driving_style_index", "tire_pressure_bar", "trip_distance_km"],
})
fig, ax = plt.subplots(figsize=(11, 5.8))
ax.axis("off")
table = ax.table(cellText=summary.values, colLabels=summary.columns,
                 cellLoc="left", colLoc="left", loc="center", colWidths=[.32, .55])
table.auto_set_font_size(False); table.set_fontsize(11); table.scale(1, 1.55)
for (r, c), cell in table.get_celld().items():
    cell.set_edgecolor("#D1DDE8")
    if r == 0:
        cell.set_facecolor(BLUE); cell.get_text().set_color("white"); cell.get_text().set_weight("bold")
    else:
        cell.set_facecolor("#F7FAFC" if r % 2 else "white")
ax.set_title(f"ML Training Dataset Schema | {len(energy):,} rows",
             fontsize=18, fontweight="bold", color=NAVY, pad=18)
save(fig, "07_ml_dataset_schema.png")

print(f"exported {len(list(OUT.glob('*.png')))} images to {OUT}")
