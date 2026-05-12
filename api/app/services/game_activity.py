from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.game import Game


def touch_game(db: Session, game_id: UUID) -> None:
    db.execute(
        update(Game)
        .where(Game.id == game_id)
        .values(updated_at=datetime.now(UTC))
        .execution_options(synchronize_session=False)
    )
