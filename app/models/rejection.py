from datetime import datetime
from app.extensions import db


class RejectionEvent(db.Model):
    __tablename__ = "rejection_events"

    id = db.Column(db.Integer, primary_key=True)
    shift_id = db.Column(db.Integer, db.ForeignKey("shifts.id"), nullable=False, index=True)
    sku_id = db.Column(db.Integer, db.ForeignKey("skus.id"), nullable=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=True)
    quantity_rejected = db.Column(db.Integer, nullable=False)
    defect_type = db.Column(db.String(150), nullable=False)
    defect_description = db.Column(db.Text, nullable=True)
    probable_cause = db.Column(db.String(255), nullable=True)
    quality_check_point = db.Column(db.String(150), nullable=True)
    batch_reference = db.Column(db.String(100), nullable=True)
    logged_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shift = db.relationship("Shift", back_populates="rejections")
    sku = db.relationship("SKU")
    machine = db.relationship("Machine")
    logger = db.relationship("User", foreign_keys=[logged_by])
