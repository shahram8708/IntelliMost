from datetime import datetime
from flask_login import UserMixin
from app.extensions import db

ROLES = ("super_admin", "admin", "plant_manager", "industrial_engineer",
         "qa_manager", "shift_supervisor", "operator")


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=True)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.Enum(*ROLES, name="user_role"), nullable=False, default="operator")
    plant_id = db.Column(db.Integer, db.ForeignKey("plants.id"), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_locked = db.Column(db.Boolean, default=False)
    last_login = db.Column(db.DateTime, nullable=True)
    failed_login_attempts = db.Column(db.Integer, default=0)
    invitation_token = db.Column(db.String(64), nullable=True, unique=True)
    invitation_expires_at = db.Column(db.DateTime, nullable=True)
    reset_token_hash = db.Column(db.String(128), nullable=True)
    reset_token_expires_at = db.Column(db.DateTime, nullable=True)
    profile_photo_path = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    department = db.Column(db.String(100), nullable=True)
    most_certification_level = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_deleted = db.Column(db.Boolean, default=False)

    plant = db.relationship("Plant", back_populates="users", foreign_keys=[plant_id])
    most_studies = db.relationship("MostStudy", back_populates="analyst", foreign_keys="MostStudy.analyst_id")
    downtime_events_logged = db.relationship("DowntimeEvent", back_populates="logged_by_user", foreign_keys="DowntimeEvent.logged_by")
    capa_owned = db.relationship("CapaRecord", back_populates="owner", foreign_keys="CapaRecord.owner_id")
    shifts_supervised = db.relationship("Shift", back_populates="supervisor", foreign_keys="Shift.supervisor_id")
    audit_logs = db.relationship("AuditLog", back_populates="user", foreign_keys="AuditLog.user_id")

    @property
    def initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.full_name[:2].upper()

    @property
    def is_super_admin(self):
        return self.role == "super_admin"

    def get_id(self):
        return str(self.id)

    @property
    def is_authenticated_active(self):
        return self.is_active and not self.is_deleted
