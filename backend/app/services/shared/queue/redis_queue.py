from __future__ import annotations

import json
import logging
from typing import Any

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def queue_push(queue_name: str, payload: dict[str, Any]) -> bool:
    try:
        _client().rpush(queue_name, json.dumps(payload, separators=(",", ":"), ensure_ascii=True))
        return True
    except RedisError:
        logger.exception("queue_push_failed", extra={"queue_name": queue_name})
        return False


def queue_pop(queue_name: str, timeout_seconds: int = 2) -> dict[str, Any] | None:
    try:
        item = _client().blpop(queue_name, timeout=timeout_seconds)
    except RedisError:
        logger.exception("queue_pop_failed", extra={"queue_name": queue_name})
        return None
    if item is None:
        return None
    _, raw = item
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("queue_payload_invalid_json", extra={"queue_name": queue_name})
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def queue_len(queue_name: str) -> int:
    try:
        return int(_client().llen(queue_name))
    except RedisError:
        logger.exception("queue_len_failed", extra={"queue_name": queue_name})
        return 0
