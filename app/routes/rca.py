import json
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.capa import CapaRecord
from app.models.rca import RcaRecord
from app.forms.rca_forms import RcaForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit

rca_bp = Blueprint("rca", __name__)


@rca_bp.route("/<int:capa_id>", methods=["GET", "POST"])
@login_required
@role_required("qa_manager", "admin", "industrial_engineer", "plant_manager")
def workspace(capa_id):
    capa = CapaRecord.query.get_or_404(capa_id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    rca = RcaRecord.query.filter_by(capa_id=capa.id).first()
    form = RcaForm(obj=rca)
    if not rca and request.method == "GET":
        form.problem_statement.data = capa.deviation_description

    if form.validate_on_submit():
        similar = form.similar_events_referenced.data
        try:
            similar_list = json.loads(similar) if similar else []
        except Exception:
            similar_list = []
        if not rca:
            rca = RcaRecord(capa_id=capa.id, analyst_id=current_user.id,
                            problem_statement=form.problem_statement.data)
            db.session.add(rca)
        rca.problem_statement = form.problem_statement.data
        rca.why_1 = form.why_1.data
        rca.why_2 = form.why_2.data
        rca.why_3 = form.why_3.data
        rca.why_4 = form.why_4.data
        rca.why_5 = form.why_5.data
        rca.root_cause_statement = form.root_cause_statement.data
        rca.root_cause_category = form.root_cause_category.data or None
        rca.similar_events_referenced = similar_list
        capa.root_cause_summary = form.root_cause_statement.data
        try:
            db.session.commit()
            log_audit("RCA_COMPLETED", "RcaRecord", rca.id, capa.capa_number)
            flash("Root cause analysis saved.", "success")
            return redirect(url_for("capa.detail", id=capa.id))
        except Exception:
            db.session.rollback()
            flash("Could not save RCA.", "error")
    return render_template("rca/workspace.html", capa=capa, rca=rca, form=form)
