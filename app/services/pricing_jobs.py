"""Job observability for the pricing subsystem.

1. log_job_run() — каждый ночной pricing-джоб пишет результат в auto_sync_log
   (та же таблица, что и синки продаж) — статус виден через
   GET /api/sales/auto-sync/status и на странице /sync, падения не тонут в логах.

2. JobRegistry — in-memory реестр для тяжёлых ручных POST'ов, запускаемых в
   фоне (?background=true): 202 + job_id сразу, статус/результат — через
   GET /api/pricing-engine/jobs/{job_id}. Реестр процесс-локальный (один
   uvicorn-воркер) и не переживает рестарт — для отладочных прогонов этого
   достаточно; регулярные запуски идут через APScheduler.
"""

from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, datetime
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

MAX_FINISHED_JOBS = 50


def log_job_run(sync_type: str, result: dict, records: int = 0) -> None:
    """Записать результат pricing-джоба в auto_sync_log (не валит джоб при ошибке)."""
    try:
        from ..db import SessionLocal
        from ..models.sales import AutoSyncLog

        status = result.get("status", "unknown")
        if status in ("ok", "success"):
            status = "success"
        message = str(result.get("message") or result.get("model_version")
                      or f"records={records}")[:500]
        error_details = None
        if status not in ("success", "partial"):
            error_details = str(result.get("message") or result.get("errors") or "")[:1000]
        elif result.get("errors"):
            error_details = str(result["errors"])[:1000]

        db = SessionLocal()
        try:
            db.add(AutoSyncLog(
                sync_date=date.today(),
                sync_type=sync_type,
                status=status,
                message=message,
                summary_records=records,
                error_details=error_details,
                executed_at=datetime.utcnow(),
            ))
            db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.error("Failed to log job run %s: %s", sync_type, e)


class JobRegistry:
    """Потокобезопасный реестр фоновых джобов: job_id → status/result."""

    def __init__(self):
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(self, name: str, fn: Callable[[], dict]) -> str:
        job_id = str(uuid.uuid4())
        with self._lock:
            self._jobs[job_id] = {
                "job_id": job_id,
                "name": name,
                "status": "running",
                "started_at": datetime.utcnow().isoformat(),
                "finished_at": None,
                "result": None,
            }

        def _run():
            try:
                result = fn()
                self._finish(job_id, "done", result)
            except Exception as e:
                logger.error("Background job %s (%s) failed: %s", name, job_id, e, exc_info=True)
                self._finish(job_id, "error", {"status": "error", "message": str(e)})

        threading.Thread(target=_run, name=f"job-{name}", daemon=True).start()
        return job_id

    def _finish(self, job_id: str, status: str, result: dict) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job["status"] = status
                job["finished_at"] = datetime.utcnow().isoformat()
                job["result"] = result
            # не копим бесконечно: оставляем последние MAX_FINISHED_JOBS завершённых
            finished = [jid for jid, j in self._jobs.items() if j["status"] != "running"]
            for jid in finished[:-MAX_FINISHED_JOBS]:
                del self._jobs[jid]

    def get(self, job_id: str) -> Optional[dict]:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None


job_registry = JobRegistry()
