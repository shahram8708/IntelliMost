from datetime import datetime
from app.extensions import db


class Shift(db.Model):
    __tablename__ = "shifts"

    id = db.Column(db.Integer, primary_key=True)
    line_id = db.Column(db.Integer, db.ForeignKey("production_lines.id"), nullable=False, index=True)
    shift_label = db.Column(db.String(20), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=True)
    supervisor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    sku_id = db.Column(db.Integer, db.ForeignKey("skus.id"), nullable=True)
    target_units = db.Column(db.Integer, nullable=False, default=0)
    actual_units = db.Column(db.Integer, default=0)
    rejection_count = db.Column(db.Integer, default=0)
    oee_percent = db.Column(db.Float, nullable=True)
    availability_percent = db.Column(db.Float, nullable=True)
    performance_percent = db.Column(db.Float, nullable=True)
    quality_percent = db.Column(db.Float, nullable=True)
    total_downtime_minutes = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text, nullable=True)
    status = db.Column(db.Enum("active", "completed", name="shift_status"), default="active")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    line = db.relationship("ProductionLine", back_populates="shifts")
    supervisor = db.relationship("User", back_populates="shifts_supervised", foreign_keys=[supervisor_id])
    sku = db.relationship("SKU")
    downtime_events = db.relationship("DowntimeEvent", back_populates="shift")
    rejections = db.relationship("RejectionEvent", back_populates="shift")
    outputs = db.relationship("ProductionOutput", back_populates="shift")


class ProductionOutput(db.Model):
    __tablename__ = "production_outputs"

    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"), nullable=False)
    logged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    cumulative_total = db.Column(db.Integer, nullable=False)
    logged_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    shift = db.relationship("Shift", back_populates="outputs")
    logger = db.relationship("User", foreign_keys=[logged_by])
