"""Удалить из складского контура позиции исключённых групп номенклатуры.

Группы берутся из `INVENTORY_EXCLUDED_GROUPS` вместе со всеми подгруппами.
Загрузчик такие позиции больше не пишет, но уже загруженную историю нужно
почистить отдельно — этим скриптом.

    python -m scripts.purge_excluded_inventory_groups --dry-run
    python -m scripts.purge_excluded_inventory_groups --apply

Данные восстановимы: снять группы из `INVENTORY_EXCLUDED_GROUPS` и
перезагрузить период через `POST /api/inventory/sync`.
"""

import argparse
import logging

from sqlalchemy import text

from app.config import settings
from app.db import SessionLocal

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

EXCLUDED_TREE = text("""
    WITH RECURSIVE tree AS (
        SELECT id FROM nomenclature_group WHERE name = ANY(:names)
        UNION ALL
        SELECT g.id FROM nomenclature_group g JOIN tree t ON g.parent_id = t.id
    )
    SELECT p.id FROM product p JOIN tree t ON t.id = p.group_id
""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="выполнить удаление")
    ap.add_argument("--dry-run", action="store_true", help="только показать объём (по умолчанию)")
    args = ap.parse_args()

    names = [n.strip() for n in (settings.INVENTORY_EXCLUDED_GROUPS or "").split(",") if n.strip()]
    if not names:
        logger.error("INVENTORY_EXCLUDED_GROUPS пуст — нечего удалять")
        return

    db = SessionLocal()
    try:
        product_ids = [r[0] for r in db.execute(EXCLUDED_TREE, {"names": names}).fetchall()]
        print(f"Группы: {', '.join(names)}")
        print(f"Номенклатур под удаление: {len(product_ids)}")
        if not product_ids:
            return

        params = {"ids": product_ids}
        wo = db.execute(
            text("""SELECT COUNT(*), COALESCE(SUM(cost), 0)
                    FROM writeoff_item WHERE product_id = ANY(:ids)"""),
            params,
        ).first()
        inv = db.execute(
            text("""SELECT COUNT(*), COALESCE(SUM(line_sum), 0)
                    FROM incoming_invoice_item WHERE product_id = ANY(:ids)"""),
            params,
        ).first()
        print(f"Позиций списаний:  {wo[0]:>7}  на {float(wo[1]):>15,.0f} ₸")
        print(f"Позиций прихода:   {inv[0]:>7}  на {float(inv[1]):>15,.0f} ₸")

        if not args.apply:
            print("\n--dry-run: ничего не удалено. Для удаления запустите с --apply")
            return

        db.execute(text("DELETE FROM writeoff_item WHERE product_id = ANY(:ids)"), params)
        db.execute(text("DELETE FROM incoming_invoice_item WHERE product_id = ANY(:ids)"), params)

        # Шапки документов пересчитываются, а опустевшие удаляются: иначе в
        # журнале остались бы акты с суммой, которой нет ни в одной позиции.
        db.execute(text("""
            UPDATE writeoff_document d SET
                items_count = COALESCE(a.cnt, 0),
                total_cost  = COALESCE(a.total, 0)
            FROM (SELECT document_id, COUNT(*) cnt, SUM(cost) total
                  FROM writeoff_item GROUP BY document_id) a
            WHERE a.document_id = d.id
        """))
        db.execute(text("""
            UPDATE incoming_invoice v SET
                items_count = COALESCE(a.cnt, 0),
                total_sum   = COALESCE(a.total, 0)
            FROM (SELECT invoice_id, COUNT(*) cnt, SUM(line_sum) total
                  FROM incoming_invoice_item GROUP BY invoice_id) a
            WHERE a.invoice_id = v.id
        """))
        empty_wo = db.execute(text("""
            DELETE FROM writeoff_document d
            WHERE NOT EXISTS (SELECT 1 FROM writeoff_item i WHERE i.document_id = d.id)
        """)).rowcount
        empty_inv = db.execute(text("""
            DELETE FROM incoming_invoice v
            WHERE NOT EXISTS (SELECT 1 FROM incoming_invoice_item i WHERE i.invoice_id = v.id)
        """)).rowcount
        db.commit()

        print(f"\nУдалено. Опустевших документов снято: списаний {empty_wo}, накладных {empty_inv}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
