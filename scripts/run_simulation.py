"""배차 → 예측 → SOC·충전·ETA 시뮬레이션을 한 번 실행하고 결과를 출력·저장한다.

실행: python scripts/run_simulation.py 12345678 2026-08-28
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pandas as pd

from ev_logistics.config import OUTPUT_DIR
from ev_logistics.simulation import run_service_simulation


def main() -> None:
    employee_id = sys.argv[1] if len(sys.argv) > 1 else "12345678"
    assignment_date = sys.argv[2] if len(sys.argv) > 2 else "2026-08-28"

    result = run_service_simulation(employee_id, assignment_date)
    simulation = result["simulation"]

    print(f"사원번호 {employee_id} / 배차일 {assignment_date}")
    print(f"차량: {result['vehicle']['display_name']}  화물: {result['payload_kg']:.0f}kg")
    print(f"출발 SOC: {result['dispatch']['battery_soc_pct']:.0f}%  "
          f"날씨: {result['dispatch']['weather_type']}")
    print(f"예상 소비량: {result['total_energy_kwh']:.1f} kWh "
          f"({result['predicted_kwh_per_100km']:.2f} kWh/100km)")
    print(f"운행 가능: {simulation['feasible']}  "
          f"충전 정차: {len(simulation['charges'])}회")
    if simulation["feasible"]:
        print(f"도착 예상: {simulation['arrival_time']:%Y-%m-%d %H:%M}  "
              f"총 {simulation['total_minutes']:.0f}분")
    print()
    print(pd.DataFrame(simulation["legs"]).to_string(index=False))

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUTPUT_DIR / "service_simulation_result.json"
    payload = {
        "employee_id": employee_id,
        "assignment_date": assignment_date,
        "vehicle": result["vehicle"],
        "dispatch": result["dispatch"],
        "predicted_kwh_per_100km": result["predicted_kwh_per_100km"],
        "total_energy_kwh": result["total_energy_kwh"],
        "simulation": {
            "feasible": simulation["feasible"],
            "legs": simulation["legs"],
            "charges": simulation["charges"],
            "arrival_time": str(simulation.get("arrival_time")),
            "total_minutes": simulation.get("total_minutes"),
        },
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out_path}")


if __name__ == "__main__":
    main()
