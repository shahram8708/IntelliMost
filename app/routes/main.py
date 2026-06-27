from flask import Blueprint, render_template, redirect, url_for, flash, send_from_directory, current_app, abort
from flask_login import current_user, login_required
from app.extensions import db
from app.models.lead import Lead
from app.forms.main_forms import DemoRequestForm, ContactForm
from app.services.notification import _send

main_bp = Blueprint("main", __name__)


@main_bp.route("/", methods=["GET", "POST"])
def index():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = DemoRequestForm()
    if form.validate_on_submit():
        lead = Lead(name=form.name.data, email=form.email.data, company=form.company.data,
                    role=form.role.data, facility_type=form.facility_type.data,
                    phone=form.phone.data, source="demo_request")
        db.session.add(lead)
        db.session.commit()
        _send("New IntelliMOST demo request",
              [current_app.config.get("MAIL_DEFAULT_SENDER")],
              f"New demo request from {form.name.data} ({form.email.data}), {form.company.data}.")
        flash("Thanks! Our team will reach out shortly to schedule your demo.", "success")
        return redirect(url_for("main.index"))
    return render_template("main/index.html", form=form)


@main_bp.route("/about")
def about():
    return render_template("main/about.html")


@main_bp.route("/features")
def features():
    return render_template("main/features.html")


@main_bp.route("/contact", methods=["GET", "POST"])
def contact():
    form = ContactForm()
    if form.validate_on_submit():
        lead = Lead(name=form.name.data, email=form.email.data, company=form.company.data,
                    message=form.message.data, source="contact")
        db.session.add(lead)
        db.session.commit()
        _send("New IntelliMOST contact message",
              [current_app.config.get("MAIL_DEFAULT_SENDER")],
              f"Message from {form.name.data} ({form.email.data}):\n{form.message.data}")
        flash("Your message has been sent. We'll be in touch soon.", "success")
        return redirect(url_for("main.contact"))
    return render_template("main/contact.html", form=form)


@main_bp.route("/uploads/<path:filename>")
@login_required
def uploads(filename):
    if ".." in filename:
        abort(404)
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
