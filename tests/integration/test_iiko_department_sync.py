"""DB-backed test for the multi-pass parent-first ordering in department sync.

iiko returns departments in arbitrary order, but our schema enforces a
self-referential FK (`departments.parent_id → departments.id`). The
loader runs `sync_departments` in *passes*: in each pass it processes
only the rows whose parent is already in the DB (or has no parent),
deferring the rest to the next pass. This test seeds an iiko response
where children come BEFORE their parents and verifies the final state
has every node correctly linked.
"""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.models.department import Department
from app.services.iiko_department_loader import IikoDepartmentLoaderService

pytestmark = pytest.mark.integration


@pytest.fixture()
def loader(db_session: Session) -> IikoDepartmentLoaderService:
    return IikoDepartmentLoaderService(db=db_session)


def _did(prefix: str) -> str:
    """Stable UUID-like id for a given prefix."""
    # Deterministic UUIDs make logs easier to read but aren't required.
    return str(uuid4())


class TestSyncDepartments:
    async def test_inserts_parents_before_children_when_order_reversed(
        self, db_session: Session, loader
    ) -> None:
        # iiko returns children FIRST, parents SECOND. Loader must reorder.
        jur_id, dept_id, sub_id = _did("J"), _did("D"), _did("S")

        iiko_response = [
            # Child of dept (deepest)
            {"id": sub_id, "parent_id": dept_id, "code": "S001",
             "name": "Sub", "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            # Mid-level dept (parent of Sub)
            {"id": dept_id, "parent_id": jur_id, "code": "D001",
             "name": "Dept", "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            # Root (parent of Dept)
            {"id": jur_id, "parent_id": None, "code": "J001",
             "name": "JurPerson", "type": "JURPERSON", "taxpayer_id_number": "12345",
             "iiko_source_domain": "test.iiko.it"},
        ]

        with patch.object(
            loader, "fetch_departments_from_iiko", return_value=iiko_response
        ):
            total = await loader.sync_departments()

        assert total == 3
        rows = {str(d.id): d for d in db_session.query(Department).all()}
        assert str(jur_id) in rows
        assert str(dept_id) in rows
        assert str(sub_id) in rows
        # FK chain holds.
        assert str(rows[str(sub_id)].parent_id) == str(dept_id)
        assert str(rows[str(dept_id)].parent_id) == str(jur_id)
        assert rows[str(jur_id)].parent_id is None

    async def test_inherits_taxpayer_id_from_parent_jurperson(
        self, db_session: Session, loader
    ) -> None:
        # When a DEPARTMENT has no BIN of its own, it inherits the parent's.
        jur_id, dept_id = _did("J"), _did("D")
        with patch.object(
            loader,
            "fetch_departments_from_iiko",
            return_value=[
                {"id": jur_id, "parent_id": None, "code": "J", "name": "Jur",
                 "type": "JURPERSON", "taxpayer_id_number": "BIN-FROM-JUR",
             "iiko_source_domain": "test.iiko.it"},
                {"id": dept_id, "parent_id": jur_id, "code": "D", "name": "Dept",
                 "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            ],
        ):
            await loader.sync_departments()

        dept = db_session.query(Department).filter_by(id=dept_id).one()
        assert dept.taxpayer_id_number == "BIN-FROM-JUR"

    async def test_idempotent_resync_updates_existing_rows(
        self, db_session: Session, loader
    ) -> None:
        dept_id = _did("D")
        first_response = [
            {"id": dept_id, "parent_id": None, "code": "OLD", "name": "Old Name",
             "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
        ]
        second_response = [
            {"id": dept_id, "parent_id": None, "code": "NEW", "name": "New Name",
             "type": "DEPARTMENT", "taxpayer_id_number": "NEW-BIN",
             "iiko_source_domain": "test.iiko.it"},
        ]

        with patch.object(loader, "fetch_departments_from_iiko", return_value=first_response):
            await loader.sync_departments()
        with patch.object(loader, "fetch_departments_from_iiko", return_value=second_response):
            await loader.sync_departments()

        # Still ONE row; iiko-managed fields updated.
        rows = db_session.query(Department).filter_by(id=dept_id).all()
        assert len(rows) == 1
        assert rows[0].name == "New Name"
        assert rows[0].code == "NEW"
        assert rows[0].taxpayer_id_number == "NEW-BIN"

    async def test_orphaned_departments_skipped_not_inserted(
        self, db_session: Session, loader
    ) -> None:
        # Department whose parent_id points at something that doesn't exist
        # AND isn't in this batch must be skipped (cannot satisfy FK).
        orphan_id = _did("O")
        with patch.object(
            loader,
            "fetch_departments_from_iiko",
            return_value=[
                {"id": orphan_id, "parent_id": str(uuid4()), "code": "ORPH",
                 "name": "Orphan", "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            ],
        ):
            total = await loader.sync_departments()

        # Loader logs a warning and skips — total reflects only successful inserts.
        assert total == 0
        assert db_session.query(Department).filter_by(id=orphan_id).one_or_none() is None

    async def test_does_not_overwrite_manual_segment_type_on_resync(
        self, db_session: Session, loader
    ) -> None:
        # Manual UI-only fields (segment_type, season_*, brand, etc.) must
        # survive a sync — the loader only touches iiko-managed columns.
        dept_id = _did("D")

        # Initial sync.
        with patch.object(
            loader,
            "fetch_departments_from_iiko",
            return_value=[
                {"id": dept_id, "parent_id": None, "code": "D", "name": "X",
                 "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            ],
        ):
            await loader.sync_departments()

        # Operator fills in segment_type via the UI.
        d = db_session.query(Department).filter_by(id=dept_id).one()
        d.segment_type = "coffeehouse"
        db_session.commit()

        # Re-sync with iiko sending the same row.
        with patch.object(
            loader,
            "fetch_departments_from_iiko",
            return_value=[
                {"id": dept_id, "parent_id": None, "code": "D", "name": "X-renamed",
                 "type": "DEPARTMENT", "taxpayer_id_number": None,
             "iiko_source_domain": "test.iiko.it"},
            ],
        ):
            await loader.sync_departments()

        d_after = db_session.query(Department).filter_by(id=dept_id).one()
        assert d_after.name == "X-renamed"  # iiko-managed: updated
        assert d_after.segment_type == "coffeehouse"  # manual: preserved
