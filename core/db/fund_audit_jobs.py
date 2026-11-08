"""Durable paid Mutual Fund audit queue, worker lease/SLA separation, and item-level credit settlement."""

from contextlib import contextmanager
import hashlib
import json
import logging
import os
from time import time
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import uuid4

from core.analysis.financial_invariants import is_synthesizable_domestic_ticker
from core.analysis.fund_research_evidence import MAX_SYNTHESIZABLE_CONSTITUENTS_PER_SLA
from core.db.connection import (
    AuthoritativeDatabaseUnavailable,
    get_configured_supabase_url,
    get_db_connection,
    is_postgres_connection,
    now_ist_iso,
)

logger = logging.getLogger(__name__)

QUEUE_TIMEOUT = 300
WORKER_LEASE = 120
CLAIM_LEASE_SECONDS = WORKER_LEASE
CUSTOMER_DELIVERY_SLA_SECONDS = 900
WORKER_HEARTBEAT_MAX_AGE = 30
DELIVERY_POLICY_VERSION = "fund-audit-sla-v2"


class FundAuditError(Exception):
    """Base error for durable paid fund audit workflows."""


class FundAuditUnavailable(FundAuditError):
    """Raised when authoritative PostgreSQL or the paid audit worker is unavailable."""


class FundAuditConflict(FundAuditError):
    """Raised on duplicate active scheme audits, stale disclosures, or mismatched request revisions."""


class FundAuditInsufficientCredits(FundAuditError):
    """Raised when the user's research credit balance cannot cover the requested audit."""


class FundAuditUnprocessable(FundAuditError):
    """Raised when a deep-dive request exceeds single-job SLA bounds or includes ineligible constituents."""


@contextmanager
def _transaction(write: bool = False):
    try:
        conn = get_db_connection()
    except AuthoritativeDatabaseUnavailable as exc:
        raise FundAuditUnavailable("The billing database is temporarily unavailable.") from exc
    cursor = conn.cursor()
    postgres = is_postgres_connection(conn)
    try:
        hosted = bool(os.environ.get("RENDER") or os.environ.get("RENDER_SERVICE_ID"))
        if not postgres and (hosted or get_configured_supabase_url()):
            raise FundAuditUnavailable("The billing database is temporarily unavailable.")
        if write and not postgres:
            cursor.execute("BEGIN IMMEDIATE")
        yield conn, cursor, "%s" if postgres else "?", postgres
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


def _job(cursor) -> Optional[Dict[str, Any]]:
    row = cursor.fetchone()
    return dict(zip((column[0] for column in cursor.description), row)) if row else None


def _lock_account(cur, p: str, user_id: str, postgres: bool):
    lock = " FOR UPDATE" if postgres else ""
    cur.execute(f"SELECT id FROM user_accounts WHERE id={p}{lock}", (user_id,))
    return cur.fetchone()


def record_worker_heartbeat(job: Optional[Dict[str, Any]] = None, *, worker_id: Optional[str] = None) -> None:
    """Refresh worker availability without extending an owned claim's lease or customer SLA."""
    with _transaction(write=True) as (_, cur, p, _):
        now = int(time())
        source = f"SELECT 'paid', {p} WHERE 1=1"
        params: Tuple[Any, ...] = (now,)
        if job is not None:
            source += f""" AND EXISTS (
                SELECT 1 FROM fund_audit_jobs
                WHERE job_id={p} AND status='PROCESSING' AND worker_token={p}
                AND deadline > {p} AND job_deadline_at > {p}
            )"""
            params += (job["job_id"], job["worker_token"], now, now)
        cur.execute(
            f"""INSERT INTO fund_audit_worker_health (worker_type, touched_at)
                {source}
                ON CONFLICT (worker_type) DO UPDATE SET touched_at=EXCLUDED.touched_at""",
            params,
        )
        if worker_id and cur.rowcount:
            cur.execute(
                f"""INSERT INTO fund_audit_worker_instances
                    (worker_id, worker_type, touched_at, active_claims)
                    VALUES ({p}, 'paid', {p}, {p})
                    ON CONFLICT (worker_id) DO UPDATE SET
                        touched_at=EXCLUDED.touched_at,
                        active_claims=EXCLUDED.active_claims""",
                (worker_id, now, 1 if job is not None else 0),
            )


def quote_revision(
    user_id: str,
    snapshot_id: str,
    allow_deep_dive: bool,
    layer1: int,
    tickers: Iterable[str],
) -> str:
    payload = json.dumps([user_id, snapshot_id, bool(allow_deep_dive), int(layer1), sorted(set(tickers))])
    return hashlib.sha256(payload.encode()).hexdigest()


def _record_settlement_operation(
    cur,
    p: str,
    *,
    user_id: str,
    operation_type: str,
    credits_delta: float,
    balance_after: float,
    idempotency_key: str,
    job_id: Optional[str] = None,
    line_key: Optional[str] = None,
    reason_code: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    cur.execute(
        f"""INSERT INTO credit_settlement_operations (
                operation_id, user_id, operation_type, credits_delta, balance_after,
                idempotency_key, job_id, line_key, reason_code, metadata_json, created_at
            ) VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT (idempotency_key) DO NOTHING""",
        (
            f"cso-{uuid4().hex}",
            user_id,
            operation_type,
            float(credits_delta),
            float(balance_after),
            idempotency_key,
            job_id,
            line_key,
            reason_code,
            json.dumps(metadata or {}, default=str),
            int(time()),
        ),
    )


def _adjust_credits(
    cur,
    p: str,
    user_id: str,
    ticker: str,
    amount: int,
    action: str,
    postgres: bool,
    *,
    operation_type: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    job_id: Optional[str] = None,
    line_key: Optional[str] = None,
    reason_code: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> float:
    balance_expr = f"credits_balance - {p}"
    if postgres:
        balance_expr = f"({balance_expr})::numeric"
    cur.execute(
        f"""UPDATE user_accounts
            SET credits_balance=ROUND({balance_expr}, 2), updated_at={p}
            WHERE id={p} AND credits_balance >= {p} RETURNING credits_balance""",
        (amount, now_ist_iso(), user_id, max(amount, 0)),
    )
    row = cur.fetchone()
    if not row:
        raise FundAuditInsufficientCredits("Insufficient research credits.")
    new_balance = float(row[0])
    cur.execute(
        f"""INSERT INTO credit_usage_ledger
            (user_id, ticker, action_type, credits_consumed, balance_after)
            VALUES ({p}, {p}, {p}, {p}, {p})""",
        (user_id, ticker, action, amount, new_balance),
    )
    if operation_type and idempotency_key:
        _record_settlement_operation(
            cur,
            p,
            user_id=user_id,
            operation_type=operation_type,
            credits_delta=-float(amount),
            balance_after=new_balance,
            idempotency_key=idempotency_key,
            job_id=job_id,
            line_key=line_key,
            reason_code=reason_code,
            metadata=metadata,
        )
    return new_balance


def _grant(cur, p: str, user_id: str, ticker: str) -> bool:
    cur.execute(
        f"""INSERT INTO user_unlocked_dossiers (user_id, ticker) VALUES ({p}, {p})
            ON CONFLICT (user_id, ticker) DO NOTHING RETURNING ticker""",
        (user_id, ticker),
    )
    return cur.fetchone() is not None


def unlock_published_fund_dossier(user_id: str, scheme_code: str, *, allow_charge: bool = True) -> float:
    """Serialize direct fund unlocks with paid audit settlement."""
    from core.db.mutual_funds import get_current_fund_disclosure

    fund_key = f"FUND:{scheme_code}"
    with _transaction(write=True) as (conn, cur, p, postgres):
        if not _lock_account(cur, p, user_id, postgres):
            raise FundAuditInsufficientCredits("Research credit account is unavailable.")
        cur.execute(f"SELECT credits_balance FROM user_accounts WHERE id={p}", (user_id,))
        balance = float(cur.fetchone()[0])
        cur.execute(
            f"SELECT 1 FROM user_unlocked_dossiers WHERE user_id={p} AND ticker={p}",
            (user_id, fund_key),
        )
        if cur.fetchone():
            return balance
        if not allow_charge:
            raise FundAuditUnavailable("New fund purchases are paused.")
        cur.execute(
            f"""SELECT 1 FROM fund_audit_jobs
                WHERE user_id={p} AND scheme_code={p} AND status IN ('QUEUED', 'PROCESSING')""",
            (user_id, scheme_code),
        )
        if cur.fetchone():
            raise FundAuditConflict("An audit for this fund is pending. Reconnect to that request.")
        lock = " FOR UPDATE" if postgres else ""
        cur.execute(f"SELECT scheme_code FROM mutual_fund_schemes WHERE scheme_code={p}{lock}", (scheme_code,))
        if not cur.fetchone():
            raise FundAuditConflict("A current fund dossier is unavailable.")
        snapshot = get_current_fund_disclosure(scheme_code, connection=conn)
        cur.execute(
            f"SELECT dossier_text, evidence_receipt_json FROM fund_forensic_dossiers WHERE scheme_code={p}",
            (scheme_code,),
        )
        row = cur.fetchone()
        try:
            receipt = json.loads(row[1]) if row and row[1] else {}
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid evidence_receipt_json on fund_forensic_dossiers for %s: %s", scheme_code, exc)
            receipt = {}
        if (
            not snapshot
            or not row
            or not str(row[0] or "").strip()
            or not isinstance(receipt, dict)
            or receipt.get("snapshot_id") != snapshot["snapshot_id"]
        ):
            raise FundAuditConflict("A current fund dossier is unavailable. Request a look-through audit.")
        if _grant(cur, p, user_id, fund_key):
            return _adjust_credits(
                cur,
                p,
                user_id,
                fund_key,
                1,
                "DEEP_DIVE_UNLOCK",
                postgres,
                operation_type="DIRECT_UNLOCK",
                idempotency_key=f"direct-unlock:{user_id}:{fund_key}",
                line_key=f"L1:{fund_key}",
                reason_code="PUBLISHED_DOSSIER_UNLOCK",
                metadata={"scheme_code": scheme_code, "snapshot_id": snapshot["snapshot_id"]},
            )
        return balance


def _check_request(
    job: Dict[str, Any], scheme_code: str, allow_deep_dive: bool, accepted_revision: str,
) -> None:
    if (
        job["scheme_code"] != scheme_code
        or bool(job["deep_dive"]) != bool(allow_deep_dive)
        or job["quote_revision"] != accepted_revision
    ):
        raise FundAuditConflict("This request key was used for a different audit.")


def get_existing_fund_audit_request(
    user_id: str, request_id: str, scheme_code: str, allow_deep_dive: bool, accepted_revision: str,
) -> Optional[Dict[str, Any]]:
    with _transaction() as (_, cur, p, _):
        cur.execute(
            f"SELECT * FROM fund_audit_jobs WHERE user_id={p} AND request_id={p}",
            (user_id, request_id),
        )
        existing = _job(cur)
        if existing:
            _check_request(existing, scheme_code, allow_deep_dive, accepted_revision)
        return existing


def enqueue_fund_audit(
    user_id: str,
    request_id: str,
    scheme: Dict[str, Any],
    snapshot_id: str,
    allow_deep_dive: bool,
    tickers: Iterable[str],
    accepted_revision: str,
) -> Dict[str, Any]:
    from core.db.mutual_funds import get_current_fund_disclosure

    scheme_code = scheme["scheme_code"]
    fund_key = f"FUND:{scheme_code}"
    unique_tickers = sorted({str(t).strip().upper() for t in tickers if str(t).strip()})
    with _transaction(write=True) as (conn, cur, p, postgres):
        lock = " FOR UPDATE" if postgres else ""
        if not _lock_account(cur, p, user_id, postgres):
            raise FundAuditInsufficientCredits("Research credit account is unavailable.")

        cur.execute(
            f"SELECT * FROM fund_audit_jobs WHERE user_id={p} AND request_id={p}",
            (user_id, request_id),
        )
        existing = _job(cur)
        if existing:
            _check_request(existing, scheme_code, allow_deep_dive, accepted_revision)
            return existing

        now = int(time())
        cur.execute(
            f"SELECT 1 FROM fund_audit_worker_health WHERE worker_type='paid' AND touched_at > {p}",
            (now - WORKER_HEARTBEAT_MAX_AGE,),
        )
        if not cur.fetchone():
            raise FundAuditUnavailable("The paid audit worker is unavailable. No credits charged.")

        cur.execute(
            f"""SELECT job_id FROM fund_audit_jobs
                WHERE user_id={p} AND scheme_code={p} AND status IN ('QUEUED', 'PROCESSING')""",
            (user_id, scheme_code),
        )
        if cur.fetchone():
            raise FundAuditConflict("An audit for this scheme is already pending. Resume the original request.")

        cur.execute(f"SELECT scheme_code FROM mutual_fund_schemes WHERE scheme_code={p}{lock}", (scheme_code,))
        if not cur.fetchone():
            raise FundAuditConflict("This scheme is no longer available.")
        current = get_current_fund_disclosure(scheme_code, connection=conn)
        if not current or current["snapshot_id"] != snapshot_id:
            raise FundAuditConflict("A new portfolio disclosure is available. Review the updated quote.")

        if allow_deep_dive:
            if len(unique_tickers) > MAX_SYNTHESIZABLE_CONSTITUENTS_PER_SLA:
                raise FundAuditUnprocessable(
                    f"Deep-dive constituent synthesis is capped at {MAX_SYNTHESIZABLE_CONSTITUENTS_PER_SLA} "
                    f"stocks per single-job SLA ({len(unique_tickers)} requested). Run the Layer-1 "
                    f"look-through audit first; remaining domestic constituents queue via daily rollout."
                )
            foreign_in_snapshot = {
                str(h.get("identifier") or "").strip().upper()
                for h in (current.get("holdings") or [])
                if str(h.get("holding_type") or "").strip().upper() == "FOREIGN_EQUITY"
            }
            for ticker in unique_tickers:
                if ticker in foreign_in_snapshot or not is_synthesizable_domestic_ticker(ticker, "EQUITY"):
                    raise FundAuditUnprocessable(
                        f"Constituent '{ticker}' is a foreign or unresolved ISIN holding and cannot be billed "
                        "for domestic NSE/BSE equity synthesis."
                    )

        cur.execute(
            f"SELECT 1 FROM user_unlocked_dossiers WHERE user_id={p} AND ticker={p}",
            (user_id, fund_key),
        )
        layer1 = int(cur.fetchone() is None)
        line_items: List[Tuple[int, str]] = [(2, ticker) for ticker in unique_tickers] if allow_deep_dive else []
        if layer1:
            line_items.insert(0, (1, fund_key))

        if quote_revision(user_id, snapshot_id, allow_deep_dive, layer1, unique_tickers) != accepted_revision:
            raise FundAuditConflict("The credit quote changed. Review the updated quote before retrying.")

        job_id = f"paid-{uuid4().hex}"
        cost = len(line_items)
        if cost:
            _adjust_credits(
                cur,
                p,
                user_id,
                fund_key,
                cost,
                "FUND_AUDIT_RESERVE",
                postgres,
                operation_type="AUDIT_RESERVE",
                idempotency_key=f"audit-reserve:{job_id}",
                job_id=job_id,
                reason_code="FUND_AUDIT_ENQUEUE",
                metadata={
                    "scheme_code": scheme_code,
                    "snapshot_id": snapshot_id,
                    "allow_deep_dive": bool(allow_deep_dive),
                    "line_count": cost,
                },
            )
        queue_expires_at = now + QUEUE_TIMEOUT
        job_deadline_at = now + CUSTOMER_DELIVERY_SLA_SECONDS
        cur.execute(
            f"""INSERT INTO fund_audit_jobs (
                    job_id, user_id, request_id, quote_revision, scheme_code, snapshot_id, scheme_json,
                    deep_dive, credits_charged, status, deadline, queue_expires_at, job_deadline_at,
                    delivery_policy_version, created_at
                ) VALUES (
                    {p}, {p}, {p}, {p}, {p}, {p}, {p},
                    {p}, {p}, 'QUEUED', {p}, {p}, {p},
                    {p}, {p}
                )""",
            (
                job_id,
                user_id,
                request_id,
                accepted_revision,
                scheme_code,
                snapshot_id,
                json.dumps(scheme, default=str),
                int(bool(allow_deep_dive)),
                cost,
                queue_expires_at,
                queue_expires_at,
                job_deadline_at,
                DELIVERY_POLICY_VERSION,
                now,
            ),
        )
        if line_items:
            cur.executemany(
                f"INSERT INTO fund_audit_items (job_id, ticker, layer, status) VALUES ({p}, {p}, {p}, 'PENDING')",
                [(job_id, ticker, layer) for layer, ticker in line_items],
            )
        cur.execute(f"SELECT * FROM fund_audit_jobs WHERE job_id={p}", (job_id,))
        created = _job(cur)
        assert created is not None
        return created


def _refund_pending(cur, p: str, job: Dict[str, Any], postgres: bool, *, reason_code: str = "UNDELIVERED_LINE") -> None:
    now = int(time())
    cur.execute(
        f"""UPDATE fund_audit_items SET status='REFUNDED', settled_at={p}
            WHERE job_id={p} AND status='PENDING' RETURNING ticker, layer""",
        (now, job["job_id"]),
    )
    items = cur.fetchall()
    for ticker, layer in sorted(items):
        line_key = f"L{layer}:{ticker}"
        _adjust_credits(
            cur,
            p,
            job["user_id"],
            ticker,
            -1,
            f"FUND_AUDIT_REFUND_L{layer}",
            postgres,
            operation_type="AUDIT_REFUND",
            idempotency_key=f"audit-refund:{job['job_id']}:{line_key}",
            job_id=job["job_id"],
            line_key=line_key,
            reason_code=reason_code,
            metadata={"scheme_code": job["scheme_code"], "layer": layer, "ticker": ticker},
        )


def _finish_failed(
    cur, p: str, job: Dict[str, Any], message: str, postgres: bool, *, reason_code: str = "AUDIT_FAILED",
) -> None:
    _refund_pending(cur, p, job, postgres, reason_code=reason_code)
    cur.execute(
        f"""UPDATE fund_audit_jobs
            SET status='FAILED', error_message={p}, worker_token=NULL, settled_at={p}
            WHERE job_id={p}""",
        (message, int(time()), job["job_id"]),
    )


def _expire_fund_audit(user_id: str, job_id: str) -> bool:
    with _transaction(write=True) as (_, cur, p, postgres):
        _lock_account(cur, p, user_id, postgres)
        lock = " FOR UPDATE" if postgres else ""
        now = int(time())
        cur.execute(
            f"""SELECT * FROM fund_audit_jobs WHERE job_id={p} AND user_id={p}
                AND status IN ('QUEUED', 'PROCESSING')
                AND (deadline <= {p} OR job_deadline_at <= {p}){lock}""",
            (job_id, user_id, now, now),
        )
        expired = _job(cur)
        if not expired:
            return False
        _finish_failed(
            cur,
            p,
            expired,
            "The audit timed out. Undelivered credits were refunded.",
            postgres,
            reason_code="SLA_OR_LEASE_EXPIRED",
        )
        return True


def reconcile_expired_fund_audits(*, limit: int = 50) -> int:
    """Settle expired jobs independently of the synthesis worker."""
    with _transaction() as (_, cur, p, _):
        now = int(time())
        cur.execute(
            f"""SELECT user_id, job_id FROM fund_audit_jobs
                WHERE status IN ('QUEUED', 'PROCESSING')
                AND (deadline <= {p} OR job_deadline_at <= {p})
                ORDER BY deadline, job_id LIMIT {p}""",
            (now, now, limit),
        )
        candidates = cur.fetchall()
    return sum(_expire_fund_audit(user_id, job_id) for user_id, job_id in candidates)


def claim_fund_audit(*, worker_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    record_worker_heartbeat(worker_id=worker_id)
    reconcile_expired_fund_audits(limit=1)
    with _transaction(write=True) as (_, cur, p, postgres):
        now = int(time())
        lock = " FOR UPDATE SKIP LOCKED" if postgres else ""
        cur.execute(
            f"""SELECT * FROM fund_audit_jobs
                WHERE status='QUEUED' AND deadline > {p} AND job_deadline_at > {p}
                ORDER BY created_at, job_id LIMIT {p}{lock}""",
            (now, now, 1),
        )
        job = _job(cur)
        if not job:
            return None
        token = uuid4().hex
        lease_until = min(now + WORKER_LEASE, int(job["job_deadline_at"]))
        cur.execute(
            f"""UPDATE fund_audit_jobs
                SET status='PROCESSING', worker_token={p}, claim_lease_expires_at={p}, deadline={p}
                WHERE job_id={p}""",
            (token, lease_until, lease_until, job["job_id"]),
        )
        cur.execute(
            f"SELECT ticker FROM fund_audit_items WHERE job_id={p} AND layer=2 ORDER BY ticker",
            (job["job_id"],),
        )
        return {
            **job,
            "status": "PROCESSING",
            "worker_token": token,
            "claim_lease_expires_at": lease_until,
            "deadline": lease_until,
            "tickers": [row[0] for row in cur.fetchall()],
        }


def _lock_owned_claim(cur, p: str, job: Dict[str, Any], postgres: bool) -> Optional[Dict[str, Any]]:
    lock = " FOR UPDATE" if postgres else ""
    now = int(time())
    cur.execute(
        f"""SELECT * FROM fund_audit_jobs WHERE job_id={p} AND status='PROCESSING'
            AND worker_token={p} AND deadline > {p} AND job_deadline_at > {p}{lock}""",
        (job["job_id"], job["worker_token"], now, now),
    )
    current = _job(cur)
    if current and (current["deadline"] <= now or current["job_deadline_at"] <= now):
        return None
    return current


def renew_fund_audit(job: Dict[str, Any]) -> bool:
    """Renew worker claim lease between synthesis steps without ever exceeding customer SLA."""
    with _transaction(write=True) as (_, cur, p, postgres):
        current = _lock_owned_claim(cur, p, job, postgres)
        if not current:
            return False
        now = int(time())
        lease_until = min(now + WORKER_LEASE, int(current["job_deadline_at"]))
        if lease_until <= now:
            return False
        cur.execute(
            f"UPDATE fund_audit_jobs SET claim_lease_expires_at={p}, deadline={p} WHERE job_id={p}",
            (lease_until, lease_until, job["job_id"]),
        )
        return True


def record_fund_constituent_delivery(job: Dict[str, Any], ticker: str, report_revision: str) -> bool:
    with _transaction(write=True) as (_, cur, p, postgres):
        _lock_account(cur, p, job["user_id"], postgres)
        if not _lock_owned_claim(cur, p, job, postgres):
            return False
        lock = " FOR SHARE" if postgres else ""
        cur.execute(f"SELECT report_text FROM reports WHERE ticker={p}{lock}", (ticker,))
        report = cur.fetchone()
        if not report or hashlib.sha256(str(report[0]).encode()).hexdigest() != report_revision:
            return True  # Keeps item PENDING so undelivered synthesis is refunded at settlement.
        cur.execute(
            f"""SELECT 1 FROM fund_audit_items
                WHERE job_id={p} AND layer=2 AND ticker={p} AND status='PENDING'""",
            (job["job_id"], ticker),
        )
        if cur.fetchone() and _grant(cur, p, job["user_id"], ticker):
            cur.execute(
                f"""UPDATE fund_audit_items
                    SET status='DELIVERED', report_revision={p}, settled_at={p}
                    WHERE job_id={p} AND layer=2 AND ticker={p} AND status='PENDING'""",
                (report_revision, int(time()), job["job_id"], ticker),
            )
        return True


def fail_fund_audit(job: Dict[str, Any], message: str) -> None:
    with _transaction(write=True) as (_, cur, p, postgres):
        _lock_account(cur, p, job["user_id"], postgres)
        if current := _lock_owned_claim(cur, p, job, postgres):
            _finish_failed(cur, p, current, message, postgres, reason_code="WORKER_REPORTED_FAILURE")


def complete_fund_audit(job: Dict[str, Any], dossier: Dict[str, Any]) -> bool:
    from core.db.mutual_funds import get_current_fund_disclosure, save_fund_forensic_dossier

    with _transaction(write=True) as (conn, cur, p, postgres):
        _lock_account(cur, p, job["user_id"], postgres)
        current = _lock_owned_claim(cur, p, job, postgres)
        if not current:
            return False
        lock = " FOR UPDATE" if postgres else ""
        cur.execute(
            f"SELECT scheme_code FROM mutual_fund_schemes WHERE scheme_code={p}{lock}",
            (job["scheme_code"],),
        )
        if not cur.fetchone():
            raise FundAuditConflict("The scheme is no longer available.")
        snapshot = get_current_fund_disclosure(job["scheme_code"], connection=conn)
        if not snapshot or snapshot["snapshot_id"] != job["snapshot_id"]:
            _finish_failed(
                cur,
                p,
                current,
                "A newer portfolio arrived. Undelivered credits were refunded. Review a new quote.",
                postgres,
                reason_code="SNAPSHOT_SUPERSEDED",
            )
            return False
        receipt = dossier.get("evidence_receipt") or {}
        if (
            dossier.get("scheme_code") != job["scheme_code"]
            or receipt.get("snapshot_id") != job["snapshot_id"]
            or not str(dossier.get("dossier_text") or "").strip()
        ):
            raise FundAuditConflict("A complete dossier could not be produced.")
        if not save_fund_forensic_dossier(dossier, connection=conn):
            raise FundAuditConflict("The dossier could not be saved.")
        cur.execute(
            f"SELECT dossier_text FROM fund_forensic_dossiers WHERE scheme_code={p}",
            (job["scheme_code"],),
        )
        saved_dossier = {**dossier, "dossier_text": cur.fetchone()[0]}
        fund_key = f"FUND:{job['scheme_code']}"
        now = int(time())
        cur.execute(
            f"SELECT 1 FROM fund_audit_items WHERE job_id={p} AND layer=1 AND status='PENDING'",
            (job["job_id"],),
        )
        if cur.fetchone() and _grant(cur, p, job["user_id"], fund_key):
            cur.execute(
                f"""UPDATE fund_audit_items
                    SET status='DELIVERED', report_revision={p}, settled_at={p}
                    WHERE job_id={p} AND layer=1 AND status='PENDING'""",
                (job["job_id"], now, job["job_id"]),
            )
        _refund_pending(cur, p, current, postgres, reason_code="PARTIAL_COMPLETION_REFUND")
        cur.execute(
            f"""UPDATE fund_audit_jobs
                SET status='COMPLETED', dossier_json={p}, worker_token=NULL, settled_at={p}
                WHERE job_id={p}""",
            (json.dumps(saved_dossier, default=str), now, job["job_id"]),
        )
        return True


def get_fund_audit_status_for_owner(
    job_id: str, user_id: str, *, include_dossier: bool = False,
) -> Optional[Dict[str, Any]]:
    status, expired = _read_fund_audit_status(job_id, user_id, include_dossier=include_dossier)
    if expired:
        _expire_fund_audit(user_id, job_id)
        status, _ = _read_fund_audit_status(job_id, user_id, include_dossier=include_dossier)
    return status


def _read_fund_audit_status(
    job_id: str, user_id: str, *, include_dossier: bool,
) -> Tuple[Optional[Dict[str, Any]], bool]:
    with _transaction() as (_, cur, p, _):
        cur.execute(
            f"SELECT * FROM fund_audit_jobs WHERE job_id={p} AND user_id={p}",
            (job_id, user_id),
        )
        job = _job(cur)
        if not job:
            return None, False
        now = int(time())
        if job["status"] in ("QUEUED", "PROCESSING") and (
            job["deadline"] <= now or job["job_deadline_at"] <= now
        ):
            return None, True
        cur.execute(
            f"""SELECT layer, ticker, status, report_revision FROM fund_audit_items
                WHERE job_id={p} ORDER BY layer, ticker""",
            (job_id,),
        )
        items = [
            dict(layer=layer, ticker=ticker, status=item_status, report_revision=revision)
            for layer, ticker, item_status, revision in cur.fetchall()
        ]
        status = job["status"]
        refunded = sum(item["status"] == "REFUNDED" for item in items)
        pending = sum(item["status"] == "PENDING" for item in items)
        progress = 100 if status == "COMPLETED" else 8
        if status == "PROCESSING" and items:
            progress += int(80 * (len(items) - pending) / len(items))
        active = status in ("QUEUED", "PROCESSING")
        return {
            "task_id": job_id,
            "scheme_code": job["scheme_code"],
            "snapshot_id": job["snapshot_id"],
            "allow_deep_dive": bool(job["deep_dive"]),
            "status": status,
            "deadline_unix": job["deadline"] if active else None,
            "customer_sla_unix": job["job_deadline_at"] if active else None,
            "delivery_policy_version": job.get("delivery_policy_version") or DELIVERY_POLICY_VERSION,
            "progress_pct": progress,
            "error": job["error_message"],
            "message": job["error_message"] or {
                "QUEUED": "Queued for research.",
                "PROCESSING": "Research is in progress.",
                "COMPLETED": "Fund dossier saved. See the settlement receipt.",
            }[status],
            "audit_settlement": {
                "credits_charged": job["credits_charged"],
                "credits_refunded": refunded,
                "items": items,
            },
            "dossier_revision": job_id if job["dossier_json"] else None,
            **({"dossier": json.loads(job["dossier_json"])} if include_dossier and job["dossier_json"] else {}),
        }, False


def list_fund_audits_for_owner(
    user_id: str, *, scheme_code: Optional[str] = None, limit: int = 20,
) -> List[Dict[str, Any]]:
    """Return owner-scoped active and recent paid fund audits for cross-device recovery."""
    bounded_limit = max(1, min(int(limit), 50))
    with _transaction() as (_, cur, p, _):
        if scheme_code:
            cur.execute(
                f"""SELECT job_id FROM fund_audit_jobs
                    WHERE user_id={p} AND scheme_code={p}
                    ORDER BY created_at DESC, job_id DESC LIMIT {p}""",
                (user_id, scheme_code.strip().upper(), bounded_limit),
            )
        else:
            cur.execute(
                f"""SELECT job_id FROM fund_audit_jobs
                    WHERE user_id={p}
                    ORDER BY created_at DESC, job_id DESC LIMIT {p}""",
                (user_id, bounded_limit),
            )
        job_ids = [row[0] for row in cur.fetchall()]
    results: List[Dict[str, Any]] = []
    for jid in job_ids:
        item = get_fund_audit_status_for_owner(jid, user_id, include_dossier=False)
        if item:
            results.append(item)
    return results

