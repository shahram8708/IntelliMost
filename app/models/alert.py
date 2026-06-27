from datetime import datetime
from app.extensions import db


class AlertRule(db.Model):
    __tablename__ = "alert_rules"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    rule_name = db.Column(db.String(200), nullable=False)
    metric_name = db.Column(db.String(100), nullable=False)
    operator = db.Column(db.Enum("gt", "lt", "gte", "lte", "eq", name="alert_operator"))
    threshold_value = db.Column(db.Float, nullable=False)
    time_window_minutes = db.Column(db.Integer, default=60)
    line_id = db.Column(db.Integer, db.ForeignKey("production_lines.id"), nullable=True)
    recipient_user_ids = db.Column(db.JSON, nullable=False)
    escalation_timeout_minutes = db.Column(db.Integer, default=60)
    escalation_user_ids = db.Column(db.JSON, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plant = db.relationship("Plant", back_populates="alert_rules")
    line = db.relationship("ProductionLine")
    creator = db.relationship("User", foreign_keys=[created_by])
    events = db.relationship("AlertEvent", back_populates="rule")


class AlertEvent(db.Model):
    __tablename__ = "alert_events"

    id = db.Column(db.Integer, primary_key=True)
    rule_id = db.Column(db.Integer, db.ForeignKey("alert_rules.id"), nullable=False, index=True)
    triggered_at = db.Column(db.DateTime, nullable=False)
    triggered_value = db.Column(db.Float, nullable=False)
    threshold_value = db.Column(db.Float, nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey("production_lines.id"), nullable=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"), nullable=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    status = db.Column(db.Enum("open", "acknowledged", "escalated", "dismissed",
                               name="alert_event_status"), default="open")
    acknowledged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    action_taken = db.Column(db.Enum("investigate", "capa_raised", "dismissed_reason",
                                     name="alert_action"), nullable=True)
    capa_id = db.Column(db.Integer, db.ForeignKey("capa_records.id"), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    escalated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    rule = db.relationship("AlertRule", back_populates="events")
    line = db.relationship("ProductionLine")
    acknowledger = db.relationship("User", foreign_keys=[acknowledged_by])
    capa = db.relationship("CapaRecord")
