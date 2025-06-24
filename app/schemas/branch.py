from pydantic import BaseModel, field_serializer
from datetime import datetime, date
from typing import Optional, List
from uuid import UUID


class BranchBase(BaseModel):
    branch_id: str
    name: str
    parent_id: Optional[str] = None
    organization_name: str
    organization_bin: str


class BranchCreate(BranchBase):
    pass


class BranchUpdate(BaseModel):
    name: Optional[str] = None
    parent_id: Optional[str] = None
    organization_name: Optional[str] = None
    organization_bin: Optional[str] = None


class Branch(BranchBase):
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class SaleBase(BaseModel):
    branch_id: str
    date: date
    amount: float


class SaleCreate(SaleBase):
    pass


class Sale(SaleBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class ForecastBase(BaseModel):
    branch_id: str
    forecast_date: date
    predicted_amount: float
    model_version: str


class ForecastCreate(ForecastBase):
    pass


class Forecast(ForecastBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class APIBranchResponse(BaseModel):
    object_code: str
    object_name: str
    object_parent: Optional[str]
    object_company: str
    object_bin: str


class DepartmentBase(BaseModel):
    code: Optional[str] = None
    code_tco: Optional[str] = None
    name: str
    type: str = 'DEPARTMENT'
    taxpayer_id_number: Optional[str] = None
    parent_id: Optional[UUID] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: Optional[str] = None
    code_tco: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    taxpayer_id_number: Optional[str] = None
    parent_id: Optional[UUID] = None


class Department(BaseModel):
    id: str
    parent_id: Optional[str] = None
    code: Optional[str] = None
    code_tco: Optional[str] = None
    name: str
    type: str = 'DEPARTMENT'
    taxpayer_id_number: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    synced_at: datetime
    
    class Config:
        from_attributes = True


class SalesSummaryBase(BaseModel):
    department_id: str
    date: date
    total_sales: float


class SalesSummaryCreate(SalesSummaryBase):
    pass


class SalesSummaryUpdate(BaseModel):
    total_sales: Optional[float] = None


class SalesSummary(SalesSummaryBase):
    id: int
    created_at: datetime
    updated_at: datetime
    synced_at: datetime
    
    class Config:
        from_attributes = True


class SalesByHourBase(BaseModel):
    department_id: str
    date: date
    hour: int
    sales_amount: float


class SalesByHourCreate(SalesByHourBase):
    pass


class SalesByHourUpdate(BaseModel):
    sales_amount: Optional[float] = None


class SalesByHour(SalesByHourBase):
    id: int
    created_at: datetime
    updated_at: datetime
    synced_at: datetime
    
    class Config:
        from_attributes = True


class IikoSalesResponse(BaseModel):
    CloseTime: str
    DepartmentId: str = None
    DishSumInt: float
    OrderNum: int
    
    class Config:
        extra = 'allow'
        allow_population_by_field_name = True