from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from ..auth import ApiKey, get_api_key_or_bypass
from ..db import get_db
from ..models.employee import Employee
from ..services.iiko_employee_loader import IikoEmployeeLoaderService

router = APIRouter(prefix="/employees", tags=["employees"])


def _serialize(emp: Employee) -> dict:
    return {
        "id": str(emp.id),
        "code": emp.code,
        "name": emp.name,
        "login": emp.login,
        "first_name": emp.first_name,
        "middle_name": emp.middle_name,
        "last_name": emp.last_name,
        "main_role_code": emp.main_role_code,
        "main_role_name": emp.main_role_name,
        "role_codes": emp.role_codes,
        "department_codes": emp.department_codes,
        "preferred_department_code": emp.preferred_department_code,
        "cell_phone": emp.cell_phone,
        "email": emp.email,
        "hire_date": emp.hire_date,
        "fire_date": emp.fire_date,
        "deleted": emp.deleted,
        "synced_at": emp.synced_at,
    }


@router.get("/")
def list_employees(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    search: Optional[str] = Query(None, description="Substring of employee name"),
    role_code: Optional[str] = Query(None, description="Filter by main role code"),
    department_code: Optional[str] = Query(None, description="Filter by preferred department code"),
    include_deleted: bool = Query(False),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
) -> List[dict]:
    query = db.query(Employee)
    if not include_deleted:
        query = query.filter(Employee.deleted.is_(False))
    if search:
        query = query.filter(Employee.name.ilike(f"%{search}%"))
    if role_code:
        query = query.filter(Employee.main_role_code == role_code)
    if department_code:
        query = query.filter(Employee.preferred_department_code == department_code)
    employees = query.order_by(Employee.name).offset(skip).limit(limit).all()
    return [_serialize(e) for e in employees]


@router.post("/sync")
async def sync_employees(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass),
):
    loader = IikoEmployeeLoaderService(db)
    return await loader.sync_employees()
