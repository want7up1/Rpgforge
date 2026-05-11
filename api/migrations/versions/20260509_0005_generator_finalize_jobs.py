"""generator finalize jobs

Revision ID: 20260509_0005
Revises: 20260509_0004
Create Date: 2026-05-09

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260509_0005"
down_revision: str | None = "20260509_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS generator_finalize_jobs (
            id UUID NOT NULL,
            status VARCHAR(32) NOT NULL,
            request_json JSONB NOT NULL,
            result_json JSONB,
            model_used TEXT,
            error_message TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            completed_at TIMESTAMP WITH TIME ZONE,
            PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_generator_finalize_jobs_status
        ON generator_finalize_jobs (status)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_generator_finalize_jobs_status")
    op.execute("DROP TABLE IF EXISTS generator_finalize_jobs")
