import os
import uuid
import hashlib
from datetime import datetime
from flask import request, current_app
from flask_login import current_user
from app.extensions import db
from app.models.audit_log import AuditLog


def log_audit(action, target_type=None, target_id=None, description=None, user=None):
    try:
        uid = (user or current_user).id if (user or getattr(current_user, "is_authenticated", False)) else None
        if uid is None:
            return
        entry = AuditLog(
            user_id=uid,
            action=action,
            target_type=target_type,
            target_id=target_id,
            description=description,
            ip_address=request.remote_addr if request else None,
            user_agent=(request.headers.get("User-Agent", "")[:500] if request else None),
            created_at=datetime.utcnow(),
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def plant_scope(query, model):
    if current_user.is_authenticated and current_user.role != "super_admin":
        return query.filter(model.plant_id == current_user.plant_id)
    return query


def current_plant_id():
    if current_user.is_authenticated:
        return current_user.plant_id
    return None


def save_upload(file_storage, subdir="", allowed_ext=None):
    if not file_storage or file_storage.filename == "":
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if allowed_ext and ext not in allowed_ext:
        return None
    folder = os.path.join(current_app.config["UPLOAD_FOLDER"], subdir)
    os.makedirs(folder, exist_ok=True)
    fname = f"{uuid.uuid4().hex}{ext}"
    path = os.path.join(folder, fname)
    file_storage.save(path)
    return os.path.join(subdir, fname) if subdir else fname


def sha256_hex(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
