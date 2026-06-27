from datetime import datetime
from app.extensions import db


class RcaRecord(db.Model):
    __tablename__ = "rca_records"

    id = db.Column(db.Integer, primary_key=True)
    capa_id = db.Column(db.Integer, db.ForeignKey("capa_records.id"), unique=True, nullable=False)
    problem_statement = db.Column(db.Text, nullable=False)
    why_1 = db.Column(db.Text, nullable=True)
    why_2 = db.Column(db.Text, nullable=True)
    why_3 = db.Column(db.Text, nullable=True)
    why_4 = db.Column(db.Text, nullable=True)
    why_5 = db.Column(db.Text, nullable=True)
    root_cause_statement = db.Column(db.Text, nullable=True)
    root_cause_category = db.Column(db.Enum("man", "machine", "method", "material",
                                            "measurement", "environment", name="rca_category"),
                                    nullable=True)
    similar_events_referenced = db.Column(db.JSON, nullable=True)
    ai_suggestions_used = db.Column(db.Boolean, default=False)
    analyst_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    capa = db.relationship("CapaRecord", back_populates="rca")
    analyst = db.relationship("User")
