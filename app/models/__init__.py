"""SQLAlchemy models — import all to ensure mapper registration."""

from .department import Department  # noqa: F401
from .sales import SalesSummary, SalesByHour, AutoSyncLog  # noqa: F401
from .forecast import Forecast, ForecastAccuracyLog, PostprocessingSettings  # noqa: F401
from .ml import ModelVersion, ModelRetrainingLog  # noqa: F401
from .branch import Branch, Sale  # noqa: F401
