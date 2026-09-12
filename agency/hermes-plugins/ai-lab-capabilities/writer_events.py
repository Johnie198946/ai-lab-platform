"""Durable wake requests for one existing Hermes Writer, never a compiler.

The native no-agent retry job calls drain(); no threads, agents or new runtime.
A native job-store lock makes pause/claim checks and wake scheduling indivisible.
Busy requests stay in SQLite until a later native scheduler tick. Compilation
and its admission/transaction checks remain exclusively the Writer's concern.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import hashlib
import os
import re
import sqlite3


@contextmanager
def connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Runtime data contains hashes only; never research text or source URLs.
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    os.close(fd)
    db = sqlite3.connect(path, timeout=10)
    try:
        db.execute('PRAGMA busy_timeout=10000')
        db.execute('CREATE TABLE IF NOT EXISTS wakes (id TEXT PRIMARY KEY, pending INTEGER NOT NULL)')
        db.commit()
        yield db
    finally:
        db.close()


def enqueue(path, receipt):
    """Caller must have independently verified the immutable save receipt."""
    if receipt.get('admission_state') != 'admitted' or receipt.get('compile_eligible') is not True:
        return {'state': 'ineligible'}
    sha = receipt.get('sha256', '')
    raw = receipt.get('raw_path', '')
    if not isinstance(sha, str) or not re.fullmatch(r'[0-9a-f]{64}', sha) or not isinstance(raw, str) or not raw:
        return {'state': 'invalid_receipt'}
    key = hashlib.sha256((raw + '\0' + sha).encode()).hexdigest()
    with connect(path) as db, db:
        added = db.execute('INSERT OR IGNORE INTO wakes VALUES (?, 1)', (key,)).rowcount
    return {'state': 'pending' if added else 'duplicate', 'event_id': key}


@contextmanager
def strict_jobs_lock(j):
    """Use the native lock file, but NEVER its timeout-to-unlocked fallback.

    This local POSIX adapter pins private native APIs with integration tests.
    Contention raises, retaining the outbox; the next native tick retries.
    """
    import fcntl
    with j._jobs_file_lock:
        if getattr(j._jobs_lock_state, 'depth', 0):
            raise RuntimeError('unexpected_nested_native_lock')
        j.ensure_dirs()
        with open(j._jobs_lock_file(), 'a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            j._jobs_lock_state.depth = 1
            j._jobs_lock_state.load_stamp = None
            try:
                yield
            finally:
                j._jobs_lock_state.depth = 0
                j._jobs_lock_state.load_stamp = None
                fcntl.flock(lock, fcntl.LOCK_UN)


def drain(path, job_id, jobs_module=None):
    """At-most-one coalesced wake per idle window; not a compile receipt.

    A busy Writer must not receive manual_run_at: native mark_job_run clears it.
    Instead leave durable pending requests for the native no-agent retry job.
    Order is native fire lock -> jobs lock -> outbox transaction, matching the
    native completion path and avoiding a check-then-trigger pause race.
    """
    if jobs_module is None:
        from cron import jobs as jobs_module
    j = jobs_module
    with j._fire_job_lock(job_id) as acquired:
        if not acquired:
            return {'state': 'busy', 'job_id': job_id}
        with strict_jobs_lock(j):
            jobs = j.load_jobs()
            job = next((x for x in jobs if x.get('id') == job_id), None)
            if job is None:
                return {'state': 'missing_job', 'job_id': job_id}
            if not j.is_job_runnable(job):
                return {'state': 'paused_or_disabled', 'job_id': job_id}
            if job.get('fire_claim') or job.get('run_claim') or j._job_running_in_this_process(job_id):
                return {'state': 'busy', 'job_id': job_id}
            with connect(path) as db:
                db.execute('BEGIN IMMEDIATE')
                count = db.execute('SELECT COUNT(*) FROM wakes WHERE pending=1').fetchone()[0]
                if not count:
                    db.rollback()
                    return {'state': 'idle', 'job_id': job_id}
                if not job.get('manual_run_at'):
                    instant = j._hermes_now().isoformat()
                    job['next_run_at'] = instant
                    job['manual_run_at'] = instant
                    # Preserve operator prompt and all pause/enable fields.
                    j.save_jobs(jobs)
                persisted = j.get_job(job_id)
                if (not persisted or persisted.get('manual_run_at') != job.get('manual_run_at')
                        or not j.is_job_runnable(persisted)):
                    raise RuntimeError('native_wake_readback_failed')
                # Commit AFTER native durable schedule. Crash in between may
                # repeat a wake but can never erase an unscheduled event.
                db.execute('UPDATE wakes SET pending=0 WHERE pending=1')
                db.commit()
                return {'state': 'scheduled', 'job_id': job_id, 'coalesced': count,
                        'compile_verified': False}


def request(path, job_id, receipt):
    """Trigger failure must not undo a successful immutable research save."""
    try:
        event = enqueue(path, receipt)
        if event['state'] not in ('pending', 'duplicate'):
            return event
        return dict(drain(path, job_id), event_id=event['event_id'])
    except Exception as exc:
        return {'state': 'trigger_failed', 'error_type': type(exc).__name__,
                'fallback': 'existing_periodic_writer', 'compile_verified': False}
