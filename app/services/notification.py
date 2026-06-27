from flask import current_app, url_for
from flask_mail import Message
from app.extensions import mail


def _send(subject, recipients, body, html=None):
    if not recipients:
        return
    try:
        msg = Message(subject=subject, recipients=recipients,
                      sender=current_app.config.get("MAIL_DEFAULT_SENDER"))
        msg.body = body
        if html:
            msg.html = html
        if current_app.config.get("MAIL_USERNAME"):
            mail.send(msg)
        else:
            current_app.logger.info("EMAIL (suppressed, no MAIL_USERNAME): %s -> %s", subject, recipients)
    except Exception as e:
        current_app.logger.warning("Email send failed: %s", e)


def send_invitation_email(user, token):
    try:
        link = url_for("auth.register", token=token, _external=True)
    except Exception:
        link = f"/register/{token}"
    body = (f"Hello {user.full_name},\n\nYou have been invited to IntelliMOST. "
            f"Complete your registration here (expires in 72 hours):\n{link}\n")
    _send("Your IntelliMOST invitation", [user.email], body)


def send_password_reset_email(user, token):
    try:
        link = url_for("auth.reset_password", token=token, _external=True)
    except Exception:
        link = f"/reset-password/{token}"
    body = (f"Hello {user.full_name},\n\nReset your IntelliMOST password using the link below "
            f"(valid for 1 hour):\n{link}\n\nIf you did not request this, ignore this email.\n")
    _send("Reset your IntelliMOST password", [user.email], body)


def send_account_lock_email(user):
    body = (f"Hello {user.full_name},\n\nYour IntelliMOST account has been locked after multiple "
            "failed login attempts. Contact your administrator to unlock it.\n")
    _send("IntelliMOST account locked", [user.email], body)


def send_alert_email(rule, event, triggered_value, is_escalation=False):
    from app.models.user import User
    ids = (rule.escalation_user_ids if is_escalation else rule.recipient_user_ids) or []
    users = User.query.filter(User.id.in_(ids)).all() if ids else []
    recipients = [u.email for u in users]
    prefix = "ESCALATED ALERT" if is_escalation else "ALERT"
    body = (f"{prefix}: {rule.rule_name}\n\nMetric: {rule.metric_name}\n"
            f"Triggered value: {triggered_value}\nThreshold: {rule.threshold_value}\n"
            f"Triggered at: {event.triggered_at}\n")
    _send(f"[{prefix}] {rule.rule_name}", recipients, body)


def send_capa_assignment_email(capa, owner):
    body = (f"Hello {owner.full_name},\n\nYou have been assigned CAPA {capa.capa_number}: "
            f"{capa.title}\nDue date: {capa.due_date}\nSeverity: {capa.severity}\n")
    _send(f"CAPA assigned: {capa.capa_number}", [owner.email], body)


def send_capa_status_email(capa, action_by):
    recips = []
    if capa.raised_by:
        recips.append(capa.raised_by.email)
    if capa.reviewer:
        recips.append(capa.reviewer.email)
    body = (f"CAPA {capa.capa_number} status changed to {capa.status} by {action_by.full_name}.\n"
            f"Title: {capa.title}\n")
    _send(f"CAPA {capa.capa_number} status: {capa.status}", recips, body)
