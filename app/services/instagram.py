from datetime import datetime, timezone
import hashlib
import hmac
import httpx
from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import Draft, Event
from .audit import log

settings = get_settings()


class InstagramAPIError(RuntimeError):
    pass


class ApprovalRequired(RuntimeError):
    pass


def verify_signature(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.meta_app_secret:
        return True  # development only; production validation requires the secret
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(settings.meta_app_secret.encode(), raw_body, hashlib.sha256).hexdigest()
    supplied = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, supplied)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class InstagramClient:
    def __init__(self):
        self.base = settings.meta_base_url.rstrip("/")
        self.token = settings.meta_access_token
        self.ig_user_id = settings.meta_ig_user_id

    def _headers(self):
        if not self.token:
            raise InstagramAPIError("META_ACCESS_TOKEN is not configured")
        return {"Authorization": f"Bearer {self.token}"}

    def get_profile(self) -> dict:
        url = f"{self.base}/me"
        params = {"fields": "id,username,name,biography,followers_count,follows_count,media_count"}
        r = httpx.get(url, params=params, headers=self._headers(), timeout=20)
        if r.is_error:
            raise InstagramAPIError(r.text)
        return r.json()

    def reply_to_comment(self, comment_id: str, message: str) -> dict:
        url = f"{self.base}/{comment_id}/replies"
        r = httpx.post(url, data={"message": message}, headers=self._headers(), timeout=20)
        if r.is_error:
            raise InstagramAPIError(r.text)
        return r.json()

    def send_dm(self, recipient_id: str, message: str) -> dict:
        if not self.ig_user_id:
            raise InstagramAPIError("META_IG_USER_ID is not configured")
        url = f"{self.base}/{self.ig_user_id}/messages"
        payload = {"recipient": {"id": recipient_id}, "message": {"text": message}}
        r = httpx.post(url, json=payload, headers=self._headers(), timeout=20)
        if r.is_error:
            raise InstagramAPIError(r.text)
        return r.json()


def send_approved_draft(db: Session, draft: Draft, actor: str) -> dict:
    locked = db.query(Draft).filter(Draft.id == draft.id).with_for_update().one()
    if locked.status not in {"approved", "edited"} or not locked.approved_by or not locked.approved_at:
        raise ApprovalRequired("Draft must have approved_by and approved_at before sending")
    if locked.sent_at:
        raise ApprovalRequired("Draft already sent")
    if not (locked.draft_text or "").strip():
        raise ApprovalRequired("Draft text is empty; edit it before sending")

    draft = locked
    event: Event = draft.event
    now = datetime.now(timezone.utc)
    if event.window_expires_at and _as_utc(event.window_expires_at) < now:
        draft.status = "expired"
        db.commit()
        log(db, "send_blocked_expired", actor=actor, event_id=event.id, draft_id=draft.id)
        raise ApprovalRequired("Reply review window expired")

    client = InstagramClient()
    if event.source == "comment":
        result = client.reply_to_comment(event.external_id, draft.draft_text.strip())
    elif event.source == "dm":
        if not event.author_id:
            raise InstagramAPIError("DM event has no recipient scoped id")
        result = client.send_dm(event.author_id, draft.draft_text.strip())
    else:
        raise InstagramAPIError(f"Unsupported source: {event.source}")

    draft.status = "sent"
    draft.sent_at = now
    db.commit()
    log(db, "sent", actor=actor, event_id=event.id, draft_id=draft.id, details={"api_result": result})
    return result
