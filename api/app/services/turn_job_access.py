"""Shared short-transaction fencing for asynchronous turn writers."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.models.generator_job import TurnJob
from app.services.timeline import TimelineConflict, assert_timeline_current


def current_turn_job(db: Session, job_id: UUID) -> TurnJob | None:
    job = db.get(TurnJob, job_id)
    if job is None:
        return None
    try:
        assert_timeline_current(db, job.game_id, job.timeline_generation or 0)
    except TimelineConflict:
        return None
    db.refresh(job)
    return job
