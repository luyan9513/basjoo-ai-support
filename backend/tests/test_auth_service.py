from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import bcrypt
import pytest

from services.auth_service import AuthService


def test_hash_password():
    password = "testpassword123"
    hashed = AuthService.hash_password(password)

    assert hashed != password
    assert hashed.startswith("$argon2id$")


def test_verify_password():
    password = "testpassword123"
    hashed = AuthService.hash_password(password)

    assert AuthService.verify_password(password, hashed) is True
    assert AuthService.verify_password("wrongpassword", hashed) is False


def test_long_password_is_not_silently_truncated_for_new_hash():
    long_password = "a" * 100
    hashed = AuthService.hash_password(long_password)

    assert AuthService.verify_password(long_password, hashed) is True
    assert AuthService.verify_password("a" * 72 + "b" * 28, hashed) is False


def test_password_with_unicode():
    password = "密码测试123"
    hashed = AuthService.hash_password(password)

    assert AuthService.verify_password(password, hashed) is True


def test_verify_existing_bcrypt_hash():
    password = "legacy-password-123"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()

    assert AuthService.verify_password(password, legacy_hash) is True
    assert AuthService.verify_password("wrong-password", legacy_hash) is False


def test_unknown_password_hash_fails_closed():
    assert AuthService.verify_password("testpassword123", "not-a-password-hash") is False


@pytest.mark.asyncio
async def test_authenticate_admin_upgrades_legacy_bcrypt_hash():
    password = "legacy-password-123"
    legacy_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode()
    admin = SimpleNamespace(hashed_password=legacy_hash, is_active=True)
    result = MagicMock()
    result.scalar_one_or_none.return_value = admin
    db = AsyncMock()
    db.execute.return_value = result

    authenticated = await AuthService(db).authenticate_admin(
        "legacy@example.com", password
    )

    assert authenticated is admin
    assert admin.hashed_password.startswith("$argon2id$")
    db.commit.assert_awaited_once()
