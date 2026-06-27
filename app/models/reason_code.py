from app.extensions import db


class ReasonCode(db.Model):
    __tablename__ = "reason_codes"

    id = db.Column(db.Integer, primary_key=True)
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=True)
    parent_id = db.Column(db.Integer, db.ForeignKey("reason_codes.id"), nullable=True)
    code = db.Column(db.String(50), nullable=False)
    label = db.Column(db.String(150), nullable=False)
    category = db.Column(db.Enum("equipment_failure", "planned_maintenance", "changeover",
                                 "process", "utilities", "quality", "other", name="reason_category"))
    level = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)

    children = db.relationship("ReasonCode", backref=db.backref("parent", remote_side=[id]))
