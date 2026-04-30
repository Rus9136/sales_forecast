from pydantic import BaseModel, Field, field_serializer
from datetime import datetime, date
from typing import Optional, List, Literal
from uuid import UUID
from enum import Enum


class SegmentType(str, Enum):
    """Типы подразделений для прогнозирования"""
    COFFEEHOUSE = "coffeehouse"      # Кофейня
    RESTAURANT = "restaurant"        # Ресторан
    CONFECTIONERY = "confectionery"  # Кондитерская
    FOOD_COURT = "food_court"        # Фудкорт в ТРЦ
    STORE = "store"                  # Магазин
    FAST_FOOD = "fast_food"          # Фаст-фуд
    BAKERY = "bakery"                # Пекарня
    CAFE = "cafe"                    # Кафе
    BAR = "bar"                      # Бар


LocationType = Literal[
    'city_center',
    'mall',
    'business_district',
    'resort_mountain',
    'resort_lake',
    'visit_center',
    'other',
]

SeasonalityIntensity = Literal['none', 'low', 'medium', 'high']


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
    segment_type: Optional[SegmentType] = SegmentType.RESTAURANT
    season_start_date: Optional[date] = None
    season_end_date: Optional[date] = None

    # Operational characteristics (manual-only, ML features)
    brand: Optional[str] = None
    location_type: Optional[LocationType] = None
    tourist_traffic_dependent: bool = False
    is_24_7: bool = False
    opening_hour: Optional[int] = Field(default=None, ge=0, le=23)
    closing_hour: Optional[int] = Field(default=None, ge=0, le=24)
    seasonality_intensity: SeasonalityIntensity = 'none'
    city: Optional[str] = None
    opened_date: Optional[date] = None
    season_start_month: Optional[int] = Field(default=None, ge=1, le=12)
    season_end_month: Optional[int] = Field(default=None, ge=1, le=12)


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(BaseModel):
    code: Optional[str] = None
    code_tco: Optional[str] = None
    name: Optional[str] = None
    type: Optional[str] = None
    taxpayer_id_number: Optional[str] = None
    parent_id: Optional[UUID] = None
    segment_type: Optional[SegmentType] = None
    season_start_date: Optional[date] = None
    season_end_date: Optional[date] = None

    # Operational characteristics (manual-only, ML features)
    brand: Optional[str] = None
    location_type: Optional[LocationType] = None
    tourist_traffic_dependent: Optional[bool] = None
    is_24_7: Optional[bool] = None
    opening_hour: Optional[int] = Field(default=None, ge=0, le=23)
    closing_hour: Optional[int] = Field(default=None, ge=0, le=24)
    seasonality_intensity: Optional[SeasonalityIntensity] = None
    city: Optional[str] = None
    opened_date: Optional[date] = None
    season_start_month: Optional[int] = Field(default=None, ge=1, le=12)
    season_end_month: Optional[int] = Field(default=None, ge=1, le=12)


class Department(BaseModel):
    id: str
    parent_id: Optional[str] = None
    code: Optional[str] = None
    code_tco: Optional[str] = None
    name: str
    type: str = 'DEPARTMENT'
    taxpayer_id_number: Optional[str] = None
    segment_type: Optional[SegmentType] = SegmentType.RESTAURANT
    season_start_date: Optional[date] = None
    season_end_date: Optional[date] = None

    brand: Optional[str] = None
    location_type: Optional[LocationType] = None
    tourist_traffic_dependent: bool = False
    is_24_7: bool = False
    opening_hour: Optional[int] = None
    closing_hour: Optional[int] = None
    seasonality_intensity: SeasonalityIntensity = 'none'
    city: Optional[str] = None
    opened_date: Optional[date] = None
    season_start_month: Optional[int] = None
    season_end_month: Optional[int] = None

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