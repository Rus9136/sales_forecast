"""Разовая загрузка складского контура по одной точке (пилот — Мадлен 18 мкр).

    python -m scripts.sync_inventory_madlen18 [--from 2026-06-01] [--to 2026-07-28]
                                              [--department <uuid>] [--refs-only]

Сначала обновляет справочники (склады/счета/поставщики/ед.изм.), затем грузит
акты списания и приходные накладные за период.
"""

import argparse
import asyncio
import logging
from datetime import date, datetime

from app.db import SessionLocal
from app.services.iiko_inventory_loader import IikoInventoryLoaderService

MADLEN_18 = "6e3aa45a-a8bc-4373-82fd-00e6ceb60357"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _parse_date(v: str) -> date:
    return datetime.strptime(v, "%Y-%m-%d").date()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="from_date", type=_parse_date, default=date(2026, 6, 1))
    ap.add_argument("--to", dest="to_date", type=_parse_date, default=date(2026, 7, 28))
    ap.add_argument("--department", default=MADLEN_18,
                    help="UUID подразделения; 'all' — вся сеть")
    ap.add_argument("--refs-only", action="store_true")
    args = ap.parse_args()

    depts = None if args.department == "all" else [args.department]

    db = SessionLocal()
    try:
        svc = IikoInventoryLoaderService(db)

        print("→ справочники…")
        print("  ", await svc.sync_references())
        if args.refs_only:
            return

        print(f"→ акты списания {args.from_date}..{args.to_date}…")
        print("  ", await svc.sync_writeoffs(args.from_date, args.to_date, depts))

        print(f"→ приходные накладные {args.from_date}..{args.to_date}…")
        print("  ", await svc.sync_incoming_invoices(args.from_date, args.to_date, depts))
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
