from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.extensions import db, bcrypt
from app.forms.admin_forms import ProfileForm
from app.forms.auth_forms import ChangePasswordForm
from app.utils.helpers import log_audit, save_upload

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = ProfileForm(obj=current_user)
    pw_form = ChangePasswordForm()
    if form.submit.data and form.validate_on_submit():
        current_user.full_name = form.full_name.data
        current_user.phone = form.phone.data
        current_user.department = form.department.data
        current_user.most_certification_level = form.most_certification_level.data
        photo = request.files.get("profile_photo")
        if photo and photo.filename:
            path = save_upload(photo, "profiles", [".jpg", ".jpeg", ".png"])
            if path:
                current_user.profile_photo_path = path
        db.session.commit()
        log_audit("PROFILE_UPDATED", "User", current_user.id)
        flash("Profile updated.", "success")
        return redirect(url_for("profile.index"))
    if pw_form.submit.data and pw_form.validate_on_submit():
        if not (current_user.password_hash and
                bcrypt.check_password_hash(current_user.password_hash, pw_form.current_password.data)):
            flash("Current password is incorrect.", "error")
        else:
            current_user.password_hash = bcrypt.generate_password_hash(pw_form.new_password.data, 12).decode("utf-8")
            db.session.commit()
            log_audit("PASSWORD_CHANGED", "User", current_user.id)
            flash("Password updated.", "success")
        return redirect(url_for("profile.index"))
    return render_template("profile/index.html", form=form, pw_form=pw_form)
