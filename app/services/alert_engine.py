from datetime import datetime, timedelta


def evaluate_all_rules(app=None):
    if app is not None:
        with app.app_context():
            _run()
    else:
        _run()


def _run():
    from app.extensions import db
    from app.models.alert import AlertRule, AlertEvent
    from app.services.notification import send_alert_email

    active_rules = AlertRule.query.filter_by(is_active=True).all()
    now = datetime.utcnow()

    for rule in active_rules:
        try:
            current_value = _get_metric_value(rule)
            if current_value is not None and _evaluate_condition(current_value, rule.operator, rule.threshold_value):
                existing = (AlertEvent.query.filter_by(rule_id=rule.id, status="open")
                            .filter(AlertEvent.triggered_at >= now - timedelta(minutes=30)).first())
                if not existing:
                    event = AlertEvent(
                        rule_id=rule.id, triggered_at=now, triggered_value=current_value,
                        threshold_value=rule.threshold_value, plant_id=rule.plant_id,
                        line_id=rule.line_id, status="open",
                    )
                    db.session.add(event)
                    db.session.commit()
                    send_alert_email(rule, event, current_value)

            past_timeout = (AlertEvent.query.filter_by(rule_id=rule.id, status="open")
                            .filter(AlertEvent.triggered_at <= now - timedelta(minutes=rule.escalation_timeout_minutes)).all())
            for evt in past_timeout:
                evt.status = "escalated"
                evt.escalated_at = now
                db.session.commit()
                if rule.escalation_user_ids:
                    send_alert_email(rule, evt, evt.triggered_value, is_escalation=True)
        except Exception:
            db.session.rollback()


def evaluate_for_metric(plant_id, metric_name, line_id=None):
    """Trigger a targeted evaluation after a data change."""
    from app.extensions import db
    from app.models.alert import AlertRule, AlertEvent
    from app.services.notification import send_alert_email
    now = datetime.utcnow()
    q = AlertRule.query.filter_by(is_active=True, plant_id=plant_id, metric_name=metric_name)
    for rule in q.all():
        if rule.line_id and line_id and rule.line_id != line_id:
            continue
        try:
            val = _get_metric_value(rule)
            if val is not None and _evaluate_condition(val, rule.operator, rule.threshold_value):
                existing = (AlertEvent.query.filter_by(rule_id=rule.id, status="open")
                            .filter(AlertEvent.triggered_at >= now - timedelta(minutes=30)).first())
                if not existing:
                    event = AlertEvent(rule_id=rule.id, triggered_at=now, triggered_value=val,
                                       threshold_value=rule.threshold_value, plant_id=rule.plant_id,
                                       line_id=rule.line_id, status="open")
                    db.session.add(event)
                    db.session.commit()
                    send_alert_email(rule, event, val)
        except Exception:
            db.session.rollback()


def _get_metric_value(rule):
    from app.models.shift import Shift
    from app.models.downtime import DowntimeEvent
    from app.models.machine import Machine
    now = datetime.utcnow()
    window_start = now - timedelta(minutes=rule.time_window_minutes)

    if rule.metric_name == "rejection_rate":
        shifts = Shift.query
        if rule.line_id:
            shifts = shifts.filter_by(line_id=rule.line_id)
        shifts = shifts.filter(Shift.start_time >= window_start).all()
        total_units = sum(s.actual_units or 0 for s in shifts)
        total_rej = sum(s.rejection_count or 0 for s in shifts)
        if total_units == 0:
            return None
        return (total_rej / total_units) * 100

    if rule.metric_name == "downtime_duration":
        events = DowntimeEvent.query.filter(DowntimeEvent.start_time >= window_start,
                                            DowntimeEvent.event_type == "unplanned")
        if rule.line_id:
            mids = [m.id for m in Machine.query.filter_by(line_id=rule.line_id).all()]
            events = events.filter(DowntimeEvent.machine_id.in_(mids))
        return sum(e.duration_minutes or 0 for e in events.all())

    if rule.metric_name == "oee_percent":
        shift = Shift.query
        if rule.line_id:
            shift = shift.filter_by(line_id=rule.line_id)
        shift = shift.filter_by(status="active").first()
        if shift and shift.oee_percent is not None:
            return shift.oee_percent
        return None

    if rule.metric_name == "output_attainment":
        shift = Shift.query
        if rule.line_id:
            shift = shift.filter_by(line_id=rule.line_id)
        shift = shift.filter_by(status="active").first()
        if shift and shift.target_units > 0:
            return (shift.actual_units / shift.target_units) * 100
        return None

    return None


def _evaluate_condition(value, operator, threshold):
    ops = {"gt": value > threshold, "lt": value < threshold, "gte": value >= threshold,
           "lte": value <= threshold, "eq": value == threshold}
    return ops.get(operator, False)
