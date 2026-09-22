import pytest
from app.config import Settings


def test_production_rejects_default_secrets_and_sqlite():
    s = Settings(app_env="production")
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        s.validate_production()


def test_development_can_boot_with_safe_defaults():
    s = Settings(app_env="development")
    s.validate_production()
