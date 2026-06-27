from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.improvement import ImprovementOpportunity
from app.forms.improvement_forms import DismissForm, DeferForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit

improvements_bp = Blueprint("improvements", __name__)


@improvements_bp.route("/")
@login_required
def index():
    status = request.args.get("status", "")
    category = request.args.get("category", "")
    q = ImprovementOpportunity.query
    if current_user.role != "super_admin":
        q = q.filter_by(plant_id=current_user.plant_id)
    if status:
        q = q.filter_by(status=status)
    if category:
        q = q.filter_by(category=category)
    opportunities = q.order_by(ImprovementOpportunity.rank_score.desc()).all()
    return render_template("improvements/index.html", opportunities=opportunities,
                           dismiss_form=DismissForm(), defer_form=DeferForm(),
                           filters={"status": status, "category": category})


def _get(id):
    opp = ImprovementOpportunity.query.get_or_404(id)
    if current_user.role != "super_admin" and opp.plant_id != current_user.plant_id:
        abort(403)
    return opp


@improvements_bp.route("/<int:id>/accept", methods=["POST"])
@login_required
@role_required("admin", "plant_manager", "industrial_engineer")
def accept(id):
    opp = _get(id)
    opp.status = "accepted"
    opp.accepted_by = current_user.id
    db.session.commit()
    log_audit("IMPROVEMENT_ACCEPTED", "ImprovementOpportunity", opp.id, opp.opportunity_title)
    flash("Opportunity accepted.", "success")
    return redirect(url_for("improvements.index"))


@improvements_bp.route("/<int:id>/dismiss", methods=["POST"])
@login_required
@role_required("admin", "plant_manager", "industrial_engineer")
def dismiss(id):
    opp = _get(id)
    form = DismissForm()
    if form.validate_on_submit():
        opp.status = "dismissed"
        opp.dismissed_reason = form.dismissed_reason.data
        db.session.commit()
        log_audit("IMPROVEMENT_DISMISSED", "ImprovementOpportunity", opp.id)
        flash("Opportunity dismissed.", "success")
    return redirect(url_for("improvements.index"))


@improvements_bp.route("/<int:id>/defer", methods=["POST"])
@login_required
@role_required("admin", "plant_manager", "industrial_engineer")
def defer(id):
    opp = _get(id)
    form = DeferForm()
    if form.validate_on_submit():
        opp.status = "deferred"
        opp.deferred_until = form.deferred_until.data
        db.session.commit()
        log_audit("IMPROVEMENT_DEFERRED", "ImprovementOpportunity", opp.id)
        flash("Opportunity deferred.", "success")
    return redirect(url_for("improvements.index"))
