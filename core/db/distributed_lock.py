"""
Wave 12: Multi-Worker Distributed Job Lease Lock.
Prevents duplicate execution of scheduled tasks (8:30 AM MF Ingest, 8:45 AM Discovery Reel,
9:00 AM Research Bouquet, and BSE Watcher loops) across multiple Uvicorn workers on Render.
"""
import logging
import os
import socket
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Iterator

from core.db.connection import get_connection, get_placeholder, is_postgres_connection, IST

logger = logging.getLogger(__name__)

WORKER_ID = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:6]}"


def ensure_lock_table_exists() -> None:
    """Ensures the distributed_job_locks table exists in both SQLite and PostgreSQL."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS distributed_job_locks (
                job_name TEXT PRIMARY KEY,
                locked_by TEXT NOT NULL,
                locked_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL
            )
            """
        )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error("Failed to initialize distributed_job_locks table: %s", e)
    finally:
        cur.close()
        try:
            conn.close()
        except Exception as close_err:
            logger.debug("Failed closing connection in ensure_lock_table_exists: %s", close_err)

DEFAULT_LEASE_TTL_SECONDS = 1800  # 30 minutes
MIN_LEASE_TTL_SECONDS = 10         # 10 seconds
MAX_LEASE_TTL_SECONDS = 86400      # 24 hours


def prune_zombie_leases(job_name: str = None) -> int:
    """
    Routinely purges expired/zombie job leases from distributed_job_locks where expires_at < NOW() (IST).
    Prevents dead worker processes (e.g. killed via SIGKILL) from permanently blocking scheduled pipelines.
    Returns the count of purged zombie leases.
    """
    ensure_lock_table_exists()
    conn = get_connection()
    is_pg = is_postgres_connection(conn)
    cur = conn.cursor()
    p = get_placeholder()
    now_ist = datetime.now(IST)
    now_iso = now_ist.isoformat()
    exp_cmp = f"expires_at < {p}" if is_pg else f"datetime(expires_at) < datetime({p})"
    try:
        if job_name:
            cur.execute(
                f"DELETE FROM distributed_job_locks WHERE job_name = {p} AND {exp_cmp}",
                (job_name, now_iso),
            )
        else:
            cur.execute(
                f"DELETE FROM distributed_job_locks WHERE {exp_cmp}",
                (now_iso,),
            )
        pruned = cur.rowcount or 0
        conn.commit()
        if pruned > 0:
            logger.info("Cleared %d zombie distributed lease(s) (expired before %s)", pruned, now_iso)
        return pruned
    except Exception as e:
        conn.rollback()
        logger.warning("Failed to clear zombie leases from distributed_job_locks: %s", e)
        return 0
    finally:
        cur.close()
        try:
            conn.close()
        except Exception as close_err:
            logger.debug("Failed closing connection in prune_zombie_leases: %s", close_err)


clear_zombie_leases = prune_zombie_leases


def acquire_job_lease(job_name: str, ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS) -> bool:
    """
    Atomically attempts to acquire a lease for `job_name`.
    Succeeds only if the lock does not exist or its `expires_at` timestamp has passed.
    Works identically on PostgreSQL (>=9.5) and SQLite (>=3.24) via ON CONFLICT.
    Enforces strict expires_at TTL and routinely clears zombie leases before acquisition.
    """
    ensure_lock_table_exists()

    # Routinely prune expired zombie leases for this job (e.g. killed worker processes)
    prune_zombie_leases(job_name=job_name)

    # Strictly enforce TTL boundaries
    if ttl_seconds is None:
        ttl_seconds = DEFAULT_LEASE_TTL_SECONDS
    try:
        ttl_val = int(ttl_seconds)
    except (ValueError, TypeError):
        ttl_val = DEFAULT_LEASE_TTL_SECONDS
    clamped_ttl = max(MIN_LEASE_TTL_SECONDS, min(ttl_val, MAX_LEASE_TTL_SECONDS))

    conn = get_connection()
    is_pg = is_postgres_connection(conn)
    cur = conn.cursor()
    p = get_placeholder()

    now_ist = datetime.now(IST)
    expires_ist = now_ist + timedelta(seconds=clamped_ttl)
    now_iso = now_ist.isoformat()
    exp_iso = expires_ist.isoformat()
    exp_cmp = f"distributed_job_locks.expires_at < {p}" if is_pg else f"datetime(distributed_job_locks.expires_at) < datetime({p})"

    sql = f"""
        INSERT INTO distributed_job_locks (job_name, locked_by, locked_at, expires_at)
        VALUES ({p}, {p}, {p}, {p})
        ON CONFLICT (job_name) DO UPDATE
        SET locked_by = EXCLUDED.locked_by,
            locked_at = EXCLUDED.locked_at,
            expires_at = EXCLUDED.expires_at
        WHERE {exp_cmp}
           OR distributed_job_locks.locked_by = {p}
    """
    try:
        cur.execute(sql, (job_name, WORKER_ID, now_iso, exp_iso, now_iso, WORKER_ID))
        acquired = (cur.rowcount or 0) > 0
        conn.commit()
        return acquired
    except Exception as e:
        conn.rollback()
        logger.warning("Lease acquisition failed for %s on worker %s: %s", job_name, WORKER_ID, e)
        return False
    finally:
        cur.close()
        try:
            conn.close()
        except Exception as close_err:
            logger.debug("Failed closing connection in acquire_job_lease: %s", close_err)


def release_job_lease(job_name: str, force: bool = True) -> None:
    """Releases a job lease. If force=True, clears the lock regardless of owner (ensuring idempotent cleanup)."""
    conn = get_connection()
    cur = conn.cursor()
    p = get_placeholder()
    try:
        if force:
            cur.execute(f"DELETE FROM distributed_job_locks WHERE job_name = {p}", (job_name,))
        else:
            cur.execute(
                f"DELETE FROM distributed_job_locks WHERE job_name = {p} AND locked_by = {p}",
                (job_name, WORKER_ID),
            )
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.warning("Failed to release lease %s: %s", job_name, e)
    finally:
        cur.close()
        try:
            conn.close()
        except Exception as close_err:
            logger.debug("Failed closing connection in release_job_lease: %s", close_err)


@contextmanager
def job_lease(
    job_name: str,
    ttl_seconds: int = 1800,
    release_on_exit: bool = False,
    release_on_failure: bool = True,
) -> Iterator[bool]:
    """
    Context manager for scheduled tasks.
    - For daily cron jobs, keep `release_on_exit=False` with a 20h TTL so secondary cloud
      workers do not re-run a completed daily job, while `release_on_failure=True` ensures
      mid-flight crashes immediately release the lock for automatic failover retry.
    - For recurring interval loops, set `release_on_exit=True`.
    """
    acquired = acquire_job_lease(job_name, ttl_seconds=ttl_seconds)
    failed = False
    try:
        yield acquired
    except Exception:
        failed = True
        raise
    finally:
        if acquired and (release_on_exit or (failed and release_on_failure)):
            release_job_lease(job_name)

