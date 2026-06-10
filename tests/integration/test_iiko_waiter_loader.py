"""DB-backed tests for waiter sales loader: name resolution + upsert.

The `WaiterName → employee_id` lookup is the most subtle piece of the
sync — iiko's OLAP report only ships waiter *names*, not stable IDs, so
the loader matches against `employees.name` and falls back to NULL when
the match is ambiguous (0 or >1 hits).
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.department import Department
from app.models.employee import Employee, SalesByWaiter
from app.services.iiko_waiter_sales_loader import IikoWaiterSalesLoaderService

pytestmark = pytest.mark.integration


@pytest.fixture()
def loader(db_session: Session) -> IikoWaiterSalesLoaderService:
    return IikoWaiterSalesLoaderService(db=db_session)


@pytest.fixture()
def alice_employee(db_session: Session) -> Employee:
    emp = Employee(id=uuid4(), name="Alice Cooper", deleted=False)
    db_session.add(emp)
    db_session.commit()
    db_session.refresh(emp)
    return emp


@pytest.fixture()
def alpha_dept(db_session: Session) -> Department:
    dept = Department(
        id=uuid4(), code="D001", name="Alpha", type="DEPARTMENT",
        iiko_source_domain="test.iiko.it",
    )
    db_session.add(dept)
    db_session.commit()
    db_session.refresh(dept)
    return dept


class TestNameResolution:
    def test_unique_match_resolves_to_employee_id(
        self, loader, alice_employee: Employee
    ) -> None:
        result = loader._build_name_to_employee_map(["Alice Cooper"])
        assert result["Alice Cooper"] == str(alice_employee.id)

    def test_no_match_resolves_to_none(self, loader) -> None:
        result = loader._build_name_to_employee_map(["Ghost Waiter"])
        assert result["Ghost Waiter"] is None

    def test_ambiguous_match_resolves_to_none(
        self, db_session: Session, loader
    ) -> None:
        # Two employees with the same display name → ambiguous.
        db_session.add_all([
            Employee(id=uuid4(), name="Twin", deleted=False),
            Employee(id=uuid4(), name="Twin", deleted=False),
        ])
        db_session.commit()

        result = loader._build_name_to_employee_map(["Twin"])
        assert result["Twin"] is None

    def test_empty_input_returns_empty(self, loader) -> None:
        assert loader._build_name_to_employee_map([]) == {}

    def test_filters_out_empty_strings(self, loader, alice_employee) -> None:
        # Empty/None waiter names shouldn't trip the IN(...) query.
        result = loader._build_name_to_employee_map(["Alice Cooper", "", None])  # type: ignore[list-item]
        assert result["Alice Cooper"] == str(alice_employee.id)
        assert "" not in result


class TestUpsert:
    def test_skips_records_for_unknown_department(
        self, db_session: Session, loader
    ) -> None:
        # No department exists with this id — record must be silently skipped.
        records = [{
            "department_id": str(uuid4()),
            "date": date(2026, 4, 1),
            "waiter_name": "Alice Cooper",
            "total_sales": 1000.0,
            "total_sales_with_discount": 950.0,
        }]
        new, updated, skipped = loader.upsert(records)
        assert (new, updated, skipped) == (0, 0, 1)
        assert db_session.query(SalesByWaiter).count() == 0

    def test_inserts_new_record_with_resolved_employee_id(
        self,
        db_session: Session,
        loader,
        alpha_dept: Department,
        alice_employee: Employee,
    ) -> None:
        records = [{
            "department_id": str(alpha_dept.id),
            "date": date(2026, 4, 1),
            "waiter_name": "Alice Cooper",
            "total_sales": 1000.0,
            "total_sales_with_discount": 950.0,
        }]
        new, updated, skipped = loader.upsert(records)
        assert (new, updated, skipped) == (1, 0, 0)

        row = db_session.query(SalesByWaiter).one()
        assert str(row.employee_id) == str(alice_employee.id)
        assert row.total_sales == 1000.0

    def test_inserts_with_null_employee_id_when_name_unknown(
        self, db_session: Session, loader, alpha_dept: Department
    ) -> None:
        records = [{
            "department_id": str(alpha_dept.id),
            "date": date(2026, 4, 1),
            "waiter_name": "Unknown Person",
            "total_sales": 500.0,
            "total_sales_with_discount": 500.0,
        }]
        loader.upsert(records)
        row = db_session.query(SalesByWaiter).one()
        assert row.employee_id is None

    def test_updates_existing_record(
        self,
        db_session: Session,
        loader,
        alpha_dept: Department,
        alice_employee: Employee,
    ) -> None:
        # Seed an existing row for the same (dept, date, waiter).
        db_session.add(SalesByWaiter(
            department_id=alpha_dept.id,
            date=date(2026, 4, 1),
            waiter_name="Alice Cooper",
            total_sales=100.0,
            total_sales_with_discount=100.0,
        ))
        db_session.commit()

        records = [{
            "department_id": str(alpha_dept.id),
            "date": date(2026, 4, 1),
            "waiter_name": "Alice Cooper",
            "total_sales": 9999.0,
            "total_sales_with_discount": 9000.0,
        }]
        new, updated, skipped = loader.upsert(records)
        assert (new, updated, skipped) == (0, 1, 0)

        row = db_session.query(SalesByWaiter).one()
        assert row.total_sales == 9999.0
        assert str(row.employee_id) == str(alice_employee.id)
