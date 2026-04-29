import httpx
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from ..config import settings
from ..models.department import Department
from ..models.employee import Employee, SalesByWaiter
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)


class IikoWaiterSalesLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    async def fetch_from_single_domain(
        self, base_url: str, from_date: date, to_date: date
    ) -> List[dict]:
        try:
            auth_service = IikoAuthService(base_url)
            token = await auth_service._refresh_token()

            request_body = {
                "reportType": "SALES",
                "groupByRowFields": [
                    "Department.Id",
                    "WaiterName",
                    "OpenDate",
                ],
                "aggregateFields": [
                    "DishSumInt",
                    "DishDiscountSumInt",
                ],
                "filters": {
                    "OpenDate.Typed": {
                        "filterType": "DateRange",
                        "periodType": "CUSTOM",
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d"),
                    },
                    "OrderDeleted": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"],
                    },
                    "DeletedWithWriteoff": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"],
                    },
                },
            }

            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{base_url}/resto/api/v2/reports/olap",
                    params={"key": token},
                    json=request_body,
                )
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data", [])
                logger.info(f"Fetched {len(data)} waiter sales records from {base_url}")
                return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching waiter sales from {base_url}: {e}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(
                    f"status={e.response.status_code} body={e.response.text[:200]}"
                )
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching waiter sales from {base_url}: {e}")
            return []

    async def fetch_from_iiko(self, from_date: date, to_date: date) -> List[dict]:
        all_rows: List[dict] = []
        for domain in self.domains:
            try:
                rows = await self.fetch_from_single_domain(domain, from_date, to_date)
                all_rows.extend(rows)
            except Exception as e:
                logger.error(f"Domain {domain} failed: {e}")
                continue
        logger.info(f"Total waiter sales rows: {len(all_rows)}")
        return all_rows

    @staticmethod
    def aggregate(rows: List[dict]) -> List[dict]:
        if not rows:
            return []
        df = pd.DataFrame(rows)
        if "OpenDate" not in df.columns:
            logger.error("OpenDate missing in waiter OLAP response")
            return []
        df["date"] = pd.to_datetime(df["OpenDate"], format="mixed").dt.date
        grouped = df.groupby(["Department.Id", "date", "WaiterName"], as_index=False).agg(
            total_sales=("DishSumInt", "sum"),
            total_sales_with_discount=("DishDiscountSumInt", "sum"),
        )
        records = []
        for _, row in grouped.iterrows():
            records.append({
                "department_id": row["Department.Id"],
                "date": row["date"],
                "waiter_name": row["WaiterName"],
                "total_sales": float(row["total_sales"]),
                "total_sales_with_discount": (
                    float(row["total_sales_with_discount"])
                    if pd.notna(row["total_sales_with_discount"])
                    else None
                ),
            })
        return records

    def _build_name_to_employee_map(self, names: List[str]) -> Dict[str, Optional[str]]:
        if not names:
            return {}
        unique_names = list({n for n in names if n})
        rows = (
            self.db.query(Employee.id, Employee.name)
            .filter(Employee.name.in_(unique_names))
            .all()
        )
        by_name: Dict[str, List[str]] = defaultdict(list)
        for emp_id, emp_name in rows:
            by_name[emp_name].append(str(emp_id))

        resolved: Dict[str, Optional[str]] = {}
        ambiguous = 0
        for name in unique_names:
            ids = by_name.get(name, [])
            if len(ids) == 1:
                resolved[name] = ids[0]
            else:
                resolved[name] = None
                if len(ids) > 1:
                    ambiguous += 1
                    logger.warning(
                        f"Ambiguous waiter name '{name}' matches {len(ids)} employees"
                    )
        unresolved = sum(1 for v in resolved.values() if v is None)
        logger.info(
            f"Name resolution: total={len(unique_names)}, "
            f"resolved={len(unique_names) - unresolved}, "
            f"unresolved={unresolved}, ambiguous={ambiguous}"
        )
        return resolved

    def upsert(self, records: List[dict]) -> Tuple[int, int, int]:
        if not records:
            return 0, 0, 0

        valid_dept_ids = {
            str(d.id)
            for d in self.db.query(Department.id).filter(
                Department.id.in_(list({r["department_id"] for r in records}))
            ).all()
        }
        skipped_dept = 0
        filtered = []
        for r in records:
            if r["department_id"] not in valid_dept_ids:
                skipped_dept += 1
                continue
            filtered.append(r)
        if skipped_dept:
            logger.warning(f"Skipped {skipped_dept} records: department not in catalog")

        name_map = self._build_name_to_employee_map([r["waiter_name"] for r in filtered])

        now = datetime.utcnow()
        new_count = 0
        updated_count = 0

        for record in filtered:
            existing = (
                self.db.query(SalesByWaiter)
                .filter(
                    SalesByWaiter.department_id == record["department_id"],
                    SalesByWaiter.date == record["date"],
                    SalesByWaiter.waiter_name == record["waiter_name"],
                )
                .first()
            )
            employee_id = name_map.get(record["waiter_name"])
            if existing:
                existing.total_sales = record["total_sales"]
                existing.total_sales_with_discount = record["total_sales_with_discount"]
                existing.employee_id = employee_id
                existing.synced_at = now
                existing.updated_at = now
                updated_count += 1
            else:
                self.db.add(
                    SalesByWaiter(
                        department_id=record["department_id"],
                        date=record["date"],
                        waiter_name=record["waiter_name"],
                        employee_id=employee_id,
                        total_sales=record["total_sales"],
                        total_sales_with_discount=record["total_sales_with_discount"],
                        synced_at=now,
                    )
                )
                new_count += 1

        self.db.commit()
        return new_count, updated_count, skipped_dept

    async def sync(
        self,
        from_date: Optional[date] = None,
        to_date: Optional[date] = None,
        department_id: Optional[str] = None,
    ) -> dict:
        try:
            if not from_date:
                from_date = date.today() - timedelta(days=1)
            if not to_date:
                to_date = from_date

            logger.info(f"Waiter sales sync {from_date}..{to_date} dept={department_id}")
            raw = await self.fetch_from_iiko(from_date, to_date)
            if not raw:
                return {
                    "status": "success",
                    "message": "No waiter sales found",
                    "new": 0,
                    "updated": 0,
                    "skipped": 0,
                    "total_raw_records": 0,
                }

            if department_id:
                before = len(raw)
                raw = [r for r in raw if r.get("Department.Id") == department_id]
                logger.info(f"Filtered by department: {before} -> {len(raw)}")

            records = self.aggregate(raw)
            new_count, updated_count, skipped = self.upsert(records)
            return {
                "status": "success",
                "message": (
                    f"Synced waiter sales {from_date}..{to_date}: "
                    f"{new_count} new + {updated_count} updated, {skipped} skipped"
                ),
                "new": new_count,
                "updated": updated_count,
                "skipped": skipped,
                "total_raw_records": len(raw),
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Waiter sales sync failed: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Waiter sales sync failed: {e}",
                "new": 0,
                "updated": 0,
                "skipped": 0,
                "total_raw_records": 0,
                "error_type": type(e).__name__,
            }
