from fastapi import APIRouter

router = APIRouter(prefix="/forecast", tags=["forecast"])

from .core import router as core_router
from .tuning import router as tuning_router
from .error_analysis import router as error_analysis_router
from .postprocessing import router as postprocessing_router
from .sku import router as sku_router

router.include_router(core_router)
router.include_router(tuning_router)
router.include_router(error_analysis_router)
router.include_router(postprocessing_router)
router.include_router(sku_router)
