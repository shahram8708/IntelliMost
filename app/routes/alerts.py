from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from app.extensions import db
from app.models.alert import AlertRule, AlertEvent
from app.models.production_line import ProductionLine
from app.models.user import User
from app.forms.alert_forms import AlertRuleForm, AcknowledgeAlertForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit

alerts_bp = Blueprint("alerts", __name__)


def _scope_events(q):
    if current_user.role != "super_admin":
        q = q.filter(AlertEvent.plant_id == current_user.plant_id)
    return q


@alerts_bp.route("/")
@login_required
def index():
    active = _scope_events(AlertEvent.query.filter(AlertEvent.status.in_(["open", "escalated"]))
                           ).order_by(AlertEvent.triggered_at.desc()).all()
    history_q = _scope_events(AlertEvent.query.filter(
        AlertEvent.status.in_(["acknowledged", "dismissed"]),
        AlertEvent.triggered_at >= datetime.utcnow() - timedelta(days=30)))
    page = request.args.get("page", 1, type=int)
    history = history_q.order_by(AlertEvent.triggered_at.desc()).paginate(page=page, per_page=20, error_out=False)
    rules_q = AlertRule.query
    if current_user.role != "super_admin":
        rules_q = rules_q.filter_by(plant_id=current_user.plant_id)
    rules = rules_q.all()
    ack_form = AcknowledgeAlertForm()
    return render_template("alerts/index.html", active=active, history=history,
                           rules=rules, ack_form=ack_form)


@alerts_bp.route("/<int:id>/acknowledge", methods=["POST"])
@login_required
def acknowledge(id):
    event = AlertEvent.query.get_or_404(id)
    if current_user.role != "super_admin" and event.plant_id != current_user.plant_id:
        abort(403)
    form = AcknowledgeAlertForm()
    if form.validate_on_submit():
        event.status = "acknowledged"
        event.acknowledged_by = current_user.id
        event.acknowledged_at = datetime.utcnow()
        event.action_taken = form.action.data
        event.notes = form.notes.data
        db.session.commit()
        log_audit("ALERT_ACKNOWLEDGED", "AlertEvent", event.id)
        flash("Alert acknowledged.", "success")
        if form.action.data == "capa_raised":
            return redirect(url_for("capa.new_capa", source_type="alert", source_id=event.id,
                                    source_description=f"Alert: {event.rule.rule_name}"))
    return redirect(url_for("alerts.index"))


def _rule_form_choices(form):
    lines = (ProductionLine.query.filter_by(plant_id=current_user.plant_id).all()
             if current_user.role != "super_admin" else ProductionLine.query.all())
    users = (User.query.filter_by(plant_id=current_user.plant_id).all()
             if current_user.role != "super_admin" else User.query.all())
    form.line_id.choices = [(0, "All Lines")] + [(l.id, l.line_name) for l in lines]
    form.recipient_user_ids.choices = [(u.id, u.full_name) for u in users]
    form.escalation_user_ids.choices = [(u.id, u.full_name) for u in users]


@alerts_bp.route("/rules/new", methods=["GET", "POST"])
@login_required
@role_required("admin", "plant_manager", "super_admin")
def new_rule():
    form = AlertRuleForm()
    _rule_form_choices(form)
    if form.validate_on_submit():
        rule = AlertRule(plant_id=current_user.plant_id or 1, rule_name=form.rule_name.data,
                         metric_name=form.metric_name.data, operator=form.operator.data,
                         threshold_value=form.threshold_value.data,
                         time_window_minutes=form.time_window_minutes.data,
                         line_id=form.line_id.data or None,
                         recipient_user_ids=form.recipient_user_ids.data,
                         escalation_timeout_minutes=form.escalation_timeout_minutes.data,
                         escalation_user_ids=form.escalation_user_ids.data or [],
                         is_active=form.is_active.data, created_by=current_user.id)
        db.session.add(rule)
        db.session.commit()
        log_audit("ALERT_RULE_CREATED", "AlertRule", rule.id, rule.rule_name)
        flash("Alert rule created.", "success")
        return redirect(url_for("alerts.index"))
    return render_template("alerts/rule_form.html", form=form, title="New Alert Rule")


@alerts_bp.route("/rules/<int:id>/edit", methods=["GET", "POST"])
@login_required
@role_required("admin", "plant_manager", "super_admin")
def edit_rule(id):
    rule = AlertRule.query.get_or_404(id)
    if current_user.role != "super_admin" and rule.plant_id != current_user.plant_id:
        abort(403)
    form = AlertRuleForm(obj=rule)
    _rule_form_choices(form)
    if form.validate_on_submit():
        rule.rule_name = form.rule_name.data
        rule.metric_name = form.metric_name.data
        rule.operator = form.operator.data
        rule.threshold_value = form.threshold_value.data
        rule.time_window_minutes = form.time_window_minutes.data
        rule.line_id = form.line_id.data or None
        rule.recipient_user_ids = form.recipient_user_ids.data
        rule.escalation_timeout_minutes = form.escalation_timeout_minutes.data
        rule.escalation_user_ids = form.escalation_user_ids.data or []
        rule.is_active = form.is_active.data
        db.session.commit()
        log_audit("ALERT_RULE_UPDATED", "AlertRule", rule.id, rule.rule_name)
        flash("Alert rule updated.", "success")
        return redirect(url_for("alerts.index"))
    return render_template("alerts/rule_form.html", form=form, title="Edit Alert Rule")


@alerts_bp.route("/rules/<int:id>/toggle", methods=["POST"])
@login_required
@role_required("admin", "plant_manager", "super_admin")
def toggle_rule(id):
    rule = AlertRule.query.get_or_404(id)
    if current_user.role != "super_admin" and rule.plant_id != current_user.plant_id:
        abort(403)
    rule.is_active = not rule.is_active
    db.session.commit()
    flash("Rule status changed.", "success")
    return redirect(url_for("alerts.index"))
