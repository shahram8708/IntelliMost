from datetime import datetime
from app.extensions import db


class Lead(db.Model):
    __tablename__ = "leads"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    company = db.Column(db.String(200), nullable=True)
    role = db.Column(db.String(100), nullable=True)
    facility_type = db.Column(db.String(100), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    message = db.Column(db.Text, nullable=True)
    source = db.Column(db.String(50), default="demo_request")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
