from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def _safe(obj) -> dict | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {"repr": str(obj)[:2000]}


def write_audit(
    db: Session,
    user: User | str,
    action: str,
    object_type: str,
    object_id: int | None,
    old: dict | None = None,
    new: dict | None = None,
) -> AuditLog:
    if isinstance(user, str):
        email, uid = user, None
    else:
        email, uid = user.email, user.id
    log = AuditLog(
        user=email,
        user_id=uid,
        action=action,
        object_type=object_type,
        object_id=object_id,
        old_value=_safe(old),
        new_value=_safe(new),
    )
    db.add(log)
    return log
