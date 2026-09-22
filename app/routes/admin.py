import hmac
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..models import Draft, Event, MetricSnapshot, GrowthAction
from ..services.instagram import InstagramClient
from ..services.telegram import set_webhook
from ..services.audit import log
from ..services.growth import send_daily_pulse

router = APIRouter(prefix="/admin")
settings = get_settings()


def guard(x_admin_token: str = Header(default="")):
    if not hmac.compare_digest(x_admin_token or "", settings.admin_token):
        raise HTTPException(status_code=403, detail="forbidden")


@router.get("/status", dependencies=[Depends(guard)])
def status(db: Session = Depends(get_db)):
    return {
        "events": db.scalar(select(func.count()).select_from(Event)),
        "pending_drafts": db.scalar(select(func.count()).select_from(Draft).where(Draft.status.in_(["pending", "edited"]))),
        "sent_drafts": db.scalar(select(func.count()).select_from(Draft).where(Draft.status == "sent")),
        "growth_actions": db.scalar(select(func.count()).select_from(GrowthAction)),
    }


@router.post("/setup/telegram-webhook", dependencies=[Depends(guard)])
def setup_telegram_webhook():
    return set_webhook()


@router.post("/jobs/snapshot", dependencies=[Depends(guard)])
def snapshot(db: Session = Depends(get_db)):
    p = InstagramClient().get_profile()
    row = MetricSnapshot(
        followers=p.get("followers_count"), follows=p.get("follows_count"),
        media_count=p.get("media_count"), username=p.get("username"), raw_payload=p,
    )
    db.add(row); db.commit(); db.refresh(row)
    log(db, "metric_snapshot", details={"followers": row.followers, "follows": row.follows})
    return {"id": row.id, "followers": row.followers, "follows": row.follows, "media_count": row.media_count}


@router.post("/jobs/pulse", dependencies=[Depends(guard)])
def pulse(db: Session = Depends(get_db)):
    return send_daily_pulse(db)
