from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class Salon(Base):
    __tablename__ = "salons"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(String(150))

    description: Mapped[str | None] = mapped_column(String(1000))

    city: Mapped[str | None] = mapped_column(String(100))

    address: Mapped[str | None] = mapped_column(String(255))

    phone: Mapped[str | None] = mapped_column(String(30))
