from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..config import get_settings
from ..models import MetricSnapshot, TargetAccount, GrowthAction
from .telegram import send_message
from .llm import generate_public_opportunity_comment

settings = get_settings()


def _target_score(item: TargetAccount, now: datetime) -> float:
    if item.last_shown_at is None:
        freshness = 80
    else:
        dt = item.last_shown_at
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        freshness = min(max((now - dt).total_seconds() / 86400, 0) * 12, 80)
    repetition_penalty = min(item.shown_count * 1.5, 25)
    return item.priority + freshness - repetition_penalty


def next_targets(db: Session, limit: int = 3) -> list[TargetAccount]:
    now = datetime.now(timezone.utc)
    rows = db.scalars(select(TargetAccount).where(TargetAccount.active.is_(True))).all()
    rows = sorted(rows, key=lambda x: _target_score(x, now), reverse=True)
    chosen: list[TargetAccount] = []
    used_clusters: set[str] = set()
    for item in rows:
        if item.cluster in used_clusters and len(rows) - len(chosen) > limit:
            continue
        chosen.append(item)
        used_clusters.add(item.cluster)
        if len(chosen) == limit:
            break
    if len(chosen) < limit:
        for item in rows:
            if item not in chosen:
                chosen.append(item)
                if len(chosen) == limit:
                    break
    for item in chosen:
        item.last_shown_at = now
        item.shown_count += 1
    db.commit()
    return chosen


def latest_snapshot(db: Session):
    return db.scalar(select(MetricSnapshot).order_by(MetricSnapshot.captured_at.desc()).limit(1))


def pulse_text(db: Session) -> str:
    latest = latest_snapshot(db)
    followers = latest.followers if latest and latest.followers is not None else settings.baseline_followers
    remaining = max(settings.target_followers - followers, 0)
    gained = followers - settings.baseline_followers
    pct = round((followers / settings.target_followers) * 100, 1)
    return (
        f"<b>GPRM 1K Pulse</b>\n"
        f"Followers: <b>{followers}</b> / {settings.target_followers} ({pct}%)\n"
        f"Depuis baseline: <b>{gained:+d}</b>\n"
        f"Reste: <b>{remaining}</b>\n"
        f"Règle: 2–4 interactions publiques réellement pertinentes, jamais forcées."
    )


def radar_text(db: Session) -> str:
    targets = next_targets(db, 3)
    lines = ["<b>Radar — 3 comptes à vérifier</b>"]
    for i, t in enumerate(targets, 1):
        lines.append(f"{i}. <b>@{t.handle}</b> — {t.cluster}\n{t.rationale}\nhttps://instagram.com/{t.handle}")
    lines.append("S’il n’y a rien de naturel à commenter aujourd’hui : passe. Aucun quota à remplir.")
    return "\n\n".join(lines)


def send_daily_pulse(db: Session):
    return send_message(pulse_text(db) + "\n\n" + radar_text(db))


def propose_external_comment(db: Session, handle: str, post_context: str, post_url: str | None = None) -> GrowthAction:
    out = generate_public_opportunity_comment(handle, post_context)
    row = GrowthAction(
        target_handle=handle.lstrip("@"),
        source_text=post_context,
        post_url=post_url,
        suggested_text=out.get("draft_text", ""),
        outcome="proposed",
    )
    db.add(row)
    db.commit()
    return row
