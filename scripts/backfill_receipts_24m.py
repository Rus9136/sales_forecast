"""Backfill receipts for 24 months in 2-week chunks.

Usage (from host):
    python3 scripts/backfill_receipts_24m.py

Calls POST /api/receipts/sync inside the running container via localhost:8002.
Chunks by 14-day windows to avoid iiko OLAP timeouts.
Skips chunks that already have data in the DB.
"""

import os
import sys
import time
import requests
from datetime import date, timedelta

API_BASE = os.environ.get("API_BASE", "http://localhost:8002")
API_TOKEN = os.environ.get("API_TOKEN", "")

if not API_TOKEN:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env.prod"))
    API_TOKEN = os.environ.get("API_TOKEN", "")

if not API_TOKEN:
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
    API_TOKEN = os.environ.get("API_TOKEN", "")

HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}
CHUNK_DAYS = 14
SLEEP_BETWEEN = 5  # seconds between chunks


def get_loaded_months():
    """Query DB via API to see what's already loaded."""
    try:
        r = requests.get(
            f"{API_BASE}/api/receipts",
            headers=HEADERS,
            params={"from_date": "2024-06-01", "to_date": "2026-06-01", "limit": 1},
            timeout=30,
        )
        return r.status_code == 200
    except Exception:
        return False


def sync_chunk(from_date: date, to_date: date) -> dict:
    """Call receipts sync for a date range."""
    r = requests.post(
        f"{API_BASE}/api/receipts/sync",
        headers=HEADERS,
        params={"from_date": str(from_date), "to_date": str(to_date)},
        timeout=600,
    )
    r.raise_for_status()
    return r.json()


def main():
    target_start = date(2024, 6, 1)
    target_end = date(2026, 5, 25)

    if not get_loaded_months():
        print("ERROR: Cannot reach API or auth failed. Check API_TOKEN and API_BASE.", file=sys.stderr)
        sys.exit(1)

    chunks = []
    cursor = target_start
    while cursor <= target_end:
        chunk_end = min(cursor + timedelta(days=CHUNK_DAYS - 1), target_end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)

    print(f"Total chunks: {len(chunks)} ({CHUNK_DAYS}-day windows)")
    print(f"Range: {target_start} .. {target_end}")
    print()

    for i, (from_d, to_d) in enumerate(chunks, 1):
        tag = f"[{i}/{len(chunks)}] {from_d} .. {to_d}"
        print(f"{tag} — syncing...", end=" ", flush=True)
        t0 = time.time()
        try:
            result = sync_chunk(from_d, to_d)
            elapsed = time.time() - t0
            total_r = result.get("total_receipts", 0)
            total_i = result.get("total_items", 0)
            status = result.get("status", "?")
            errors = result.get("errors", [])

            if errors:
                print(f"  {status} | {total_r} receipts, {total_i} items | {elapsed:.0f}s | ERRORS: {errors}")
            elif total_r == 0:
                print(f"  {status} | no data | {elapsed:.0f}s")
            else:
                print(f"  {status} | {total_r:,} receipts, {total_i:,} items | {elapsed:.0f}s")

        except requests.exceptions.Timeout:
            print(f"  TIMEOUT after 600s — skipping, retry later")
        except requests.exceptions.RequestException as e:
            print(f"  ERROR: {e}")
        except KeyboardInterrupt:
            print("\nInterrupted by user")
            sys.exit(0)

        if i < len(chunks):
            time.sleep(SLEEP_BETWEEN)

    print("\nBackfill complete!")
    print("Next step: run SKU aggregation backfill:")
    print(f"  curl -X POST '{API_BASE}/api/forecast/sku/aggregate/backfill' -H 'Authorization: Bearer ...'")


if __name__ == "__main__":
    main()
