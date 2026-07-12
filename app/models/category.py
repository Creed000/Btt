from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    icon: Mapped[str | None] = mapped_column(
        String(10),
        nullable=True,
    )

    services = relationship(
        "Service",
        back_populates="category",
        cascade="all, delete-orphan",
    )
