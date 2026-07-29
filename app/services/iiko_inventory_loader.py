"""Загрузчик складских документов iiko: акты списания и приходные накладные.

Разведка боевого API (2026-07-29) зафиксировала три особенности, вокруг
которых построен этот модуль:

1. ``storeId`` в query-параметрах у обоих документных эндпоинтов **молча
   игнорируется** — сервер отдаёт всю сеть независимо от фильтра. Отбор по
   подразделению делается здесь, после разбора ответа.
2. ``incomingInvoice`` отдаёт XML на десятки мегабайт (≈64 МБ за два месяца
   по сети), поэтому он читается потоково недельными срезами, а не
   ``ET.fromstring`` целиком.
3. ``writeoff.items[].cost`` — себестоимость всей строки, не за единицу.
   Складывается как есть, умножать на ``amount`` нельзя.

Эндпоинты:
    списания   GET /resto/api/v2/documents/writeoff?dateFrom=&dateTo=  (JSON)
    приход     GET /resto/api/documents/export/incomingInvoice?from=&to= (XML)
    склады     GET /resto/api/corporation/stores                        (XML)
    счета      GET /resto/api/v2/entities/list?rootType=Account         (JSON)
    поставщики GET /resto/api/suppliers                                 (XML)
    ед. изм.   GET /resto/api/v2/entities/list?rootType=MeasureUnit     (JSON)
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple
from urllib.parse import urlparse

import httpx
from psycopg2.extras import execute_values
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..config import settings
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)

# Недельные срезы: компромисс между числом запросов и объёмом одного ответа.
INVOICE_CHUNK_DAYS = 7
HTTP_TIMEOUT = 300.0


def _domain_host(url: str) -> str:
    parsed = urlparse(url if "://" in url else f"https://{url}")
    return parsed.hostname or url


def _f(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: Any) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _dt(v: Optional[str]) -> Optional[datetime]:
    """iiko отдаёт и '2026-07-01T23:00', и '2026-06-01T00:00:17', и с зоной."""
    if not v:
        return None
    raw = v.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:26] if "." in raw else raw[:19], fmt)
        except ValueError:
            continue
    try:  # хвост с таймзоной вида +05:00
        return datetime.fromisoformat(raw).replace(tzinfo=None)
    except ValueError:
        logger.warning("Не разобрана дата iiko: %r", v)
        return None


def _d(v: Optional[str]) -> Optional[date]:
    parsed = _dt(v)
    return parsed.date() if parsed else None


def _chunks(from_date: date, to_date: date, days: int) -> Iterator[Tuple[date, date]]:
    cur = from_date
    while cur <= to_date:
        end = min(cur + timedelta(days=days - 1), to_date)
        yield cur, end
        cur = end + timedelta(days=1)


class IikoInventoryLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    # ==================================================================
    # Справочники
    # ==================================================================

    async def sync_references(self) -> Dict[str, int]:
        """Склады, счета, поставщики, единицы измерения по всем доменам."""
        totals = {"stores": 0, "accounts": 0, "suppliers": 0, "measure_units": 0}

        for base_url in self.domains:
            host = _domain_host(base_url)
            try:
                token = await IikoAuthService(base_url)._refresh_token()
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    stores_xml = (await client.get(
                        f"{base_url}/resto/api/corporation/stores", params={"key": token}
                    )).text
                    suppliers_xml = (await client.get(
                        f"{base_url}/resto/api/suppliers", params={"key": token}
                    )).text
                    accounts = (await client.get(
                        f"{base_url}/resto/api/v2/entities/list",
                        params={"key": token, "rootType": "Account"},
                    )).json()
                    units = (await client.get(
                        f"{base_url}/resto/api/v2/entities/list",
                        params={"key": token, "rootType": "MeasureUnit"},
                    )).json()

                totals["stores"] += self._upsert_stores(stores_xml, host)
                totals["suppliers"] += self._upsert_suppliers(suppliers_xml, host)
                totals["accounts"] += self._upsert_accounts(accounts, host)
                totals["measure_units"] += self._upsert_measure_units(units, host)
                logger.info("%s: справочники складского контура обновлены", host)
            except Exception as e:
                logger.error("%s: ошибка синхронизации справочников: %s", host, e, exc_info=True)

        self.db.commit()
        return totals

    def _upsert_stores(self, xml_text: str, domain: str) -> int:
        rows = []
        for s in ET.fromstring(xml_text):
            sid = s.findtext("id")
            if not sid:
                continue
            rows.append((
                sid, s.findtext("parentId") or None, s.findtext("code") or None,
                (s.findtext("name") or "").strip(), domain,
            ))
        if not rows:
            return 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            # parentId у склада может указывать не на DEPARTMENT (напр. на JURPERSON),
            # поэтому FK проставляется только если такое подразделение реально есть.
            execute_values(
                cur,
                """
                INSERT INTO store (id, department_id, code, name, iiko_source_domain, synced_at)
                SELECT v.id, d.id, v.code, v.name, v.domain, NOW()
                FROM (VALUES %s) AS v(id, parent_id, code, name, domain)
                LEFT JOIN departments d ON d.id = v.parent_id
                ON CONFLICT (id) DO UPDATE SET
                    department_id = EXCLUDED.department_id,
                    code = EXCLUDED.code,
                    name = EXCLUDED.name,
                    iiko_source_domain = EXCLUDED.iiko_source_domain,
                    synced_at = NOW()
                """,
                rows,
                template="(%s::uuid, %s::uuid, %s, %s, %s)",
            )
        return len(rows)

    def _upsert_suppliers(self, xml_text: str, domain: str) -> int:
        rows = []
        for e in ET.fromstring(xml_text):
            sid = e.findtext("id")
            if not sid:
                continue
            rows.append((
                sid, e.findtext("code") or None, (e.findtext("name") or "").strip(),
                e.findtext("taxpayerIdNumber") or None,
                (e.findtext("deleted") or "false").lower() == "true", domain,
            ))
        if not rows:
            return 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO supplier (id, code, name, taxpayer_id_number, is_deleted,
                                      iiko_source_domain, synced_at)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code, name = EXCLUDED.name,
                    taxpayer_id_number = EXCLUDED.taxpayer_id_number,
                    is_deleted = EXCLUDED.is_deleted, synced_at = NOW()
                """,
                rows,
                template="(%s::uuid, %s, %s, %s, %s, %s, NOW())",
            )
        return len(rows)

    def _upsert_accounts(self, accounts: List[dict], domain: str) -> int:
        rows = [(
            a["id"], a.get("code") or None, a.get("name") or "",
            a.get("type") or None, a.get("accountParentId") or None,
            bool(a.get("deleted")), domain,
        ) for a in accounts if a.get("id")]
        if not rows:
            return 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO iiko_account (id, code, name, account_type, parent_id,
                                          is_deleted, iiko_source_domain, synced_at)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code, name = EXCLUDED.name,
                    account_type = EXCLUDED.account_type, parent_id = EXCLUDED.parent_id,
                    is_deleted = EXCLUDED.is_deleted, synced_at = NOW()
                """,
                rows,
                template="(%s::uuid, %s, %s, %s, %s::uuid, %s, %s, NOW())",
            )
        return len(rows)

    def _upsert_measure_units(self, units: List[dict], domain: str) -> int:
        rows = [(u["id"], u.get("code") or None, u.get("name") or "", domain)
                for u in units if u.get("id")]
        if not rows:
            return 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO measure_unit (id, code, name, iiko_source_domain, synced_at)
                VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    code = EXCLUDED.code, name = EXCLUDED.name, synced_at = NOW()
                """,
                rows,
                template="(%s::uuid, %s, %s, %s, NOW())",
            )
        return len(rows)

    # ==================================================================
    # Вспомогательные карты
    # ==================================================================

    def _store_map(self, domain: str) -> Dict[str, Optional[str]]:
        """store_id → department_id (может быть None для складов без точки)."""
        rows = self.db.execute(
            text("SELECT id::text, department_id::text FROM store WHERE iiko_source_domain = :d"),
            {"d": domain},
        ).fetchall()
        return {r[0]: r[1] for r in rows}

    def _product_map(self, domain: str, product_ids: Sequence[str]) -> Dict[str, int]:
        if not product_ids:
            return {}
        rows = self.db.execute(
            text("""
                SELECT iiko_product_id::text, id FROM product
                WHERE iiko_source_domain = :domain
                  AND iiko_product_id = ANY(:ids ::uuid[])
            """),
            {"domain": domain, "ids": list(product_ids)},
        ).fetchall()
        return {str(r[0]): r[1] for r in rows}

    @staticmethod
    def _wanted(dept_id: Optional[str], department_ids: Optional[set]) -> bool:
        if department_ids is None:
            return True
        return dept_id is not None and dept_id in department_ids

    def _domain_has_wanted(self, domain: str, wanted: Optional[set]) -> bool:
        """Есть ли в домене склады нужных точек.

        Без этой проверки бэкфилл качает многомегабайтный XML со всех доменов
        на каждом недельном срезе, даже если целевая точка живёт в одном из них.
        """
        if wanted is None:
            return True
        return any(dept in wanted for dept in self._store_map(domain).values() if dept)

    # ==================================================================
    # Акты списания
    # ==================================================================

    async def sync_writeoffs(
        self, from_date: date, to_date: date,
        department_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Загрузить акты списания. department_ids=None → вся сеть."""
        wanted = {str(d) for d in department_ids} if department_ids else None
        started = datetime.utcnow()
        total_docs = total_items = unresolved = 0

        for base_url in self.domains:
            host = _domain_host(base_url)
            if not self._domain_has_wanted(host, wanted):
                logger.info("%s: нет складов нужных подразделений — домен пропущен", host)
                continue
            try:
                token = await IikoAuthService(base_url)._refresh_token()
                async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
                    resp = await client.get(
                        f"{base_url}/resto/api/v2/documents/writeoff",
                        params={
                            "key": token,
                            "dateFrom": from_date.strftime("%Y-%m-%d"),
                            "dateTo": to_date.strftime("%Y-%m-%d"),
                        },
                    )
                    resp.raise_for_status()
                    payload = resp.json()

                if payload.get("result") != "SUCCESS":
                    logger.error("%s: writeoff вернул %s: %s",
                                 host, payload.get("result"), payload.get("errors"))
                    continue

                docs, items, missed = self._parse_writeoffs(payload.get("response", []), host, wanted)
                d, i = self._store_writeoffs(docs, items)
                total_docs += d
                total_items += i
                unresolved += missed
                logger.info("%s: списания %s..%s — %d док., %d поз.", host, from_date, to_date, d, i)
            except httpx.HTTPError as e:
                logger.error("%s: HTTP-ошибка загрузки списаний: %s", host, e)
            except Exception as e:
                logger.error("%s: ошибка загрузки списаний: %s", host, e, exc_info=True)

        self.db.commit()
        result = {
            "documents": total_docs, "items": total_items,
            "unresolved_products": unresolved,
            "duration_sec": round((datetime.utcnow() - started).total_seconds(), 2),
        }
        self._log_sync("writeoff", from_date, to_date, result, wanted)
        return result

    def _parse_writeoffs(
        self, raw_docs: List[dict], domain: str, wanted: Optional[set],
    ) -> Tuple[List[dict], List[dict], int]:
        store_map = self._store_map(domain)

        kept: List[dict] = []
        for doc in raw_docs:
            store_id = doc.get("storeId")
            dept_id = store_map.get(store_id) if store_id else None
            if not self._wanted(dept_id, wanted):
                continue
            doc["_department_id"] = dept_id
            kept.append(doc)

        product_ids = {i["productId"] for d in kept for i in d.get("items", []) if i.get("productId")}
        product_map = self._product_map(domain, list(product_ids))

        docs: List[dict] = []
        items: List[dict] = []
        unresolved = 0

        for doc in kept:
            dt = _dt(doc.get("dateIncoming"))
            if dt is None:
                logger.warning("Списание %s без разбираемой даты — пропущено", doc.get("id"))
                continue
            doc_items = doc.get("items") or []
            total_cost = sum(_f(i.get("cost")) or 0.0 for i in doc_items)
            docs.append({
                "id": doc["id"],
                "department_id": doc["_department_id"],
                "store_id": doc.get("storeId"),
                "account_id": doc.get("accountId"),
                "document_number": doc.get("documentNumber"),
                "date_incoming": dt,
                "doc_date": dt.date(),
                "status": doc.get("status") or "UNKNOWN",
                "conception_id": doc.get("conceptionId"),
                "comment": doc.get("comment"),
                "items_count": len(doc_items),
                "total_cost": total_cost,
                "domain": domain,
            })
            for it in doc_items:
                pid = it.get("productId")
                mapped = product_map.get(pid)
                if pid and mapped is None:
                    unresolved += 1
                items.append({
                    "document_id": doc["id"],
                    "department_id": doc["_department_id"],
                    "store_id": doc.get("storeId"),
                    "doc_date": dt.date(),
                    "num": _i(it.get("num")),
                    "iiko_product_id": pid,
                    "product_id": mapped,
                    "product_size_id": it.get("productSizeId"),
                    "amount": _f(it.get("amount")) or 0.0,
                    "amount_factor": _f(it.get("amountFactor")),
                    "measure_unit_id": it.get("measureUnitId"),
                    "container_id": it.get("containerId"),
                    "cost": _f(it.get("cost")),
                })

        return docs, items, unresolved

    def _store_writeoffs(self, docs: List[dict], items: List[dict]) -> Tuple[int, int]:
        if not docs:
            return 0, 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO writeoff_document (
                    id, department_id, store_id, account_id, document_number,
                    date_incoming, doc_date, status, conception_id, comment,
                    items_count, total_cost, iiko_source_domain, synced_at
                ) VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    department_id = EXCLUDED.department_id,
                    store_id = EXCLUDED.store_id,
                    account_id = EXCLUDED.account_id,
                    document_number = EXCLUDED.document_number,
                    date_incoming = EXCLUDED.date_incoming,
                    doc_date = EXCLUDED.doc_date,
                    status = EXCLUDED.status,
                    conception_id = EXCLUDED.conception_id,
                    comment = EXCLUDED.comment,
                    items_count = EXCLUDED.items_count,
                    total_cost = EXCLUDED.total_cost,
                    synced_at = NOW()
                """,
                [(
                    d["id"], d["department_id"], d["store_id"], d["account_id"],
                    d["document_number"], d["date_incoming"], d["doc_date"], d["status"],
                    d["conception_id"], d["comment"], d["items_count"], d["total_cost"],
                    d["domain"],
                ) for d in docs],
                template="(%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s::timestamp, "
                         "%s::date, %s, %s::uuid, %s, %s, %s, %s, NOW())",
            )

            doc_ids = [d["id"] for d in docs]
            cur.execute("DELETE FROM writeoff_item WHERE document_id = ANY(%s::uuid[])", (doc_ids,))

            if items:
                execute_values(
                    cur,
                    """
                    INSERT INTO writeoff_item (
                        document_id, department_id, store_id, doc_date, num,
                        iiko_product_id, product_id, product_size_id,
                        amount, amount_factor, measure_unit_id, container_id, cost
                    ) VALUES %s
                    """,
                    [(
                        it["document_id"], it["department_id"], it["store_id"], it["doc_date"],
                        it["num"], it["iiko_product_id"], it["product_id"], it["product_size_id"],
                        it["amount"], it["amount_factor"], it["measure_unit_id"],
                        it["container_id"], it["cost"],
                    ) for it in items],
                    template="(%s::uuid, %s::uuid, %s::uuid, %s::date, %s, %s::uuid, %s, "
                             "%s::uuid, %s, %s, %s::uuid, %s::uuid, %s)",
                    page_size=1000,
                )
        return len(docs), len(items)

    # ==================================================================
    # Приходные накладные
    # ==================================================================

    async def sync_incoming_invoices(
        self, from_date: date, to_date: date,
        department_ids: Optional[Sequence[str]] = None,
    ) -> Dict[str, Any]:
        """Загрузить приходные накладные недельными срезами (ответ — десятки МБ)."""
        wanted = {str(d) for d in department_ids} if department_ids else None
        started = datetime.utcnow()
        total_docs = total_items = unresolved = 0

        for base_url in self.domains:
            host = _domain_host(base_url)
            if not self._domain_has_wanted(host, wanted):
                logger.info("%s: нет складов нужных подразделений — домен пропущен", host)
                continue
            try:
                token = await IikoAuthService(base_url)._refresh_token()
                store_map = self._store_map(host)

                for chunk_from, chunk_to in _chunks(from_date, to_date, INVOICE_CHUNK_DAYS):
                    raw_docs = await self._fetch_invoice_chunk(base_url, token, chunk_from, chunk_to, store_map, wanted)
                    if not raw_docs:
                        continue
                    docs, items, missed = self._resolve_invoice_products(raw_docs, host)
                    d, i = self._store_invoices(docs, items)
                    total_docs += d
                    total_items += i
                    unresolved += missed
                    logger.info("%s: накладные %s..%s — %d док., %d поз.",
                                host, chunk_from, chunk_to, d, i)
            except httpx.HTTPError as e:
                logger.error("%s: HTTP-ошибка загрузки накладных: %s", host, e)
            except Exception as e:
                logger.error("%s: ошибка загрузки накладных: %s", host, e, exc_info=True)

        self.db.commit()
        result = {
            "documents": total_docs, "items": total_items,
            "unresolved_products": unresolved,
            "duration_sec": round((datetime.utcnow() - started).total_seconds(), 2),
        }
        self._log_sync("invoice", from_date, to_date, result, wanted)
        return result

    async def _fetch_invoice_chunk(
        self, base_url: str, token: str, chunk_from: date, chunk_to: date,
        store_map: Dict[str, Optional[str]], wanted: Optional[set],
    ) -> List[dict]:
        """Потоковый разбор XML: документы, у которых есть позиции нужных складов.

        Элементы отбрасываются сразу после обработки, поэтому пиковая память
        не зависит от размера ответа.
        """
        parser = ET.XMLPullParser(("end",))
        kept: List[dict] = []

        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            async with client.stream(
                "GET",
                f"{base_url}/resto/api/documents/export/incomingInvoice",
                params={
                    "key": token,
                    "from": chunk_from.strftime("%Y-%m-%d"),
                    "to": chunk_to.strftime("%Y-%m-%d"),
                },
            ) as resp:
                resp.raise_for_status()
                async for raw in resp.aiter_bytes():
                    parser.feed(raw)
                    for event, elem in parser.read_events():
                        if elem.tag != "document":
                            continue
                        parsed = self._parse_invoice_element(elem, store_map, wanted)
                        if parsed:
                            kept.append(parsed)
                        elem.clear()

        parser.close()
        for event, elem in parser.read_events():
            if elem.tag == "document":
                parsed = self._parse_invoice_element(elem, store_map, wanted)
                if parsed:
                    kept.append(parsed)
                elem.clear()

        return kept

    def _parse_invoice_element(
        self, elem: ET.Element, store_map: Dict[str, Optional[str]], wanted: Optional[set],
    ) -> Optional[dict]:
        inv_id = elem.findtext("id")
        if not inv_id:
            return None

        raw_items = elem.find("items")
        if raw_items is None:
            return None

        items: List[dict] = []
        for it in raw_items:
            store_id = it.findtext("store")
            dept_id = store_map.get(store_id) if store_id else None
            if not self._wanted(dept_id, wanted):
                continue
            items.append({
                "department_id": dept_id,
                "store_id": store_id,
                "num": _i(it.findtext("num")),
                "iiko_product_id": it.findtext("product") or None,
                "product_article": it.findtext("productArticle") or None,
                "amount": _f(it.findtext("amount")),
                "actual_amount": _f(it.findtext("actualAmount")),
                "price": _f(it.findtext("price")),
                "price_without_vat": _f(it.findtext("priceWithoutVat")),
                "line_sum": _f(it.findtext("sum")),
                "vat_percent": _f(it.findtext("vatPercent")),
                "vat_sum": _f(it.findtext("vatSum")),
                "discount_sum": _f(it.findtext("discountSum")),
                "amount_unit_id": it.findtext("amountUnit") or None,
                "is_additional_expense": (it.findtext("isAdditionalExpense") or "false").lower() == "true",
            })

        if not items:
            return None

        incoming_date = _d(elem.findtext("incomingDate"))
        date_incoming = _dt(elem.findtext("dateIncoming"))
        doc_date = incoming_date or (date_incoming.date() if date_incoming else None)
        if doc_date is None:
            logger.warning("Накладная %s без разбираемой даты — пропущена", inv_id)
            return None

        for it in items:
            it["doc_date"] = doc_date
            it["invoice_id"] = inv_id

        return {
            "id": inv_id,
            "supplier_id": elem.findtext("supplier") or None,
            "default_store_id": elem.findtext("defaultStore") or None,
            "document_number": elem.findtext("documentNumber") or None,
            "incoming_document_number": elem.findtext("incomingDocumentNumber") or None,
            "incoming_date": incoming_date,
            "date_incoming": date_incoming,
            "doc_date": doc_date,
            "status": elem.findtext("status") or "UNKNOWN",
            "conception_id": elem.findtext("conception") or None,
            "comment": elem.findtext("comment") or None,
            "linked_outgoing_invoice_id": elem.findtext("linkedOutgoingInvoiceId") or None,
            "items_count": len(items),
            "total_sum": sum(i["line_sum"] or 0.0 for i in items),
            "items": items,
        }

    def _resolve_invoice_products(
        self, raw_docs: List[dict], domain: str,
    ) -> Tuple[List[dict], List[dict], int]:
        product_ids = {
            i["iiko_product_id"] for d in raw_docs for i in d["items"] if i.get("iiko_product_id")
        }
        product_map = self._product_map(domain, list(product_ids))

        docs: List[dict] = []
        items: List[dict] = []
        unresolved = 0

        for d in raw_docs:
            doc = {k: v for k, v in d.items() if k != "items"}
            doc["domain"] = domain
            docs.append(doc)
            for it in d["items"]:
                pid = it.get("iiko_product_id")
                mapped = product_map.get(pid) if pid else None
                if pid and mapped is None:
                    unresolved += 1
                it["product_id"] = mapped
                items.append(it)

        return docs, items, unresolved

    def _store_invoices(self, docs: List[dict], items: List[dict]) -> Tuple[int, int]:
        if not docs:
            return 0, 0
        conn = self.db.connection().connection
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO incoming_invoice (
                    id, supplier_id, default_store_id, document_number,
                    incoming_document_number, incoming_date, date_incoming, doc_date,
                    status, conception_id, comment, linked_outgoing_invoice_id,
                    items_count, total_sum, iiko_source_domain, synced_at
                ) VALUES %s
                ON CONFLICT (id) DO UPDATE SET
                    supplier_id = EXCLUDED.supplier_id,
                    default_store_id = EXCLUDED.default_store_id,
                    document_number = EXCLUDED.document_number,
                    incoming_document_number = EXCLUDED.incoming_document_number,
                    incoming_date = EXCLUDED.incoming_date,
                    date_incoming = EXCLUDED.date_incoming,
                    doc_date = EXCLUDED.doc_date,
                    status = EXCLUDED.status,
                    conception_id = EXCLUDED.conception_id,
                    comment = EXCLUDED.comment,
                    linked_outgoing_invoice_id = EXCLUDED.linked_outgoing_invoice_id,
                    items_count = EXCLUDED.items_count,
                    total_sum = EXCLUDED.total_sum,
                    synced_at = NOW()
                """,
                [(
                    d["id"], d["supplier_id"], d["default_store_id"], d["document_number"],
                    d["incoming_document_number"], d["incoming_date"], d["date_incoming"],
                    d["doc_date"], d["status"], d["conception_id"], d["comment"],
                    d["linked_outgoing_invoice_id"], d["items_count"], d["total_sum"], d["domain"],
                ) for d in docs],
                template="(%s::uuid, %s::uuid, %s::uuid, %s, %s, %s::date, %s::timestamp, "
                         "%s::date, %s, %s::uuid, %s, %s::uuid, %s, %s, %s, NOW())",
            )

            inv_ids = [d["id"] for d in docs]
            cur.execute("DELETE FROM incoming_invoice_item WHERE invoice_id = ANY(%s::uuid[])", (inv_ids,))

            if items:
                execute_values(
                    cur,
                    """
                    INSERT INTO incoming_invoice_item (
                        invoice_id, department_id, store_id, doc_date, num,
                        iiko_product_id, product_id, product_article,
                        amount, actual_amount, price, price_without_vat, line_sum,
                        vat_percent, vat_sum, discount_sum, amount_unit_id,
                        is_additional_expense
                    ) VALUES %s
                    """,
                    [(
                        it["invoice_id"], it["department_id"], it["store_id"], it["doc_date"],
                        it["num"], it["iiko_product_id"], it["product_id"], it["product_article"],
                        it["amount"], it["actual_amount"], it["price"], it["price_without_vat"],
                        it["line_sum"], it["vat_percent"], it["vat_sum"], it["discount_sum"],
                        it["amount_unit_id"], it["is_additional_expense"],
                    ) for it in items],
                    template="(%s::uuid, %s::uuid, %s::uuid, %s::date, %s, %s::uuid, %s, %s, "
                             "%s, %s, %s, %s, %s, %s, %s, %s, %s::uuid, %s)",
                    page_size=1000,
                )
        return len(docs), len(items)

    # ==================================================================
    # Журнал
    # ==================================================================

    def _log_sync(
        self, sync_type: str, from_date: date, to_date: date,
        result: Dict[str, Any], wanted: Optional[set],
    ) -> None:
        dept = next(iter(wanted)) if wanted and len(wanted) == 1 else None
        try:
            self.db.execute(
                text("""
                    INSERT INTO inventory_sync_log (
                        sync_type, department_id, from_date, to_date,
                        documents, items, unresolved, status, duration_sec
                    ) VALUES (
                        :t, :dept ::uuid, :f, :to, :docs, :items, :unres, 'success', :dur
                    )
                """),
                {
                    "t": sync_type, "dept": dept, "f": from_date, "to": to_date,
                    "docs": result["documents"], "items": result["items"],
                    "unres": result["unresolved_products"], "dur": result["duration_sec"],
                },
            )
            self.db.commit()
        except Exception as e:  # журнал не должен ронять загрузку
            logger.warning("Не удалось записать inventory_sync_log: %s", e)
            self.db.rollback()
