"""generator job stream fields

Revision ID: 20260509_0007
Revises: 20260509_0006
Create Date: 2026-05-09

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260509_0007"
down_revision: str | None = "20260509_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STREAM_COLUMNS_SQL = """
ALTER TABLE {table_name}
    ADD COLUMN IF NOT EXISTS reasoning_content TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS content_buffer TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS progress_message TEXT,
    ADD COLUMN IF NOT EXISTS stream_started_at TIMESTAMP WITH TIME ZONE,
    ADD COLUMN IF NOT EXISTS last_event_at TIMESTAMP WITH TIME ZONE
"""


def upgrade() -> None:
    op.execute(STREAM_COLUMNS_SQL.format(table_name="generator_chat_jobs"))
    op.execute(STREAM_COLUMNS_SQL.format(table_name="generator_finalize_jobs"))


def downgrade() -> None:
    for table_name in ("generator_chat_jobs", "generator_finalize_jobs"):
        op.execute(
            f"""
            ALTER TABLE {table_name}
                DROP COLUMN IF EXISTS last_event_at,
                DROP COLUMN IF EXISTS stream_started_at,
                DROP COLUMN IF EXISTS progress_message,
                DROP COLUMN IF EXISTS content_buffer,
                DROP COLUMN IF EXISTS reasoning_content
            """
        )
