"""turn jobs

Revision ID: 20260509_0008
Revises: 20260509_0007
Create Date: 2026-05-09

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260509_0008"
down_revision: str | None = "20260509_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS turn_jobs (
            id UUID NOT NULL,
            game_id UUID NOT NULL,
            status VARCHAR(32) NOT NULL,
            request_json JSONB NOT NULL,
            turn_id UUID,
            model_used TEXT,
            error_message TEXT,
            reasoning_content TEXT NOT NULL DEFAULT '',
            content_buffer TEXT NOT NULL DEFAULT '',
            progress_message TEXT,
            stream_started_at TIMESTAMP WITH TIME ZONE,
            last_event_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id),
            FOREIGN KEY(game_id) REFERENCES games (id) ON DELETE CASCADE
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_turn_jobs_game_id ON turn_jobs (game_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_turn_jobs_status ON turn_jobs (status)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_turn_jobs_status")
    op.execute("DROP INDEX IF EXISTS ix_turn_jobs_game_id")
    op.execute("DROP TABLE IF EXISTS turn_jobs")
