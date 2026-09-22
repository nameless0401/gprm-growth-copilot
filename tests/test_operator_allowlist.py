from app.routes.telegram import _is_authorized_operator
from app.config import get_settings


def test_unknown_operator_rejected_when_allowlist_configured(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "allowed_operator_ids", "111,222")
    assert _is_authorized_operator("111") is True
    assert _is_authorized_operator("999") is False


def test_falls_back_to_chat_id_when_no_allowlist(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "allowed_operator_ids", "")
    monkeypatch.setattr(settings, "telegram_chat_id", "555")
    assert _is_authorized_operator("555") is True
    assert _is_authorized_operator("777") is False
