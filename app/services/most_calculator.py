from app.extensions import db
from app.models.most_study import MostStudy
from app.models.most_element import MostElement
from app.models.shift import Shift, ProductionOutput

VALID_INDICES = [0, 1, 3, 6, 10, 16, 24, 32]
TMU_TO_SEC = 0.036

PARAMS = {
    "general_move": ["A1", "B1", "G1", "A2", "B2", "P1", "A3"],
    "controlled_move": ["A1", "B1", "G1", "M1", "X1", "I1", "A2"],
    "tool_use": ["A1", "B1", "G1", "A2", "B2", "P1", "A3"],
}


def validate_index_value(value):
    return value in VALID_INDICES


def calculate_element_tmu(most_method, index_values):
    if most_method == "tool_use":
        base = sum(int(index_values.get(p, 0)) for p in PARAMS["tool_use"])
        return base * 10 + int(index_values.get("tool_tmu", 0))
    keys = PARAMS.get(most_method, PARAMS["general_move"])
    return sum(int(index_values.get(p, 0)) for p in keys) * 10


def tmu_to_time(tmu):
    seconds = tmu * TMU_TO_SEC
    minutes = seconds / 60
    mm = int(seconds // 60)
    ss = int(round(seconds - mm * 60))
    return {"seconds": round(seconds, 2), "minutes": round(minutes, 3),
            "formatted": f"{mm:02d}:{ss:02d}"}


def calculate_standard_time(study_id):
    study = MostStudy.query.get(study_id)
    if not study:
        return None
    total = 0.0
    for el in study.elements:
        el.element_tmu = calculate_element_tmu(el.most_method, el.index_values or {})
        total += el.element_tmu
    raw = total * TMU_TO_SEC
    allowed = raw * (1 + (study.allowance_percent or 0) / 100)
    study.total_tmu = total
    study.standard_time_sec = round(raw, 3)
    study.allowed_time_sec = round(allowed, 3)
    db.session.commit()
    return {
        "total_tmu": total,
        "standard_time_sec": round(raw, 3),
        "allowed_time_sec": round(allowed, 3),
        "standard_time_min": round(raw / 60, 3),
        "allowed_time_min": round(allowed / 60, 3),
    }


def get_comparison_data(study_id):
    study = MostStudy.query.get(study_id)
    if not study:
        return []
    std = study.allowed_time_sec or study.standard_time_sec or 0
    machine_id = study.workstation_id
    rows = []
    shifts = (Shift.query.join(Shift.line)
              .filter(Shift.line_id.in_(
                  db.session.query(study.workstation.line_id) if study.workstation else []))
              .order_by(Shift.start_time.desc()).limit(15).all()) if study.workstation else []
    for s in shifts:
        if s.actual_units and s.actual_units > 0 and study.workstation:
            op_min = (s.line.shift_duration_hours * 60) - s.line.planned_break_minutes - (s.total_downtime_minutes or 0)
            actual_cycle = (op_min * 60) / s.actual_units if s.actual_units else 0
            ratio = (std / actual_cycle) if actual_cycle else 0
            rows.append({
                "date": s.start_time.strftime("%d %b"),
                "actual_time_sec": round(actual_cycle, 2),
                "efficiency_ratio": round(ratio * 100, 1),
                "shift_label": s.shift_label,
            })
    return list(reversed(rows))
