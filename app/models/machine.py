from datetime import datetime
from app.extensions import db


class Machine(db.Model):
    __tablename__ = "machines"

    id = db.Column(db.Integer, primary_key=True)
    line_id = db.Column(db.Integer, db.ForeignKey("production_lines.id"), nullable=False, index=True)
    machine_name = db.Column(db.String(100), nullable=False)
    machine_code = db.Column(db.String(50), unique=True, nullable=True)
    machine_type = db.Column(db.String(100), nullable=False)
    manufacturer = db.Column(db.String(100), nullable=True)
    model_number = db.Column(db.String(100), nullable=True)
    installation_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    line = db.relationship("ProductionLine", back_populates="machines")
    downtime_events = db.relationship("DowntimeEvent", back_populates="machine")
    most_studies = db.relationship("MostStudy", back_populates="workstation")
