"""Lightweight fetch scheduler (MVP): background thread, no Celery/Redis needed.

Rationale: for a dozen feeds a polling thread inside the API process is
simpler and more robust than Celery+Redis. Upgrade path documented in README.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

log = logging.getLogger("wcm.scheduler")
_started = False


def _due_loop(interval_s: int = 60) -> None:
    from app.database import SessionLocal
    from app.importer.service import run_source
    from app.models import DataSource

    while True:
        try:
            db = SessionLocal()
            try:
                now = datetime.now(UTC).replace(tzinfo=None)
                due = (
                    db.query(DataSource)
                    .filter(DataSource.enabled.is_(True))
                    .filter(DataSource.update_interval != "manual")
                    .all()
                )
                for src in due:
                    try:
                        if src.next_run_at is None or src.next_run_at <= now:
                            log.info("scheduler: running source #%s %s", src.id, src.name)
                            run_source(db, src.id, triggered_by="scheduler")
                    except Exception as exc:
                        log.warning("scheduler: source #%s failed: %s", src.id, exc)
            finally:
                db.close()
        except Exception as exc:
            log.warning("scheduler loop error: %s", exc)
        time.sleep(interval_s)


def start_scheduler() -> None:
    global _started
    if _started:
        return
    _started = True
    t = threading.Thread(target=_due_loop, kwargs={"interval_s": 60}, daemon=True, name="wcm-scheduler")
    t.start()
    log.info("fetch scheduler started (60s tick, no external infra)")
