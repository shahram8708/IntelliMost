from datetime import datetime
from app.extensions import db


class MostStudy(db.Model):
    __tablename__ = "most_studies"

    id = db.Column(db.Integer, primary_key=True)
    study_name = db.Column(db.String(200), nullable=False)
    workstation_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=False, index=True)
    sku_id = db.Column(db.Integer, db.ForeignKey("skus.id"), nullable=True)
    analyst_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False, index=True)
    status = db.Column(db.Enum("draft", "published", "archived", "under_revision", name="study_status"),
                       default="draft")
    sample_size = db.Column(db.Integer, nullable=False, default=1)
    allowance_percent = db.Column(db.Float, nullable=False, default=15.0)
    total_tmu = db.Column(db.Float, default=0.0)
    standard_time_sec = db.Column(db.Float, default=0.0)
    allowed_time_sec = db.Column(db.Float, default=0.0)
    study_date = db.Column(db.Date, nullable=False)
    shift_observed = db.Column(db.String(20), nullable=True)
    working_conditions = db.Column(db.Text, nullable=True)
    operator_rating = db.Column(db.Float, nullable=True)
    version = db.Column(db.Integer, default=1)
    parent_study_id = db.Column(db.Integer, db.ForeignKey("most_studies.id"), nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    observation_method = db.Column(db.Enum("manual_timer", "video_upload", "direct_entry",
                                           name="obs_method"), default="direct_entry")
    video_file_path = db.Column(db.String(255), nullable=True)
    ai_assistance_used = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    workstation = db.relationship("Machine", back_populates="most_studies")
    sku = db.relationship("SKU")
    analyst = db.relationship("User", back_populates="most_studies", foreign_keys=[analyst_id])
    plant = db.relationship("Plant")
    elements = db.relationship("MostElement", back_populates="study",
                               cascade="all, delete-orphan", order_by="MostElement.sequence_order")
    parent_study = db.relationship("MostStudy", remote_side=[id])
