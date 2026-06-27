from datetime import datetime
from app.extensions import db


class ImprovementOpportunity(db.Model):
    __tablename__ = "improvement_opportunities"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=False)
    line_id = db.Column(db.Integer, db.ForeignKey("production_lines.id"), nullable=True)
    machine_id = db.Column(db.Integer, db.ForeignKey("machines.id"), nullable=True)
    sku_id = db.Column(db.Integer, db.ForeignKey("skus.id"), nullable=True)
    opportunity_title = db.Column(db.String(300), nullable=False)
    opportunity_description = db.Column(db.Text, nullable=False)
    category = db.Column(db.Enum("changeover_reduction", "cycle_time_improvement",
                                 "downtime_reduction", "rejection_reduction",
                                 "standard_time_update", name="improvement_category"))
    impact_minutes_per_shift = db.Column(db.Float, nullable=True)
    impact_units_per_shift = db.Column(db.Integer, nullable=True)
    evidence_summary = db.Column(db.Text, nullable=True)
    supporting_data = db.Column(db.JSON, nullable=True)
    rank_score = db.Column(db.Float, default=0.0)
    status = db.Column(db.Enum("new", "accepted", "deferred", "dismissed",
                               name="improvement_status"), default="new")
    accepted_by = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    dismissed_reason = db.Column(db.Text, nullable=True)
    deferred_until = db.Column(db.Date, nullable=True)
    generated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    line = db.relationship("ProductionLine")
    machine = db.relationship("Machine")
    sku = db.relationship("SKU")
    acceptor = db.relationship("User", foreign_keys=[accepted_by])
