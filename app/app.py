"""일일 물류 배송 조회 - Streamlit 화면.

서비스 로직은 모두 `ev_logistics` 패키지에 있고, 이 파일은 입력/표시만 담당한다.
실행: 프로젝트 루트에서 `streamlit run app/app.py`
"""

from __future__ import annotations

import io
import sys
from datetime import date, datetime, time
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from ev_logistics.adapter import demo_warning
from ev_logistics.assignments import (
    has_available_vehicle,
    load_assignments,
    new_session_assignment_path,
    save_dispatch,
)
from ev_logistics.config import (
    CARGO_SET_WEIGHT_KG,
    DEFAULT_SPEED_KMH,
    FIXED_DEPARTURE_HOUR,
    route_config,
)
from ev_logistics.dispatch import (
    apply_hvac_control,
    create_dispatch,
    driving_style_label,
    validate_employee_id,
)
from ev_logistics.model import load_energy_model
from ev_logistics.route import (
    build_route_grade_view,
    charger_status_view,
    load_route_grade,
    load_service_route,
    route_summary,
)
from ev_logistics.simulation import predict_route_segments, simulate_route
from ev_logistics.vehicles import load_vehicles


@st.cache_data
def cached_vehicles() -> pd.DataFrame:
    return load_vehicles()


@st.cache_data
def cached_service_route() -> pd.DataFrame:
    return load_service_route()


@st.cache_data
def cached_route_grade() -> pd.DataFrame:
    return load_route_grade()


@st.cache_resource
def cached_model() -> dict:
    return load_energy_model()


def reset_to_main_screen() -> None:
    for key in [
        "dispatch", "saved_row", "message", "pending_overwrite",
        "employee_id_input", "locked_employee_id", "locked_dispatch_date",
    ]:
        st.session_state.pop(key, None)


st.set_page_config(page_title="EV 물류 운행 지원", page_icon="⚡", layout="wide")

if "session_assignment_path" not in st.session_state:
    st.session_state["session_assignment_path"] = str(new_session_assignment_path())
SESSION_ASSIGNMENT_PATH = Path(st.session_state["session_assignment_path"])

st.title("일일 물류 배송 조회")

try:
    vehicles = cached_vehicles()
    route = route_config()
    route_rows = cached_service_route()
    route_grade_rows = cached_route_grade()
    model_bundle = cached_model()
except Exception as error:  # noqa: BLE001 - 화면에 원인을 그대로 보여준다.
    st.error(f"데이터 또는 모델을 불러오지 못했습니다: {error}")
    st.stop()

model = model_bundle["model"]
metrics = model_bundle["metrics"]
lookup_locked = "dispatch" in st.session_state

with st.sidebar:
    st.header("사원번호 조회")
    with st.form("employee_lookup_form", clear_on_submit=False):
        if lookup_locked:
            locked = st.session_state["dispatch"]
            employee_id_input = st.text_input(
                "8자리 사원번호", value=locked["employee_id"],
                max_chars=8, key="locked_employee_id", disabled=True,
            )
            dispatch_date = st.date_input(
                "배차일", value=date.fromisoformat(locked["assignment_date"]),
                key="locked_dispatch_date", disabled=True,
            )
        else:
            employee_id_input = st.text_input(
                "8자리 사원번호", value="", max_chars=8, key="employee_id_input",
            )
            dispatch_date = st.date_input("배차일", value=date.today())
        lookup_button = st.form_submit_button(
            "사원번호 조회", type="primary", use_container_width=True,
            disabled=lookup_locked,
        )
    if lookup_locked:
        st.button(
            "메인화면으로 돌아가기", use_container_width=True,
            on_click=reset_to_main_screen,
        )

if lookup_button:
    try:
        employee_id = validate_employee_id(employee_id_input)
        dispatch = create_dispatch(employee_id, dispatch_date.isoformat())
        default_vehicle = vehicles.iloc[dispatch["seed"] % len(vehicles)]
        message, saved_row = save_dispatch(
            dispatch, default_vehicle["vehicle_id"],
            dispatch["default_cargo_set_count"],
            assignment_path=SESSION_ASSIGNMENT_PATH,
        )
        st.session_state["dispatch"] = dispatch
        st.session_state["saved_row"] = saved_row.to_dict()
        st.session_state["message"] = message
        st.session_state["cargo_count_input"] = dispatch["default_cargo_set_count"]
        st.session_state["speed_input"] = DEFAULT_SPEED_KMH
        st.rerun()
    except ValueError as error:
        st.error(str(error))

if "dispatch" in st.session_state:
    dispatch = st.session_state["dispatch"]
    saved_row = pd.Series(st.session_state["saved_row"])
    saved_vehicle_id = saved_row.get("vehicle_id")
    default_index = (
        vehicles["vehicle_id"].tolist().index(saved_vehicle_id)
        if saved_vehicle_id in set(vehicles["vehicle_id"]) else 0
    )

    with st.sidebar:
        st.header("운행 조건")
        vehicle_name = st.selectbox(
            "차량 변경", vehicles["display_name"].tolist(), index=default_index
        )
        max_sets = int(
            float(vehicles.iloc[default_index]["project_max_payload_kg"])
            // CARGO_SET_WEIGHT_KG
        )
        cargo_set_count = st.number_input(
            f"화물 박스 수 (1박스 = {CARGO_SET_WEIGHT_KG:.0f}kg)",
            0, max_sets, key="cargo_count_input", step=1,
        )
        speed_kmh = st.number_input(
            "평균 속도 (km/h)", 20, 130, key="speed_input", step=5, format="%d"
        )
        hvac_control = st.selectbox(
            "HVAC 제어", ["자동(날씨 기준)", "강제 ON", "강제 OFF"]
        )
        update_button = st.button("조건 저장 및 다시 예측", use_container_width=True)

    if update_button:
        requested_vehicle_id = vehicles.loc[
            vehicles["display_name"].eq(vehicle_name), "vehicle_id"
        ].iloc[0]
        controlled = apply_hvac_control(dispatch, hvac_control)
        pending = {
            "dispatch": controlled,
            "requested_vehicle_id": requested_vehicle_id,
            "cargo_set_count": int(cargo_set_count),
        }
        if has_available_vehicle(controlled, SESSION_ASSIGNMENT_PATH):
            message, saved_row = save_dispatch(
                controlled, requested_vehicle_id, int(cargo_set_count),
                assignment_path=SESSION_ASSIGNMENT_PATH,
            )
            st.session_state["dispatch"] = controlled
            st.session_state["saved_row"] = saved_row.to_dict()
            st.session_state["message"] = message
            st.rerun()
        st.session_state["pending_overwrite"] = pending
        st.rerun()

if "pending_overwrite" in st.session_state:
    pending = st.session_state["pending_overwrite"]

    @st.dialog("이미 배정된 차량입니다")
    def confirm_overwrite_dialog() -> None:
        st.warning("현재 실행의 모든 차량이 사용 중입니다.")
        st.write("기존 배정값을 삭제하고 선택한 조건으로 덮어쓰시겠습니까?")
        confirm, cancel = st.columns(2)
        for label, do_overwrite, button in (
            ("확인: 덮어쓰기", True, confirm),
            ("취소: 예비차량 저장", False, cancel),
        ):
            if button.button(label, use_container_width=True, type="primary" if do_overwrite else "secondary"):
                message, saved_row = save_dispatch(
                    pending["dispatch"], pending["requested_vehicle_id"],
                    pending["cargo_set_count"],
                    assignment_path=SESSION_ASSIGNMENT_PATH,
                    overwrite_confirmed=do_overwrite,
                )
                st.session_state["saved_row"] = saved_row.to_dict()
                st.session_state["dispatch"] = pending["dispatch"]
                st.session_state["message"] = message
                del st.session_state["pending_overwrite"]
                st.rerun()

    confirm_overwrite_dialog()

if "dispatch" in st.session_state:
    dispatch = st.session_state["dispatch"]
    saved_row = pd.Series(st.session_state["saved_row"])
    cargo_set_count = int(saved_row.get("cargo_set_count", 0))
    selected_vehicle_id = saved_row.get("vehicle_id")
    selected_vehicle = vehicles.loc[vehicles["vehicle_id"].eq(selected_vehicle_id)]
    vehicle_tire = 9.0 if selected_vehicle.empty else float(
        selected_vehicle.iloc[0]["tire_pressure_bar"]
    )
    vehicle_empty_weight = 0.0 if selected_vehicle.empty else float(
        selected_vehicle.iloc[0]["project_combination_empty_weight_kg"]
    )

    if saved_row["assignment_status"] == "RESERVE":
        st.warning("모든 차량이 사용 중이어서 예비차량으로 저장되었습니다.")
    else:
        st.success(st.session_state["message"])

    segment_predictions = predict_route_segments(
        model=model,
        grade_rows=route_grade_rows,
        payload_kg=cargo_set_count * CARGO_SET_WEIGHT_KG,
        tire_pressure_bar=vehicle_tire,
        speed_kmh=st.session_state.get("speed_input", DEFAULT_SPEED_KMH),
        dispatch=dispatch,
    )
    total_energy = float(segment_predictions["predicted_energy_kwh"].sum())
    total_distance = route_summary()["total_route_distance_km"]
    prediction = total_energy / total_distance * 100.0
    route_average_grade = float(np.average(
        segment_predictions["segment_average_grade_pct"],
        weights=segment_predictions["segment_distance_km"],
    ))
    battery_usable = float(saved_row.get("battery_usable_kwh", 460.0))
    if pd.isna(battery_usable):
        battery_usable = 460.0
    departure_soc = float(saved_row.get("battery_soc_pct", dispatch["battery_soc_pct"]))
    if pd.isna(departure_soc):
        departure_soc = dispatch["battery_soc_pct"]
    simulation = simulate_route(
        segment_predictions, battery_usable, departure_soc, route_rows,
        datetime.combine(
            date.fromisoformat(dispatch["assignment_date"]),
            time(FIXED_DEPARTURE_HOUR, 0),
        ),
    )

    date_text = datetime.strptime(dispatch["assignment_date"], "%Y-%m-%d").strftime("%y.%m.%d")
    st.subheader(f"{date_text} / 운행 정보")

    row1 = st.columns(2)
    row1[0].markdown(f'**사원번호**<br><span style="font-size:1.15rem">{dispatch["employee_id"]}</span>', unsafe_allow_html=True)
    row1[1].markdown(f'**차량번호**<br><span style="font-size:1.15rem">{saved_row["vehicle_display_name"]}</span>', unsafe_allow_html=True)
    row2 = st.columns(2)
    row2[0].markdown(f'**출발 배터리 SOC**<br><span style="font-size:1.15rem">{dispatch["battery_soc_pct"]:.0f}%</span>', unsafe_allow_html=True)
    row2[1].markdown(
        f'**화물 박스 / 총 화물량**<br><span style="font-size:1.15rem">'
        f'{cargo_set_count:,}박스 / {cargo_set_count * CARGO_SET_WEIGHT_KG:,.1f} kg</span>',
        unsafe_allow_html=True,
    )

    if simulation["charges"]:
        recommendations = []
        for charge in simulation["charges"]:
            matching_leg = next(
                (leg for leg in simulation["legs"] if str(leg["구간"]).startswith(f'{charge["휴게소"]} →')),
                None,
            )
            next_stop = matching_leg["구간"].split(" → ", 1)[1] if matching_leg else "다음 구간"
            recommendations.append(f'{charge["휴게소"]} ~ {next_stop}<br>사이의 휴게소를 이용하세요')
        charger_recommendation = "<br>".join(recommendations)
    else:
        charger_recommendation = "충전 불필요"

    row3 = st.columns(2)
    row3[0].markdown(
        f'**충전 휴게소**<br><span style="font-size:1.05rem; line-height:1.3">{charger_recommendation}</span>',
        unsafe_allow_html=True,
    )
    arrival_display = (
        simulation["arrival_time"].strftime("%Y-%m-%d %H:%M")
        if simulation["feasible"] else "도착 불가"
    )
    row3[1].markdown(
        f'**운행 시간**<br><span style="font-size:1.05rem; line-height:1.5">'
        f'출발: {dispatch["assignment_date"]} {FIXED_DEPARTURE_HOUR:02d}:00<br>도착: {arrival_display}</span>',
        unsafe_allow_html=True,
    )
    row4 = st.columns(2)
    row4[0].markdown(
        f'**예상 에너지 소비량**<br><span style="font-size:1.05rem">'
        f'{total_energy:.1f} kWh<br>({prediction:.2f} kWh/100km)</span>',
        unsafe_allow_html=True,
    )
    explanatory_power = max(0.0, min(100.0, float(metrics["R2"]) * 100))
    row4[1].markdown(
        f'**예측 신뢰 지표**<br><span style="font-size:1.05rem; line-height:1.5">'
        f'모델 설명력: {explanatory_power:.1f}%<br>'
        f'예상 오차: ±{float(metrics["RMSE"]):.2f} kWh/100km</span>',
        unsafe_allow_html=True,
    )

    with st.expander("배차 상세정보", expanded=False):
        left, right = st.columns(2)
        with left:
            st.metric("총 운행중량", f"{vehicle_empty_weight + cargo_set_count * CARGO_SET_WEIGHT_KG:,.1f} kg")
            st.metric("배정 상태", saved_row["assignment_status"])
            style = float(dispatch["driving_style_index"])
            st.metric("운전성향", f"{style:.2f} · {driving_style_label(style)}")
        with right:
            st.metric("날씨", f'{dispatch["weather_type"]} / {dispatch["ambient_temp_C"]}°C')
            st.metric("HVAC", f'{dispatch["hvac_mode"]} / {dispatch["hvac_power_kw"]} kW')

    with st.expander("에너지·충전 정보", expanded=False):
        st.metric("모델 R²", f'{metrics["R2"]:.4f}')
        st.caption(f'MAE {metrics["MAE"]:.3f} kWh/100km · RMSE {metrics["RMSE"]:.3f} kWh/100km')
        st.info(demo_warning())
        if simulation["feasible"]:
            st.success(f"총 소요시간: {simulation['total_minutes']:.0f}분")
            st.caption(
                "총 정차시간은 충전시간과 휴게소 진입·연결·출차 7분을 합한 값이며, "
                "총 소요시간은 전체 주행시간과 모든 정차시간을 합한 값입니다."
            )
            if simulation["charges"]:
                st.dataframe(pd.DataFrame(simulation["charges"]), use_container_width=True, hide_index=True)
            else:
                st.info("예상 경로에서 충전이 필요하지 않습니다.")
            st.dataframe(pd.DataFrame(simulation["legs"]), use_container_width=True, hide_index=True)
        else:
            st.error("현재 배차 조건으로는 최소 안전 SOC를 유지하며 목적지에 도착할 수 없습니다.")

    with st.expander("노선 정보", expanded=False):
        summary = st.columns(2)
        summary[0].metric("전체 노선 거리", f"{total_distance:,.1f} km")
        summary[1].metric("노선 평균 경사", f"{route_average_grade:.3f}%")
        st.caption(
            "경사각도는 구간 시작·끝 고도 차이로 계산한 평균값이며 "
            "구간 내부의 순간 최대경사와는 다를 수 있습니다."
        )
        st.dataframe(
            build_route_grade_view(route_grade_rows, segment_predictions),
            use_container_width=True, hide_index=True,
        )

    with st.expander("충전소 정보", expanded=False):
        charger_view = charger_status_view(route_rows)[[
            "sequence", "rest_area_name_ko", "trip_distance_from_start_km",
            "max_verified_power_kw", "service_charger_status", "추천 상태",
        ]]
        st.dataframe(charger_view, use_container_width=True, hide_index=True)

record_date = st.session_state.get("dispatch", {}).get(
    "assignment_date", date.today().isoformat()
)
record_date_text = datetime.strptime(record_date, "%Y-%m-%d").strftime("%y.%m.%d")
st.subheader(f"{record_date_text} / 일일 배차기록")
st.caption(f"저장 파일: {SESSION_ASSIGNMENT_PATH.name}")
daily_records = load_assignments(SESSION_ASSIGNMENT_PATH)
st.dataframe(daily_records.tail(20), use_container_width=True, hide_index=True)

export_records = daily_records.rename(columns={
    "employee_id": "사원번호",
    "vehicle_display_name": "차량번호",
    "assignment_status": "배차 허가 여부",
})[["사원번호", "차량번호", "배차 허가 여부"]].copy()
export_records["배차 허가 여부"] = export_records["배차 허가 여부"].map({
    "ASSIGNED": "허가",
    "OVERWRITTEN": "허가(덮어쓰기)",
    "RESERVE": "예비차량",
}).fillna(export_records["배차 허가 여부"])

file_date = record_date
csv_col, excel_col = st.columns(2)
with csv_col:
    st.download_button(
        "CSV로 저장",
        data=export_records.to_csv(index=False, encoding="utf-8-sig"),
        file_name=f"일일배차기록_{file_date}.csv",
        mime="text/csv", use_container_width=True,
    )
with excel_col:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        export_records.to_excel(writer, index=False, sheet_name="일일 배차기록")
    st.download_button(
        "Excel로 저장",
        data=buffer.getvalue(),
        file_name=f"일일배차기록_{file_date}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
