from app.extensions import db
from app.models.shift import Shift


def calculate_oee(shift_id):
    shift = Shift.query.get(shift_id)
    if not shift or not shift.line:
        return None
    line = shift.line
    planned = (line.shift_duration_hours * 60) - line.planned_break_minutes
    if planned <= 0:
        planned = 1

    unplanned_dt = sum(
        (dt.duration_minutes or 0) for dt in shift.downtime_events
        if dt.event_type == "unplanned" and dt.duration_minutes
    )
    operating = planned - unplanned_dt
    availability = operating / planned if planned > 0 else 0

    ideal_cycle = planned / shift.target_units if shift.target_units > 0 else 0
    performance = (ideal_cycle * shift.actual_units) / operating if operating > 0 else 0
    performance = min(performance, 1.0)

    good_units = (shift.actual_units or 0) - (shift.rejection_count or 0)
    quality = good_units / shift.actual_units if shift.actual_units and shift.actual_units > 0 else 0

    oee = availability * performance * quality

    shift.oee_percent = round(oee * 100, 2)
    shift.availability_percent = round(availability * 100, 2)
    shift.performance_percent = round(performance * 100, 2)
    shift.quality_percent = round(quality * 100, 2)
    db.session.commit()

    oee_pct = round(oee * 100, 2)
    if oee_pct >= 85:
        bench = "world_class"
    elif oee_pct >= 65:
        bench = "acceptable"
    else:
        bench = "requires_attention"

    return {
        "oee_percent": oee_pct,
        "availability_percent": round(availability * 100, 2),
        "performance_percent": round(performance * 100, 2),
        "quality_percent": round(quality * 100, 2),
        "operating_time_min": round(operating, 1),
        "unplanned_downtime_min": round(unplanned_dt, 1),
        "good_units": good_units,
        "benchmark_status": bench,
    }
