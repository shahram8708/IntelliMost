from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.downtime import DowntimeEvent
from app.models.machine import Machine
from app.models.shift import Shift
from app.models.production_line import ProductionLine
from app.models.reason_code import ReasonCode
from app.forms.downtime_forms import DowntimeForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit
from app.services.oee_calculator import calculate_oee
from app.services.alert_engine import evaluate_for_metric

downtime_bp = Blueprint("downtime", __name__)


def _plant_machine_ids():
    if current_user.role == "super_admin":
        return [m.id for m in Machine.query.all()]
    return [m.id for m in Machine.query.join(Machine.line)
            .filter_by(plant_id=current_user.plant_id).all()]


@downtime_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    mids = _plant_machine_ids()
    q = DowntimeEvent.query.filter(DowntimeEvent.machine_id.in_(mids)) if mids else DowntimeEvent.query.filter(db.false())
    machine_id = request.args.get("machine_id", type=int)
    event_type = request.args.get("event_type", "")
    if machine_id:
        q = q.filter_by(machine_id=machine_id)
    if event_type:
        q = q.filter_by(event_type=event_type)
    pagination = q.order_by(DowntimeEvent.start_time.desc()).paginate(page=page, per_page=20, error_out=False)

    pareto_rows = (db.session.query(ReasonCode.label, func.sum(DowntimeEvent.duration_minutes))
                   .join(DowntimeEvent, DowntimeEvent.reason_code_id == ReasonCode.id)
                   .filter(DowntimeEvent.machine_id.in_(mids))
                   .group_by(ReasonCode.label)
                   .order_by(func.sum(DowntimeEvent.duration_minutes).desc()).limit(10).all()) if mids else []
    pareto = {"labels": [r[0] for r in pareto_rows], "data": [round(r[1] or 0, 1) for r in pareto_rows]}

    trend = {"labels": [], "data": []}
    for i in range(29, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        total = (db.session.query(func.sum(DowntimeEvent.duration_minutes))
                 .filter(DowntimeEvent.machine_id.in_(mids),
                         DowntimeEvent.start_time >= start, DowntimeEvent.start_time < end).scalar()) if mids else 0
        trend["labels"].append(day.strftime("%d %b"))
        trend["data"].append(round((total or 0) / 60, 2))

    machines = (Machine.query.join(Machine.line).filter_by(plant_id=current_user.plant_id).all()
                if current_user.role != "super_admin" else Machine.query.all())
    mtbf_mttr = _mtbf_mttr(mids)
    return render_template("downtime/index.html", pagination=pagination, events=pagination.items,
                           pareto=pareto, trend=trend, machines=machines, mtbf_mttr=mtbf_mttr,
                           filters={"machine_id": machine_id, "event_type": event_type})


def _mtbf_mttr(mids):
    rows = []
    for mid in mids[:12]:
        m = Machine.query.get(mid)
        events = (DowntimeEvent.query.filter_by(machine_id=mid, event_type="unplanned")
                  .filter(DowntimeEvent.duration_minutes.isnot(None)).all())
        if not events:
            continue
        mttr = sum(e.duration_minutes for e in events) / len(events)
        rows.append({"machine": m.machine_name, "mttr": round(mttr, 1), "count": len(events)})
    return rows


@downtime_bp.route("/log", methods=["GET", "POST"])
@login_required
@role_required("shift_supervisor", "operator", "admin", "plant_manager")
def log_event():
    form = DowntimeForm()
    machines = (Machine.query.join(Machine.line).filter_by(plant_id=current_user.plant_id, is_active=True).all()
                if current_user.role != "super_admin" else Machine.query.all())
    shifts = (Shift.query.join(ProductionLine).filter(ProductionLine.plant_id == current_user.plant_id,
                                                      Shift.status == "active").all())
    reasons = ReasonCode.query.filter(
        (ReasonCode.plant_id == current_user.plant_id) | (ReasonCode.plant_id.is_(None)),
        ReasonCode.is_active == True).all()
    form.machine_id.choices = [(m.id, m.machine_name) for m in machines]
    form.shift_id.choices = [(s.id, f"{s.line.line_name} - {s.shift_label}") for s in shifts]
    form.reason_code_id.choices = [(0, "Select reason")] + [(r.id, r.label) for r in reasons if r.level == 3]

    if form.validate_on_submit():
        dt = DowntimeEvent(machine_id=form.machine_id.data, shift_id=form.shift_id.data,
                           event_type=form.event_type.data,
                           reason_code_id=form.reason_code_id.data or None,
                           start_time=form.start_time.data, end_time=form.end_time.data,
                           logged_by=current_user.id, notes=form.notes.data)
        if form.end_time.data and form.start_time.data:
            dt.duration_minutes = (form.end_time.data - form.start_time.data).total_seconds() / 60
            dt.is_resolved = True
        db.session.add(dt)
        try:
            db.session.commit()
            shift = Shift.query.get(form.shift_id.data)
            if shift and dt.duration_minutes:
                shift.total_downtime_minutes = (shift.total_downtime_minutes or 0) + dt.duration_minutes
                db.session.commit()
                calculate_oee(shift.id)
                evaluate_for_metric(shift.line.plant_id, "downtime_duration", shift.line_id)
                evaluate_for_metric(shift.line.plant_id, "oee_percent", shift.line_id)
            log_audit("DOWNTIME_LOGGED", "DowntimeEvent", dt.id, dt.event_type)
            flash("Downtime event logged.", "success")
        except Exception:
            db.session.rollback()
            flash("Could not log downtime.", "error")
        return redirect(url_for("downtime.log_event"))
    return render_template("downtime/log_event.html", form=form, machines=machines,
                           shifts=shifts, reasons=reasons)


@downtime_bp.route("/<int:id>/close", methods=["POST"])
@login_required
def close(id):
    dt = DowntimeEvent.query.get_or_404(id)
    if current_user.role != "super_admin":
        if not dt.machine or dt.machine.line.plant_id != current_user.plant_id:
            abort(403)
    end = request.form.get("end_time")
    dt.end_time = datetime.fromisoformat(end) if end else datetime.utcnow()
    dt.duration_minutes = (dt.end_time - dt.start_time).total_seconds() / 60
    dt.is_resolved = True
    db.session.commit()
    shift = dt.shift
    if shift:
        shift.total_downtime_minutes = (shift.total_downtime_minutes or 0) + dt.duration_minutes
        db.session.commit()
        calculate_oee(shift.id)
    log_audit("DOWNTIME_CLOSED", "DowntimeEvent", dt.id)
    flash("Downtime event closed.", "success")
    return redirect(request.referrer or url_for("downtime.index"))
