import pytest
from app.db import Base, engine, SessionLocal
from app.models import Event, Draft
from app.services.instagram import send_approved_draft, ApprovalRequired


def setup_module():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_unapproved_draft_can_never_send():
    db = SessionLocal()
    e = Event(source="comment", external_id="c-test", text="hello", raw_payload={})
    db.add(e); db.commit(); db.refresh(e)
    d = Draft(event_id=e.id, draft_text="reply", status="pending")
    db.add(d); db.commit(); db.refresh(d)
    with pytest.raises(ApprovalRequired):
        send_approved_draft(db, d, actor="test")
    db.close()


def test_empty_approved_draft_is_blocked():
    db = SessionLocal()
    e = Event(source="comment", external_id="c-empty", text="hello", raw_payload={})
    db.add(e); db.commit(); db.refresh(e)
    from datetime import datetime, timezone
    d = Draft(event_id=e.id, draft_text="   ", status="approved", approved_by="111", approved_at=datetime.now(timezone.utc))
    db.add(d); db.commit(); db.refresh(d)
    with pytest.raises(ApprovalRequired, match="empty"):
        send_approved_draft(db, d, actor="test")
    db.close()
