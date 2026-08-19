from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class MasterInvite(Base):
    __tablename__ = "master_invites"
    __table_args__ = (
        CheckConstraint(
            "status IN "
            "('pending', 'accepted', 'declined', 'expired', 'replaced')",
            name="ck_master_invites_status_valid",
        ),
        CheckConstraint(
            "(status = 'pending' AND resolved_at IS NULL) "
            "OR (status <> 'pending' AND resolved_at IS NOT NULL)",
            name="ck_master_invites_resolved_state",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    salon_id: Mapped[int] = mapped_column(
        ForeignKey(
            "salons.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    invited_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    invited_by_user_id: Mapped[int] = mapped_column(
        ForeignKey(
            "users.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default=text("'pending'"),
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        server_default=text("CURRENT_TIMESTAMP"),
        nullable=False,
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    salon = relationship(
        "Salon",
        foreign_keys=[salon_id],
    )

    invited_user = relationship(
        "User",
        foreign_keys=[invited_user_id],
    )

    invited_by = relationship(
        "User",
        foreign_keys=[invited_by_user_id],
    )
