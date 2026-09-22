import html
import httpx
from ..config import get_settings
from ..models import Draft

settings = get_settings()


def _api(method: str) -> str:
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def send_message(text: str, reply_markup: dict | None = None):
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {"ok": False, "disabled": True}
    payload = {"chat_id": settings.telegram_chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    r = httpx.post(_api("sendMessage"), json=payload, timeout=20)
    return r.json()


def notify_draft(draft: Draft):
    e = draft.event
    source = "DM" if e.source == "dm" else "Commentaire"
    text = (
        f"<b>{source} — validation requise</b>\n"
        f"Auteur: <code>{html.escape(e.author_username or e.author_id or 'inconnu')}</code>\n"
        f"Original: {html.escape((e.text or '')[:900])}\n\n"
        f"<b>Brouillon</b>\n{html.escape(draft.draft_text or '[LLM non configuré]')}\n\n"
        f"ID: <code>{draft.id}</code>"
    )
    keyboard = {"inline_keyboard": [[
        {"text": "✅ Envoyer", "callback_data": f"approve:{draft.id}"},
        {"text": "✏️ Modifier", "callback_data": f"edit:{draft.id}"},
        {"text": "⏭ Ignorer", "callback_data": f"reject:{draft.id}"},
    ]]}
    return send_message(text, keyboard)


def answer_callback(callback_query_id: str, text: str):
    if not settings.telegram_bot_token:
        return
    httpx.post(_api("answerCallbackQuery"), json={"callback_query_id": callback_query_id, "text": text}, timeout=20)


def set_webhook():
    url = f"{settings.public_base_url.rstrip('/')}/webhooks/telegram"
    payload = {"url": url, "secret_token": settings.telegram_webhook_secret, "drop_pending_updates": False}
    r = httpx.post(_api("setWebhook"), json=payload, timeout=20)
    return r.json()
