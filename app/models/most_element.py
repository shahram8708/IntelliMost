from datetime import datetime
from app.extensions import db


class MostElement(db.Model):
    __tablename__ = "most_elements"

    id = db.Column(db.Integer, primary_key=True)
    study_id = db.Column(db.Integer, db.ForeignKey("most_studies.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    element_name = db.Column(db.String(200), nullable=False)
    element_description = db.Column(db.Text, nullable=True)
    sequence_order = db.Column(db.Integer, nullable=False)
    most_method = db.Column(db.Enum("general_move", "controlled_move", "tool_use", name="most_method"))
    index_values = db.Column(db.JSON, nullable=False)
    element_tmu = db.Column(db.Float, default=0.0)
    ai_suggested = db.Column(db.Boolean, default=False)
    ai_confidence = db.Column(db.Float, nullable=True)
    analyst_override = db.Column(db.Boolean, default=False)
    timer_duration_sec = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    study = db.relationship("MostStudy", back_populates="elements")
