"""add SaaS fields to salons

Revision ID: a81f4c2d7e10
Revises: 9d3c1f
Create Date: 2026-08-04

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a81f4c2d7e10"
down_revision: Union[str, Sequence[str], None] = "9d3c1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "salons",
        sa.Column(
            "owner_id",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "slug",
            sa.String(length=100),
            nullable=True,
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "plan",
            sa.String(length=30),
            nullable=False,
            server_default="free",
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "subscription_status",
            sa.String(length=30),
            nullable=False,
            server_default="trial",
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "trial_ends_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "subscription_ends_at",
            sa.DateTime(),
            nullable=True,
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.add_column(
        "salons",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # ÐÐ°Ð¿Ð¾Ð»Ð½ÑÐµÐ¼ ÑÐ½Ð¸ÐºÐ°Ð»ÑÐ½ÑÐ¹ slug Ð´Ð»Ñ ÑÐ¶Ðµ ÑÑÑÐµÑÑÐ²ÑÑÑÐ¸Ñ ÑÐ°Ð»Ð¾Ð½Ð¾Ð².
    op.execute(
        sa.text(
            """
            UPDATE salons
            SET slug = 'salon-' || id
            WHERE slug IS NULL
            """
        )
    )

    # ÐÐ°Ð·Ð½Ð°ÑÐ°ÐµÐ¼ Ð²Ð»Ð°Ð´ÐµÐ»ÑÑÐ° ÑÑÑÐµÑÑÐ²ÑÑÑÐ¸Ð¼ ÑÐ°Ð»Ð¾Ð½Ð°Ð¼.
    # Ð¡Ð½Ð°ÑÐ°Ð»Ð° Ð±ÐµÑÑÐ¼ owner/admin, Ð¸Ð½Ð°ÑÐµ Ð¿ÐµÑÐ²Ð¾Ð³Ð¾ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ.
    op.execute(
        sa.text(
            """
            UPDATE salons
            SET owner_id = COALESCE(
                (
                    SELECT id
                    FROM users
                    WHERE role IN ('owner', 'admin')
                    ORDER BY
                        CASE WHEN role = 'owner' THEN 0 ELSE 1 END,
                        id
                    LIMIT 1
                ),
                (
                    SELECT id
                    FROM users
                    ORDER BY id
                    LIMIT 1
                )
            )
            WHERE owner_id IS NULL
            """
        )
    )

    # ÐÑÐ»Ð¸ ÑÐ°Ð±Ð»Ð¸ÑÐ° salons Ð¿ÑÑÑÐ°, Ð¾Ð³ÑÐ°Ð½Ð¸ÑÐµÐ½Ð¸Ñ Ð²ÐºÐ»ÑÑÐ°ÑÑÑ Ð±ÐµÐ· Ð¿ÑÐ¾Ð±Ð»ÐµÐ¼.
    # ÐÑÐ»Ð¸ Ð² Ð½ÐµÐ¹ ÐµÑÑÑ ÑÑÑÐ¾ÐºÐ¸, Ð½Ð¾ Ð² users Ð½ÐµÑ Ð½Ð¸ Ð¾Ð´Ð½Ð¾Ð³Ð¾ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»Ñ,
    # Ð¼Ð¸Ð³ÑÐ°ÑÐ¸Ñ Ð¾ÑÑÐ°Ð½Ð¾Ð²Ð¸ÑÑÑ Ð·Ð´ÐµÑÑ â ÑÑÐ¾ Ð±ÐµÐ·Ð¾Ð¿Ð°ÑÐ½ÐµÐµ, ÑÐµÐ¼ Ð½Ð°Ð·Ð½Ð°ÑÐ¸ÑÑ
    # Ð½ÐµÑÑÑÐµÑÑÐ²ÑÑÑÐµÐ³Ð¾ Ð²Ð»Ð°Ð´ÐµÐ»ÑÑÐ°.
    connection = op.get_bind()
    salons_without_owner = connection.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM salons
            WHERE owner_id IS NULL
            """
        )
    ).scalar_one()

    if salons_without_owner:
        raise RuntimeError(
            "ÐÐµÐ»ÑÐ·Ñ Ð½Ð°Ð·Ð½Ð°ÑÐ¸ÑÑ Ð²Ð»Ð°Ð´ÐµÐ»ÑÑÐ° ÑÑÑÐµÑÑÐ²ÑÑÑÐ¸Ð¼ ÑÐ°Ð»Ð¾Ð½Ð°Ð¼: "
            "Ð² ÑÐ°Ð±Ð»Ð¸ÑÐµ users Ð½ÐµÑ Ð¿Ð¾Ð»ÑÐ·Ð¾Ð²Ð°ÑÐµÐ»ÐµÐ¹."
        )

    op.alter_column(
        "salons",
        "owner_id",
        existing_type=sa.Integer(),
        nullable=False,
    )

    op.alter_column(
        "salons",
        "slug",
        existing_type=sa.String(length=100),
        nullable=False,
    )

    op.create_index(
        "ix_salons_owner_id",
        "salons",
        ["owner_id"],
        unique=False,
    )

    op.create_index(
        "ix_salons_slug",
        "salons",
        ["slug"],
        unique=True,
    )

    op.create_foreign_key(
        "fk_salons_owner_id_users",
        "salons",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # ÐÐ¾ÑÐ»Ðµ Ð·Ð°Ð¿Ð¾Ð»Ð½ÐµÐ½Ð¸Ñ Ð´Ð°Ð½Ð½ÑÑ ÑÐµÑÐ²ÐµÑÐ½ÑÐµ Ð·Ð½Ð°ÑÐµÐ½Ð¸Ñ Ð¿Ð¾ ÑÐ¼Ð¾Ð»ÑÐ°Ð½Ð¸Ñ
    # Ð´Ð»Ñ plan/status/is_active Ð¾ÑÑÐ°Ð²Ð»ÑÐµÐ¼ Ð¿Ð¾Ð»ÐµÐ·Ð½ÑÐ¼Ð¸ Ð´Ð»Ñ Ð¿ÑÑÐ¼ÑÑ INSERT.
    op.alter_column(
        "salons",
        "created_at",
        server_default=None,
    )

    op.alter_column(
        "salons",
        "updated_at",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_salons_owner_id_users",
        "salons",
        type_="foreignkey",
    )

    op.drop_index(
        "ix_salons_slug",
        table_name="salons",
    )

    op.drop_index(
        "ix_salons_owner_id",
        table_name="salons",
    )

    op.drop_column(
        "salons",
        "updated_at",
    )

    op.drop_column(
        "salons",
        "created_at",
    )

    op.drop_column(
        "salons",
        "is_active",
    )

    op.drop_column(
        "salons",
        "subscription_ends_at",
    )

    op.drop_column(
        "salons",
        "trial_ends_at",
    )

    op.drop_column(
        "salons",
        "subscription_status",
    )

    op.drop_column(
        "salons",
        "plan",
    )

    op.drop_column(
        "salons",
        "slug",
    )

    op.drop_column(
        "salons",
        "owner_id",
    )
