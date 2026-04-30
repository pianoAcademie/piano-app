from __future__ import annotations

import logging

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


def consume_rate_limit(*, bucket: str, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    redis_key = f"ratelimit:{bucket}:{key}"
    try:
        client = _client()
        pipeline = client.pipeline()
        pipeline.incr(redis_key)
        pipeline.ttl(redis_key)
        count_raw, ttl_raw = pipeline.execute()

        count = int(count_raw or 0)
        ttl = int(ttl_raw or -1)
        if count <= 1 or ttl < 0:
            client.expire(redis_key, window_seconds)
            ttl = window_seconds

        return count <= limit, max(ttl, 1)
    except RedisError:
        logger.exception(
            "rate_limit_check_failed",
            extra={"bucket": bucket, "limit": limit, "window_seconds": window_seconds},
        )
        return True, 0
