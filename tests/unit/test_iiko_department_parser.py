"""Pure-Python parser tests for IikoDepartmentLoaderService."""

from __future__ import annotations

import pytest

from app.services.iiko_department_loader import IikoDepartmentLoaderService

pytestmark = pytest.mark.unit


@pytest.fixture
def loader():
    return IikoDepartmentLoaderService(db=None)  # type: ignore[arg-type]


class TestParseDepartmentsXml:
    def test_extracts_basic_department_fields(self, loader) -> None:
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>dept-1</id>
                <parentId>jur-1</parentId>
                <code>D001</code>
                <name>Alpha Branch</name>
                <type>DEPARTMENT</type>
            </corporateItemDto>
        </departments>"""
        result = loader._parse_departments_xml(xml)
        assert len(result) == 1
        d = result[0]
        assert d["id"] == "dept-1"
        assert d["parent_id"] == "jur-1"
        assert d["code"] == "D001"
        assert d["name"] == "Alpha Branch"
        assert d["type"] == "DEPARTMENT"

    def test_top_level_taxpayer_id_for_department(self, loader) -> None:
        # DEPARTMENT type stores BIN at top level.
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>d1</id>
                <name>X</name>
                <type>DEPARTMENT</type>
                <taxpayerIdNumber>123456789012</taxpayerIdNumber>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert d["taxpayer_id_number"] == "123456789012"

    def test_nested_taxpayer_id_for_jurperson(self, loader) -> None:
        # JURPERSON nests BIN inside <jurPersonAdditionalPropertiesDto>.
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>j1</id>
                <name>Y</name>
                <type>JURPERSON</type>
                <jurPersonAdditionalPropertiesDto>
                    <taxpayerId>987654321098</taxpayerId>
                </jurPersonAdditionalPropertiesDto>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert d["taxpayer_id_number"] == "987654321098"

    def test_top_level_takes_priority_over_nested(self, loader) -> None:
        # If both fields are populated, top-level wins (matches loader logic).
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>x</id>
                <name>X</name>
                <type>DEPARTMENT</type>
                <taxpayerIdNumber>TOP-LEVEL</taxpayerIdNumber>
                <jurPersonAdditionalPropertiesDto>
                    <taxpayerId>NESTED</taxpayerId>
                </jurPersonAdditionalPropertiesDto>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert d["taxpayer_id_number"] == "TOP-LEVEL"

    def test_taxpayer_none_when_neither_field_present(self, loader) -> None:
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>x</id>
                <name>X</name>
                <type>DEPARTMENT</type>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert d["taxpayer_id_number"] is None

    def test_empty_taxpayer_value_falls_back_to_nested(self, loader) -> None:
        # Whitespace-only top-level → fall back to nested.
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>x</id>
                <name>X</name>
                <type>DEPARTMENT</type>
                <taxpayerIdNumber>   </taxpayerIdNumber>
                <jurPersonAdditionalPropertiesDto>
                    <taxpayerId>FROM-NESTED</taxpayerId>
                </jurPersonAdditionalPropertiesDto>
            </corporateItemDto>
        </departments>"""
        d = loader._parse_departments_xml(xml)[0]
        assert d["taxpayer_id_number"] == "FROM-NESTED"

    def test_default_type_when_missing(self, loader) -> None:
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto>
                <id>x</id>
                <name>X</name>
            </corporateItemDto>
        </departments>"""
        # Loader defaults to DEPARTMENT when <type> is missing.
        d = loader._parse_departments_xml(xml)[0]
        assert d["type"] == "DEPARTMENT"

    def test_malformed_xml_raises_parse_error(self, loader) -> None:
        from xml.etree.ElementTree import ParseError

        with pytest.raises(ParseError):
            loader._parse_departments_xml("<not-xml>")

    def test_extracts_multiple_departments(self, loader) -> None:
        xml = """<?xml version="1.0"?>
        <departments>
            <corporateItemDto><id>1</id><name>A</name><type>DEPARTMENT</type></corporateItemDto>
            <corporateItemDto><id>2</id><name>B</name><type>JURPERSON</type></corporateItemDto>
            <corporateItemDto><id>3</id><name>C</name><type>CORPORATION</type></corporateItemDto>
        </departments>"""
        result = loader._parse_departments_xml(xml)
        assert [d["id"] for d in result] == ["1", "2", "3"]
        assert [d["type"] for d in result] == ["DEPARTMENT", "JURPERSON", "CORPORATION"]
