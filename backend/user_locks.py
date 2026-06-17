"""In-process async locks keyed by user id."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")

_LOCKS: dict[str, asyncio.Lock] = {}
_LOCKS_GUARD = asyncio.Lock()


async def get_user_lock(user_id: str) -> asyncio.Lock:
    async with _LOCKS_GUARD:
        lock = _LOCKS.get(user_id)
        if lock is None:
            lock = asyncio.Lock()
            _LOCKS[user_id] = lock
        return lock


async def run_with_user_lock(user_id: str, operation: Callable[[], T | Awaitable[T]]) -> T:
    lock = await get_user_lock(user_id)
    async with lock:
        result = operation()
        if asyncio.iscoroutine(result) or isinstance(result, Awaitable):
            return await result
        return result


__all__ = ["get_user_lock", "run_with_user_lock"]
