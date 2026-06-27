from datetime import datetime
from app.extensions import db


class Plant(db.Model):
    __tablename__ = "plants"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    location = db.Column(db.String(255), nullable=True)
    timezone = db.Column(db.String(50), nullable=False, default="Asia/Kolkata")
    industry_type = db.Column(db.String(100), nullable=False)
    subscription_tier = db.Column(db.Enum("starter", "professional", "enterprise", name="sub_tier"),
                                  default="starter")
    subscription_active = db.Column(db.Boolean, default=True)
    contact_email = db.Column(db.String(255), nullable=True)
    contact_phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = db.relationship("User", back_populates="plant", foreign_keys="User.plant_id")
    lines = db.relationship("ProductionLine", back_populates="plant")
    alert_rules = db.relationship("AlertRule", back_populates="plant")
