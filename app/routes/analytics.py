from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.production_line import ProductionLine
from app.models.shift import Shift
from app.models.machine import Machine

analytics_bp = Blueprint("analytics", __name__)


@analytics_bp.route("/")
@login_required
def index():
    lines = (ProductionLine.query.filter_by(plant_id=current_user.plant_id).all()
             if current_user.role != "super_admin" else ProductionLine.query.all())
    return render_template("analytics/index.html", lines=lines)


@analytics_bp.route("/data")
@login_required
def data():
    metric = request.args.get("metric", "oee_percent")
    days = request.args.get("days", 30, type=int)
    line_id = request.args.get("line_id", type=int)
    start = datetime.utcnow() - timedelta(days=days)

    q = Shift.query.join(ProductionLine)
    if current_user.role != "super_admin":
        q = q.filter(ProductionLine.plant_id == current_user.plant_id)
    if line_id:
        q = q.filter(Shift.line_id == line_id)
    q = q.filter(Shift.start_time >= start)

    labels, values = [], []
    for i in range(days - 1, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        dstart = datetime(day.year, day.month, day.day)
        dend = dstart + timedelta(days=1)
        day_shifts = [s for s in q if dstart <= s.start_time < dend]
        labels.append(day.strftime("%d %b"))
        values.append(_metric_for(metric, day_shifts))

    return jsonify({"labels": labels, "datasets": [{
        "label": metric, "data": values, "borderColor": "#0D9488",
        "backgroundColor": "rgba(13,148,136,0.15)", "tension": 0.3, "fill": True}]})


def _metric_for(metric, shifts):
    if not shifts:
        return 0
    if metric == "oee_percent":
        vals = [s.oee_percent for s in shifts if s.oee_percent is not None]
    elif metric == "availability":
        vals = [s.availability_percent for s in shifts if s.availability_percent is not None]
    elif metric == "performance":
        vals = [s.performance_percent for s in shifts if s.performance_percent is not None]
    elif metric == "quality":
        vals = [s.quality_percent for s in shifts if s.quality_percent is not None]
    elif metric == "rejection_rate":
        units = sum(s.actual_units or 0 for s in shifts)
        rej = sum(s.rejection_count or 0 for s in shifts)
        return round(rej / units * 100, 2) if units else 0
    elif metric == "downtime_hours":
        return round(sum((s.total_downtime_minutes or 0) for s in shifts) / 60, 2)
    elif metric == "output_attainment":
        target = sum(s.target_units or 0 for s in shifts)
        actual = sum(s.actual_units or 0 for s in shifts)
        return round(actual / target * 100, 2) if target else 0
    else:
        vals = [s.oee_percent for s in shifts if s.oee_percent is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0
