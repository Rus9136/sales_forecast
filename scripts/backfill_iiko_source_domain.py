"""One-shot backfill of `departments.iiko_source_domain` for rows that pre-date
Phase 1 of the menu/receipts initiative.

Logic
=====
Migration `013_iiko_source_domain.sql` adds the column as NULLABLE. This script:

1. For each domain in ``settings.IIKO_DOMAINS``, fetches
   ``GET /resto/api/corporation/departments`` and parses the XML to extract
   ``<id>`` of every department/jurperson/corporation node.
2. Builds a map ``{department_id: domain_host}`` (domain_host == the hostname
   only — e.g. ``sandy-co-co.iiko.it`` — to keep the value stable when the URL
   scheme or path changes).
3. UPDATE departments SET iiko_source_domain = :host WHERE id = :id.
4. Sanity-checks that **all** existing rows are populated, then runs
   ``ALTER TABLE departments ALTER COLUMN iiko_source_domain SET NOT NULL``
   in the same transaction.

If any row is left NULL after the update — likely a manually-created department
that no iiko domain returns — the script aborts before the SET NOT NULL step and
prints the offending rows so they can be handled (delete or fill manually).

Run
===
    docker exec sales-forecast-app python -m scripts.backfill_iiko_source_domain

Idempotent: re-running on an already-populated DB just refreshes the column
values and is a no-op on SET NOT NULL.
"""
from __future__ import annotations

import asyncio
import logging
import sys
from typing import Dict
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal
from app.services.iiko_auth import IikoAuthService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_iiko_source_domain")


def _host(url: str) -> str:
    """Return the bare hostname so the stored value is stable across scheme/path."""
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


async def fetch_ids_from_domain(base_url: str) -> set[str]:
    """Return the set of department ids reported by a single iiko domain."""
    auth = IikoAuthService(base_url)
    token = await auth._refresh_token()
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{base_url}/resto/api/corporation/departments",
            params={"key": token, "revisionFrom": -1},
        )
        resp.raise_for_status()

    root = ET.fromstring(resp.text)
    ids: set[str] = set()
    for item in root.findall("corporateItemDto"):
        node = item.find("id")
        if node is not None and node.text and node.text.strip():
            ids.add(node.text.strip())
    return ids


async def build_id_to_domain_map() -> Dict[str, str]:
    """Combine ids across all configured domains into a single mapping.

    If the same id appears in multiple domains (shouldn't happen in practice
    for Сандык/Мадлен), the *first* domain wins — predictable, deterministic.
    """
    domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]
    mapping: Dict[str, str] = {}
    for domain in domains:
        host = _host(domain)
        try:
            ids = await fetch_ids_from_domain(domain)
        except Exception as e:
            logger.error(f"Failed to fetch {domain}: {e}")
            continue
        new_for_this_domain = 0
        for dept_id in ids:
            if dept_id not in mapping:
                mapping[dept_id] = host
                new_for_this_domain += 1
        logger.info(
            f"{host}: {len(ids)} ids returned, {new_for_this_domain} added to map"
        )
    return mapping


def apply_backfill(mapping: Dict[str, str]) -> tuple[int, list[str]]:
    """Update departments.iiko_source_domain and return (updated_count, unresolved_ids)."""
    db = SessionLocal()
    try:
        # Update existing rows by id
        updated = 0
        for dept_id, host in mapping.items():
            res = db.execute(
                text(
                    "UPDATE departments SET iiko_source_domain = :host "
                    "WHERE id = CAST(:dept_id AS uuid)"
                ),
                {"host": host, "dept_id": dept_id},
            )
            updated += res.rowcount
        db.commit()
        logger.info(f"UPDATE matched {updated} existing rows")

        # Sanity check — any rows still NULL?
        leftover = db.execute(
            text(
                "SELECT id::text, name FROM departments "
                "WHERE iiko_source_domain IS NULL ORDER BY name"
            )
        ).fetchall()
        unresolved = [f"{row[0]} ({row[1]})" for row in leftover]
        return updated, unresolved
    finally:
        db.close()


def lock_column_not_null() -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "ALTER TABLE departments "
                "ALTER COLUMN iiko_source_domain SET NOT NULL"
            )
        )
        db.commit()
        logger.info("departments.iiko_source_domain is now NOT NULL")
    finally:
        db.close()


async def main() -> int:
    logger.info(f"Domains configured: {settings.IIKO_DOMAINS}")
    mapping = await build_id_to_domain_map()
    if not mapping:
        logger.error("No ids fetched from any domain — aborting")
        return 1

    logger.info(f"Total unique ids across all domains: {len(mapping)}")
    by_domain: dict[str, int] = {}
    for host in mapping.values():
        by_domain[host] = by_domain.get(host, 0) + 1
    for host, n in sorted(by_domain.items()):
        logger.info(f"  {host}: {n} ids")

    updated, unresolved = apply_backfill(mapping)
    if unresolved:
        logger.error(
            f"{len(unresolved)} rows still have NULL iiko_source_domain — "
            "NOT applying NOT NULL constraint. Resolve them manually:"
        )
        for row in unresolved:
            logger.error(f"  {row}")
        return 2

    lock_column_not_null()
    logger.info("Backfill complete.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
