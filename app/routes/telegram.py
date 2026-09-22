import html
import hmac
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from ..config import get_settings
from ..db import get_db
from ..models import Draft, OperatorState
from ..services.audit import log
from ..services.instagram import send_approved_draft, ApprovalRequired, InstagramAPIError
from ..services.telegram import answer_callback, send_message
from ..services.growth import pulse_text, radar_text, propose_external_comment

router = APIRouter()
settings = get_settings()


def _check_secret(request: Request):
    supplied = request.headers.get("x-telegram-bot-api-secret-token") or ""
    if not hmac.compare_digest(supplied, settings.telegram_webhook_secret):
        raise HTTPException(status_code=403, detail="invalid telegram secret")


def _is_authorized_operator(operator_id: str) -> bool:
    allowed = settings.allowed_operator_id_set
    if allowed:
        return operator_id in allowed
    return bool(settings.telegram_chat_id) and operator_id == str(settings.telegram_chat_id)


@router.post("/webhooks/telegram")
async def telegram_webhook(request: Request, db: Session = Depends(get_db)):
    _check_secret(request)
    update = await request.json()
    callback = update.get("callback_query")
    if callback:
        data = callback.get("data", "")
        operator = str((callback.get("from") or {}).get("id") or "telegram")
        cqid = callback.get("id")
        if not _is_authorized_operator(operator):
            log(db, "unauthorized_operator_blocked", actor=operator, details={"data": data})
            answer_callback(cqid, "Non autorisé")
            return {"ok": True}
        action, _, draft_id = data.partition(":")
        draft = db.get(Draft, draft_id)
        if not draft:
            answer_callback(cqid, "Brouillon introuvable")
            return {"ok": True}
        if action == "approve":
            if draft.status not in {"pending", "edited"}:
                answer_callback(cqid, f"Déjà {draft.status}")
                return {"ok": True}
            draft.status = "approved"
            draft.approved_by = operator
            draft.approved_at = datetime.now(timezone.utc)
            db.commit()
            log(db, "approved", actor=operator, event_id=draft.event_id, draft_id=draft.id)
            try:
                send_approved_draft(db, draft, actor=operator)
                answer_callback(cqid, "Envoyé ✅")
            except (ApprovalRequired, InstagramAPIError) as exc:
                log(db, "send_error", actor=operator, event_id=draft.event_id, draft_id=draft.id, details={"error": str(exc)})
                answer_callback(cqid, f"Erreur: {str(exc)[:120]}")
        elif action == "reject":
            draft.status = "rejected"; db.commit()
            log(db, "rejected", actor=operator, event_id=draft.event_id, draft_id=draft.id)
            answer_callback(cqid, "Ignoré")
        elif action == "edit":
            state = db.get(OperatorState, operator) or OperatorState(operator_id=operator)
            state.awaiting_edit_draft_id = draft.id
            db.add(state); db.commit()
            answer_callback(cqid, "Envoie maintenant le texte corrigé dans ce chat")
            send_message(f"✏️ Envoie le nouveau texte pour <code>{draft.id}</code>. Il restera en attente jusqu’à un second clic sur Envoyer.")
        return {"ok": True}

    message = update.get("message") or {}
    text = (message.get("text") or "").strip()
    operator = str((message.get("from") or {}).get("id") or "telegram")
    if not _is_authorized_operator(operator):
        log(db, "unauthorized_operator_blocked", actor=operator, details={"text": text[:200]})
        return {"ok": True}
    if text == "/pulse":
        send_message(pulse_text(db)); return {"ok": True}
    if text == "/radar":
        send_message(radar_text(db)); return {"ok": True}
    if text.startswith("/opportunity "):
        body = text[len("/opportunity "):].strip()
        handle, sep, context = body.partition(" ")
        if not sep:
            send_message("Usage: <code>/opportunity @compte texte/contexte du post</code>")
            return {"ok": True}
        row = propose_external_comment(db, handle, context)
        draft = row.suggested_text or "[LLM non configuré]"
        send_message(f"<b>Commentaire proposé pour @{html.escape(row.target_handle)}</b>\n{html.escape(draft)}\n\nÀ copier/coller manuellement. Aucune action Instagram n’a été exécutée.")
        return {"ok": True}

    state = db.get(OperatorState, operator)
    if state and state.awaiting_edit_draft_id and text:
        draft = db.get(Draft, state.awaiting_edit_draft_id)
        if draft and draft.status in {"pending", "edited"}:
            before = draft.draft_text
            draft.draft_text = text
            draft.status = "edited"
            draft.approved_by = None
            draft.approved_at = None
            state.awaiting_edit_draft_id = None
            db.commit()
            log(db, "edited", actor=operator, event_id=draft.event_id, draft_id=draft.id, details={"before": before, "after": text})
            send_message(f"✅ Brouillon modifié.\n\n{html.escape(text)}\n\nUtilise la carte précédente et clique <b>Envoyer</b> pour validation finale.")
    return {"ok": True}
