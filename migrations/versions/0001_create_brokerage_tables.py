"""create brokerage notes tables

Revision ID: 0001
Revises:
Create Date: 2026-09-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "imported_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_name", sa.String(length=255), nullable=False),
        sa.Column("file_sha256", sa.String(length=64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imported_files_file_sha256", "imported_files", ["file_sha256"], unique=True)

    op.create_table(
        "brokerage_notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("file_id", sa.Integer(), nullable=False),
        sa.Column("broker_name", sa.String(length=255), nullable=False),
        sa.Column("broker_cnpj", sa.String(length=20), nullable=True),
        sa.Column("note_number", sa.String(length=20), nullable=False),
        sa.Column("page", sa.Integer(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("market", sa.String(length=10), nullable=False),
        sa.Column("account_number", sa.String(length=20), nullable=True),
        sa.Column("client_name", sa.String(length=255), nullable=True),
        sa.Column("client_tax_id", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["file_id"], ["imported_files.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_number", "trading_date", "market", name="uq_note_identity"),
    )
    op.create_index("ix_brokerage_notes_note_number", "brokerage_notes", ["note_number"], unique=False)
    op.create_index("ix_brokerage_notes_trading_date", "brokerage_notes", ["trading_date"], unique=False)
    op.create_index("ix_brokerage_notes_file_id", "brokerage_notes", ["file_id"], unique=False)

    op.create_table(
        "brokerage_trades",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("trading_date", sa.Date(), nullable=False),
        sa.Column("market_type", sa.String(length=30), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=True),
        sa.Column("side", sa.String(length=1), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=6), nullable=False),
        sa.Column("value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["note_id"], ["brokerage_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brokerage_trades_note_id", "brokerage_trades", ["note_id"], unique=False)
    op.create_index("ix_brokerage_trades_trading_date", "brokerage_trades", ["trading_date"], unique=False)
    op.create_index("ix_brokerage_trades_ticker", "brokerage_trades", ["ticker"], unique=False)

    op.create_table(
        "brokerage_note_costs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("note_id", sa.Integer(), nullable=False),
        sa.Column("net_operations_value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("settlement_fee", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("registration_fee", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("clearing_total", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("emoluments", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("brokerage_fee", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("iss", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("irrf", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("other_fees", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("net_value", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.ForeignKeyConstraint(["note_id"], ["brokerage_notes.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("note_id"),
    )


def downgrade() -> None:
    op.drop_table("brokerage_note_costs")
    op.drop_table("brokerage_trades")
    op.drop_table("brokerage_notes")
    op.drop_index("ix_imported_files_file_sha256", table_name="imported_files")
    op.drop_table("imported_files")
