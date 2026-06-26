import time
from dataclasses import dataclass, field

MAX_QUEUE_PER_USER = 2
_JOB_TTL = 3600  # seconds; jobs older than this are silently dropped

@dataclass
class GenerationJob:
    job_id: str
    user_id: int
    status: str = "pending"   # pending | running | done | failed
    count: int = 0
    error: str | None = None
    created_at: float = field(default_factory=time.monotonic)

_jobs: dict[str, GenerationJob] = {}


def _cleanup() -> None:
    cutoff = time.monotonic() - _JOB_TTL
    stale = [jid for jid, j in _jobs.items() if j.created_at < cutoff]
    for jid in stale:
        del _jobs[jid]


def create_job(job_id: str, user_id: int) -> GenerationJob:
    _cleanup()
    job = GenerationJob(job_id=job_id, user_id=user_id)
    _jobs[job_id] = job
    return job


def count_active(user_id: int) -> int:
    return sum(
        1 for j in _jobs.values()
        if j.user_id == user_id and j.status in ("pending", "running")
    )


def get_job(job_id: str) -> GenerationJob | None:
    return _jobs.get(job_id)


def mark_running(job_id: str) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "running"


def complete_job(job_id: str, count: int) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "done"
        _jobs[job_id].count = count


def fail_job(job_id: str, error: str) -> None:
    if job_id in _jobs:
        _jobs[job_id].status = "failed"
        _jobs[job_id].error = error
