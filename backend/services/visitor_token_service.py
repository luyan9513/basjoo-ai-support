"""Signed identity tokens for public Widget chat sessions."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from config import settings

VISITOR_TOKEN_ISSUER = "basjoo"
VISITOR_TOKEN_AUDIENCE = "basjoo-widget"
VISITOR_TOKEN_TYPE = "visitor_session"


class VisitorTokenError(ValueError):
    """The public visitor token is missing, invalid, expired, or mismatched."""


@dataclass(frozen=True)
class VisitorTokenClaims:
    agent_id: str
    session_id: str
    visitor_id: str


def create_visitor_token(
    *,
    agent_id: str,
    session_id: str,
    visitor_id: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.visitor_token_expire_minutes)
    )
    payload = {
        "typ": VISITOR_TOKEN_TYPE,
        "iss": VISITOR_TOKEN_ISSUER,
        "aud": VISITOR_TOKEN_AUDIENCE,
        "iat": now,
        "exp": expires_at,
        "agent_id": agent_id,
        "session_id": session_id,
        "visitor_id": visitor_id,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_visitor_token(token: str) -> VisitorTokenClaims:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm],
            audience=VISITOR_TOKEN_AUDIENCE,
            issuer=VISITOR_TOKEN_ISSUER,
        )
    except JWTError as exc:
        raise VisitorTokenError("Invalid visitor token") from exc

    if payload.get("typ") != VISITOR_TOKEN_TYPE:
        raise VisitorTokenError("Invalid visitor token type")

    agent_id = payload.get("agent_id")
    session_id = payload.get("session_id")
    visitor_id = payload.get("visitor_id")
    if not all(isinstance(value, str) and value for value in (agent_id, session_id, visitor_id)):
        raise VisitorTokenError("Visitor token is missing required claims")

    return VisitorTokenClaims(
        agent_id=agent_id,
        session_id=session_id,
        visitor_id=visitor_id,
    )
