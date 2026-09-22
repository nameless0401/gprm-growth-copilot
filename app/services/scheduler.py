import asyncio
from datetime import datetime, timezone
from sqlalchemy import select, func
from ..config import get_settings
from ..db import SessionLocal
from ..models import AuditLog, MetricSnapshot, Draft
from .audit import log
from .growth import send_daily_pulse
from .instagram import InstagramClient
from .telegram import notify_draft

settings = get_settings()


def _did_action_today(db, action: str) -> bool:
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return bool(db.scalar(select(func.count()).select_from(AuditLog).where(AuditLog.action == action, AuditLog.created_at >= day_start)))


def _retry_pending_notifications(db) -> None:
    drafts = db.scalars(
        select(Draft)
        .where(Draft.status.in_(["pending", "edited"]), Draft.notified_at.is_(None))
        .order_by(Draft.created_at.asc())
        .limit(20)
    ).all()
    for draft in drafts:
        try:
            result = notify_draft(draft)
            if not result.get("ok"):
                raise RuntimeError(f"Telegram notification failed: {result}")
            draft.notified_at = datetime.now(timezone.utc)
            db.commit()
            log(db, "draft_notified_retry", event_id=draft.event_id, draft_id=draft.id)
        except Exception as exc:
            db.rollback()
            log(db, "draft_notify_retry_error", event_id=draft.event_id, draft_id=draft.id, details={"error": str(exc)})
            break


def run_notification_retry_cycle():
    db = SessionLocal()
    try:
        _retry_pending_notifications(db)
    finally:
        db.close()


def run_daily_cycle():
    db = SessionLocal()
    try:
        _retry_pending_notifications(db)
        if settings.meta_access_token and settings.meta_api_version != "vXX.X" and not _did_action_today(db, "daily_snapshot"):
            try:
                p = InstagramClient().get_profile()
                db.add(MetricSnapshot(
                    followers=p.get("followers_count"), follows=p.get("follows_count"), media_count=p.get("media_count"),
                    username=p.get("username"), raw_payload=p,
                ))
                db.commit()
                log(db, "daily_snapshot", details={"followers": p.get("followers_count")})
            except Exception as exc:
                log(db, "daily_snapshot_error", details={"error": str(exc)})
        if settings.telegram_bot_token and settings.telegram_chat_id and not _did_action_today(db, "daily_pulse_sent"):
            try:
                result = send_daily_pulse(db)
                if not result.get("ok"):
                    raise RuntimeError(f"Telegram pulse failed: {result}")
                log(db, "daily_pulse_sent")
            except Exception as exc:
                log(db, "daily_pulse_error", details={"error": str(exc)})
    finally:
        db.close()


async def scheduler_loop():
    while True:
        now = datetime.now(timezone.utc)
        if now.hour >= settings.daily_pulse_hour_utc:
            await asyncio.to_thread(run_daily_cycle)
        else:
            await asyncio.to_thread(run_notification_retry_cycle)
        await asyncio.sleep(900)
