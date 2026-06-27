from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models.rejection import RejectionEvent
from app.models.shift import Shift
from app.models.production_line import ProductionLine
from app.models.machine import Machine
from app.models.sku import SKU
from app.forms.rejection_forms import RejectionForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit
from app.services.oee_calculator import calculate_oee
from app.services.alert_engine import evaluate_for_metric

rejections_bp = Blueprint("rejections", __name__)


def _scoped_query():
    q = RejectionEvent.query.join(Shift).join(Shift.line)
    if current_user.role != "super_admin":
        q = q.filter(ProductionLine.plant_id == current_user.plant_id)
    return q


@rejections_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    sku_id = request.args.get("sku_id", type=int)
    defect = request.args.get("defect_type", "")
    q = _scoped_query()
    if sku_id:
        q = q.filter(RejectionEvent.sku_id == sku_id)
    if defect:
        q = q.filter(RejectionEvent.defect_type.ilike(f"%{defect}%"))
    pagination = q.order_by(RejectionEvent.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    trend = {"labels": [], "data": []}
    for i in range(29, -1, -1):
        day = datetime.utcnow().date() - timedelta(days=i)
        start = datetime(day.year, day.month, day.day)
        end = start + timedelta(days=1)
        total = (_scoped_query().with_entities(func.sum(RejectionEvent.quantity_rejected))
                 .filter(RejectionEvent.created_at >= start, RejectionEvent.created_at < end).scalar())
        trend["labels"].append(day.strftime("%d %b"))
        trend["data"].append(int(total or 0))

    pareto_rows = (_scoped_query().with_entities(RejectionEvent.defect_type,
                                                 func.sum(RejectionEvent.quantity_rejected))
                   .group_by(RejectionEvent.defect_type)
                   .order_by(func.sum(RejectionEvent.quantity_rejected).desc()).limit(10).all())
    pareto = {"labels": [r[0] for r in pareto_rows], "data": [int(r[1] or 0) for r in pareto_rows]}

    skus = (SKU.query.filter_by(plant_id=current_user.plant_id).all()
            if current_user.role != "super_admin" else SKU.query.all())
    return render_template("rejections/index.html", pagination=pagination,
                           rejections=pagination.items, trend=trend, pareto=pareto, skus=skus,
                           filters={"sku_id": sku_id, "defect_type": defect})


@rejections_bp.route("/log", methods=["GET", "POST"])
@login_required
@role_required("shift_supervisor", "operator", "qa_manager", "admin")
def log_rejection():
    form = RejectionForm()
    shifts = (Shift.query.join(ProductionLine).filter(ProductionLine.plant_id == current_user.plant_id)
              .order_by(Shift.start_time.desc()).limit(30).all())
    machines = (Machine.query.join(Machine.line).filter_by(plant_id=current_user.plant_id).all())
    skus = SKU.query.filter_by(plant_id=current_user.plant_id).all()
    form.shift_id.choices = [(s.id, f"{s.line.line_name} - {s.shift_label}") for s in shifts]
    form.machine_id.choices = [(0, "None")] + [(m.id, m.machine_name) for m in machines]
    form.sku_id.choices = [(0, "None")] + [(s.id, s.sku_name) for s in skus]

    if form.validate_on_submit():
        rej = RejectionEvent(shift_id=form.shift_id.data, sku_id=form.sku_id.data or None,
                             machine_id=form.machine_id.data or None,
                             quantity_rejected=form.quantity_rejected.data,
                             defect_type=form.defect_type.data,
                             defect_description=form.defect_description.data,
                             probable_cause=form.probable_cause.data,
                             quality_check_point=form.quality_check_point.data,
                             batch_reference=form.batch_reference.data,
                             logged_by=current_user.id)
        db.session.add(rej)
        try:
            db.session.commit()
            shift = Shift.query.get(form.shift_id.data)
            if shift:
                shift.rejection_count = (shift.rejection_count or 0) + form.quantity_rejected.data
                db.session.commit()
                calculate_oee(shift.id)
                evaluate_for_metric(shift.line.plant_id, "rejection_rate", shift.line_id)
            log_audit("REJECTION_LOGGED", "RejectionEvent", rej.id, rej.defect_type)
            flash("Rejection logged.", "success")
        except Exception:
            db.session.rollback()
            flash("Could not log rejection.", "error")
        return redirect(url_for("rejections.log_rejection"))
    return render_template("rejections/log_rejection.html", form=form, shifts=shifts,
                           machines=machines, skus=skus)
