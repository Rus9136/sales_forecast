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
    
    # Convert UUIDs to strings
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
            "created_at": dept.created_at,
            "updated_at": dept.updated_at,
            "synced_at": dept.synced_at
        }
        result.append(dept_dict)
    
    return result


@router.get("/{department_id}", response_model=Department)
def get_department(department_id: str, db: Session = Depends(get_db)):
    """Get a specific department by ID"""
    department = db.query(DepartmentModel).filter(DepartmentModel.id == department_id).first()
    if not department:
        raise HTTPException(status_code=404, detail="Department not found")
    return department


@router.post("/", response_model=Department)
def create_department(
    department: DepartmentCreate,
    db: Session = Depends(get_db)
):
    """Create a new department"""
    db_department = DepartmentModel(**department.dict())
    db.add(db_department)
    db.commit()
    db.refresh(db_department)
    return db_department


@router.put("/{department_id}", response_model=Department)
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
    return department


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