"""Pure-Python parser tests for `IikoEmployeeLoaderService`.

Covers `_parse_roles_xml`, `_parse_employees_xml`, `_parse_date`,
`_parse_bool`, `_text`. No DB, no network.
"""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy.orm import Session

from app.services.iiko_employee_loader import (
    IikoEmployeeLoaderService,
    _parse_bool,
    _parse_date,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def service() -> IikoEmployeeLoaderService:
    """The XML-parsing methods don't touch the DB at all, but __init__ takes
    a Session — pass `None` since nothing accessed in these tests calls it.
    """
    return IikoEmployeeLoaderService(db=None)  # type: ignore[arg-type]


class TestParseDate:
    def test_full_iso_string(self) -> None:
        assert _parse_date("2026-04-30T12:34:56") == date(2026, 4, 30)

    def test_date_only_iso(self) -> None:
        assert _parse_date("2026-04-30") == date(2026, 4, 30)

    def test_falls_back_to_first_10_chars(self) -> None:
        # iiko sometimes ships timezones python's fromisoformat can't handle.
        # Worst case the loader falls back to slicing the date prefix.
        assert _parse_date("2026-04-30 06:00:00 +05:00") == date(2026, 4, 30)

    def test_none_input_returns_none(self) -> None:
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self) -> None:
        assert _parse_date("") is None

    def test_garbage_returns_none(self) -> None:
        assert _parse_date("not-a-date-at-all") is None


class TestParseBool:
    def test_true_lowercase(self) -> None:
        assert _parse_bool("true") is True

    def test_true_uppercase(self) -> None:
        assert _parse_bool("TRUE") is True

    def test_true_mixed_case_with_whitespace(self) -> None:
        assert _parse_bool("  True  ") is True

    def test_false_returns_false(self) -> None:
        assert _parse_bool("false") is False

    def test_garbage_is_false(self) -> None:
        assert _parse_bool("yes") is False
        assert _parse_bool("1") is False
        assert _parse_bool(None) is False


class TestParseRolesXml:
    def test_extracts_id_and_code_lookups(self, service) -> None:
        xml = """<?xml version="1.0"?>
        <employeeRoles>
            <role>
                <id>role-1</id>
                <code>WR1</code>
                <name>Официант</name>
            </role>
            <role>
                <id>role-2</id>
                <code>BAR</code>
                <name>Бариста</name>
            </role>
        </employeeRoles>"""
        by_id, by_code = service._parse_roles_xml(xml)
        assert by_id == {"role-1": "Официант", "role-2": "Бариста"}
        assert by_code == {"WR1": "Официант", "BAR": "Бариста"}

    def test_skips_role_without_name(self, service) -> None:
        xml = """<?xml version="1.0"?>
        <employeeRoles>
            <role>
                <id>x</id>
                <code>X</code>
            </role>
            <role>
                <id>y</id>
                <code>Y</code>
                <name>Y-Name</name>
            </role>
        </employeeRoles>"""
        by_id, by_code = service._parse_roles_xml(xml)
        assert "x" not in by_id
        assert by_id == {"y": "Y-Name"}

    def test_first_write_wins_for_duplicate_codes(self, service) -> None:
        xml = """<?xml version="1.0"?>
        <employeeRoles>
            <role><id>r1</id><code>WR1</code><name>First</name></role>
            <role><id>r2</id><code>WR1</code><name>Second</name></role>
        </employeeRoles>"""
        _, by_code = service._parse_roles_xml(xml)
        assert by_code["WR1"] == "First"

    def test_malformed_xml_returns_empty(self, service) -> None:
        assert service._parse_roles_xml("<not-xml") == ({}, {})


class TestParseEmployeesXml:
    def _xml(self, employees: str) -> str:
        return f'<?xml version="1.0"?><employees>{employees}</employees>'

    def test_extracts_basic_fields(self, service) -> None:
        xml = self._xml("""
            <employee>
                <id>emp-1</id>
                <code>E001</code>
                <name>Иванов Иван Иванович</name>
                <login>ivanov</login>
                <firstName>Иван</firstName>
                <lastName>Иванов</lastName>
                <middleName>Иванович</middleName>
                <mainRoleCode>WR1</mainRoleCode>
                <mainRoleId>role-1</mainRoleId>
                <preferredDepartmentCode>D001</preferredDepartmentCode>
                <cellPhone>+77001234567</cellPhone>
                <email>ivan@example.com</email>
                <hireDate>2025-01-15</hireDate>
                <fireDate></fireDate>
                <deleted>false</deleted>
            </employee>
        """)
        result = service._parse_employees_xml(xml)
        assert len(result) == 1
        emp = result[0]
        assert emp["id"] == "emp-1"
        assert emp["code"] == "E001"
        assert emp["name"] == "Иванов Иван Иванович"
        assert emp["main_role_code"] == "WR1"
        assert emp["main_role_id"] == "role-1"
        assert emp["hire_date"] == date(2025, 1, 15)
        assert emp["fire_date"] is None
        assert emp["deleted"] is False

    def test_resolves_main_role_name_by_id_first(self, service) -> None:
        xml = self._xml("""
            <employee>
                <id>e1</id>
                <name>X</name>
                <mainRoleId>role-1</mainRoleId>
                <mainRoleCode>WR1</mainRoleCode>
            </employee>
        """)
        result = service._parse_employees_xml(
            xml,
            roles_by_id={"role-1": "By ID"},
            roles_by_code={"WR1": "By Code"},
        )
        # ID lookup wins because role IDs are stable while codes can be empty.
        assert result[0]["main_role_name"] == "By ID"

    def test_falls_back_to_code_when_id_unknown(self, service) -> None:
        xml = self._xml("""
            <employee>
                <id>e1</id>
                <name>X</name>
                <mainRoleId>missing-role</mainRoleId>
                <mainRoleCode>WR1</mainRoleCode>
            </employee>
        """)
        result = service._parse_employees_xml(
            xml,
            roles_by_id={},
            roles_by_code={"WR1": "Fallback"},
        )
        assert result[0]["main_role_name"] == "Fallback"

    def test_extracts_multiple_role_codes_and_dept_codes(self, service) -> None:
        xml = self._xml("""
            <employee>
                <id>e1</id>
                <name>X</name>
                <roleCodes>WR1</roleCodes>
                <roleCodes>BAR</roleCodes>
                <departmentCodes>D001</departmentCodes>
                <departmentCodes>D002</departmentCodes>
            </employee>
        """)
        emp = service._parse_employees_xml(xml)[0]
        assert emp["role_codes"] == ["WR1", "BAR"]
        assert emp["department_codes"] == ["D001", "D002"]

    def test_skips_employee_without_id_or_name(self, service) -> None:
        xml = self._xml("""
            <employee><id>e1</id></employee>
            <employee><name>NoID</name></employee>
            <employee><id>e2</id><name>Valid</name></employee>
        """)
        ids = [e["id"] for e in service._parse_employees_xml(xml)]
        assert ids == ["e2"]

    def test_malformed_xml_returns_empty(self, service) -> None:
        assert service._parse_employees_xml("<not-xml>") == []

    def test_role_codes_empty_when_none_listed(self, service) -> None:
        xml = self._xml(
            "<employee><id>e1</id><name>N</name></employee>"
        )
        emp = service._parse_employees_xml(xml)[0]
        assert emp["role_codes"] is None
        assert emp["department_codes"] is None
