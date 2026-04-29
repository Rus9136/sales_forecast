import httpx
import logging
from datetime import datetime, date
from typing import List, Optional
from xml.etree import ElementTree as ET

from sqlalchemy.orm import Session

from ..config import settings
from ..models.employee import Employee
from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)


def _text(el: Optional[ET.Element]) -> Optional[str]:
    if el is None or el.text is None:
        return None
    text = el.text.strip()
    return text or None


def _parse_date(value: Optional[str]) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).date()
    except ValueError:
        try:
            return datetime.strptime(value[:10], "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"Could not parse date value: {value}")
            return None


def _parse_bool(value: Optional[str]) -> bool:
    return (value or "").strip().lower() == "true"


class IikoEmployeeLoaderService:
    def __init__(self, db: Session):
        self.db = db
        self.domains = [d.strip() for d in settings.IIKO_DOMAINS.split(",") if d.strip()]

    async def fetch_employees_from_single_domain(self, base_url: str) -> List[dict]:
        try:
            auth_service = IikoAuthService(base_url)
            token = await auth_service._refresh_token()

            async with httpx.AsyncClient(timeout=60.0) as client:
                roles_resp = await client.get(
                    f"{base_url}/resto/api/employees/roles",
                    params={"key": token},
                )
                roles_resp.raise_for_status()
                roles_by_id, roles_by_code = self._parse_roles_xml(roles_resp.text)
                logger.info(
                    f"Fetched {len(roles_by_id)} roles from {base_url}"
                )

                response = await client.get(
                    f"{base_url}/resto/api/employees",
                    params={"key": token, "includeDeleted": "true"},
                )
                response.raise_for_status()
                employees = self._parse_employees_xml(
                    response.text, roles_by_id, roles_by_code
                )
                logger.info(f"Fetched {len(employees)} employees from {base_url}")
                return employees
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching employees from {base_url}: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching employees from {base_url}: {e}")
            return []

    def _parse_roles_xml(self, xml_text: str) -> tuple[dict, dict]:
        """Parse /resto/api/employees/roles -> (by_id, by_code) lookup maps."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"Failed to parse roles XML: {e}")
            return {}, {}
        by_id: dict = {}
        by_code: dict = {}
        for role in root.findall("role"):
            rid = _text(role.find("id"))
            code = _text(role.find("code"))
            name = _text(role.find("name"))
            if not name:
                continue
            if rid:
                by_id[rid] = name
            if code:
                # First-write-wins; if both domains have same code with different names,
                # the first one parsed remains. Per-domain lookup avoids cross-domain mixing
                # because each domain calls _parse_roles_xml on its own.
                by_code.setdefault(code, name)
        return by_id, by_code

    def _parse_employees_xml(
        self,
        xml_text: str,
        roles_by_id: Optional[dict] = None,
        roles_by_code: Optional[dict] = None,
    ) -> List[dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"Failed to parse employees XML: {e}")
            return []

        roles_by_id = roles_by_id or {}
        roles_by_code = roles_by_code or {}

        result = []
        for emp in root.findall("employee"):
            emp_id = _text(emp.find("id"))
            name = _text(emp.find("name"))
            if not emp_id or not name:
                continue

            role_codes = [
                _text(rc) for rc in emp.findall("roleCodes") if _text(rc)
            ]
            department_codes = [
                _text(dc) for dc in emp.findall("departmentCodes") if _text(dc)
            ]

            main_role_id = _text(emp.find("mainRoleId"))
            main_role_code = _text(emp.find("mainRoleCode"))
            # Prefer ID-based lookup (stable even when role code is empty/non-Latin).
            main_role_name = (
                roles_by_id.get(main_role_id)
                or roles_by_code.get(main_role_code)
            )

            result.append({
                "id": emp_id,
                "code": _text(emp.find("code")),
                "name": name,
                "login": _text(emp.find("login")),
                "first_name": _text(emp.find("firstName")),
                "middle_name": _text(emp.find("middleName")),
                "last_name": _text(emp.find("lastName")),
                "main_role_code": main_role_code,
                "main_role_id": main_role_id,
                "main_role_name": main_role_name,
                "role_codes": role_codes or None,
                "department_codes": department_codes or None,
                "preferred_department_code": _text(emp.find("preferredDepartmentCode")),
                "cell_phone": _text(emp.find("cellPhone")),
                "email": _text(emp.find("email")),
                "hire_date": _parse_date(_text(emp.find("hireDate"))),
                "fire_date": _parse_date(_text(emp.find("fireDate"))),
                "deleted": _parse_bool(_text(emp.find("deleted"))),
            })
        return result

    async def fetch_employees_from_iiko(self) -> List[dict]:
        seen_ids = set()
        merged = []
        for domain in self.domains:
            try:
                logger.info(f"Fetching employees from {domain}")
                items = await self.fetch_employees_from_single_domain(domain)
                for emp in items:
                    if emp["id"] in seen_ids:
                        continue
                    seen_ids.add(emp["id"])
                    merged.append(emp)
            except Exception as e:
                logger.error(f"Failed to fetch employees from {domain}: {e}")
                continue
        logger.info(f"Total unique employees across domains: {len(merged)}")
        return merged

    def upsert_employees(self, records: List[dict]) -> tuple[int, int]:
        new_count = 0
        updated_count = 0
        now = datetime.utcnow()

        for record in records:
            existing = self.db.query(Employee).filter(Employee.id == record["id"]).first()
            if existing:
                for key, value in record.items():
                    if key == "id":
                        continue
                    setattr(existing, key, value)
                existing.synced_at = now
                existing.updated_at = now
                updated_count += 1
            else:
                self.db.add(Employee(**record, synced_at=now))
                new_count += 1

        self.db.commit()
        logger.info(f"Synced employees: {new_count} new, {updated_count} updated")
        return new_count, updated_count

    async def sync_employees(self) -> dict:
        try:
            records = await self.fetch_employees_from_iiko()
            if not records:
                return {
                    "status": "success",
                    "message": "No employees fetched",
                    "new": 0,
                    "updated": 0,
                    "total": 0,
                }
            new_count, updated_count = self.upsert_employees(records)
            return {
                "status": "success",
                "message": f"Synced {new_count} new + {updated_count} updated employees",
                "new": new_count,
                "updated": updated_count,
                "total": len(records),
            }
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error syncing employees: {e}", exc_info=True)
            return {
                "status": "error",
                "message": f"Employees sync failed: {e}",
                "new": 0,
                "updated": 0,
                "total": 0,
            }
