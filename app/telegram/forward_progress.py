from dataclasses import dataclass
from typing import Awaitable, Callable


@dataclass
class ProgressSnapshot:
    job_id: int
    total: int
    processed: int
    success: int
    skipped: int
    failed: int
    stopped: bool = False


ProgressCallback = Callable[[ProgressSnapshot], Awaitable[None]]
