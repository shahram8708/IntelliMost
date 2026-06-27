import io
import csv
import secrets
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash, request, abort, Response)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.user import User
from app.models.plant import Plant
from app.models.production_line import ProductionLine
from app.models.machine import Machine
from app.models.sku import SKU
from app.models.reason_code import ReasonCode
from app.models.alert import AlertRule
from app.models.audit_log import AuditLog
from app.models.lead import Lead
from app.forms.admin_forms import (InviteUserForm, EditUserForm, PlantForm, ProductionLineForm,
                                   MachineForm, SkuForm, ReasonCodeForm)
from app.utils.decorators import role_required
from app.utils.helpers import log_audit
from app.services.notification import send_invitation_email

admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
@login_required
@role_required("admin", "super_admin")
def guard():
    pass


def _is_super():
    return current_user.role == "super_admin"


@admin_bp.route("/")
def index():
    if _is_super():
        users = User.query.filter_by(is_deleted=False).count()
        plants = Plant.query.count()
    else:
        users = User.query.filter_by(plant_id=current_user.plant_id, is_deleted=False).count()
        plants = 1
    recent = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(15).all()
    return render_template("admin/index.html", user_count=users, plant_count=plants, recent=recent)


@admin_bp.route("/users")
def users():
    page = request.args.get("page", 1, type=int)
    role = request.args.get("role", "")
    q = User.query.filter_by(is_deleted=False)
    if not _is_super():
        q = q.filter_by(plant_id=current_user.plant_id)
    if role:
        q = q.filter_by(role=role)
    pagination = q.order_by(User.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    invite_form = InviteUserForm()
    invite_form.plant_id.choices = [(0, "None")] + [(p.id, p.name) for p in Plant.query.all()]
    return render_template("admin/users.html", pagination=pagination, users=pagination.items,
                           invite_form=invite_form, filter_role=role)


@admin_bp.route("/users/invite", methods=["GET", "POST"])
def invite_user():
    form = InviteUserForm()
    form.plant_id.choices = [(0, "None")] + [(p.id, p.name) for p in Plant.query.all()]
    if form.validate_on_submit():
        if User.query.filter(db.func.lower(User.email) == form.email.data.lower()).first():
            flash("A user with that email already exists.", "error")
            return redirect(url_for("admin.users"))
        token = secrets.token_urlsafe(32)
        user = User(email=form.email.data.lower(), full_name=form.full_name.data,
                    role=form.role.data, plant_id=form.plant_id.data or None,
                    is_active=False, invitation_token=token,
                    invitation_expires_at=datetime.utcnow() + timedelta(hours=72))
        db.session.add(user)
        db.session.commit()
        send_invitation_email(user, token)
        log_audit("USER_INVITED", "User", user.id, user.email)
        flash(f"Invitation sent to {user.email}.", "success")
        return redirect(url_for("admin.users"))
    return render_template("admin/user_invite.html", form=form)


@admin_bp.route("/users/<int:id>")
def user_detail(id):
    user = User.query.get_or_404(id)
    if not _is_super() and user.plant_id != current_user.plant_id:
        abort(403)
    logs = AuditLog.query.filter_by(user_id=user.id).order_by(AuditLog.created_at.desc()).limit(20).all()
    return render_template("admin/user_detail.html", user=user, logs=logs)


@admin_bp.route("/users/<int:id>/edit", methods=["GET", "POST"])
def edit_user(id):
    user = User.query.get_or_404(id)
    if not _is_super() and user.plant_id != current_user.plant_id:
        abort(403)
    form = EditUserForm(obj=user)
    form.plant_id.choices = [(0, "None")] + [(p.id, p.name) for p in Plant.query.all()]
    if form.validate_on_submit():
        if user.role == "super_admin" and form.role.data != "super_admin" and not _is_super():
            flash("You cannot change a super admin's role.", "error")
            return redirect(url_for("admin.user_detail", id=id))
        user.full_name = form.full_name.data
        user.role = form.role.data
        user.plant_id = form.plant_id.data or None
        user.is_active = form.is_active.data
        user.is_locked = form.is_locked.data
        user.phone = form.phone.data
        user.department = form.department.data
        db.session.commit()
        log_audit("USER_UPDATED", "User", user.id, user.email)
        flash("User updated.", "success")
        return redirect(url_for("admin.user_detail", id=id))
    return render_template("admin/user_edit.html", form=form, user=user)


@admin_bp.route("/users/<int:id>/deactivate", methods=["POST"])
def deactivate_user(id):
    user = User.query.get_or_404(id)
    if not _is_super() and user.plant_id != current_user.plant_id:
        abort(403)
    user.is_active = False
    db.session.commit()
    log_audit("USER_DEACTIVATED", "User", user.id, user.email)
    flash("User deactivated.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:id>/unlock", methods=["POST"])
def unlock_user(id):
    user = User.query.get_or_404(id)
    user.is_locked = False
    user.failed_login_attempts = 0
    db.session.commit()
    log_audit("USER_UNLOCKED", "User", user.id, user.email)
    flash("User unlocked.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/users/<int:id>/resend-invite", methods=["POST"])
def resend_invite(id):
    user = User.query.get_or_404(id)
    token = secrets.token_urlsafe(32)
    user.invitation_token = token
    user.invitation_expires_at = datetime.utcnow() + timedelta(hours=72)
    db.session.commit()
    send_invitation_email(user, token)
    flash("Invitation resent.", "success")
    return redirect(url_for("admin.user_detail", id=id))


@admin_bp.route("/plants")
def plants():
    rows = Plant.query.all() if _is_super() else Plant.query.filter_by(id=current_user.plant_id).all()
    return render_template("admin/plants.html", plants=rows)


@admin_bp.route("/plants/new", methods=["GET", "POST"])
@role_required("super_admin")
def new_plant():
    form = PlantForm()
    if form.validate_on_submit():
        plant = Plant(name=form.name.data, location=form.location.data, timezone=form.timezone.data,
                      industry_type=form.industry_type.data, subscription_tier=form.subscription_tier.data,
                      contact_email=form.contact_email.data, contact_phone=form.contact_phone.data)
        db.session.add(plant)
        db.session.commit()
        log_audit("PLANT_CREATED", "Plant", plant.id, plant.name)
        flash("Plant created.", "success")
        return redirect(url_for("admin.plants"))
    return render_template("admin/plant_form.html", form=form, title="New Plant")


@admin_bp.route("/plants/<int:id>/edit", methods=["GET", "POST"])
def edit_plant(id):
    plant = Plant.query.get_or_404(id)
    if not _is_super() and plant.id != current_user.plant_id:
        abort(403)
    form = PlantForm(obj=plant)
    if form.validate_on_submit():
        form.populate_obj(plant)
        db.session.commit()
        log_audit("PLANT_UPDATED", "Plant", plant.id, plant.name)
        flash("Plant updated.", "success")
        return redirect(url_for("admin.plants"))
    return render_template("admin/plant_form.html", form=form, title="Edit Plant")


def _plant_id():
    return current_user.plant_id or (request.args.get("plant_id", type=int) or 1)


@admin_bp.route("/lines", methods=["GET", "POST"])
def lines():
    pid = current_user.plant_id
    form = ProductionLineForm()
    if form.validate_on_submit():
        line = ProductionLine(plant_id=pid or 1, line_name=form.line_name.data, line_code=form.line_code.data,
                              target_output_per_shift=form.target_output_per_shift.data,
                              shift_duration_hours=form.shift_duration_hours.data,
                              planned_break_minutes=form.planned_break_minutes.data)
        db.session.add(line)
        db.session.commit()
        log_audit("LINE_CREATED", "ProductionLine", line.id, line.line_name)
        flash("Line created.", "success")
        return redirect(url_for("admin.lines"))
    rows = (ProductionLine.query.all() if _is_super()
            else ProductionLine.query.filter_by(plant_id=pid).all())
    return render_template("admin/lines.html", lines=rows, form=form)


@admin_bp.route("/lines/<int:id>/edit", methods=["GET", "POST"])
def edit_line(id):
    line = ProductionLine.query.get_or_404(id)
    if not _is_super() and line.plant_id != current_user.plant_id:
        abort(403)
    form = ProductionLineForm(obj=line)
    if form.validate_on_submit():
        form.populate_obj(line)
        db.session.commit()
        flash("Line updated.", "success")
        return redirect(url_for("admin.lines"))
    return render_template("admin/line_form.html", form=form)


@admin_bp.route("/machines")
def machines():
    if _is_super():
        rows = Machine.query.all()
    else:
        rows = Machine.query.join(Machine.line).filter_by(plant_id=current_user.plant_id).all()
    return render_template("admin/machines.html", machines=rows)


def _line_choices():
    if _is_super():
        return [(l.id, l.line_name) for l in ProductionLine.query.all()]
    return [(l.id, l.line_name) for l in ProductionLine.query.filter_by(plant_id=current_user.plant_id).all()]


@admin_bp.route("/machines/new", methods=["GET", "POST"])
def new_machine():
    form = MachineForm()
    form.line_id.choices = _line_choices()
    if form.validate_on_submit():
        m = Machine(line_id=form.line_id.data, machine_name=form.machine_name.data,
                    machine_code=form.machine_code.data, machine_type=form.machine_type.data,
                    manufacturer=form.manufacturer.data, model_number=form.model_number.data,
                    installation_date=form.installation_date.data)
        db.session.add(m)
        db.session.commit()
        log_audit("MACHINE_CREATED", "Machine", m.id, m.machine_name)
        flash("Machine created.", "success")
        return redirect(url_for("admin.machines"))
    return render_template("admin/machine_form.html", form=form, title="New Machine")


@admin_bp.route("/machines/<int:id>/edit", methods=["GET", "POST"])
def edit_machine(id):
    m = Machine.query.get_or_404(id)
    if not _is_super() and m.line.plant_id != current_user.plant_id:
        abort(403)
    form = MachineForm(obj=m)
    form.line_id.choices = _line_choices()
    if form.validate_on_submit():
        form.populate_obj(m)
        db.session.commit()
        flash("Machine updated.", "success")
        return redirect(url_for("admin.machines"))
    return render_template("admin/machine_form.html", form=form, title="Edit Machine")


@admin_bp.route("/skus")
def skus():
    rows = (SKU.query.all() if _is_super()
            else SKU.query.filter_by(plant_id=current_user.plant_id).all())
    return render_template("admin/skus.html", skus=rows)


@admin_bp.route("/skus/new", methods=["GET", "POST"])
def new_sku():
    form = SkuForm()
    if form.validate_on_submit():
        s = SKU(plant_id=current_user.plant_id or 1, sku_code=form.sku_code.data,
                sku_name=form.sku_name.data, description=form.description.data,
                unit_of_measure=form.unit_of_measure.data, standard_batch_size=form.standard_batch_size.data)
        db.session.add(s)
        db.session.commit()
        flash("SKU created.", "success")
        return redirect(url_for("admin.skus"))
    return render_template("admin/sku_form.html", form=form, title="New SKU")


@admin_bp.route("/skus/<int:id>/edit", methods=["GET", "POST"])
def edit_sku(id):
    s = SKU.query.get_or_404(id)
    if not _is_super() and s.plant_id != current_user.plant_id:
        abort(403)
    form = SkuForm(obj=s)
    if form.validate_on_submit():
        form.populate_obj(s)
        db.session.commit()
        flash("SKU updated.", "success")
        return redirect(url_for("admin.skus"))
    return render_template("admin/sku_form.html", form=form, title="Edit SKU")


@admin_bp.route("/reason-codes", methods=["GET", "POST"])
def reason_codes():
    form = ReasonCodeForm()
    codes = ReasonCode.query.filter(
        (ReasonCode.plant_id == current_user.plant_id) | (ReasonCode.plant_id.is_(None))).all()
    form.parent_id.choices = [(0, "None (top level)")] + [(c.id, c.label) for c in codes]
    if form.validate_on_submit():
        rc = ReasonCode(plant_id=current_user.plant_id, code=form.code.data, label=form.label.data,
                        category=form.category.data, parent_id=form.parent_id.data or None,
                        level=form.level.data)
        db.session.add(rc)
        db.session.commit()
        flash("Reason code added.", "success")
        return redirect(url_for("admin.reason_codes"))
    tops = [c for c in codes if not c.parent_id]
    return render_template("admin/reason_codes.html", tops=tops, form=form)


@admin_bp.route("/alert-rules")
def alert_rules():
    rows = (AlertRule.query.all() if _is_super()
            else AlertRule.query.filter_by(plant_id=current_user.plant_id).all())
    return render_template("admin/alert_rules.html", rules=rows)


@admin_bp.route("/audit-logs")
@role_required("super_admin", "admin")
def audit_logs():
    page = request.args.get("page", 1, type=int)
    action = request.args.get("action", "")
    q = AuditLog.query
    if action:
        q = q.filter(AuditLog.action.ilike(f"%{action}%"))
    pagination = q.order_by(AuditLog.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("admin/audit_logs.html", pagination=pagination, logs=pagination.items,
                           filter_action=action)


@admin_bp.route("/audit-logs/export")
@role_required("super_admin", "admin")
def export_audit():
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["ID", "User", "Action", "Target", "Target ID", "IP", "Created At"])
    for log in AuditLog.query.order_by(AuditLog.created_at.desc()).limit(5000):
        writer.writerow([log.id, log.user.full_name if log.user else "", log.action,
                         log.target_type or "", log.target_id or "", log.ip_address or "",
                         log.created_at.isoformat()])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=audit_logs.csv"})


@admin_bp.route("/integrations")
def integrations():
    return render_template("admin/integrations.html")


@admin_bp.route("/leads")
@role_required("super_admin")
def leads():
    rows = Lead.query.order_by(Lead.created_at.desc()).all()
    return render_template("admin/leads.html", leads=rows)
