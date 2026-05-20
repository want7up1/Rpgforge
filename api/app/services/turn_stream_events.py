import asyncio
import json
import logging
from contextlib import suppress
from datetime import UTC, datetime
from time import monotonic
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder
from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError

from app.config import settings

TurnStreamEvent = dict[str, Any]
RedisStreamEvent = tuple[str, TurnStreamEvent]

logger = logging.getLogger(__name__)
STREAM_MAXLEN = 512
STREAM_TTL_SECONDS = 24 * 60 * 60
REDIS_RETRY_DELAY_SECONDS = 5.0
REDIS_SOCKET_TIMEOUT_SECONDS = 0.5


class TurnStreamEventBroker:
    def __init__(self, namespace: str = "turn") -> None:
        self.namespace = namespace
        self._subscribers: dict[UUID, set[asyncio.Queue[TurnStreamEvent]]] = {}
        self._latest: dict[UUID, TurnStreamEvent] = {}
        self._redis: Redis | None = None
        self._redis_disabled_until = 0.0

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
        return self._latest.get(job_id) or self.latest_stream_event(job_id)

    def latest_stream_entry(self, job_id: UUID) -> RedisStreamEvent | None:
        client = self._redis_client()
        if client is None:
            return None
        try:
            entries = client.xrevrange(self._stream_key(job_id), count=1)
        except RedisError as exc:
            self._disable_redis(exc)
            return None
        if not entries:
            return None
        event = self._decode_stream_fields(entries[0][1])
        if event is None:
            return None
        return str(entries[0][0]), event

    def latest_stream_id(self, job_id: UUID) -> str | None:
        entry = self.latest_stream_entry(job_id)
        return entry[0] if entry is not None else None

    def latest_stream_event(self, job_id: UUID) -> TurnStreamEvent | None:
        entry = self.latest_stream_entry(job_id)
        return entry[1] if entry is not None else None

    async def read_stream_event(
        self,
        job_id: UUID,
        last_id: str,
        *,
        timeout_seconds: float,
    ) -> RedisStreamEvent | None:
        if monotonic() < self._redis_disabled_until:
            await asyncio.sleep(timeout_seconds)
            return None

        client = self._async_redis_client(timeout_seconds)
        try:
            streams = await client.xread(
                {self._stream_key(job_id): last_id},
                count=1,
                block=max(1, int(timeout_seconds * 1000)),
            )
        except RedisError as exc:
            self._disable_redis(exc)
            await asyncio.sleep(timeout_seconds)
            return None
        finally:
            with suppress(Exception):
                await client.aclose()

        if not streams:
            return None
        _stream_name, entries = streams[0]
        if not entries:
            return None
        event_id, fields = entries[0]
        event = self._decode_stream_fields(fields)
        if event is None:
            return None
        return str(event_id), event

    def publish(self, job_id: UUID, event: TurnStreamEvent) -> None:
        enriched_event = {
            "job_id": str(job_id),
            "sent_at": datetime.now(UTC).isoformat(),
            **event,
        }
        self._latest[job_id] = enriched_event
        self._publish_to_redis(job_id, enriched_event)

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

    def _publish_to_redis(self, job_id: UUID, event: TurnStreamEvent) -> None:
        client = self._redis_client()
        if client is None:
            return
        stream_key = self._stream_key(job_id)
        try:
            client.xadd(
                stream_key,
                {"payload": json.dumps(jsonable_encoder(event), ensure_ascii=False)},
                maxlen=STREAM_MAXLEN,
                approximate=True,
            )
            client.expire(stream_key, STREAM_TTL_SECONDS)
        except RedisError as exc:
            self._disable_redis(exc)

    def _redis_client(self) -> Redis | None:
        if monotonic() < self._redis_disabled_until:
            return None
        if self._redis is None:
            try:
                self._redis = Redis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
                    socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
                )
            except RedisError as exc:
                self._disable_redis(exc)
                return None
        return self._redis

    def _async_redis_client(self, timeout_seconds: float) -> AsyncRedis:
        return AsyncRedis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            socket_timeout=max(REDIS_SOCKET_TIMEOUT_SECONDS, timeout_seconds + 0.5),
        )

    def _disable_redis(self, exc: RedisError) -> None:
        self._redis_disabled_until = monotonic() + REDIS_RETRY_DELAY_SECONDS
        if self._redis is not None:
            with suppress(Exception):
                self._redis.close()
            self._redis = None
        logger.warning("Redis stream broker unavailable for %s events: %s", self.namespace, exc)

    def _stream_key(self, job_id: UUID) -> str:
        return f"rpgforge:stream-events:{self.namespace}:{job_id}"

    @staticmethod
    def _decode_stream_fields(fields: dict[str, Any]) -> TurnStreamEvent | None:
        payload = fields.get("payload")
        if not isinstance(payload, str):
            return None
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None


turn_stream_event_broker = TurnStreamEventBroker(namespace="turn")


def format_sse_event(event_type: str, payload: TurnStreamEvent) -> str:
    encoded = json.dumps(jsonable_encoder(payload), ensure_ascii=False)
    return f"event: {event_type}\ndata: {encoded}\n\n"
