import secrets
from datetime import datetime, timedelta
from flask import (Blueprint, render_template, redirect, url_for, flash, request)
from flask_login import login_user, logout_user, login_required, current_user
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

from app.extensions import db, bcrypt, limiter
from app.models.user import User
from app.forms.auth_forms import (LoginForm, RegisterForm, ForgotPasswordForm, PasswordResetForm)
from app.services.notification import send_password_reset_email, send_account_lock_email
from app.utils.helpers import log_audit, sha256_hex

auth_bp = Blueprint("auth", __name__)


def _serializer():
    from flask import current_app
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="pw-reset")


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute;50 per day", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter(db.func.lower(User.email) == form.email.data.lower().strip()).first()
        if not user or user.is_deleted:
            flash("Invalid email or password.", "error")
            return redirect(url_for("auth.login"))
        if user.is_locked or user.failed_login_attempts >= 5:
            user.is_locked = True
            db.session.commit()
            flash("Your account is locked due to repeated failed logins. Contact your administrator.", "error")
            return redirect(url_for("auth.login"))
        if not user.is_active:
            flash("This account has been deactivated.", "error")
            return redirect(url_for("auth.login"))
        if user.password_hash and bcrypt.check_password_hash(user.password_hash, form.password.data):
            user.failed_login_attempts = 0
            user.is_locked = False
            user.last_login = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=form.remember_me.data)
            log_audit("USER_LOGIN", "User", user.id, f"{user.email} logged in")
            nxt = request.args.get("next")
            return redirect(nxt or url_for("dashboard.index"))
        user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
        if user.failed_login_attempts >= 5:
            user.is_locked = True
            db.session.commit()
            send_account_lock_email(user)
            flash("Account locked after 5 failed attempts. A notification email has been sent.", "error")
        else:
            db.session.commit()
            flash("Invalid email or password.", "error")
        return redirect(url_for("auth.login"))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    log_audit("USER_LOGOUT", "User", current_user.id, f"{current_user.email} logged out")
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/register/<token>", methods=["GET", "POST"])
@limiter.limit("10 per hour", methods=["POST"])
def register(token):
    user = User.query.filter_by(invitation_token=token).first()
    error = None
    if not user:
        error = "This invitation link is invalid."
    elif user.invitation_expires_at and user.invitation_expires_at < datetime.utcnow():
        error = "This invitation link has expired. Please request a new one."
    form = RegisterForm()
    if error:
        return render_template("auth/register.html", form=form, error=error, token=token)
    if form.validate_on_submit():
        user.full_name = form.full_name.data.strip()
        user.password_hash = bcrypt.generate_password_hash(form.password.data, 12).decode("utf-8")
        user.is_active = True
        user.invitation_token = None
        user.invitation_expires_at = None
        db.session.commit()
        login_user(user)
        log_audit("USER_REGISTERED", "User", user.id, f"{user.email} completed registration")
        flash("Welcome to IntelliMOST!", "success")
        return redirect(url_for("dashboard.index"))
    return render_template("auth/register.html", form=form, error=None, token=token, invited=user)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot_password():
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter(db.func.lower(User.email) == form.email.data.lower().strip()).first()
        if user and user.is_active and not user.is_deleted:
            token = _serializer().dumps(user.email)
            user.reset_token_hash = sha256_hex(token)
            user.reset_token_expires_at = datetime.utcnow() + timedelta(hours=1)
            db.session.commit()
            send_password_reset_email(user, token)
        flash("If that email is registered, a password reset link has been sent.", "info")
        return redirect(url_for("auth.login"))
    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    try:
        email = _serializer().loads(token, max_age=3600)
    except (BadSignature, SignatureExpired):
        flash("This reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    user = User.query.filter(db.func.lower(User.email) == email.lower()).first()
    if (not user or user.reset_token_hash != sha256_hex(token)
            or not user.reset_token_expires_at or user.reset_token_expires_at < datetime.utcnow()):
        flash("This reset link is invalid or has expired.", "error")
        return redirect(url_for("auth.forgot_password"))
    form = PasswordResetForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(form.password.data, 12).decode("utf-8")
        user.reset_token_hash = None
        user.reset_token_expires_at = None
        user.failed_login_attempts = 0
        user.is_locked = False
        db.session.commit()
        log_audit("PASSWORD_RESET", "User", user.id, f"{user.email} reset password", user=user)
        flash("Your password has been reset. Please sign in.", "success")
        return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html", form=form, token=token)
