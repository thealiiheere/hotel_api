"""Initial schema: users, rooms, bookings with all constraints

Revision ID: 0001
Revises:
Create Date: 2026-10-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # btree_gist lets one GiST index combine "room_id =" with "daterange &&"
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="guest"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('guest', 'admin')", name=op.f("ck_users_role_valid")),
    )

    op.create_table(
        "rooms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("room_type", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("price_per_night", sa.Numeric(10, 2), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rooms"),
        sa.UniqueConstraint("number", name="uq_rooms_number"),
        sa.CheckConstraint("capacity > 0", name=op.f("ck_rooms_capacity_positive")),
        sa.CheckConstraint("price_per_night > 0", name=op.f("ck_rooms_price_positive")),
    )

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("room_id", sa.Integer(), nullable=False),
        sa.Column("check_in", sa.Date(), nullable=False),
        sa.Column("check_out", sa.Date(), nullable=False),
        sa.Column("guests", sa.Integer(), nullable=False),
        sa.Column("nightly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("total_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_bookings"),
        # RESTRICT: deleting a user/room that has bookings fails instead of erasing history
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_bookings_user_id_users", ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name="fk_bookings_room_id_rooms", ondelete="RESTRICT"
        ),
        sa.CheckConstraint("check_in < check_out", name=op.f("ck_bookings_dates_order")),
        sa.CheckConstraint("guests > 0", name=op.f("ck_bookings_guests_positive")),
        sa.CheckConstraint("nightly_rate > 0", name=op.f("ck_bookings_nightly_rate_positive")),
        sa.CheckConstraint(
            "total_price = nightly_rate * (check_out - check_in)",
            name=op.f("ck_bookings_total_price_matches"),
        ),
        sa.CheckConstraint(
            "status IN ('active', 'cancelled')", name=op.f("ck_bookings_status_valid")
        ),
        sa.CheckConstraint(
            "(status = 'cancelled') = (cancelled_at IS NOT NULL)",
            name=op.f("ck_bookings_cancelled_at_matches_status"),
        ),
    )
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    op.create_index("ix_bookings_room_id", "bookings", ["room_id"])

    # Active bookings of the same room may not overlap. '[)' = check-out day is free.
    op.execute(
        """
        ALTER TABLE bookings
        ADD CONSTRAINT ex_bookings_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            daterange(check_in, check_out, '[)') WITH &&
        )
        WHERE (status = 'active')
        """
    )


def downgrade() -> None:
    op.drop_table("bookings")
    op.drop_table("rooms")
    op.drop_table("users")
    # btree_gist is left installed: other objects in the database may rely on it
