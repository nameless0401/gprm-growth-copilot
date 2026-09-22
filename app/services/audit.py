from sqlalchemy.orm import Session
from ..models import AuditLog


def log(db: Session, action: str, actor: str = "system", event_id: str | None = None,
        draft_id: str | None = None, details: dict | None = None):
    row = AuditLog(action=action, actor=actor, event_id=event_id, draft_id=draft_id, details=details or {})
    db.add(row)
    db.commit()
    return row
