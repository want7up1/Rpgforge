"""manual setting editor and versions

Revision ID: 20260512_0015
Revises: 20260512_0014
Create Date: 2026-05-12

"""
from collections.abc import Sequence

from alembic import op

revision: str = "20260512_0015"
down_revision: str | None = "20260512_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE lore_entries
            ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE,
            ADD COLUMN IF NOT EXISTS archived_at TIMESTAMP WITH TIME ZONE
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_lore_entries_active
            ON lore_entries (game_id, is_active)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS game_setting_versions (
            id UUID PRIMARY KEY,
            game_id UUID NOT NULL REFERENCES games(id) ON DELETE CASCADE,
            scope VARCHAR(64) NOT NULL,
            entity_id UUID,
            action VARCHAR(64) NOT NULL,
            snapshot_json JSONB NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_game_setting_versions_game_scope
            ON game_setting_versions (game_id, scope, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_game_setting_versions_entity
            ON game_setting_versions (game_id, scope, entity_id)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_game_setting_versions_entity")
    op.execute("DROP INDEX IF EXISTS ix_game_setting_versions_game_scope")
    op.execute("DROP TABLE IF EXISTS game_setting_versions")
    op.execute("DROP INDEX IF EXISTS ix_lore_entries_active")
    op.execute(
        """
        ALTER TABLE lore_entries
            DROP COLUMN IF EXISTS archived_at,
            DROP COLUMN IF EXISTS is_active
        """
    )
