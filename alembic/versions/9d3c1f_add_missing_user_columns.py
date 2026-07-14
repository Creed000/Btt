"""add missing user columns

Revision ID: 9d3c1f
Revises: 77305b67f6d8
Create Date: 2026-07-14

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "9d3c1f"
down_revision: Union[str, Sequence[str], None] = "77305b67f6d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="client",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(length=50),
            nullable=False,
            server_default="Europe/Moscow",
        ),
    )

    op.add_column(
        "users",
        sa.Column(
            "last_seen",
            sa.DateTime(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "last_seen")
    op.drop_column("users", "timezone")
    op.drop_column("users", "role")
