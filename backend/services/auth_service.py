from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pwdlib.hashers.argon2 import Argon2Hasher
from pwdlib.hashers.bcrypt import BcryptHasher
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import logging

from models import AdminUser
from config import settings

logger = logging.getLogger(__name__)

password_hash = PasswordHash((Argon2Hasher(), BcryptHasher()))


def _is_bcrypt_hash(hashed_password: str) -> bool:
    return hashed_password.startswith(("$2a$", "$2b$", "$2y$"))


def _legacy_bcrypt_password(password: str) -> str:
    """Preserve the old UTF-8 72-byte canonicalization for existing hashes."""
    return password.encode("utf-8")[:72].decode("utf-8", errors="ignore")


class AuthError(Exception):
    """Base authentication error."""
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class TokenExpiredError(AuthError):
    """Token has expired."""
    pass


class TokenInvalidError(AuthError):
    """Token is malformed or has an invalid signature."""
    pass


class AdminNotFoundError(AuthError):
    """Admin user does not exist."""
    pass


class AdminDeactivatedError(AuthError):
    """Admin account is deactivated."""
    pass


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        password = (
            _legacy_bcrypt_password(plain_password)
            if _is_bcrypt_hash(hashed_password)
            else plain_password
        )
        try:
            return password_hash.verify(password, hashed_password)
        except (UnknownHashError, TypeError, ValueError):
            return False

    @staticmethod
    def verify_and_update_password(
        plain_password: str, hashed_password: str
    ) -> tuple[bool, str | None]:
        try:
            if _is_bcrypt_hash(hashed_password):
                valid = password_hash.verify(
                    _legacy_bcrypt_password(plain_password), hashed_password
                )
                return valid, password_hash.hash(plain_password) if valid else None
            return password_hash.verify_and_update(plain_password, hashed_password)
        except (UnknownHashError, TypeError, ValueError):
            return False, None

    @staticmethod
    def hash_password(password: str) -> str:
        return password_hash.hash(password)

    def create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        to_encode = data.copy()

        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=settings.access_token_expire_minutes
            )

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(
            to_encode, settings.secret_key, algorithm=settings.algorithm
        )

        return encoded_jwt

    async def authenticate_admin(
        self, email: str, password: str
    ) -> AdminUser:
        result = await self.db.execute(
            select(AdminUser).where(AdminUser.email == email)
        )
        admin = result.scalar_one_or_none()

        if not admin:
            raise AdminNotFoundError("No account found with this email")

        valid_password, updated_hash = self.verify_and_update_password(
            password, admin.hashed_password
        )
        if not valid_password:
            raise AuthError("Incorrect password")

        if not admin.is_active:
            raise AdminDeactivatedError("Admin account is deactivated")

        if updated_hash is not None:
            admin.hashed_password = updated_hash
            await self.db.commit()

        return admin

    async def get_current_admin(self, token: str) -> AdminUser:
        from jose import ExpiredSignatureError

        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.algorithm]
            )
            admin_id = payload.get("sub")

            if admin_id is None:
                raise TokenInvalidError("Token missing subject claim")

        except ExpiredSignatureError:
            raise TokenExpiredError("Token has expired")
        except JWTError:
            raise TokenInvalidError("Invalid token")

        result = await self.db.execute(
            select(AdminUser).where(AdminUser.id == int(admin_id))
        )
        admin = result.scalar_one_or_none()

        if admin is None:
            raise AdminNotFoundError("Admin user not found")
        if not admin.is_active:
            raise AdminDeactivatedError("Admin account is deactivated")

        return admin

    async def create_admin(
        self,
        email: str,
        password: str,
        name: str,
        role: str = "admin",
        workspace_id: int | None = None,
    ) -> AdminUser:
        admin = AdminUser(
            email=email,
            hashed_password=self.hash_password(password),
            name=name,
            role=role,
            is_active=True,
            workspace_id=workspace_id,
        )
        self.db.add(admin)
        await self.db.commit()
        await self.db.refresh(admin)
        return admin
