from enum import Enum

from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserRole(str, Enum):
    CLIENT = "client"
    MASTER = "master"
    SALON_ADMIN = "salon_admin"
    SUPER_ADMIN = "super_admin"


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole),
        unique=True,
        nullable=False,
    )
