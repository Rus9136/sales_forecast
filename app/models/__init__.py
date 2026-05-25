"""SQLAlchemy models — import all to ensure mapper registration."""

from .department import Department  # noqa: F401
from .sales import SalesSummary, SalesByHour, AutoSyncLog  # noqa: F401
from .forecast import Forecast, ForecastAccuracyLog, PostprocessingSettings  # noqa: F401
from .ml import ModelVersion, ModelRetrainingLog  # noqa: F401
from .employee import Employee, SalesByWaiter  # noqa: F401
from .branch import Branch, Sale  # noqa: F401
from .ai import AIRecommendation, AIPromptLog, AIPrompt  # noqa: F401
from .auth_ui import AppRole, AppUser, AppSession  # noqa: F401
from .menu import NomenclatureCategory, NomenclatureGroup, Product  # noqa: F401
from .receipts import Receipt, ReceiptItem  # noqa: F401
