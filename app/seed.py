import json
from pathlib import Path
from sqlalchemy import select
from .db import SessionLocal
from .models import TargetAccount, MetricSnapshot
from .config import get_settings

settings = get_settings()


def seed():
    db = SessionLocal()
    try:
        path = Path(__file__).resolve().parents[1] / "config" / "targets.json"
        targets = json.loads(path.read_text(encoding="utf-8"))
        for item in targets:
            if not db.scalar(select(TargetAccount).where(TargetAccount.handle == item["handle"])):
                db.add(TargetAccount(**item))
        if not db.scalar(select(MetricSnapshot).limit(1)):
            db.add(MetricSnapshot(followers=settings.baseline_followers, username="d_gprm", raw_payload={"source":"baseline"}))
        db.commit()
    finally:
        db.close()
