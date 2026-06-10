"""Append-only audit trail for pricing actions (ТЗ п.9.3).

log_audit() пишет строку в pricing_audit_log в рамках ТЕКУЩЕЙ транзакции
вызывающего кода (commit делает вызывающий). Ошибка аудита не валит
основную операцию — только логируется.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


def log_audit(
    db: Session,
    entity_type: str,
    entity_id: Any,
    action: str,
    actor: Optional[str] = None,
    department_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    try:
        db.execute(
            text("""
                INSERT INTO pricing_audit_log
                    (entity_type, entity_id, action, actor, department_id, details)
                VALUES (:etype, :eid, :action, :actor,
                        CAST(:dept_id AS uuid), CAST(:details AS jsonb))
            """),
            {
                "etype": entity_type,
                "eid": str(entity_id) if entity_id is not None else None,
                "action": action,
                "actor": actor or "api",
                "dept_id": str(department_id) if department_id else None,
                "details": json.dumps(details, ensure_ascii=False, default=str) if details else None,
            },
        )
    except Exception as e:
        logger.error("Audit log write failed (%s %s %s): %s", entity_type, entity_id, action, e)
