from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from ..db import get_db
from ..models.branch import Department as DepartmentModel, SalesSummary
from ..schemas.branch import Department, DepartmentCreate, DepartmentUpdate
from ..auth import get_api_key_or_bypass, ApiKey

router = APIRouter(prefix="/departments", tags=["departments"])


def serialize_department(dept, **extra_fields) -> dict:
    """Convert a Department ORM object to a dict with string UUIDs"""
    result = {
        "id": str(dept.id),
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
        "code": dept.code,
        "code_tco": dept.code_tco,
        "name": dept.name,
        "type": dept.type,
        "taxpayer_id_number": dept.taxpayer_id_number,
        "segment_type": dept.segment_type if dept.segment_type else "restaurant",
        "season_start_date": dept.season_start_date.isoformat() if dept.season_start_date else None,
        "season_end_date": dept.season_end_date.isoformat() if dept.season_end_date else None,
        "created_at": dept.created_at,
        "updated_at": dept.updated_at,
        "synced_at": dept.synced_at
    }
    result.update(extra_fields)
    return result


@router.get("/")
def get_departments(
    skip: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    type: Optional[str] = Query("DEPARTMENT", description="Filter by department type. Default: DEPARTMENT (sales points only)"),
    parent_id: Optional[str] = None,
    show_all_types: bool = Query(False, description="Set to true to show all department types"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get departments with smart filtering. By default shows only DEPARTMENT type (actual sales points)"""
    query = db.query(DepartmentModel)

    if show_all_types:
        if type and type != "DEPARTMENT":
            query = query.filter(DepartmentModel.type == type)
    else:
        query = query.filter(DepartmentModel.type == "DEPARTMENT")

    if parent_id:
        query = query.filter(DepartmentModel.parent_id == parent_id)

    departments = query.offset(skip).limit(limit).all()
    return [serialize_department(dept) for dept in departments]


@router.get("/types/stats")
def get_department_types_stats(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get statistics about department types and their sales activity"""

    type_counts = db.query(
        DepartmentModel.type,
        func.count(DepartmentModel.id).label('count')
    ).group_by(DepartmentModel.type).all()

    sales_active_counts = db.query(
        DepartmentModel.type,
        func.count(func.distinct(SalesSummary.department_id)).label('sales_active_count')
    ).join(
        SalesSummary, DepartmentModel.id == SalesSummary.department_id, isouter=True
    ).group_by(DepartmentModel.type).all()

    stats = {}
    for type_name, count in type_counts:
        stats[type_name] = {
            'total_count': count,
            'sales_active_count': 0,
            'description': get_type_description(type_name)
        }

    for type_name, sales_count in sales_active_counts:
        if type_name in stats:
            stats[type_name]['sales_active_count'] = sales_count or 0

    return {
        'stats_by_type': stats,
        'summary': {
            'total_departments': sum(s['total_count'] for s in stats.values()),
            'sales_active_departments': sum(s['sales_active_count'] for s in stats.values()),
            'recommended_filter': 'DEPARTMENT',
            'explanation': 'Only DEPARTMENT type has actual sales data. JURPERSON and CORPORATION are organizational entities.'
        }
    }


@router.get("/sales-points")
def get_sales_points_only(
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    with_sales_data: bool = Query(False, description="Show only departments that have sales data"),
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get only DEPARTMENT type entries (actual sales points) with optional sales data filtering"""

    query = db.query(DepartmentModel).filter(DepartmentModel.type == "DEPARTMENT")

    if with_sales_data:
        query = query.join(SalesSummary, DepartmentModel.id == SalesSummary.department_id)
        query = query.distinct()

    departments = query.offset(skip).limit(limit).all()

    # Single query to get all department IDs that have sales data (instead of N+1)
    dept_ids = [dept.id for dept in departments]
    if dept_ids:
        sales_dept_ids = set(
            row[0] for row in db.query(SalesSummary.department_id)
            .filter(SalesSummary.department_id.in_(dept_ids))
            .distinct()
            .all()
        )
    else:
        sales_dept_ids = set()

    result = [
        serialize_department(dept, has_sales_data=(dept.id in sales_dept_ids))
        for dept in departments
    ]

    return {
        'departments': result,
        'total_count': len(result),
        'filter_applied': 'DEPARTMENT type only',
        'sales_data_filter': with_sales_data
    }


@router.get("/{department_id}")
def get_department(
    department_id: str,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get a specific department by ID"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    return serialize_department(department)


@router.post("/")
def create_department(
    department: DepartmentCreate,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Create a new department"""
    db_department = DepartmentModel(**department.dict())
    db.add(db_department)
    db.commit()
    db.refresh(db_department)
    return serialize_department(db_department)


@router.put("/{department_id}")
def update_department(
    department_id: str,
    department_update: DepartmentUpdate,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Update a department"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    update_data = department_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(department, field, value)

    db.commit()
    db.refresh(department)
    return serialize_department(department)


@router.delete("/{department_id}")
def delete_department(
    department_id: str,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Delete a department"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    db.delete(department)
    db.commit()
    return {"message": f"Department {department_id} deleted successfully"}


@router.get("/{department_id}/children", response_model=List[Department])
def get_department_children(
    department_id: str,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get all children of a specific department"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")

    children = db.query(DepartmentModel).filter(DepartmentModel.parent_id == department_id).all()
    return children


def get_type_description(dept_type: str) -> str:
    """Get human-readable description for department types"""
    descriptions = {
        'DEPARTMENT': 'Торговые точки (реальные места продаж)',
        'JURPERSON': 'Юридические лица (организационные единицы)',
        'CORPORATION': 'Корпорации (верхний уровень иерархии)'
    }
    return descriptions.get(dept_type, 'Неизвестный тип')
