from enum import Enum

from sqlalchemy import CheckConstraint, Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserRole(str, Enum):
    CLIENT = "client"
    MASTER = "master"
    OWNER = "owner"
    ADMIN = "admin"


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (
        CheckConstraint(
            "name IN ('client', 'master', 'owner', 'admin')",
            name="ck_roles_name_valid",
        ),
    )

    id: Mapped[int] = mapped_column(
        primary_key=True,
    )

    name: Mapped[UserRole] = mapped_column(
        SqlEnum(
            UserRole,
            native_enum=False,
            length=20,
            values_callable=lambda enum_cls: [
                item.value
                for item in enum_cls
            ],
        ),
        unique=True,
        nullable=False,
    )
