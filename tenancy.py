from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from core.db import SessionLocal, set_tenant_context
from core.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


class CurrentUser:
    """Resolved identity for the current request — attached to every tenant-scoped route."""

    def __init__(self, user_id: UUID, merchant_id: UUID, role: str):
        self.user_id = user_id
        self.merchant_id = merchant_id
        self.role = role


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        payload = decode_token(credentials.credentials)
    except JWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    if payload.type != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token used where access token required")

    return CurrentUser(
        user_id=UUID(payload.sub),
        merchant_id=UUID(payload.merchant_id),
        role=payload.role,
    )


def get_tenant_db(current_user: CurrentUser = Depends(get_current_user)) -> Session:
    """
    Every tenant-scoped route depends on this instead of the plain get_db.
    It opens a session, sets the RLS session variable for this request's
    merchant, and yields — so every query on this session is automatically
    scoped, even if a route forgets an explicit merchant_id filter.
    """
    db = SessionLocal()
    try:
        set_tenant_context(db, current_user.merchant_id)
        yield db
    finally:
        db.close()


def require_role(*allowed_roles: str):
    """Route-level guard, e.g. Depends(require_role('owner', 'admin'))."""

    def _check(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient permissions")
        return current_user

    return _check
