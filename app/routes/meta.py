from datetime import datetime, timedelta, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..models import Event, Draft
from ..services.audit import log
from ..services.instagram import verify_signature
from ..services.llm import generate_draft
from ..services.telegram import notify_draft

router = APIRouter()
settings = get_settings()


@router.get("/webhooks/meta")
def verify_meta_webhook(request: Request):
    q = request.query_params
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == settings.meta_verify_token:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verification failed")


def _persist_event(db: Session, *, source: str, external_id: str, author_id: str | None,
                   author_username: str | None, text: str | None, media_id: str | None,
                   raw: dict, expires_hours: int):
    existing = db.scalar(select(Event).where(Event.source == source, Event.external_id == external_id))
    if existing:
        return existing, False
    e = Event(
        source=source, external_id=external_id, author_id=author_id,
        author_username=author_username, text=text, media_id=media_id,
        raw_payload=raw,
        window_expires_at=datetime.now(timezone.utc) + timedelta(hours=expires_hours),
    )
    db.add(e)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return db.scalar(select(Event).where(Event.source == source, Event.external_id == external_id)), False
    db.refresh(e)
    log(db, "received", event_id=e.id, details={"source": source, "external_id": external_id})
    return e, True


def _notify_draft(db: Session, draft: Draft) -> None:
    try:
        result = notify_draft(draft)
        if not result.get("ok"):
            raise RuntimeError(f"Telegram notification failed: {result}")
        draft.notified_at = datetime.now(timezone.utc)
        db.commit()
        log(db, "draft_notified", event_id=draft.event_id, draft_id=draft.id)
    except Exception as exc:
        log(db, "draft_notify_error", event_id=draft.event_id, draft_id=draft.id, details={"error": str(exc)})


def _draft_and_notify(db: Session, event: Event):
    result = generate_draft(event.source, event.text or "", context=f"media_id={event.media_id or ''}")
    d = Draft(event_id=event.id, draft_text=result["draft_text"], confidence=result["confidence"], flags=result["flags"])
    db.add(d)
    db.commit()
    db.refresh(d)
    log(db, "draft_generated", event_id=event.id, draft_id=d.id, details={"confidence": d.confidence, "flags": d.flags})
    _notify_draft(db, d)


@router.post("/webhooks/meta")
async def meta_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    if not verify_signature(raw_body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=403, detail="invalid signature")
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="invalid json")

    created = 0
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") in {"comments", "live_comments"}:
                v = change.get("value", {})
                cid = str(v.get("id") or "")
                if not cid:
                    continue
                author = v.get("from") or {}
                author_id = str(author.get("id") or "") or None
                if author_id and settings.meta_ig_user_id and author_id == settings.meta_ig_user_id:
                    continue
                event, is_new = _persist_event(
                    db, source="comment", external_id=cid,
                    author_id=author_id,
                    author_username=author.get("username"), text=v.get("text"),
                    media_id=str((v.get("media") or {}).get("id") or "") or None,
                    raw=change, expires_hours=settings.comment_review_ttl_hours,
                )
                if is_new:
                    _draft_and_notify(db, event); created += 1
        for msg in entry.get("messaging", []):
            message = msg.get("message") or {}
            mid = str(message.get("mid") or "")
            if not mid or message.get("is_echo"):
                continue
            sender = msg.get("sender") or {}
            event, is_new = _persist_event(
                db, source="dm", external_id=mid,
                author_id=str(sender.get("id") or "") or None,
                author_username=None, text=message.get("text"), media_id=None,
                raw=msg, expires_hours=settings.dm_reply_window_hours,
            )
            if is_new:
                _draft_and_notify(db, event); created += 1
    return {"ok": True, "created": created}
