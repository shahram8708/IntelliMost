from datetime import datetime, date, timedelta


def check_overdue_capas(app=None):
    if app is not None:
        with app.app_context():
            _check_overdue_capas()
    else:
        _check_overdue_capas()


def _check_overdue_capas():
    from app.extensions import db
    from app.models.capa import CapaRecord
    from app.services.notification import send_capa_status_email
    today = date.today()
    rows = (CapaRecord.query
            .filter(CapaRecord.due_date < today,
                    CapaRecord.status.notin_(["closed", "overdue"])).all())
    for capa in rows:
        capa.status = "overdue"
        db.session.commit()
        try:
            if capa.owner:
                send_capa_status_email(capa, capa.owner)
        except Exception:
            pass


def close_completed_shifts(app=None):
    if app is not None:
        with app.app_context():
            _close_completed_shifts()
    else:
        _close_completed_shifts()


def _close_completed_shifts():
    from app.extensions import db
    from app.models.shift import Shift
    from app.services.oee_calculator import calculate_oee
    now = datetime.utcnow()
    active = Shift.query.filter_by(status="active").all()
    for s in active:
        if not s.line:
            continue
        end = s.start_time + timedelta(hours=s.line.shift_duration_hours)
        if end < now:
            s.status = "completed"
            s.end_time = end
            db.session.commit()
            try:
                calculate_oee(s.id)
            except Exception:
                db.session.rollback()
