from fastapi.testclient import TestClient
from app.main import app
from app.config import get_settings


def test_health():
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


def test_meta_verification_rejects_bad_token():
    with TestClient(app) as client:
        r = client.get("/webhooks/meta", params={"hub.mode":"subscribe","hub.verify_token":"wrong","hub.challenge":"123"})
        assert r.status_code == 403


def test_meta_verification_accepts_configured_token():
    token = get_settings().meta_verify_token
    with TestClient(app) as client:
        r = client.get("/webhooks/meta", params={"hub.mode":"subscribe","hub.verify_token":token,"hub.challenge":"123"})
        assert r.status_code == 200
        assert r.text == "123"
