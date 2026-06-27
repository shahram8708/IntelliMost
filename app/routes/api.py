from datetime import datetime
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.production_line import ProductionLine
from app.models.shift import Shift
from app.models.downtime import DowntimeEvent
from app.models.machine import Machine
from app.models.alert import AlertEvent
from app.models.capa import CapaRecord
from app.models.rca import RcaRecord
from app.services.ai_assistant import suggest_most_indices
from app.utils.helpers import log_audit

api_bp = Blueprint("api", __name__)


@api_bp.before_request
@login_required
def require_login():
    pass


@api_bp.route("/dashboard/metrics")
def dashboard_metrics():
    pid = current_user.plant_id
    lines = (ProductionLine.query.filter_by(is_active=True).all()
             if current_user.role == "super_admin"
             else ProductionLine.query.filter_by(plant_id=pid, is_active=True).all())
    line_data = []
    oees = []
    total_t = total_a = 0
    for l in lines:
        shift = Shift.query.filter_by(line_id=l.id, status="active").first()
        active_dt = DowntimeEvent.query.filter_by(shift_id=shift.id, is_resolved=False).count() if shift else 0
        status = "idle" if not shift else ("fault" if active_dt else "running")
        out = shift.actual_units if shift else 0
        tgt = shift.target_units if shift else 0
        oee = shift.oee_percent if shift and shift.oee_percent else 0
        if oee:
            oees.append(oee)
        total_t += tgt
        total_a += out
        line_data.append({"id": l.id, "name": l.line_name, "status": status,
                          "output": out, "target": tgt, "oee": oee})
    aq = AlertEvent.query.filter(AlertEvent.status.in_(["open", "escalated"]))
    if current_user.role != "super_admin":
        aq = aq.filter_by(plant_id=pid)
    recent = aq.order_by(AlertEvent.triggered_at.desc()).limit(5).all()
    active_dt_total = sum(1 for l in line_data if l["status"] == "fault")
    return jsonify({
        "oee": round(sum(oees) / len(oees), 1) if oees else 0,
        "attainment_percent": round(total_a / total_t * 100, 1) if total_t else 0,
        "active_alerts": aq.count(),
        "active_downtime_events": active_dt_total,
        "production_lines": line_data,
        "recent_alerts": [{"id": e.id, "rule_name": e.rule.rule_name if e.rule else "",
                           "triggered_value": e.triggered_value,
                           "triggered_at": e.triggered_at.isoformat(),
                           "status": e.status} for e in recent],
    })


@api_bp.route("/line/<int:id>/status")
def line_status(id):
    line = ProductionLine.query.get_or_404(id)
    if current_user.role != "super_admin" and line.plant_id != current_user.plant_id:
        abort(403)
    shift = Shift.query.filter_by(line_id=line.id, status="active").first()
    dt = DowntimeEvent.query.filter_by(shift_id=shift.id, is_resolved=False).all() if shift else []
    return jsonify({
        "line": line.line_name,
        "output": shift.actual_units if shift else 0,
        "target": shift.target_units if shift else 0,
        "active_downtime": [{"machine": d.machine.machine_name if d.machine else "",
                             "start": d.start_time.isoformat()} for d in dt],
    })


@api_bp.route("/most/suggest-indices", methods=["POST"])
def most_suggest():
    payload = request.get_json(silent=True) or {}
    result = suggest_most_indices(payload.get("element_name", ""),
                                  payload.get("element_description", ""),
                                  payload.get("timer_duration_sec"))
    return jsonify(result)


@api_bp.route("/rca/similar-events", methods=["POST"])
def rca_similar():
    payload = request.get_json(silent=True) or {}
    desc = (payload.get("deviation_description") or "").strip()
    results = []
    if desc:
        terms = [t for t in desc.split() if len(t) > 4][:5]
        q = (db.session.query(RcaRecord, CapaRecord)
             .join(CapaRecord, RcaRecord.capa_id == CapaRecord.id))
        if current_user.role != "super_admin":
            q = q.filter(CapaRecord.plant_id == current_user.plant_id)
        for term in terms:
            for rca, capa in q.filter(
                (RcaRecord.problem_statement.ilike(f"%{term}%")) |
                (CapaRecord.deviation_description.ilike(f"%{term}%"))).limit(5):
                if not any(r["capa_number"] == capa.capa_number for r in results):
                    results.append({
                        "capa_number": capa.capa_number, "title": capa.title,
                        "root_cause_statement": rca.root_cause_statement,
                        "root_cause_category": rca.root_cause_category,
                        "closed_at": capa.closed_at.isoformat() if capa.closed_at else None})
            if len(results) >= 5:
                break
    return jsonify({"results": results[:5]})


@api_bp.route("/alert/<int:id>/acknowledge", methods=["POST"])
def alert_acknowledge(id):
    event = AlertEvent.query.get_or_404(id)
    if current_user.role != "super_admin" and event.plant_id != current_user.plant_id:
        abort(403)
    payload = request.get_json(silent=True) or {}
    event.status = "acknowledged"
    event.acknowledged_by = current_user.id
    event.acknowledged_at = datetime.utcnow()
    event.action_taken = payload.get("action")
    event.notes = payload.get("notes")
    db.session.commit()
    log_audit("ALERT_ACKNOWLEDGED", "AlertEvent", event.id)
    return jsonify({"ok": True, "status": event.status})


@api_bp.route("/shift/active")
def shift_active():
    line_id = request.args.get("line_id", type=int)
    q = Shift.query.join(ProductionLine).filter(Shift.status == "active")
    if current_user.role != "super_admin":
        q = q.filter(ProductionLine.plant_id == current_user.plant_id)
    if line_id:
        q = q.filter(Shift.line_id == line_id)
    shift = q.first()
    if not shift:
        return jsonify({"shift_id": None})
    return jsonify({"shift_id": shift.id, "line_name": shift.line.line_name,
                    "start_time": shift.start_time.isoformat(), "target_units": shift.target_units,
                    "actual_units": shift.actual_units, "rejection_count": shift.rejection_count})


@api_bp.route("/downtime/active")
def downtime_active():
    mids = ([m.id for m in Machine.query.all()] if current_user.role == "super_admin"
            else [m.id for m in Machine.query.join(Machine.line)
                  .filter_by(plant_id=current_user.plant_id).all()])
    events = DowntimeEvent.query.filter(DowntimeEvent.machine_id.in_(mids),
                                        DowntimeEvent.is_resolved == False).all() if mids else []
    return jsonify([{"id": e.id, "machine": e.machine.machine_name if e.machine else "",
                     "event_type": e.event_type, "start_time": e.start_time.isoformat()} for e in events])
