import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder

TurnStreamEvent = dict[str, Any]


class TurnStreamEventBroker:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[TurnStreamEvent]]] = {}
        self._latest: dict[UUID, TurnStreamEvent] = {}

    def subscribe(self, job_id: UUID) -> asyncio.Queue[TurnStreamEvent]:
        queue: asyncio.Queue[TurnStreamEvent] = asyncio.Queue(maxsize=64)
        self._subscribers.setdefault(job_id, set()).add(queue)
        return queue

    def unsubscribe(self, job_id: UUID, queue: asyncio.Queue[TurnStreamEvent]) -> None:
        subscribers = self._subscribers.get(job_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(job_id, None)

    def latest(self, job_id: UUID) -> TurnStreamEvent | None:
        return self._latest.get(job_id)

    def publish(self, job_id: UUID, event: TurnStreamEvent) -> None:
        enriched_event = {
            "job_id": str(job_id),
            "sent_at": datetime.now(UTC).isoformat(),
            **event,
        }
        self._latest[job_id] = enriched_event

        for queue in list(self._subscribers.get(job_id, ())):
            try:
                queue.put_nowait(enriched_event)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    queue.put_nowait(enriched_event)
                except asyncio.QueueFull:
                    pass


turn_stream_event_broker = TurnStreamEventBroker()


def format_sse_event(event_type: str, payload: TurnStreamEvent) -> str:
    encoded = json.dumps(jsonable_encoder(payload), ensure_ascii=False)
    return f"event: {event_type}\ndata: {encoded}\n\n"
