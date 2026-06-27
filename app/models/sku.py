from datetime import datetime
from app.extensions import db


class SKU(db.Model):
    __tablename__ = "skus"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    sku_code = db.Column(db.String(50), nullable=False)
    sku_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True)
    unit_of_measure = db.Column(db.String(20), default="units")
    standard_batch_size = db.Column(db.Integer, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
