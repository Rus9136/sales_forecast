"""Create receipt + receipt_item partitions for the next N months ahead.

Run weekly via APScheduler or manually:
    python -m scripts.create_receipt_partitions

Idempotent — uses CREATE TABLE IF NOT EXISTS.
"""

from __future__ import annotations

import logging
import sys
from datetime import date, timedelta

logger = logging.getLogger(__name__)

MONTHS_AHEAD = 6


def ensure_partitions(conn, months_ahead: int = MONTHS_AHEAD) -> list[str]:
    """Create missing partitions for receipt and receipt_item tables.

    Returns list of partition names created.
    """
    today = date.today()
    created: list[str] = []

    cur = conn.cursor()
    for offset in range(months_ahead + 1):
        year = today.year + (today.month + offset - 1) // 12
        month = (today.month + offset - 1) % 12 + 1
        start = date(year, month, 1)
        if month == 12:
            end = date(year + 1, 1, 1)
        else:
            end = date(year, month + 1, 1)

        for table in ("receipt", "receipt_item"):
            pname = f"{table}_{start.strftime('%Y_%m')}"
            cur.execute(
                f"SELECT 1 FROM pg_class WHERE relname = %s", (pname,)
            )
            if cur.fetchone():
                continue
            cur.execute(
                f"CREATE TABLE IF NOT EXISTS {pname} PARTITION OF {table} "
                f"FOR VALUES FROM ('{start}') TO ('{end}')"
            )
            created.append(pname)
            logger.info(f"Created partition {pname}")

    conn.commit()
    cur.close()
    return created


def main():
    import os
    import psycopg2

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        from dotenv import load_dotenv
        load_dotenv()
        db_url = os.environ.get("DATABASE_URL", "")

    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        sys.exit(1)

    conn = psycopg2.connect(db_url)
    try:
        created = ensure_partitions(conn)
        if created:
            print(f"Created {len(created)} partitions: {', '.join(created)}")
        else:
            print("All partitions already exist")
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
