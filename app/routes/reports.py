from flask import Blueprint, render_template, request, flash, redirect, url_for, Response
from flask_login import login_required, current_user
from app.models.production_line import ProductionLine
from app.forms.report_forms import ReportForm, ScheduledReportForm
from app.utils.decorators import role_required
from app.services.report_generator import generate_report

reports_bp = Blueprint("reports", __name__)

MIME = {"pdf": "application/pdf",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


@reports_bp.route("/")
@login_required
def index():
    return render_template("reports/index.html", form=ReportForm())


@reports_bp.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    form = ReportForm()
    lines = (ProductionLine.query.filter_by(plant_id=current_user.plant_id).all()
             if current_user.role != "super_admin" else ProductionLine.query.all())
    form.line_ids.choices = [(l.id, l.line_name) for l in lines]
    if form.validate_on_submit():
        from datetime import datetime, time
        params = {
            "plant_id": current_user.plant_id,
            "start_date": datetime.combine(form.start_date.data, time.min) if form.start_date.data else None,
            "end_date": datetime.combine(form.end_date.data, time.max) if form.end_date.data else None,
            "line_ids": form.line_ids.data,
        }
        content, ext, name = generate_report(form.report_type.data, params, form.format.data)
        return Response(content, mimetype=MIME.get(ext, "application/octet-stream"),
                        headers={"Content-Disposition": f"attachment; filename={name}.{ext}"})
    return render_template("reports/index.html", form=form)


@reports_bp.route("/schedule", methods=["GET", "POST"])
@login_required
@role_required("admin", "plant_manager", "super_admin")
def schedule():
    form = ScheduledReportForm()
    if form.validate_on_submit():
        flash("Scheduled report saved. Delivery will run on the configured schedule.", "success")
        return redirect(url_for("reports.index"))
    return render_template("reports/index.html", form=ReportForm(), schedule_form=form)
