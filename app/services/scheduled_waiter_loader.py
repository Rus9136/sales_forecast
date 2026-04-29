import asyncio
import concurrent.futures
import logging
from datetime import date, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..db import get_db
from ..models.employee import SalesByWaiter
from .iiko_employee_loader import IikoEmployeeLoaderService
from .iiko_waiter_sales_loader import IikoWaiterSalesLoaderService

logger = logging.getLogger(__name__)

# Минимальный порог: ниже этого значения gap-check не триггерит ресинк
# (защита от ложного срабатывания на маленьких сетях).
EXPECTED_MIN_WAITER_DEPARTMENTS = 5


async def _sync_employees() -> dict:
    db: Session = next(get_db())
    try:
        loader = IikoEmployeeLoaderService(db)
        return await loader.sync_employees()
    finally:
        db.close()


async def _sync_waiter_sales() -> dict:
    db: Session = next(get_db())
    try:
        # iiko OLAP needs from < to (otherwise 409). Mirror the existing main sync trick.
        yesterday = date.today() - timedelta(days=1)
        loader = IikoWaiterSalesLoaderService(db)
        return await loader.sync(yesterday, date.today())
    finally:
        db.close()


async def _check_waiter_gaps(days_back: int = 7) -> dict:
    """Look for missing waiter sales over the last N days and resync them."""
    db: Session = next(get_db())
    try:
        active_dept_ids = {
            row[0]
            for row in db.query(SalesByWaiter.department_id)
            .filter(SalesByWaiter.date >= date.today() - timedelta(days=30))
            .distinct()
            .all()
        }
        if not active_dept_ids:
            logger.info("Waiter gap check: no active departments")
            return {
                "status": "success",
                "message": "No active waiter-sales departments",
                "resynced_dates": [],
            }

        expected = len(active_dept_ids)
        logger.info(f"Waiter gap check: expected {expected} active departments")

        loader = IikoWaiterSalesLoaderService(db)
        resynced = []

        for i in range(days_back):
            check_date = date.today() - timedelta(days=i + 1)
            dept_count = (
                db.query(func.count(func.distinct(SalesByWaiter.department_id)))
                .filter(SalesByWaiter.date == check_date)
                .scalar()
                or 0
            )
            logger.info(f"Waiter gap check {check_date}: {dept_count}/{expected}")

            if (
                dept_count < expected - 2
                and dept_count < EXPECTED_MIN_WAITER_DEPARTMENTS
            ):
                # Missing/under-counted: resync. iiko OLAP needs from < to.
                logger.warning(
                    f"Waiter gap detected for {check_date}: only {dept_count} departments — resyncing"
                )
                result = await loader.sync(check_date, check_date + timedelta(days=1))
                if result.get("status") == "success":
                    after = (result.get("new") or 0) + (result.get("updated") or 0)
                    resynced.append({
                        "date": str(check_date),
                        "before": dept_count,
                        "after": after,
                    })
                    logger.info(
                        f"Waiter resync for {check_date}: before={dept_count}, after={after}"
                    )
                else:
                    logger.error(
                        f"Waiter resync for {check_date} failed: {result.get('message')}"
                    )

        return {
            "status": "success",
            "message": f"Checked {days_back} days, resynced {len(resynced)} dates",
            "resynced_dates": resynced,
        }
    finally:
        db.close()


def _run_async(coro_factory, timeout: int):
    try:
        asyncio.get_running_loop()
        # Already in a loop — run in a fresh thread.
        def runner():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(coro_factory())
            finally:
                new_loop.close()

        with concurrent.futures.ThreadPoolExecutor() as executor:
            return executor.submit(runner).result(timeout=timeout)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro_factory())
        finally:
            loop.close()


def run_employees_sync():
    logger.info("Scheduler triggered: employees sync")
    try:
        result = _run_async(_sync_employees, timeout=300)
        logger.info(f"Employees sync completed: {result.get('status')} — {result.get('message')}")
        return result
    except Exception as e:
        logger.error(f"Employees sync scheduler failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def run_waiter_sales_sync():
    logger.info("Scheduler triggered: waiter sales sync")
    try:
        result = _run_async(_sync_waiter_sales, timeout=600)
        logger.info(f"Waiter sales sync completed: {result.get('status')} — {result.get('message')}")
        return result
    except Exception as e:
        logger.error(f"Waiter sales sync scheduler failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}


def run_waiter_gap_check():
    logger.info("Scheduler triggered: waiter sales gap check")
    try:
        result = _run_async(_check_waiter_gaps, timeout=900)
        logger.info(f"Waiter gap check completed: {result.get('message')}")
        return result
    except Exception as e:
        logger.error(f"Waiter gap check failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}
