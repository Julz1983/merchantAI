import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from core.db import Base


class Merchant(Base):
    """
    The tenant root. Every other tenant-scoped table carries merchant_id and is
    protected by a Postgres RLS policy against this table's primary key.

    Nothing merchant-specific is ever hardcoded in application code — branding,
    AI persona, and status all live here as data.
    """

    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    logo_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # { primary, secondary, accent } — drives widget + dashboard theming
    brand_colors: Mapped[dict] = mapped_column(JSON, default=dict)

    # Structured persona settings only (see architecture §0.4) — never raw
    # system-prompt text, to avoid a merchant turning the assistant into an
    # unreviewed liability surface.
    ai_persona: Mapped[dict] = mapped_column(JSON, default=dict)

    status: Mapped[str] = mapped_column(String(32), default="trial")  # trial | active | suspended

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
