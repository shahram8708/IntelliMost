from datetime import datetime, timedelta, date
from sqlalchemy import func


def generate_opportunities(app=None):
    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()


def _run():
    from app.models.plant import Plant
    plants = Plant.query.filter_by(is_active=True).all()
    for plant in plants:
        try:
            _analyze_changeover_performance(plant.id)
            _analyze_rejection_trends(plant.id)
            _analyze_downtime_pareto(plant.id)
            _analyze_standard_time_gaps(plant.id)
        except Exception:
            from app.extensions import db
            db.session.rollback()


def _exists(plant_id, title):
    from app.models.improvement import ImprovementOpportunity
    return (ImprovementOpportunity.query
            .filter_by(plant_id=plant_id, opportunity_title=title)
            .filter(ImprovementOpportunity.status.in_(["new", "deferred"])).first())


def _add(plant_id, title, desc, category, impact_min=None, evidence=None, line_id=None,
         machine_id=None, score=0.0, data=None):
    from app.extensions import db
    from app.models.improvement import ImprovementOpportunity
    if _exists(plant_id, title):
        return
    opp = ImprovementOpportunity(
        plant_id=plant_id, line_id=line_id, machine_id=machine_id,
        opportunity_title=title, opportunity_description=desc, category=category,
        impact_minutes_per_shift=impact_min, evidence_summary=evidence,
        supporting_data=data, rank_score=score, status="new",
        generated_at=datetime.utcnow(),
    )
    db.session.add(opp)
    db.session.commit()


def _analyze_changeover_performance(plant_id):
    from app.models.downtime import DowntimeEvent
    from app.models.machine import Machine
    from app.models.production_line import ProductionLine
    cutoff = datetime.utcnow() - timedelta(days=30)
    lines = ProductionLine.query.filter_by(plant_id=plant_id).all()
    for line in lines:
        mids = [m.id for m in Machine.query.filter_by(line_id=line.id).all()]
        if not mids:
            continue
        events = (DowntimeEvent.query
                  .filter(DowntimeEvent.machine_id.in_(mids),
                          DowntimeEvent.event_type == "changeover",
                          DowntimeEvent.start_time >= cutoff,
                          DowntimeEvent.duration_minutes.isnot(None)).all())
        if len(events) >= 5:
            avg = sum(e.duration_minutes for e in events) / len(events)
            if avg > 40:
                _add(plant_id,
                     f"{line.line_name} Changeover Above Standard",
                     f"Average changeover on {line.line_name} is {avg:.0f} minutes across "
                     f"{len(events)} events in the last 30 days, exceeding the 40 minute target.",
                     "changeover_reduction", impact_min=round(avg - 40, 1),
                     evidence=f"{len(events)} changeovers, avg {avg:.0f} min",
                     line_id=line.id, score=round(avg - 40, 1))


def _analyze_rejection_trends(plant_id):
    from app.models.rejection import RejectionEvent
    from app.models.shift import Shift
    from app.models.production_line import ProductionLine
    cutoff = datetime.utcnow() - timedelta(days=14)
    lines = ProductionLine.query.filter_by(plant_id=plant_id).all()
    for line in lines:
        shifts = Shift.query.filter_by(line_id=line.id).filter(Shift.start_time >= cutoff).all()
        units = sum(s.actual_units or 0 for s in shifts)
        rej = sum(s.rejection_count or 0 for s in shifts)
        if units > 0:
            rate = rej / units * 100
            if rate > 2.0:
                _add(plant_id,
                     f"Rising Rejection Rate on {line.line_name}",
                     f"Rejection rate on {line.line_name} is {rate:.2f}% over the last 14 days, "
                     "above the 2% target.",
                     "rejection_reduction",
                     evidence=f"{rej} rejects / {units} units = {rate:.2f}%",
                     line_id=line.id, score=round(rate, 1))


def _analyze_downtime_pareto(plant_id):
    from app.extensions import db
    from app.models.downtime import DowntimeEvent
    from app.models.machine import Machine
    from app.models.reason_code import ReasonCode
    cutoff = datetime.utcnow() - timedelta(days=30)
    mids = [m.id for m in Machine.query.join(Machine.line)
            .filter_by(plant_id=plant_id).all()] if False else \
        [m.id for m in Machine.query.all()]
    rows = (db.session.query(DowntimeEvent.reason_code_id,
                             func.sum(DowntimeEvent.duration_minutes))
            .filter(DowntimeEvent.event_type == "unplanned",
                    DowntimeEvent.start_time >= cutoff,
                    DowntimeEvent.machine_id.in_(mids))
            .group_by(DowntimeEvent.reason_code_id)
            .order_by(func.sum(DowntimeEvent.duration_minutes).desc()).all())
    total = sum((r[1] or 0) for r in rows)
    if rows and total > 0 and rows[0][1]:
        rc = ReasonCode.query.get(rows[0][0]) if rows[0][0] else None
        label = rc.label if rc else "Unspecified reason"
        pct = rows[0][1] / total * 100
        _add(plant_id,
             f"{label} is top unplanned downtime cause",
             f"{label} accounts for {pct:.0f}% of unplanned downtime minutes "
             "in the last 30 days. Focused maintenance could recover significant time.",
             "downtime_reduction", impact_min=round(rows[0][1] / 30, 1),
             evidence=f"{rows[0][1]:.0f} min ({pct:.0f}% of unplanned)",
             score=round(pct, 1))


def _analyze_standard_time_gaps(plant_id):
    from app.models.machine import Machine
    from app.models.most_study import MostStudy
    machines = Machine.query.join(Machine.line).filter_by(is_active=True).all()
    cutoff = date.today() - timedelta(days=90)
    for m in machines:
        if m.line and m.line.plant_id != plant_id:
            continue
        latest = (MostStudy.query.filter_by(workstation_id=m.id, status="published")
                  .order_by(MostStudy.study_date.desc()).first())
        if not latest or latest.study_date < cutoff:
            _add(plant_id,
                 f"Standard time outdated for {m.machine_name}",
                 f"{m.machine_name} has no published MOST study within the last 90 days. "
                 "Update the standard time to keep performance metrics accurate.",
                 "standard_time_update", machine_id=m.id,
                 evidence="No recent published MOST study", score=5.0)
