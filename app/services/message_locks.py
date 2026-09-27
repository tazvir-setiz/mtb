import asyncio
from contextlib import asynccontextmanager

_locks = {}


@asynccontextmanager
async def message_lock(source_id, message_id, destination_id):
    key = (source_id, message_id, destination_id)
    entry = _locks.setdefault(key, [asyncio.Lock(), 0])
    entry[1] += 1
    try:
        async with entry[0]:
            yield
    finally:
        entry[1] -= 1
        if not entry[1]:
            _locks.pop(key, None)
