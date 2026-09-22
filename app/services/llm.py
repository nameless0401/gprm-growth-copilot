import json
from ..config import get_settings

settings = get_settings()

STYLE = """You write short Instagram replies and public comment drafts for Guy (@d_gprm), a personal account, not a brand.
Voice: natural, concise, calm, occasionally dry/contextual humor. French or English follows the source language.
Never use generic marketing praise, engagement bait, follow requests, sales language, or excessive emojis.
For medical topics: concise, careful, non-diagnostic, professional. For friends/lifestyle: relaxed and human.
Output STRICT JSON with keys draft_text, confidence (low|medium|high), flags (array of short strings).
No action is ever sent automatically; you only draft text for human review."""


def generate_draft(source: str, text: str, context: str = "") -> dict:
    if not settings.openai_api_key or not settings.openai_model:
        return {
            "draft_text": "",
            "confidence": "low",
            "flags": ["llm_not_configured", "manual_draft_required"],
        }
    try:
        from openai import OpenAI
    except ImportError as exc:
        return {"draft_text": "", "confidence": "low", "flags": ["openai_sdk_missing", str(exc)]}
    client = OpenAI(api_key=settings.openai_api_key)
    prompt = f"Source: {source}\nContext: {context}\nIncoming text: {text}\nCreate ONE reply draft."
    resp = client.responses.create(model=settings.openai_model, input=f"{STYLE}\n\n{prompt}")
    raw = (resp.output_text or "").strip()
    try:
        data = json.loads(raw)
    except Exception:
        data = {"draft_text": raw, "confidence": "medium", "flags": ["unstructured_model_output"]}
    data.setdefault("draft_text", "")
    data.setdefault("confidence", "medium")
    data.setdefault("flags", [])
    return data


def generate_public_opportunity_comment(handle: str, post_context: str) -> dict:
    instruction = f"Draft one public comment for a post by @{handle}. The operator will paste it manually. Never imply that we know private data."
    return generate_draft("external_public_post", post_context, instruction)
