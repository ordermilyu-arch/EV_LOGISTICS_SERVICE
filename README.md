# EV 물류 운행 지원 시스템 — 일일 물류 배송 조회 서비스

Volvo FH Electric 전기 트럭을 기준으로, **사원번호와 배차일만 입력하면**
차량 배정 → 에너지 소비량 예측 → 구간별 SOC 시뮬레이션 → 충전 계획 →
예상 도착시간까지 한 번에 계산하는 Streamlit 기반 물류 운영 서비스다.

부산항 신선대 컨테이너터미널에서 한진인천컨테이너터미널(HJIT)까지의
고정 노선(465.6km, 17개 구간)을 기준으로 차량·화물·운행환경·배터리 상태와
구간별 경사도를 반영해 운행 가능 여부를 판정한다.

---

## 핵심 기능

| 단계 | 설명 | 구현 |
|---|---|---|
| 결정적 배차 생성 | 사원번호 + 배차일을 SHA-256 seed로 변환해 동일 입력에 동일한 차량·SOC·운전성향·날씨 생성 | `dispatch.py` |
| 에너지 소비 예측 | 물리 기반 파생변수 + StandardScaler + Linear Regression으로 구간별 kWh/100km 예측 (R² 0.94) | `model.py`, `features.py` |
| SOC 시뮬레이션 | 17개 구간의 거리·평균경사를 개별 입력해 누적 소비에너지와 도착 SOC 계산 | `simulation.py` |
| 충전 계획 | 운영 가능한 휴게소만 후보로 두고, 필요한 경우에만 100%까지 충전 | `simulation.py` |
| ETA 계산 | 배차일 10:00 출발 기준으로 주행 + 충전 + 정차시간 합산 | `simulation.py` |
| 일일 배차기록 | 사원번호·차량번호·배차 허가 여부를 CSV / Excel로 저장 | `assignments.py` |

## 시스템 흐름

```text
8자리 사원번호 + 배차일
        │  SHA-256 seed
        ▼
create_dispatch      차량 / 화물 / 날씨·HVAC / 출발 SOC / 운전성향
        ▼
load_service_route   17개 구간 거리 + Copernicus DEM 기반 구간 평균경사
        ▼
adapt_model_input    실제 트럭 화물량·타이어 공기압 → 학습 데이터 범위로 변환
        ▼
predict_route_segments → simulate_route   구간별 에너지 · SOC · 충전 · ETA
        ▼
Streamlit 결과 화면 + 일일 배차기록 CSV/Excel
```

## 머신러닝 모델

- **파이프라인**: Feature Engineering + `StandardScaler` + `LinearRegression`
- **학습 데이터**: `data/ev_energy_consumption.csv` (8,000행), 타깃 `energy_consumption_kwhper100km`
- **성능** (test 20%, `random_state=42`)

  | 지표 | 값 | 화면 표기 |
  |---|---|---|
  | R² | 0.9417 | 모델 설명력 94.2% |
  | MAE | 0.705 kWh/100km | — |
  | RMSE | 0.887 kWh/100km | 예상 오차 ±0.89 kWh/100km |

- **실험 설계**: Baseline / Scaling / Feature Engineering / FE + Scaling 네 조합을
  동일 분할로 비교해 FE + Scaling / LinearRegression 조합을 선정
- **물리 기반 파생변수 7개**: 속도 제곱(공기저항), 외기온도 편차, 배터리 온도 편차,
  타이어 공기압 편차, 적재량 × 경사도, HVAC × 외기온도 편차, 속도 × 운전성향
- 학습된 모델은 `models/energy_model.joblib`로 저장해 서비스 실행 시 재학습 없이 재사용
  (`scripts/train_model.py`로 생성, 파일이 없으면 앱이 최초 실행 시 자동 학습)

## 노선 경사도 데이터 방법론

기존 노선 CSV에는 거리·충전기 정보만 있고 경사/고도 정보가 없어 `road_grade_pct = 0`을
고정 입력하던 문제를 다음과 같이 보완했다.

1. [OpenStreetMap Nominatim](https://nominatim.org/release-docs/latest/api/Search/)으로
   출발지·도착지·휴게소 16곳의 좌표 조회 (일부는 `서울방향` 명칭으로 재조회해 보정)
2. [Open-Meteo Elevation API](https://open-meteo.com/en/docs/elevation-api)
   (Copernicus DEM, 약 90m 해상도)로 각 지점 고도 조회
3. `구간 평균경사(%) = (도착 고도 − 출발 고도) / 구간 거리 × 100` 으로 계산 →
   `data/busan_port_hjit_route_grade.csv`
4. 모델에 17개 구간의 거리와 평균경사를 **개별 입력**해 구간별 소비율·소비에너지를
   예측하고 누적 (노선 전체를 하나의 평균값으로 처리하지 않음)

> **한계**: 구간 시작·끝 고도 차이 기반 평균경사이므로 구간 내부의 오르막·내리막이
> 상쇄될 수 있고, DEM 지표면 고도는 교량·터널의 실제 도로 높이와 다를 수 있다.

## 운영 기준

`data/route_config_busan_port_hjit.json`에서 읽어 사용한다.

| 항목 | 값 |
|---|---|
| 출발 시각 | 배차일 오전 10:00 |
| 노선 총거리 | 465.6 km |
| 평균 주행속도 | 100 km/h |
| 최소 안전 SOC | 10% |
| 충전 목표 SOC | 100% (충전이 필요한 경우) |
| 충전 효율 | 92% |
| 충전 1회 추가 정차시간 | 7분 |
| 충전 후보 제외 | 충전 출력 미확인 / `OUT_OF_SERVICE` 휴게소 |

## 기술 스택

Python 3.12 · Streamlit · scikit-learn · pandas · NumPy · joblib · XlsxWriter ·
[uv](https://github.com/astral-sh/uv)

## 프로젝트 구조

```text
EV_LOGISTICS_SERVICE/
├─ src/ev_logistics/          # 서비스 로직 (UI·스크립트가 공통으로 호출)
│  ├─ config.py               # 경로 + 상수 + route_config/adapter JSON 로더
│  ├─ features.py             # create_ev_features (파생변수 7개)
│  ├─ model.py                # train_energy_model / load_energy_model
│  ├─ dispatch.py             # 사원번호 검증, seed, create_dispatch
│  ├─ vehicles.py             # load_vehicles, usable_vehicles (vehicle_status 검증)
│  ├─ route.py                # 노선·휴게소 로드, 충전 후보 필터, 구간 경사 표
│  ├─ adapter.py              # 학습 ↔ 서비스 스케일 보정 (데모)
│  ├─ simulation.py           # predict_route_segments, simulate_route, run_service_simulation
│  └─ assignments.py          # 일일 배차기록 저장·중복 처리
├─ app/app.py                 # Streamlit 화면 (로직 없음)
├─ scripts/
│  ├─ train_model.py          # 모델 학습 → models/energy_model.joblib
│  └─ run_simulation.py       # CLI로 한 건 시뮬레이션
├─ tests/test_service.py      # 스모크 테스트 7개
├─ data/                      # ML 학습 CSV, 차량·노선·경사 CSV, 설정 JSON 2개
├─ models/                    # energy_model.joblib (git 제외, 스크립트로 생성)
└─ outputs/                   # 세션별 배차기록·시뮬레이션 결과 (git 제외)
```

## 실행 방법

### uv 사용

```bash
uv sync                                   # 의존성 설치
uv run python scripts/train_model.py      # 모델 학습 (선택 - 앱이 자동 학습도 함)
uv run streamlit run app/app.py           # 서비스 실행

uv run python scripts/run_simulation.py 12345678 2026-08-28   # CLI 한 건
uv run --group dev python -m pytest -q                         # 테스트
```

### pip 사용

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
streamlit run app/app.py
```

### VS Code에서 실행

`Terminal → New Terminal` 을 열고 위 `pip 사용` 또는 `uv 사용` 명령을 그대로 입력한다.
`F5`(디버그 실행)로는 Streamlit 앱이 뜨지 않으므로 반드시 터미널에서 `streamlit run` 을 쓴다.

### 실행 시 주의

- **반드시 `streamlit run app/app.py`** 로 실행한다. `python app/app.py` 로 직접 실행하면
  웹 서버가 뜨지 않고 `missing ScriptRunContext! ... running in bare mode` 경고만 출력되고 끝난다.
- `.streamlit/config.toml` 은 배포용으로 `headless = true` 라서 브라우저가 자동으로 열리지
  않는다. 터미널에 표시되는 `Local URL: http://localhost:8501` 을 직접 브라우저에 입력한다.
  종료는 `Ctrl+C`.
- `models/energy_model.joblib` 이 없으면 앱이 최초 실행 시 자동으로 학습해 생성한다(수 초).
  미리 만들려면 `python scripts/train_model.py`.

## 참고 논문

- [Electric vehicle routing problem with machine learning for energy prediction](https://www.sciencedirect.com/science/article/pii/S0191261520304549) — 에너지 예측·SOC·충전 판단 흐름
- [Energy consumption analysis and prediction of electric vehicles based on real-world driving data](https://www.sciencedirect.com/science/article/pii/S030626192030920X) — 속도·온도·운전조건을 모델 입력으로 구성
- [Adaptive Routing and Recharging Policies for Electric Vehicles](https://pubsonline.informs.org/doi/10.1287/trsc.2016.0724) — 휴게소 필터링과 안전 SOC 기준

## 한계 및 향후 개선

- 모델 스케일 보정(`data/model_adapter_config.json`)은 **데모 시연용**이다. 승용 EV 학습
  데이터를 대형 전기트럭 스케일로 맞추는 계층으로, 실제 정확도를 주장하려면 대형
  전기트럭 실측 데이터로 재학습해야 한다.
- 충전 계획은 "안전 SOC를 못 지키는 직전 휴게소에서 100% 충전"하는 그리디 방식으로,
  여러 충전 조합의 총 도착시간을 비교하는 최적화는 향후 과제다.
- 서비스 입력에서 `battery_temp_C = 30`(최적값) 고정. 실차 데이터가 있으면 확장 가능.
- 구간 평균경사는 DEM 유도값이며, 트리 모델(XGBoost/LightGBM)·SHAP 해석은 남겨 두었다.
