from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Branch(Base):
    __tablename__ = "branches"
    __table_args__ = (
        CheckConstraint(
            "LENGTH(TRIM(name)) > 0",
            name="ck_branches_name_not_blank",
        ),
        CheckConstraint(
            "LENGTH(TRIM(address)) > 0",
            name="ck_branches_address_not_blank",
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

    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    address: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    salon = relationship(
        "Salon",
        back_populates="branches",
    )
