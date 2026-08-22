from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClientFamilyLink(Base):
    __tablename__ = "client_family_links"
    __table_args__ = (
        UniqueConstraint("adult_user_id", "child_user_id", name="uq_client_family_links_pair"),
        CheckConstraint("adult_user_id <> child_user_id", name="ck_client_family_links_not_self"),
        Index("ix_client_family_links_adult", "adult_user_id"),
        Index("ix_client_family_links_child", "child_user_id"),
        Index(
            "uq_client_family_links_child_billing_recipient",
            "child_user_id",
            unique=True,
            postgresql_where=text("is_billing_recipient"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    adult_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    child_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    relationship_label: Mapped[str | None] = mapped_column(String(80), nullable=True)
    is_billing_recipient: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


class ClientFamilyBillingAllocation(Base):
    __tablename__ = "client_family_billing_allocations"
    __table_args__ = (
        UniqueConstraint("child_user_id", "payer_user_id", name="uq_client_family_billing_allocation_child_payer"),
        CheckConstraint(
            "allocation_type IN ('PERCENT', 'FIXED', 'REMAINDER')",
            name="ck_client_family_billing_allocation_type",
        ),
        CheckConstraint(
            "(allocation_type = 'REMAINDER' AND allocation_value IS NULL) OR "
            "(allocation_type <> 'REMAINDER' AND allocation_value IS NOT NULL AND allocation_value >= 0)",
            name="ck_client_family_billing_allocation_value",
        ),
        Index("ix_client_family_billing_allocations_child", "child_user_id"),
        Index("ix_client_family_billing_allocations_payer", "payer_user_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        server_default=text("gen_random_uuid()"),
    )
    child_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    payer_user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    allocation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    allocation_value: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
