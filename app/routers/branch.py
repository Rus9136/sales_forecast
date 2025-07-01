from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from ..db import get_db
from ..models.branch import Branch as BranchModel
from ..schemas.branch import Branch, BranchCreate, BranchUpdate
from ..services.iiko_department_loader import IikoDepartmentLoaderService
from ..auth import get_api_key_or_bypass, ApiKey

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("/", response_model=List[Branch])
def get_branches(
    skip: int = Query(0, ge=0),
    limit: int = Query(10000, ge=1, le=10000),
    organization_bin: Optional[str] = None,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get all branches with optional filtering"""
    query = db.query(BranchModel)
    
    if organization_bin:
        query = query.filter(BranchModel.organization_bin == organization_bin)
    
    branches = query.offset(skip).limit(limit).all()
    return branches


@router.get("/{branch_id}", response_model=Branch)
def get_branch(
    branch_id: str, 
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Get a specific branch by ID"""
    branch = db.query(BranchModel).filter(BranchModel.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    return branch


@router.post("/sync")
async def sync_branches(
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Sync departments from iiko API"""
    try:
        service = IikoDepartmentLoaderService(db)
        total_processed = await service.sync_departments()
        return {"message": f"Successfully processed {total_processed} departments from iiko"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{branch_id}", response_model=Branch)
def update_branch(
    branch_id: str,
    branch_update: BranchUpdate,
    db: Session = Depends(get_db),
    api_key: Optional[ApiKey] = Depends(get_api_key_or_bypass)
):
    """Update a branch"""
    branch = db.query(BranchModel).filter(BranchModel.branch_id == branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")
    
    update_data = branch_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(branch, field, value)
    
    db.commit()
    db.refresh(branch)
    return branch