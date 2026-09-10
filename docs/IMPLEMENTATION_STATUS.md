# 구현 현황

`PROJECT_DATA_GUIDE.md`의 설계 요구사항과 현재 코드를 대조한 결과다.

## 구현 완료

| 기능 | 위치 | 비고 |
|---|---|---|
| 8자리 사원번호 검증 | `dispatch.validate_employee_id` | 빈값/비숫자/자릿수 구분 메시지 |
| 결정적 배차 (seed) | `dispatch.make_assignment_seed`, `create_dispatch` | SHA-256, 같은 입력 → 같은 결과 |
| 날씨·HVAC·SOC·운전성향·기본 화물량 생성 | `dispatch.create_dispatch` | SOC 50~90% 5% 단위, 화물 3~10박스 |
| HVAC 강제 ON/OFF | `dispatch.apply_hvac_control` | |
| 차량 CSV 로드, 개별/전체 조회 | `vehicles.load_vehicles`, `get_vehicle` | |
| 차량 상태(`vehicle_status`) 검증 | `vehicles.usable_vehicles` | `NORMAL`이 아닌 차량은 배정 제외 |
| 차량 변경 시 화물량 유지 | `app/app.py` (`cargo_count_input` 세션 유지) | |
| 노선 CSV 순서·누적거리 정렬 | `route.load_service_route` | 구간 경사 CSV 조인 |
| 충전 후보 필터 | `route.available_chargers` | `ev_charger_available`·`service_usable_for_charging`·출력 확인·`OUT_OF_SERVICE` 제외 |
| 충전 후보 제외 사유 표시 | `route.charger_status_view` | |
| 모델 학습/저장/재사용 | `model.train_energy_model`, `load_energy_model` | FE + StandardScaler + LinearRegression |
| 학습↔서비스 스케일 보정 | `adapter.adapt_model_input`, `output_calibration_factor` | 데모용 경고 문구 화면 표시 |
| 구간별 에너지 예측 | `simulation.predict_route_segments` | 17개 구간 개별 입력 |
| 구간별 SOC 계산, 안전 SOC 10% 판정 | `simulation.simulate_route` | 구간 경계 겹침까지 반영 |
| 충전 계획 (효율 92%, 목표 100%, 정차 7분) | `simulation.simulate_route` | 필요한 경우에만 충전 |
| ETA (주행 + 충전 + 정차) | `simulation.simulate_route` | 배차일 10:00 출발 기준 |
| 전체 연결 → 결과 dict 1개 | `simulation.run_service_simulation` | 스크립트·노트북·앱이 공통 사용 |
| Streamlit 화면 확장 | `app/app.py` | 배차 상세 / 에너지·충전 / 노선 / 충전소 4개 expander |
| 일일 배차기록 CSV·Excel 저장 | `assignments.py`, `app/app.py` | 세션 파일은 `outputs/`에 기록 |
| 차량 중복·예비차량·덮어쓰기 처리 | `assignments.save_dispatch` | |

## 남은 개선 항목

1. **충전 계획 최적화 수준** — 현재는 "안전 SOC를 못 지키는 직전 휴게소에서 100% 충전"하는
   그리디 방식이다. `PROJECT_DATA_GUIDE.md` 6절이 요구한 "이동시간 + 충전시간 + 진입/연결/출차
   시간을 모두 포함해 여러 후보 충전 계획을 비교"하는 탐색은 구현되어 있지 않다.
2. **배터리 온도** — 학습 피처에는 있으나 서비스 입력에서 `battery_temp_C = 30`(최적값) 고정.
   실차 데이터가 있으면 dispatch에서 생성하도록 확장.
3. **모델 보정의 근본 해결** — `model_adapter_config.json`은 승용 EV 학습 데이터를 대형
   전기트럭 스케일로 억지로 맞추는 데모 계층이다. 대형 전기트럭 실측 데이터로 재학습해야 한다.
4. **경사 데이터 정밀도** — 구간 시작·끝 고도 차이 기반 평균경사(Copernicus DEM ~90m)라
   구간 내부의 오르막·내리막이 상쇄된다. 실주행 GPS·고도 로그로 교체 시 정확도 향상.
5. **트리 모델·SHAP** — `01_energy_model_analysis.ipynb`에서 RandomForest·GradientBoosting까지
   비교하지만 XGBoost/LightGBM과 SHAP 해석은 향후 과제로 남겨 둠.
