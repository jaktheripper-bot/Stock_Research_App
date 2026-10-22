"""
Job Lease Lock Alias Module.
Provides backwards and alternate import compatibility for core.db.distributed_lock.
"""
from core.db.distributed_lock import (
    WORKER_ID,
    ensure_lock_table_exists,
    acquire_job_lease,
    release_job_lease,
    job_lease,
    prune_zombie_leases,
    clear_zombie_leases,
)

__all__ = [
    "WORKER_ID",
    "ensure_lock_table_exists",
    "acquire_job_lease",
    "release_job_lease",
    "job_lease",
    "prune_zombie_leases",
    "clear_zombie_leases",
]
