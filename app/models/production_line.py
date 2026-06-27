from datetime import datetime
from app.extensions import db


class ProductionLine(db.Model):
    __tablename__ = "production_lines"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False, index=True)
    line_name = db.Column(db.String(100), nullable=False)
    line_code = db.Column(db.String(50), nullable=True)
    target_output_per_shift = db.Column(db.Integer, nullable=False, default=1000)
    shift_duration_hours = db.Column(db.Float, default=8.0)
    planned_break_minutes = db.Column(db.Integer, default=30)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plant = db.relationship("Plant", back_populates="lines")
    machines = db.relationship("Machine", back_populates="line")
    shifts = db.relationship("Shift", back_populates="line")
