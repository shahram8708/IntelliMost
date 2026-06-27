from datetime import datetime
from app.extensions import db


class CapaRecord(db.Model):
    __tablename__ = "capa_records"

    id = db.Column(db.Integer, primary_key=True)
    capa_number = db.Column(db.String(30), unique=True, nullable=False)
    title = db.Column(db.String(300), nullable=False)
    severity = db.Column(db.Enum("critical", "major", "minor", name="capa_severity"))
    source_type = db.Column(db.Enum("alert", "deviation", "audit", "customer_complaint",
                                    "self_initiated", name="capa_source"))
    source_id = db.Column(db.Integer, nullable=True)
    source_description = db.Column(db.String(300), nullable=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    affected_machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=True)
    affected_sku_id = db.Column(db.Integer, db.ForeignKey("skus.id"), nullable=True)
    affected_batch = db.Column(db.String(100), nullable=True)
    deviation_description = db.Column(db.Text, nullable=False)
    immediate_action = db.Column(db.Text, nullable=True)
    root_cause_summary = db.Column(db.Text, nullable=True)
    corrective_action = db.Column(db.Text, nullable=True)
    preventive_action = db.Column(db.Text, nullable=True)
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    raised_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    status = db.Column(db.Enum("open", "in_progress", "pending_review", "closed", "overdue",
                               name="capa_status"), default="open")
    priority = db.Column(db.Enum("high", "medium", "low", name="capa_priority"), default="medium")
    due_date = db.Column(db.Date, nullable=False)
    closed_at = db.Column(db.DateTime, nullable=True)
    closure_notes = db.Column(db.Text, nullable=True)
    effectiveness_verified = db.Column(db.Boolean, default=False)
    effectiveness_date = db.Column(db.Date, nullable=True)
    evidence_paths = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    plant = db.relationship("Plant")
    affected_machine = db.relationship("Machine")
    affected_sku = db.relationship("SKU")
    owner = db.relationship("User", back_populates="capa_owned", foreign_keys=[owner_id])
    raised_by = db.relationship("User", foreign_keys=[raised_by_id])
    reviewer = db.relationship("User", foreign_keys=[reviewer_id])
    rca = db.relationship("RcaRecord", back_populates="capa", uselist=False, cascade="all, delete-orphan")
    comments = db.relationship("CapaComment", back_populates="capa", cascade="all, delete-orphan",
                               order_by="CapaComment.created_at")

    @property
    def is_overdue(self):
        from datetime import date
        return self.status != "closed" and self.due_date < date.today()


class CapaComment(db.Model):
    __tablename__ = "capa_comments"

    id = db.Column(db.Integer, primary_key=True)
    capa_id = db.Column(db.Integer, db.ForeignKey("capa_records.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    capa = db.relationship("CapaRecord", back_populates="comments")
    user = db.relationship("User")
