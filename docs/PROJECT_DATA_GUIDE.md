# EV 물류 운행 지원 시스템 - 데이터 구성 가이드

## 1. 이 문서의 목적

이 프로젝트는 Volvo FH Electric 기반의 전기 물류 트럭 운행 지원 시스템이다.

사용자가 8자리 사원번호를 입력하면 가상의 차량/화물/운행환경을 배정하고,
머신러닝으로 전력 소비량을 예측한 뒤 부산항 신선대 컨테이너터미널에서
한진인천컨테이너터미널(HJIT)까지의 고정 노선을 기준으로 충전 휴게소와 예상 도착시간을 계산한다.

---

## 2. VS Code 프로젝트에 넣을 데이터 파일

아래 4개 데이터 파일은 모두 프로젝트에 포함한다.

```text
data/
├─ vehicles_volvo_fh_electric_10.csv
├─ busan_port_hjit_service_route.csv
├─ route_config_busan_port_hjit.json
└─ model_adapter_config.json
```

이 MD 파일은 프로젝트 루트 또는 `docs/` 폴더에 둔다.

```text
docs/
└─ PROJECT_DATA_GUIDE.md
```

---

## 3. 각 파일의 역할

### `vehicles_volvo_fh_electric_10.csv`

Volvo FH Electric 10대의 가상 차량 데이터.

주요 역할:

- 사원번호 입력 후 1~10호차 중 기본 차량 배정
- 사용자가 차량을 변경할 때 선택 목록으로 사용
- 차량별 `tire_pressure_bar` 값을 ML 입력에 사용
- 배터리 용량 / 충전 최대 출력 / 기본 SOC 제공

차량 10대는 같은 Volvo FH Electric을 사용하되,
프로젝트에서는 타이어 공기압을 서로 다르게 설정한다.

---

### `busan_port_hjit_service_route.csv`

부산 → 인천 고정 물류 노선의 휴게소 데이터.

고정 노선:

```text
부산항 신선대 컨테이너터미널
→ 경부고속도로 부산기점
→ 경부고속도로 서울방향
→ 신갈JC
→ 영동고속도로 인천방향
→ 월곶JC
→ 제3경인고속화도로
→ 인천신항
→ 한진인천컨테이너터미널(HJIT)
```

CSV에는 다음 정보가 들어 있다.

- 휴게소 순서
- 누적거리
- 이전 휴게소에서의 거리
- EV 충전 가능 여부
- 확인된 충전기 출력
- 서비스에서 사용할 충전기 상태

프로젝트 규칙:

```text
충전기 출력 정보가 확인되지 않음
→ OUT_OF_SERVICE
→ 충전 추천 후보에서 제외
```

원본 데이터의 NULL 의미는 유지하고,
서비스용 CSV에서만 고장 상태로 해석한다.

---

### `route_config_busan_port_hjit.json`

노선 전체에서 공통으로 사용하는 설정값.

주요 값:

```text
출발지:
부산항 신선대 컨테이너터미널

도착지:
한진인천컨테이너터미널(HJIT)

프로젝트 고정 총거리:
465.6 km

기본 출발 SOC:
90% (route_config의 default_departure_soc_pct)
서비스 화면에서는 사원번호+배차일 seed로 50~90% 중 5% 단위 자동 배정

최소 안전 SOC:
10%

평균 주행속도:
100 km/h (simulation_average_speed_kmh)

최대 충전 목표 SOC:
100% (maximum_charge_target_soc_pct)
충전 정차가 발생하면 다음 운행을 위해 100%까지 채운다

충전 효율:
92%

충전 1회 추가 정차시간:
7분
```

이 값들은 Python 코드에 직접 숫자를 반복해서 적지 말고
JSON에서 불러와 사용한다(`src/ev_logistics/config.py`가 이 파일을 읽는다).

---

### `model_adapter_config.json`

현재 머신러닝 모델과 실제 Volvo FH Electric 서비스 입력값 사이를 연결한다.

현재 ML 학습 데이터의:

- 화물량
- 타이어 공기압
- 전력소비량

스케일이 실제 대형 전기트럭과 다르기 때문에
서비스 입력값을 기존 모델의 범위에 맞게 변환하기 위한 설정 파일이다.

주의:

이 보정은 미니 프로젝트 시연용이다.

실제 물류 서비스 수준의 정확도를 주장하려면
향후 대형 전기트럭 실측 데이터로 다시 학습해야 한다.

---

## 4. 실제 프로젝트 폴더 구조

이 가이드가 처음 제안한 모듈 분할(`assignment.py`, `vehicle.py`, `route.py`,
`energy_predictor.py`, `soc_simulator.py`, `charging_optimizer.py`, `eta.py`,
`simulation.py`)은 아래 `src/ev_logistics/` 패키지로 구현되어 있다.

```text
EV_LOGISTICS_SERVICE/
│
├─ data/
│   ├─ ev_energy_consumption.csv
│   ├─ vehicles_volvo_fh_electric_10.csv
│   ├─ busan_port_hjit_service_route.csv
│   ├─ busan_port_hjit_route_grade.csv
│   ├─ route_config_busan_port_hjit.json
│   └─ model_adapter_config.json
│
├─ models/                 # energy_model.joblib (scripts/train_model.py로 생성)
├─ outputs/                # 세션별 배차기록·시뮬레이션 결과 (git 제외)
│
├─ src/ev_logistics/
│   ├─ config.py           # 경로 + 상수 + route_config/adapter JSON 로더
│   ├─ features.py         # create_ev_features (파생변수 7개)
│   ├─ model.py            # train_energy_model / load_energy_model
│   ├─ dispatch.py         # 사원번호 검증, seed, create_dispatch (← assignment.py)
│   ├─ vehicles.py         # load_vehicles, usable_vehicles (← vehicle.py)
│   ├─ route.py            # 노선/휴게소 로드, 충전 후보 필터 (← route.py)
│   ├─ adapter.py          # adapt_model_input (← energy_predictor.py)
│   ├─ simulation.py       # predict_route_segments, simulate_route,
│   │                      #   run_service_simulation
│   │                      #   (← soc_simulator + charging_optimizer + eta + simulation)
│   └─ assignments.py      # 일일 배차기록 저장·중복 처리
│
├─ app/app.py              # Streamlit 화면 (로직 없음, 패키지만 호출)
├─ scripts/
│   ├─ train_model.py
│   ├─ run_simulation.py
│   ├─ export_presentation_assets.py
│   └─ create_presentation.py
├─ notebooks/
│   ├─ 01_energy_model_analysis.ipynb
│   └─ 02_service_simulation_demo.ipynb
├─ docs/
└─ README.md
```

---

## 5. 서비스 흐름

```text
8자리 사원번호 입력
        ↓
assignment.py
        ↓
오늘의 가상 배차 생성
        ↓
차량 / 화물 / 날씨 / HVAC
        ↓
사용자가 차량 변경 가능
사용자가 화물량 변경 가능
        ↓
energy_predictor.py
        ↓
예상 kWh/100km
        ↓
route.py
        ↓
고정 노선 및 휴게소 로드
        ↓
soc_simulator.py
        ↓
구간별 SOC 계산
        ↓
charging_optimizer.py
        ↓
가장 빠른 충전 계획 계산
        ↓
eta.py
        ↓
예상 도착시간 계산
        ↓
simulation.py
        ↓
전체 결과 반환
        ↓
Streamlit / Gradio
```

---

## 6. 중요한 설계 규칙

### 사원번호

```text
8자리 숫자
```

사원번호 + 날짜를 seed로 사용하여:

- 차량
- 화물량
- 날씨
- HVAC

를 가상 생성한다.

같은 날짜에 같은 사원번호를 입력하면 같은 배차가 나오도록 한다.

---

### 차량

기본 차량은 자동 배정하지만 사용자가 1~10호차 중 변경 가능하다.

차량을 변경하면:

```text
tire_pressure_bar 변경
→ ML 입력 변경
→ 예상 소비전력 변경
→ SOC 계산 변경
→ 충전 계획 변경 가능
```

화물량은 차량을 변경해도 유지한다.

---

### 화물

초기 화물량은 가상 배정한다.

사용자는 서비스 화면에서 화물 무게를 직접 수정할 수 있다.

---

### 날씨 / HVAC

가상 환경은 다음 세 종류를 사용한다.

```text
추운 날
→ 난방 ON

기본
→ HVAC OFF

더운 날
→ 냉방 ON
```

이 값은 단순 표시용이 아니라 ML 입력값에 사용한다.

---

### 충전 휴게소

충전 후보가 되려면:

```text
ev_charger_available == 1
AND
service_usable_for_charging == 1
```

이어야 한다.

충전기 출력 정보가 없는 휴게소는 프로젝트에서 고장으로 취급한다.

---

### 안전 SOC

```text
minimum_reserve_soc_pct = 10
```

다음 구간 도착 예상 SOC가 10% 미만이라면
그 구간을 안전하게 도달할 수 없는 것으로 판단한다.

---

### 충전 목표

충전이 필요한 경우 100%까지 충전한다.

주행 중 충전 횟수는 목적지 도착 가능 조건을 만족하는 최소 횟수로 계획한다.

---

### 최적화 목표

이 프로젝트의 목표는:

```text
충전 횟수 최소화
```

만이 아니라

```text
총 예상 도착시간 최소화
```

이다.

따라서:

- 이동시간
- 충전시간
- 충전소 진입/연결/출차시간

을 모두 포함하여 후보 충전 계획을 비교한다.

---

## 7. 설계 항목 ↔ 구현 위치

| 이 가이드가 요구한 기능 | 구현 위치 |
|---|---|
| 8자리 사원번호 검증, seed, 날씨·HVAC·화물량 생성 | `src/ev_logistics/dispatch.py` |
| 차량 CSV 로드, 개별/전체 조회, 차량 변경, 상태 검증 | `src/ev_logistics/vehicles.py` |
| 노선 CSV·route_config 로드, 충전 휴게소 필터 | `src/ev_logistics/route.py` |
| ML 모델 로드, model_adapter 변환, 서비스 소비량 반환 | `src/ev_logistics/model.py` + `adapter.py` |
| 구간별 SOC 계산 | `src/ev_logistics/simulation.py::simulate_route` |
| 충전 계획(도달 가능·고장 제외·출력·충전량·시간) | `src/ev_logistics/simulation.py::simulate_route` |
| ETA(주행 + 충전 + 정차 부가시간) | `src/ev_logistics/simulation.py::simulate_route` |
| 전체 연결(하나의 결과 dict 반환) | `src/ev_logistics/simulation.py::run_service_simulation` |
| Streamlit UI | `app/app.py` |

남은 개선 항목은 `docs/IMPLEMENTATION_STATUS.md`를 참고한다.
