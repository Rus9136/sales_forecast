from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from ..models.branch import Department as DepartmentModel
from ..schemas.branch import Department, DepartmentCreate, DepartmentUpdate

router = APIRouter(prefix="/departments", tags=["departments"])


@router.get("/")
def get_departments(
    skip: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    type: Optional[str] = None,
    parent_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get all departments with optional filtering"""
    query = db.query(DepartmentModel)
    
    if type:
        query = query.filter(DepartmentModel.type == type)
    
    if parent_id:
        query = query.filter(DepartmentModel.parent_id == parent_id)
    
    departments = query.offset(skip).limit(limit).all()
    
    # Convert UUIDs to strings and include new fields
    result = []
    for dept in departments:
        dept_dict = {
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
        result.append(dept_dict)
    
    return result


@router.get("/{department_id}")
def get_department(department_id: str, db: Session = Depends(get_db)):
    """Get a specific department by ID"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    
    # Convert UUIDs to strings and include new fields (same format as list endpoint)
    return {
        "id": str(department.id),
        "parent_id": str(department.parent_id) if department.parent_id else None,
        "code": department.code,
        "code_tco": department.code_tco,
        "name": department.name,
        "type": department.type,
        "taxpayer_id_number": department.taxpayer_id_number,
        "segment_type": department.segment_type if department.segment_type else "restaurant",
        "season_start_date": department.season_start_date.isoformat() if department.season_start_date else None,
        "season_end_date": department.season_end_date.isoformat() if department.season_end_date else None,
        "created_at": department.created_at,
        "updated_at": department.updated_at,
        "synced_at": department.synced_at
    }


@router.post("/")
def create_department(
    department: DepartmentCreate,
    db: Session = Depends(get_db)
):
    """Create a new department"""
    db_department = DepartmentModel(**department.dict())
    db.add(db_department)
    db.commit()
    db.refresh(db_department)
    
    # Return formatted response
    return {
        "id": str(db_department.id),
        "parent_id": str(db_department.parent_id) if db_department.parent_id else None,
        "code": db_department.code,
        "code_tco": db_department.code_tco,
        "name": db_department.name,
        "type": db_department.type,
        "taxpayer_id_number": db_department.taxpayer_id_number,
        "segment_type": db_department.segment_type if db_department.segment_type else "restaurant",
        "season_start_date": db_department.season_start_date.isoformat() if db_department.season_start_date else None,
        "season_end_date": db_department.season_end_date.isoformat() if db_department.season_end_date else None,
        "created_at": db_department.created_at,
        "updated_at": db_department.updated_at,
        "synced_at": db_department.synced_at
    }


@router.put("/{department_id}")
def update_department(
    department_id: str,
    department_update: DepartmentUpdate,
    db: Session = Depends(get_db)
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
    
    # Return formatted response
    return {
        "id": str(department.id),
        "parent_id": str(department.parent_id) if department.parent_id else None,
        "code": department.code,
        "code_tco": department.code_tco,
        "name": department.name,
        "type": department.type,
        "taxpayer_id_number": department.taxpayer_id_number,
        "segment_type": department.segment_type if department.segment_type else "restaurant",
        "season_start_date": department.season_start_date.isoformat() if department.season_start_date else None,
        "season_end_date": department.season_end_date.isoformat() if department.season_end_date else None,
        "created_at": department.created_at,
        "updated_at": department.updated_at,
        "synced_at": department.synced_at
    }


@router.delete("/{department_id}")
def delete_department(department_id: str, db: Session = Depends(get_db)):
    """Delete a department"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    
    db.delete(department)
    db.commit()
    return {"message": f"Department {department_id} deleted successfully"}


@router.get("/{department_id}/children", response_model=List[Department])
def get_department_children(department_id: str, db: Session = Depends(get_db)):
    """Get all children of a specific department"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    
    children = db.query(DepartmentModel).filter(DepartmentModel.parent_id == department_id).all()
    return children