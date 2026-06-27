import os
import pytz
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, render_template, request

from config import config_map
from app.extensions import (db, migrate, login_manager, bcrypt, mail, limiter,
                            scheduler, babel, csrf)

load_dotenv()


def create_app(config_name=None):
    config_name = config_name or os.environ.get("FLASK_ENV", "development")
    if config_name not in config_map:
        config_name = "development"

    app = Flask(__name__)
    app.config.from_object(config_map[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    babel.init_app(app)
    csrf.init_app(app)

    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "info"

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "profiles"), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "evidence"), exist_ok=True)
    os.makedirs(os.path.join(app.config["UPLOAD_FOLDER"], "videos"), exist_ok=True)

    register_blueprints(app)
    register_filters(app)
    register_error_handlers(app)
    register_context(app)

    with app.app_context():
        db.create_all()
        from seeds.seed import run_seed
        try:
            if User.query.count() == 0:
                run_seed()
        except Exception as e:
            app.logger.warning("Seed skipped: %s", e)

    if not app.config.get("TESTING") and os.environ.get("DISABLE_SCHEDULER") != "1":
        init_scheduler(app)

    return app


def register_blueprints(app):
    from app.routes.auth import auth_bp
    from app.routes.main import main_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.production import production_bp
    from app.routes.work_study import work_study_bp
    from app.routes.downtime import downtime_bp
    from app.routes.rejections import rejections_bp
    from app.routes.capa import capa_bp
    from app.routes.rca import rca_bp
    from app.routes.alerts import alerts_bp
    from app.routes.improvements import improvements_bp
    from app.routes.reports import reports_bp
    from app.routes.analytics import analytics_bp
    from app.routes.api import api_bp
    from app.routes.admin import admin_bp
    from app.routes.profile import profile_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp, url_prefix="/dashboard")
    app.register_blueprint(production_bp, url_prefix="/production")
    app.register_blueprint(work_study_bp, url_prefix="/work-study")
    app.register_blueprint(downtime_bp, url_prefix="/downtime")
    app.register_blueprint(rejections_bp, url_prefix="/rejections")
    app.register_blueprint(capa_bp, url_prefix="/capa")
    app.register_blueprint(rca_bp, url_prefix="/rca")
    app.register_blueprint(alerts_bp, url_prefix="/alerts")
    app.register_blueprint(improvements_bp, url_prefix="/improvements")
    app.register_blueprint(reports_bp, url_prefix="/reports")
    app.register_blueprint(analytics_bp, url_prefix="/analytics")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(profile_bp, url_prefix="/profile")


def register_filters(app):
    def format_datetime(dt, fmt="%d %b %Y %H:%M"):
        if not dt:
            return ""
        tzname = app.config.get("APP_TIMEZONE", "Asia/Kolkata")
        try:
            from flask_login import current_user
            if current_user.is_authenticated and current_user.plant and current_user.plant.timezone:
                tzname = current_user.plant.timezone
        except Exception:
            pass
        try:
            tz = pytz.timezone(tzname)
            if dt.tzinfo is None:
                dt = pytz.utc.localize(dt)
            return dt.astimezone(tz).strftime(fmt)
        except Exception:
            return dt.strftime(fmt)

    def tmu_to_minutes(tmu):
        if tmu is None:
            return ""
        sec = tmu * 0.036
        return f"{sec:.2f} sec / {sec/60:.2f} min"

    def format_duration(minutes):
        if minutes is None:
            return ""
        minutes = float(minutes)
        h = int(minutes // 60)
        m = int(round(minutes - h * 60))
        if h:
            return f"{h} hr {m} min"
        return f"{m} min"

    def efficiency_class(ratio):
        if ratio is None:
            return "text-muted"
        if ratio >= 80:
            return "text-success"
        if ratio >= 60:
            return "text-warning"
        return "text-danger"

    app.jinja_env.filters["format_datetime"] = format_datetime
    app.jinja_env.filters["tmu_to_minutes"] = tmu_to_minutes
    app.jinja_env.filters["format_duration"] = format_duration
    app.jinja_env.filters["efficiency_class"] = efficiency_class


def register_error_handlers(app):
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()
        return render_template("errors/500.html"), 500


def register_context(app):
    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        unread = 0
        try:
            if current_user.is_authenticated:
                from app.models.alert import AlertEvent
                q = AlertEvent.query.filter_by(status="open")
                if current_user.role != "super_admin":
                    q = q.filter_by(plant_id=current_user.plant_id)
                unread = q.count()
        except Exception:
            unread = 0
        return {"now": datetime.utcnow(), "unread_alerts": unread}


def init_scheduler(app):
    from app.services.alert_engine import evaluate_all_rules
    from app.services.improvement_engine import generate_opportunities
    from app.services.scheduler_jobs import check_overdue_capas, close_completed_shifts

    if scheduler.running:
        return
    scheduler.init_app(app)

    if not scheduler.get_job("alert_eval"):
        scheduler.add_job(id="alert_eval", func=evaluate_all_rules, trigger="interval",
                          minutes=5, args=[app], replace_existing=True)
    if not scheduler.get_job("improvement_gen"):
        scheduler.add_job(id="improvement_gen", func=generate_opportunities, trigger="cron",
                          hour=1, minute=0, args=[app], replace_existing=True)
    if not scheduler.get_job("capa_overdue"):
        scheduler.add_job(id="capa_overdue", func=check_overdue_capas, trigger="cron",
                          hour=8, minute=0, args=[app], replace_existing=True)
    if not scheduler.get_job("shift_close"):
        scheduler.add_job(id="shift_close", func=close_completed_shifts, trigger="interval",
                          minutes=15, args=[app], replace_existing=True)
    try:
        scheduler.start()
    except Exception:
        pass
