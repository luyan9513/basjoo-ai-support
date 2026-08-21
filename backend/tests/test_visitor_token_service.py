"""Unit tests for signed public visitor-session tokens."""

from datetime import timedelta

import pytest
from jose import jwt

from config import settings
from services.visitor_token_service import (
    VISITOR_TOKEN_AUDIENCE,
    VISITOR_TOKEN_ISSUER,
    VisitorTokenError,
    create_visitor_token,
    decode_visitor_token,
)


def test_visitor_token_round_trip_preserves_identity():
    token = create_visitor_token(
        agent_id="agent-1",
        session_id="session-1",
        visitor_id="visitor-1",
    )

    claims = decode_visitor_token(token)

    assert claims.agent_id == "agent-1"
    assert claims.session_id == "session-1"
    assert claims.visitor_id == "visitor-1"


def test_expired_visitor_token_is_rejected():
    token = create_visitor_token(
        agent_id="agent-1",
        session_id="session-1",
        visitor_id="visitor-1",
        expires_delta=timedelta(seconds=-1),
    )

    with pytest.raises(VisitorTokenError):
        decode_visitor_token(token)


def test_token_with_wrong_type_is_rejected():
    token = jwt.encode(
        {
            "typ": "admin_access",
            "iss": VISITOR_TOKEN_ISSUER,
            "aud": VISITOR_TOKEN_AUDIENCE,
            "agent_id": "agent-1",
            "session_id": "session-1",
            "visitor_id": "visitor-1",
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )

    with pytest.raises(VisitorTokenError):
        decode_visitor_token(token)
