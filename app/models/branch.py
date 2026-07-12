from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)

    salon_id: Mapped[int] = mapped_column(
        ForeignKey("salons.id")
    )

    name: Mapped[str] = mapped_column(String(100))

    address: Mapped[str] = mapped_column(String(255))
