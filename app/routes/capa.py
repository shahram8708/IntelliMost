from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort, Response
from flask_login import login_required, current_user
from app.extensions import db
from app.models.capa import CapaRecord, CapaComment
from app.models.machine import Machine
from app.models.sku import SKU
from app.models.user import User
from app.forms.capa_forms import CapaForm, CapaUpdateForm, CapaStatusForm, CapaCommentForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit, save_upload
from app.services.notification import send_capa_assignment_email, send_capa_status_email
from app.services.report_generator import generate_capa_pdf

capa_bp = Blueprint("capa", __name__)


def _scoped():
    q = CapaRecord.query
    if current_user.role != "super_admin":
        q = q.filter_by(plant_id=current_user.plant_id)
    return q


def _next_capa_number():
    year = date.today().year
    prefix = f"CAPA-{year}-"
    last = (CapaRecord.query.filter(CapaRecord.capa_number.like(f"{prefix}%"))
            .order_by(CapaRecord.id.desc()).first())
    n = 1
    if last:
        try:
            n = int(last.capa_number.split("-")[-1]) + 1
        except Exception:
            n = CapaRecord.query.count() + 1
    return f"{prefix}{n:04d}"


@capa_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    severity = request.args.get("severity", "")
    owner = request.args.get("owner", type=int)
    q = _scoped()
    if status:
        q = q.filter_by(status=status)
    if severity:
        q = q.filter_by(severity=severity)
    if owner:
        q = q.filter_by(owner_id=owner)
    pagination = q.order_by(CapaRecord.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    today = date.today()
    all_open = _scoped().filter(CapaRecord.status != "closed").all()
    aging = {"lt7": 0, "d7_30": 0, "gt30": 0}
    for c in all_open:
        days = (today - c.due_date).days
        if days > 30:
            aging["gt30"] += 1
        elif days >= 7:
            aging["d7_30"] += 1
        else:
            aging["lt7"] += 1
    users = (User.query.filter_by(plant_id=current_user.plant_id).all()
             if current_user.role != "super_admin" else User.query.all())
    return render_template("capa/index.html", pagination=pagination, capas=pagination.items,
                           aging=aging, users=users,
                           filters={"status": status, "severity": severity, "owner": owner})


@capa_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("qa_manager", "admin", "plant_manager", "super_admin")
def new_capa():
    form = CapaForm()
    machines = Machine.query.join(Machine.line).filter_by(plant_id=current_user.plant_id).all()
    skus = SKU.query.filter_by(plant_id=current_user.plant_id).all()
    users = User.query.filter_by(plant_id=current_user.plant_id).all()
    form.affected_machine_id.choices = [(0, "None")] + [(m.id, m.machine_name) for m in machines]
    form.affected_sku_id.choices = [(0, "None")] + [(s.id, s.sku_name) for s in skus]
    form.owner_id.choices = [(u.id, u.full_name) for u in users]
    form.reviewer_id.choices = [(0, "None")] + [(u.id, u.full_name) for u in users]

    if request.args.get("source_type"):
        form.source_type.data = request.args.get("source_type")
        form.source_description.data = request.args.get("source_description", "")

    if form.validate_on_submit():
        capa = CapaRecord(
            capa_number=_next_capa_number(), title=form.title.data, severity=form.severity.data,
            source_type=form.source_type.data, source_description=form.source_description.data,
            plant_id=current_user.plant_id, affected_machine_id=form.affected_machine_id.data or None,
            affected_sku_id=form.affected_sku_id.data or None, affected_batch=form.affected_batch.data,
            deviation_description=form.deviation_description.data, immediate_action=form.immediate_action.data,
            owner_id=form.owner_id.data, raised_by_id=current_user.id,
            reviewer_id=form.reviewer_id.data or None, due_date=form.due_date.data,
            priority=form.priority.data, status="open")
        db.session.add(capa)
        try:
            db.session.commit()
            owner = User.query.get(capa.owner_id)
            if owner:
                send_capa_assignment_email(capa, owner)
            src_id = request.args.get("source_id", type=int)
            if src_id:
                capa.source_id = src_id
                db.session.commit()
            log_audit("CAPA_CREATED", "CapaRecord", capa.id, capa.capa_number)
            flash(f"{capa.capa_number} created.", "success")
            return redirect(url_for("capa.detail", id=capa.id))
        except Exception:
            db.session.rollback()
            flash("Could not create CAPA.", "error")
    return render_template("capa/new_capa.html", form=form, machines=machines, skus=skus, users=users)


@capa_bp.route("/<int:id>")
@login_required
def detail(id):
    capa = CapaRecord.query.get_or_404(id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    update_form = CapaUpdateForm(obj=capa)
    status_form = CapaStatusForm()
    comment_form = CapaCommentForm()
    return render_template("capa/detail.html", capa=capa, update_form=update_form,
                           status_form=status_form, comment_form=comment_form)


@capa_bp.route("/<int:id>/update", methods=["POST"])
@login_required
@role_required("qa_manager", "admin", "plant_manager", "super_admin")
def update(id):
    capa = CapaRecord.query.get_or_404(id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    form = CapaUpdateForm()
    if form.validate_on_submit():
        capa.corrective_action = form.corrective_action.data
        capa.preventive_action = form.preventive_action.data
        capa.immediate_action = form.immediate_action.data
        capa.root_cause_summary = form.root_cause_summary.data
        db.session.commit()
        log_audit("CAPA_UPDATED", "CapaRecord", capa.id, capa.capa_number)
        flash("CAPA updated.", "success")
    return redirect(url_for("capa.detail", id=id))


@capa_bp.route("/<int:id>/status", methods=["POST"])
@login_required
@role_required("qa_manager", "admin", "plant_manager")
def status(id):
    capa = CapaRecord.query.get_or_404(id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    form = CapaStatusForm()
    if form.validate_on_submit():
        new_status = form.new_status.data
        if new_status == "closed":
            if not form.closure_notes.data:
                flash("Closure notes are required to close a CAPA.", "error")
                return redirect(url_for("capa.detail", id=id))
            evidence_path = None
            if form.evidence.data:
                evidence_path = save_upload(form.evidence.data, "evidence",
                                            [".jpg", ".jpeg", ".png", ".pdf"])
            if not evidence_path and not capa.evidence_paths:
                flash("Evidence is required to close a CAPA.", "error")
                return redirect(url_for("capa.detail", id=id))
            paths = capa.evidence_paths or []
            if evidence_path:
                paths.append(evidence_path)
            capa.evidence_paths = paths
            capa.closed_at = datetime.utcnow()
            capa.closure_notes = form.closure_notes.data
        else:
            if form.evidence.data:
                paths = capa.evidence_paths or []
                p = save_upload(form.evidence.data, "evidence", [".jpg", ".jpeg", ".png", ".pdf"])
                if p:
                    paths.append(p)
                capa.evidence_paths = paths
        capa.status = new_status
        db.session.commit()
        send_capa_status_email(capa, current_user)
        log_audit("CAPA_STATUS_CHANGED", "CapaRecord", capa.id, f"{capa.capa_number} -> {new_status}")
        flash("CAPA status updated.", "success")
    return redirect(url_for("capa.detail", id=id))


@capa_bp.route("/<int:id>/comment", methods=["POST"])
@login_required
def comment(id):
    capa = CapaRecord.query.get_or_404(id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    form = CapaCommentForm()
    if form.validate_on_submit():
        db.session.add(CapaComment(capa_id=capa.id, user_id=current_user.id, body=form.body.data))
        db.session.commit()
        flash("Comment added.", "success")
    return redirect(url_for("capa.detail", id=id))


@capa_bp.route("/<int:id>/export")
@login_required
def export(id):
    capa = CapaRecord.query.get_or_404(id)
    if current_user.role != "super_admin" and capa.plant_id != current_user.plant_id:
        abort(403)
    pdf = generate_capa_pdf(capa.id)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename={capa.capa_number}.pdf"})
