from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user
from sqlalchemy.orm import joinedload
from app.extensions import db
from app.models.production_line import ProductionLine
from app.models.shift import Shift, ProductionOutput
from app.models.downtime import DowntimeEvent
from app.models.rejection import RejectionEvent
from app.models.most_study import MostStudy
from app.forms.rejection_forms import OutputLogForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit
from app.services.oee_calculator import calculate_oee
from app.services.alert_engine import evaluate_for_metric

production_bp = Blueprint("production", __name__)


def _scoped_lines():
    q = ProductionLine.query.filter_by(is_active=True)
    if current_user.role != "super_admin":
        q = q.filter_by(plant_id=current_user.plant_id)
    return q


@production_bp.route("/")
@login_required
def index():
    lines = _scoped_lines().options(joinedload(ProductionLine.shifts)).all()
    data = []
    for line in lines:
        shift = Shift.query.filter_by(line_id=line.id, status="active").first()
        active_dt = 0
        if shift:
            active_dt = DowntimeEvent.query.filter_by(shift_id=shift.id, is_resolved=False).count()
        status = "idle"
        if shift:
            status = "fault" if active_dt else "running"
        data.append({"line": line, "shift": shift, "active_dt": active_dt, "status": status})
    return render_template("production/index.html", data=data)


@production_bp.route("/line/<int:id>")
@login_required
def line_detail(id):
    line = ProductionLine.query.get_or_404(id)
    if current_user.role != "super_admin" and line.plant_id != current_user.plant_id:
        abort(403)
    shift = Shift.query.filter_by(line_id=line.id, status="active").first()
    last7 = (Shift.query.filter_by(line_id=line.id)
             .order_by(Shift.start_time.desc()).limit(7).all())
    last7 = list(reversed(last7))
    active_dt = []
    rejections = []
    oee = None
    if shift:
        active_dt = (DowntimeEvent.query.filter_by(shift_id=shift.id)
                     .order_by(DowntimeEvent.start_time.desc()).all())
        rejections = RejectionEvent.query.filter_by(shift_id=shift.id).all()
        oee = calculate_oee(shift.id)
    mids = [m.id for m in line.machines]
    studies = (MostStudy.query.filter(MostStudy.workstation_id.in_(mids),
                                      MostStudy.status == "published").all() if mids else [])
    chart = {"labels": [s.start_time.strftime("%d %b") for s in last7],
             "actual": [s.actual_units or 0 for s in last7],
             "target": [s.target_units or 0 for s in last7]}
    return render_template("production/line_detail.html", line=line, shift=shift, last7=last7,
                           active_dt=active_dt, rejections=rejections, oee=oee,
                           studies=studies, chart=chart)


@production_bp.route("/shift/<int:id>")
@login_required
def shift_detail(id):
    shift = Shift.query.get_or_404(id)
    if current_user.role != "super_admin" and shift.line.plant_id != current_user.plant_id:
        abort(403)
    outputs = (ProductionOutput.query.filter_by(shift_id=shift.id)
               .order_by(ProductionOutput.logged_at.desc()).all())
    oee = calculate_oee(shift.id)
    return render_template("production/shift_detail.html", shift=shift, outputs=outputs, oee=oee)


@production_bp.route("/output/log", methods=["GET", "POST"])
@login_required
@role_required("operator", "shift_supervisor", "admin", "plant_manager")
def output_log():
    form = OutputLogForm()
    shifts = (Shift.query.join(ProductionLine).filter(ProductionLine.plant_id == current_user.plant_id,
                                                      Shift.status == "active").all())
    form.shift_id.choices = [(s.id, f"{s.line.line_name} - {s.shift_label}") for s in shifts]
    if form.validate_on_submit():
        shift = Shift.query.get(form.shift_id.data)
        if not shift:
            flash("Shift not found.", "error")
            return redirect(url_for("production.output_log"))
        shift.actual_units = (shift.actual_units or 0) + form.quantity.data
        out = ProductionOutput(shift_id=shift.id, logged_by=current_user.id,
                               quantity=form.quantity.data, cumulative_total=shift.actual_units,
                               logged_at=datetime.utcnow(), notes=form.notes.data)
        db.session.add(out)
        try:
            db.session.commit()
            calculate_oee(shift.id)
            evaluate_for_metric(shift.line.plant_id, "output_attainment", shift.line_id)
            log_audit("OUTPUT_LOGGED", "Shift", shift.id, f"+{form.quantity.data} units")
            flash("Output logged successfully.", "success")
        except Exception:
            db.session.rollback()
            flash("Could not log output. Try again.", "error")
        return redirect(url_for("production.output_log"))
    return render_template("production/output_log.html", form=form, shifts=shifts)
