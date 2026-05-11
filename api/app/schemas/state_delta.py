from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

StateDeltaStatus = Literal["pending", "approved", "edited", "rejected"]


class StateDeltaRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    turn_id: UUID
    delta_json: dict[str, Any]
    status: StateDeltaStatus
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class StateDeltaUpdate(BaseModel):
    delta_json: dict[str, Any] = Field(default_factory=dict)
