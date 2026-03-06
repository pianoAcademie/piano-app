from __future__ import annotations

import logging
from contextlib import contextmanager
from uuid import uuid4

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import settings

logger = logging.getLogger(__name__)


def _client() -> Redis:
    return Redis.from_url(settings.redis_url, decode_responses=True)


@contextmanager
def redis_lock(lock_key: str, *, ttl_seconds: int = 300):
    token = str(uuid4())
    acquired = False
    try:
        acquired = bool(_client().set(lock_key, token, nx=True, ex=ttl_seconds))
    except RedisError:
        logger.exception("redis_lock_acquire_failed", extra={"lock_key": lock_key})
        acquired = False

    try:
        yield acquired
    finally:
        if not acquired:
            return
        try:
            current = _client().get(lock_key)
            if current == token:
                _client().delete(lock_key)
        except RedisError:
            logger.exception("redis_lock_release_failed", extra={"lock_key": lock_key})
