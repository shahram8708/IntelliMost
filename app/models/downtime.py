from datetime import datetime
from app.extensions import db


class DowntimeEvent(db.Model):
    __tablename__ = "downtime_events"

    id = db.Column(db.Integer, primary_key=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=False, index=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"), nullable=False, index=True)
    event_type = db.Column(db.Enum("unplanned", "planned_maintenance", "changeover", "breakdown",
                                   name="downtime_type"))
    reason_code_id = db.Column(db.Integer, db.ForeignKey("reason_codes.id"), nullable=True)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    duration_minutes = db.Column(db.Float, nullable=True)
    logged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    notes = db.Column(db.Text, nullable=True)
    is_resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    machine = db.relationship("Machine", back_populates="downtime_events")
    shift = db.relationship("Shift", back_populates="downtime_events")
    reason_code = db.relationship("ReasonCode")
    logged_by_user = db.relationship("User", back_populates="downtime_events_logged", foreign_keys=[logged_by])
