import os
import uuid
from datetime import datetime, date
from flask import (Blueprint, render_template, redirect, url_for, flash, request,
                   session, abort, Response, current_app)
from flask_login import login_required, current_user
from app.extensions import db
from app.models.most_study import MostStudy
from app.models.most_element import MostElement
from app.models.machine import Machine
from app.models.sku import SKU
from app.models.user import User
from app.forms.study_forms import StudyMetaForm, VideoUploadForm, ElementForm, AllowanceForm
from app.utils.decorators import role_required
from app.utils.helpers import log_audit, save_upload
from app.services import most_calculator
from app.services.report_generator import generate_most_pdf

work_study_bp = Blueprint("work_study", __name__)
INDEX_OPTIONS = [0, 1, 3, 6, 10, 16, 24, 32]


def _plant_machines():
    return (Machine.query.join(Machine.line)
            .filter_by(plant_id=current_user.plant_id, is_active=True).all())


def _plant_skus():
    return SKU.query.filter_by(plant_id=current_user.plant_id, is_active=True).all()


@work_study_bp.route("/")
@login_required
def index():
    page = request.args.get("page", 1, type=int)
    status = request.args.get("status", "")
    ws = request.args.get("workstation_id", type=int)
    analyst = request.args.get("analyst_id", type=int)
    q = MostStudy.query
    if current_user.role != "super_admin":
        q = q.filter_by(plant_id=current_user.plant_id)
    if status:
        q = q.filter_by(status=status)
    if ws:
        q = q.filter_by(workstation_id=ws)
    if analyst:
        q = q.filter_by(analyst_id=analyst)
    pagination = q.order_by(MostStudy.created_at.desc()).paginate(page=page, per_page=20, error_out=False)
    return render_template("work_study/index.html", pagination=pagination,
                           studies=pagination.items, machines=_plant_machines(),
                           analysts=User.query.filter_by(plant_id=current_user.plant_id).all(),
                           filters={"status": status, "workstation_id": ws, "analyst_id": analyst})


@work_study_bp.route("/new", methods=["GET", "POST"])
@login_required
@role_required("industrial_engineer", "admin", "plant_manager")
def new_study():
    step = request.values.get("step", "1")
    wiz = session.get("study_wizard", {})

    meta_form = StudyMetaForm()
    meta_form.workstation_id.choices = [(m.id, m.machine_name) for m in _plant_machines()]
    meta_form.sku_id.choices = [(0, "None")] + [(s.id, s.sku_name) for s in _plant_skus()]

    video_form = VideoUploadForm()
    element_form = ElementForm()
    allowance_form = AllowanceForm()

    if request.method == "POST":
        action = request.form.get("action", "")

        if step == "1" and meta_form.validate_on_submit():
            wiz = {
                "study_name": meta_form.study_name.data,
                "workstation_id": meta_form.workstation_id.data,
                "sku_id": meta_form.sku_id.data or None,
                "shift_observed": meta_form.shift_observed.data,
                "study_date": meta_form.study_date.data.isoformat(),
                "sample_size": meta_form.sample_size.data,
                "allowance_percent": meta_form.allowance_percent.data,
                "working_conditions": meta_form.working_conditions.data,
                "observation_method": meta_form.observation_method.data,
                "elements": wiz.get("elements", []),
                "video_path": wiz.get("video_path"),
            }
            session["study_wizard"] = wiz
            if wiz["observation_method"] == "direct_entry":
                return redirect(url_for("work_study.new_study", step=3))
            return redirect(url_for("work_study.new_study", step=2))

        if step == "2":
            if video_form.video_file.data:
                path = save_upload(video_form.video_file.data, "videos", [".mp4"])
                wiz["video_path"] = path
            session["study_wizard"] = wiz
            return redirect(url_for("work_study.new_study", step=3))

        if step == "3":
            if action == "add_element" and element_form.validate_on_submit():
                method = element_form.most_method.data
                idx = {}
                params = most_calculator.PARAMS[method]
                for p in params:
                    val = request.form.get(f"idx_{p}", type=int) or 0
                    idx[p] = val if val in INDEX_OPTIONS else 0
                if method == "tool_use":
                    idx["tool_tmu"] = request.form.get("idx_tool_tmu", type=int) or 0
                tmu = most_calculator.calculate_element_tmu(method, idx)
                els = wiz.get("elements", [])
                els.append({
                    "element_name": element_form.element_name.data,
                    "element_description": element_form.element_description.data,
                    "most_method": method, "index_values": idx, "element_tmu": tmu,
                    "ai_suggested": request.form.get("ai_suggested") == "1",
                })
                wiz["elements"] = els
                session["study_wizard"] = wiz
                flash("Element added.", "success")
                return redirect(url_for("work_study.new_study", step=3))
            if action == "remove_element":
                i = request.form.get("element_index", type=int)
                els = wiz.get("elements", [])
                if i is not None and 0 <= i < len(els):
                    els.pop(i)
                    wiz["elements"] = els
                    session["study_wizard"] = wiz
                return redirect(url_for("work_study.new_study", step=3))
            if action == "next":
                if not wiz.get("elements"):
                    flash("Add at least one element before continuing.", "error")
                    return redirect(url_for("work_study.new_study", step=3))
                return redirect(url_for("work_study.new_study", step=4))

        if step == "4":
            if action == "recalc" and allowance_form.allowance_percent.data is not None:
                wiz["allowance_percent"] = allowance_form.allowance_percent.data
                session["study_wizard"] = wiz
                return redirect(url_for("work_study.new_study", step=4))
            if action == "next":
                return redirect(url_for("work_study.new_study", step=5))

        if step == "5":
            return _finalize_study(wiz, publish=(action == "publish"))

    totals = _wizard_totals(wiz)
    if step == "1":
        if not request.form:
            meta_form.study_date.data = date.today()
    return render_template("work_study/new_study.html", step=int(step), wiz=wiz,
                           meta_form=meta_form, video_form=video_form, element_form=element_form,
                           allowance_form=allowance_form, index_options=INDEX_OPTIONS,
                           params=most_calculator.PARAMS, totals=totals,
                           machines=_plant_machines(), skus=_plant_skus())


def _wizard_totals(wiz):
    els = wiz.get("elements", [])
    total = sum(e["element_tmu"] for e in els)
    allowance = wiz.get("allowance_percent", 15.0)
    raw = total * 0.036
    allowed = raw * (1 + allowance / 100)
    mm = int(allowed // 60)
    ss = int(round(allowed - mm * 60))
    return {"total_tmu": total, "raw_sec": round(raw, 2), "allowed_sec": round(allowed, 2),
            "formatted": f"{mm:02d}:{ss:02d}", "count": len(els), "allowance": allowance}


def _finalize_study(wiz, publish):
    if not wiz.get("elements"):
        flash("Cannot create a study with no elements.", "error")
        return redirect(url_for("work_study.new_study", step=3))
    study = MostStudy(
        study_name=wiz["study_name"], workstation_id=wiz["workstation_id"],
        sku_id=wiz.get("sku_id"), analyst_id=current_user.id, plant_id=current_user.plant_id,
        status="published" if publish else "draft",
        sample_size=wiz["sample_size"], allowance_percent=wiz["allowance_percent"],
        study_date=date.fromisoformat(wiz["study_date"]),
        shift_observed=wiz.get("shift_observed"), working_conditions=wiz.get("working_conditions"),
        observation_method=wiz["observation_method"], video_file_path=wiz.get("video_path"),
        ai_assistance_used=any(e.get("ai_suggested") for e in wiz["elements"]),
        published_at=datetime.utcnow() if publish else None,
    )
    db.session.add(study)
    db.session.flush()
    for i, e in enumerate(wiz["elements"], start=1):
        el = MostElement(study_id=study.id, element_name=e["element_name"],
                         element_description=e.get("element_description"), sequence_order=i,
                         most_method=e["most_method"], index_values=e["index_values"],
                         element_tmu=e["element_tmu"], ai_suggested=e.get("ai_suggested", False))
        db.session.add(el)
    try:
        db.session.commit()
        most_calculator.calculate_standard_time(study.id)
        log_audit("STUDY_PUBLISHED" if publish else "STUDY_SAVED_DRAFT", "MostStudy", study.id, study.study_name)
        session.pop("study_wizard", None)
        flash("Study published." if publish else "Draft saved.", "success")
        return redirect(url_for("work_study.detail", id=study.id))
    except Exception:
        db.session.rollback()
        flash("Could not save the study.", "error")
        return redirect(url_for("work_study.new_study", step=5))


@work_study_bp.route("/<int:id>")
@login_required
def detail(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    comparison = most_calculator.get_comparison_data(study.id)
    versions = MostStudy.query.filter(
        (MostStudy.id == (study.parent_study_id or study.id)) |
        (MostStudy.parent_study_id == (study.parent_study_id or study.id))
    ).order_by(MostStudy.version).all()
    return render_template("work_study/detail.html", study=study, elements=study.elements,
                           comparison=comparison, versions=versions)


@work_study_bp.route("/<int:id>/edit", methods=["GET", "POST"])
@login_required
@role_required("industrial_engineer", "admin")
def edit(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    if study.status not in ("draft", "under_revision"):
        flash("Only draft or under-revision studies can be edited.", "error")
        return redirect(url_for("work_study.detail", id=id))
    if request.method == "POST":
        study.study_name = request.form.get("study_name", study.study_name)
        study.allowance_percent = request.form.get("allowance_percent", type=float) or study.allowance_percent
        study.working_conditions = request.form.get("working_conditions", study.working_conditions)
        db.session.commit()
        most_calculator.calculate_standard_time(study.id)
        log_audit("STUDY_UPDATED", "MostStudy", study.id, study.study_name)
        flash("Study updated.", "success")
        return redirect(url_for("work_study.detail", id=id))
    return render_template("work_study/edit.html", study=study)


@work_study_bp.route("/<int:id>/publish", methods=["POST"])
@login_required
@role_required("industrial_engineer", "admin")
def publish(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    if not study.elements or study.sample_size <= 0:
        flash("Study needs at least one element and a valid sample size.", "error")
        return redirect(url_for("work_study.detail", id=id))
    study.status = "published"
    study.published_at = datetime.utcnow()
    study.version = (study.version or 1) + 1
    db.session.commit()
    most_calculator.calculate_standard_time(study.id)
    log_audit("STUDY_PUBLISHED", "MostStudy", study.id, study.study_name)
    flash("Study published.", "success")
    return redirect(url_for("work_study.detail", id=id))


@work_study_bp.route("/<int:id>/archive", methods=["POST"])
@login_required
@role_required("industrial_engineer", "admin")
def archive(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    study.status = "archived"
    db.session.commit()
    log_audit("STUDY_ARCHIVED", "MostStudy", study.id, study.study_name)
    flash("Study archived.", "success")
    return redirect(url_for("work_study.detail", id=id))


@work_study_bp.route("/<int:id>/revise", methods=["POST"])
@login_required
@role_required("industrial_engineer", "admin")
def revise(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    new = MostStudy(
        study_name=study.study_name, workstation_id=study.workstation_id, sku_id=study.sku_id,
        analyst_id=current_user.id, plant_id=study.plant_id, status="draft",
        sample_size=study.sample_size, allowance_percent=study.allowance_percent,
        study_date=date.today(), shift_observed=study.shift_observed,
        working_conditions=study.working_conditions, observation_method=study.observation_method,
        version=(study.version or 1) + 1, parent_study_id=study.parent_study_id or study.id,
    )
    db.session.add(new)
    db.session.flush()
    for e in study.elements:
        db.session.add(MostElement(study_id=new.id, element_name=e.element_name,
                                   element_description=e.element_description, sequence_order=e.sequence_order,
                                   most_method=e.most_method, index_values=e.index_values,
                                   element_tmu=e.element_tmu))
    study.status = "under_revision"
    db.session.commit()
    most_calculator.calculate_standard_time(new.id)
    log_audit("STUDY_REVISED", "MostStudy", new.id, new.study_name)
    flash("Revision created as a new draft.", "success")
    return redirect(url_for("work_study.edit", id=new.id))


@work_study_bp.route("/<int:id>/export")
@login_required
def export(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    pdf = generate_most_pdf(study.id)
    return Response(pdf, mimetype="application/pdf",
                    headers={"Content-Disposition": f"attachment; filename=MOST_{study.id}.pdf"})


@work_study_bp.route("/<int:id>/compare")
@login_required
def compare(id):
    study = MostStudy.query.get_or_404(id)
    if current_user.role != "super_admin" and study.plant_id != current_user.plant_id:
        abort(403)
    comparison = most_calculator.get_comparison_data(study.id)
    return render_template("work_study/compare.html", study=study, comparison=comparison)
