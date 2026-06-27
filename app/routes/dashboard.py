from datetime import datetime, timedelta
from flask import Blueprint, render_template
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.plant import Plant
from app.models.user import User
from app.models.production_line import ProductionLine
from app.models.machine import Machine
from app.models.shift import Shift
from app.models.downtime import DowntimeEvent
from app.models.rejection import RejectionEvent
from app.models.reason_code import ReasonCode
from app.models.capa import CapaRecord
from app.models.alert import AlertEvent
from app.models.most_study import MostStudy
from app.models.audit_log import AuditLog

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/")
@login_required
def index():
    ctx = {"role": current_user.role}
    role = current_user.role
    pid = current_user.plant_id

    if role == "super_admin":
        ctx.update(_super_admin_ctx())
    elif role == "admin":
        ctx.update(_super_admin_ctx() if pid is None else _plant_manager_ctx(pid))
    elif role == "plant_manager":
        ctx.update(_plant_manager_ctx(pid))
    elif role == "industrial_engineer":
        ctx.update(_ie_ctx(pid))
    elif role == "qa_manager":
        ctx.update(_qa_ctx(pid))
    elif role == "shift_supervisor":
        ctx.update(_supervisor_ctx())
    else:
        ctx.update(_operator_ctx())
    return render_template("dashboard/index.html", **ctx)


def _super_admin_ctx():
    return {
        "plant_count": Plant.query.filter_by(is_active=True).count(),
        "user_count": User.query.filter_by(is_deleted=False).count(),
        "line_count": ProductionLine.query.count(),
        "study_count": MostStudy.query.filter_by(status="published").count(),
        "open_capas": CapaRecord.query.filter(CapaRecord.status != "closed").count(),
        "active_alerts": AlertEvent.query.filter(AlertEvent.status.in_(["open", "escalated"])).count(),
        "recent_audit": AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all(),
        "plants": Plant.query.all(),
    }


def _plant_manager_ctx(pid):
    lines = ProductionLine.query.filter_by(plant_id=pid, is_active=True).all()
    line_ids = [l.id for l in lines]
    active_shifts = Shift.query.filter(Shift.line_id.in_(line_ids), Shift.status == "active").all() if line_ids else []
    oees = [s.oee_percent for s in active_shifts if s.oee_percent is not None]
    avg_oee = round(sum(oees) / len(oees), 1) if oees else 0
    total_target = sum(s.target_units for s in active_shifts) or 0
    total_actual = sum(s.actual_units for s in active_shifts) or 0
    attainment = round(total_actual / total_target * 100, 1) if total_target else 0
    week_ago = datetime.utcnow() - timedelta(days=7)
    mids = [m.id for l in lines for m in l.machines]
    active_dt = DowntimeEvent.query.filter(DowntimeEvent.machine_id.in_(mids),
                                           DowntimeEvent.is_resolved == False).count() if mids else 0
    top_reasons = []
    if mids:
        rows = (db.session.query(ReasonCode.label, func.sum(DowntimeEvent.duration_minutes))
                .join(DowntimeEvent, DowntimeEvent.reason_code_id == ReasonCode.id)
                .filter(DowntimeEvent.machine_id.in_(mids), DowntimeEvent.start_time >= week_ago)
                .group_by(ReasonCode.label)
                .order_by(func.sum(DowntimeEvent.duration_minutes).desc()).limit(3).all())
        top_reasons = [{"label": r[0], "minutes": round(r[1] or 0, 1)} for r in rows]
    open_capas = CapaRecord.query.filter_by(plant_id=pid).filter(CapaRecord.status != "closed").count()
    active_alerts = AlertEvent.query.filter_by(plant_id=pid).filter(AlertEvent.status.in_(["open", "escalated"])).count()
    return {
        "avg_oee": avg_oee, "attainment": attainment, "active_dt": active_dt,
        "open_capas": open_capas, "active_alerts": active_alerts, "top_reasons": top_reasons,
        "lines": lines, "active_shifts": {s.line_id: s for s in active_shifts},
    }


def _ie_ctx(pid):
    studies = (MostStudy.query.filter_by(plant_id=pid)
               .order_by(MostStudy.created_at.desc()).limit(10).all())
    cutoff = datetime.utcnow().date() - timedelta(days=90)
    machines = Machine.query.join(Machine.line).filter_by(plant_id=pid).all()
    overdue_ws = []
    for m in machines:
        latest = (MostStudy.query.filter_by(workstation_id=m.id, status="published")
                  .order_by(MostStudy.study_date.desc()).first())
        if not latest or latest.study_date < cutoff:
            overdue_ws.append(m)
    pending_ai = MostStudy.query.filter_by(plant_id=pid, status="draft", ai_assistance_used=True).count()
    return {"studies": studies, "overdue_ws": overdue_ws[:8], "pending_ai": pending_ai,
            "published_count": MostStudy.query.filter_by(plant_id=pid, status="published").count()}


def _qa_ctx(pid):
    open_capas = CapaRecord.query.filter_by(plant_id=pid).filter(CapaRecord.status != "closed").count()
    overdue = CapaRecord.query.filter_by(plant_id=pid, status="overdue").count()
    recent_rej = (RejectionEvent.query.join(Shift).join(Shift.line)
                  .filter(ProductionLine.plant_id == pid)
                  .order_by(RejectionEvent.created_at.desc()).limit(10).all())
    week_ago = datetime.utcnow() - timedelta(days=7)
    lines = ProductionLine.query.filter_by(plant_id=pid).all()
    rej_chart = {"labels": [], "data": []}
    for l in lines:
        shifts = Shift.query.filter_by(line_id=l.id).filter(Shift.start_time >= week_ago).all()
        units = sum(s.actual_units or 0 for s in shifts)
        rej = sum(s.rejection_count or 0 for s in shifts)
        rate = round(rej / units * 100, 2) if units else 0
        rej_chart["labels"].append(l.line_name)
        rej_chart["data"].append(rate)
    return {"open_capas": open_capas, "overdue": overdue, "recent_rej": recent_rej,
            "rej_chart": rej_chart}


def _supervisor_ctx():
    shift = None
    if current_user.plant_id:
        line = (ProductionLine.query.filter_by(plant_id=current_user.plant_id).first())
        shift = (Shift.query.filter_by(status="active")
                 .join(ProductionLine).filter(ProductionLine.plant_id == current_user.plant_id).first())
    active_dt = 0
    if shift:
        active_dt = DowntimeEvent.query.filter_by(shift_id=shift.id, is_resolved=False).count()
    return {"my_shift": shift, "active_dt": active_dt}


def _operator_ctx():
    shift = None
    if current_user.plant_id:
        shift = (Shift.query.filter_by(status="active")
                 .join(ProductionLine).filter(ProductionLine.plant_id == current_user.plant_id).first())
    today = datetime.utcnow().date()
    from app.models.shift import ProductionOutput
    my_logs = (ProductionOutput.query.filter_by(logged_by=current_user.id)
               .filter(ProductionOutput.logged_at >= datetime(today.year, today.month, today.day))
               .order_by(ProductionOutput.logged_at.desc()).all())
    return {"my_shift": shift, "my_logs": my_logs}
