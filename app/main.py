from contextlib import asynccontextmanager
import pathlib
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware
from .config import settings
from .logging_config import setup_logging
from .db import engine, Base
from .routers import branch, department, sales, forecast, monitoring, auth, employee
from .routers import ai_recommendations, menu, receipts, pricing_analytics, pricing_engine
from .routers import labor_demand, inventory
from .routers.users_ui import ui_auth_router, ui_users_router
from .auth_ui import bootstrap_admin, seed_default_roles
from .db import SessionLocal
from .services.scheduled_sales_loader import run_auto_sync, run_gap_check
from .services.scheduled_waiter_loader import (
    run_employees_sync,
    run_waiter_gap_check,
    run_waiter_sales_sync,
)
from .services.scheduled_department_loader import run_department_sync
from .services.scheduled_nomenclature_loader import run_nomenclature_sync
from .services.scheduled_receipts_loader import run_receipts_sync, run_receipts_gap_check
from .services.scheduled_inventory_loader import run_inventory_sync
from .services.iiko_stock_loader import run_daily_stock_sync
from .services.scheduled_pricing_analytics import run_pricing_analytics_aggregation, run_menu_clustering
from .services.scheduled_pricing_engine import run_catalog_price_sync, run_elasticity_update, run_price_optimization, run_outcome_evaluation, run_pricing_weekly_report, run_pricing_monthly_report, run_price_order_sync
from .services.scheduled_recipe_loader import run_recipe_sync
from .services.model_retraining_service import run_auto_retrain
from .services.sku_model_retraining_service import run_sku_auto_retrain
from .services.scheduled_forecast_job import run_daily_forecast_sweep
from .services.model_monitoring_service import get_model_monitoring_service
from apscheduler.schedulers.background import BackgroundScheduler
import logging
import os

setup_logging(debug=settings.DEBUG, log_level=settings.LOG_LEVEL)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

# Initialize scheduler for automatic sales loading
scheduler = BackgroundScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown logic"""
    # --- Startup ---
    # Seed default roles + bootstrap admin (idempotent)
    try:
        with SessionLocal() as db:
            seed_default_roles(db)
            created = bootstrap_admin(
                db,
                settings.BOOTSTRAP_ADMIN_PHONE,
                settings.BOOTSTRAP_ADMIN_NAME,
            )
            if created is not None:
                logger.info(f"Bootstrap admin user created/promoted: {created.phone}")
    except Exception as e:
        logger.error(f"Failed to seed UI auth tables: {e}", exc_info=True)

    try:
        # Раньше всех остальных: чеки не грузятся по точке, которой нет в
        # справочнике, а падает при этом весь батч целиком.
        scheduler.add_job(
            func=run_department_sync,
            trigger="cron",
            hour=0,
            minute=45,
            id='daily_department_sync',
            name='Daily Department Catalog Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_auto_sync,
            trigger="cron",
            hour=2,
            minute=0,
            id='daily_sales_sync',
            name='Daily Sales Auto-Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_auto_retrain,
            trigger="cron",
            day_of_week=6,  # Sunday
            hour=3,
            minute=0,
            id='weekly_model_retrain',
            name='Weekly Model Retraining',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_recipe_sync,
            trigger="cron",
            day_of_week=6,  # Sunday
            hour=3,
            minute=30,
            id='weekly_recipe_sync',
            name='Weekly Recipe Sync',
            replace_existing=True
        )

        # SKU-retrain снова включён (Фаза 2.2): run_sku_auto_retrain теперь
        # запускает ОТДЕЛЬНЫЙ процесс `python -m app.jobs.sku_retrain` с
        # RLIMIT_AS — его OOM изолирован от API (в отличие от прежнего
        # in-process обучения, что каждое воскресенье убивало uvicorn, P0-2).
        scheduler.add_job(
            func=run_sku_auto_retrain,
            trigger="cron",
            day_of_week=6,  # Sunday
            hour=3,
            minute=45,
            id='weekly_sku_model_retrain',
            name='Weekly SKU Model Retraining (out-of-process)',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_menu_clustering,
            trigger="cron",
            day_of_week=6,  # Sunday
            hour=3,
            minute=15,
            id='weekly_menu_clustering',
            name='Weekly Menu Role Clustering',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_daily_metrics_calculation,
            trigger="cron",
            hour=4,
            minute=0,
            id='daily_metrics_calculation',
            name='Daily Performance Metrics Calculation',
            replace_existing=True
        )

        # Ежедневный batch-прогноз t+1/t+7 по всем активным точкам + SKU top-50
        # (аудит P0-6, Фаза 1.3/1.4). 06:00 — после ночных синков продаж.
        scheduler.add_job(
            func=run_daily_forecast_sweep,
            trigger="cron",
            hour=6,
            minute=0,
            id='daily_forecast_sweep',
            name='Daily Forecast Sweep (all active departments)',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_pricing_analytics_aggregation,
            trigger="cron",
            hour=4,
            minute=30,
            id='daily_pricing_analytics',
            name='Daily Pricing Analytics Aggregation',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_catalog_price_sync,
            trigger="cron",
            hour=3,
            minute=20,
            id='daily_catalog_price_sync',
            name='Daily Menu Price Sync (orders) + applied detection',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_price_order_sync,
            trigger="cron",
            hour=3,
            minute=25,
            id='daily_price_order_sync',
            name='Daily iiko Price Order Status Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_outcome_evaluation,
            trigger="cron",
            hour=5,
            minute=30,
            id='daily_outcome_evaluation',
            name='Daily Recommendation Outcome Evaluation',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_elasticity_update,
            trigger="cron",
            day_of_week=6,  # Sunday
            hour=3,
            minute=30,
            id='weekly_elasticity_update',
            name='Weekly Elasticity Estimation',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_price_optimization,
            trigger="cron",
            hour=5,
            minute=0,
            id='daily_price_optimization',
            name='Daily Price Optimization',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_pricing_weekly_report,
            trigger="cron",
            day_of_week=0,
            hour=8,
            minute=0,
            id='weekly_pricing_report',
            name='Weekly Pricing Report (LLM)',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_pricing_monthly_report,
            trigger="cron",
            day=1,
            hour=8,
            minute=0,
            id='monthly_pricing_report',
            name='Monthly Pricing Report (LLM)',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_gap_check,
            trigger="cron",
            hour=10,
            minute=0,
            id='daily_gap_check',
            name='Daily Sales Gap Check',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_nomenclature_sync,
            trigger="cron",
            hour=1,
            minute=0,
            id='daily_nomenclature_sync',
            name='Daily Nomenclature Catalog Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_employees_sync,
            trigger="cron",
            hour=1,
            minute=30,
            id='daily_employees_sync',
            name='Daily Employees Catalog Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_receipts_sync,
            trigger="cron",
            hour=2,
            minute=15,
            id='daily_receipts_sync',
            name='Daily Receipts Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_inventory_sync,
            trigger="cron",
            hour=2,
            minute=45,
            id='daily_inventory_sync',
            name='Daily Inventory Documents Sync',
            replace_existing=True
        )

        # Остатки iiko отдаёт только срезом «на сейчас», истории у отчёта нет:
        # не сняли вчерашний день — восстановить его будет уже нечем.
        scheduler.add_job(
            func=run_daily_stock_sync,
            trigger="cron",
            hour=2,
            minute=50,
            id='daily_stock_balance_sync',
            name='Daily Stock Balance Snapshot',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_waiter_sales_sync,
            trigger="cron",
            hour=2,
            minute=30,
            id='daily_waiter_sales_sync',
            name='Daily Waiter Sales Sync',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_waiter_gap_check,
            trigger="cron",
            hour=11,
            minute=0,
            id='daily_waiter_gap_check',
            name='Daily Waiter Sales Gap Check',
            replace_existing=True
        )

        scheduler.add_job(
            func=run_receipts_gap_check,
            trigger="cron",
            hour=11,
            minute=30,
            id='daily_receipts_gap_check',
            name='Daily Receipts Gap Check',
            replace_existing=True
        )

        scheduler.start()
        logger.info(
            "Background scheduler started - Departments 0:45, Nomenclature 1:00, Employees 1:30, Sales 2:00, "
            "Receipts 2:15, Waiter sales 2:30, Inventory docs 2:45, Retrain Sun 3:00, Menu clustering Sun 3:15, Catalog price 3:20, Price order sync 3:25, "
            "Elasticity Sun 3:30, Recipes Sun 3:30, SKU retrain Sun 3:45 (out-of-process), Metrics 4:00, Pricing analytics 4:30, Forecast sweep 6:00, "
            "Price optimization 5:00, Outcome evaluation 5:30, Gap check 10:00, Waiter gap 11:00, Receipts gap 11:30"
        )

    except Exception as e:
        logger.error(f"Failed to start scheduler: {e}")

    yield

    # --- Shutdown ---
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("Background scheduler shut down successfully")
    except Exception as e:
        logger.error(f"Error shutting down scheduler: {e}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG,
    lifespan=lifespan,
)

# Set up Jinja2 templates
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# CORS: parse allowed origins from settings
allowed_origins = [o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        return response


app.add_middleware(SecurityHeadersMiddleware)

app.include_router(branch.router, prefix="/api")
app.include_router(department.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(employee.router, prefix="/api")
app.include_router(ai_recommendations.router, prefix="/api")
app.include_router(menu.router, prefix="/api")
app.include_router(receipts.router, prefix="/api")
app.include_router(pricing_analytics.router, prefix="/api")
app.include_router(pricing_engine.router, prefix="/api")
app.include_router(labor_demand.router, prefix="/api")
app.include_router(inventory.router, prefix="/api")
app.include_router(ui_auth_router, prefix="/api")
app.include_router(ui_users_router, prefix="/api")

# SPA static files (React frontend build output)
SPA_DIR = pathlib.Path(__file__).parent / "static" / "spa"
if (SPA_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=SPA_DIR / "assets"), name="spa-assets")


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon.ico file"""
    favicon_path = os.path.join(os.path.dirname(__file__), "..", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    raise HTTPException(status_code=404, detail="Favicon not found")


def run_daily_metrics_calculation():
    """
    Wrapper function for scheduler to run daily metrics calculation
    This function will be called by APScheduler
    """
    logger.info("Scheduler triggered: Starting daily performance metrics calculation")

    try:
        # Handle event loop similar to other scheduled tasks
        import asyncio
        import concurrent.futures
        from datetime import date, timedelta

        def calculate_metrics_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                monitoring_service = get_model_monitoring_service()
                # Calculate for yesterday
                target_date = date.today() - timedelta(days=1)
                return new_loop.run_until_complete(
                    monitoring_service.calculate_daily_metrics(target_date)
                )
            finally:
                new_loop.close()

        try:
            existing_loop = asyncio.get_running_loop()
            logger.warning("Event loop already running, creating new thread for metrics calculation")

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(calculate_metrics_in_thread)
                result = future.result(timeout=300)  # 5 minute timeout

        except RuntimeError:
            # No event loop running
            result = calculate_metrics_in_thread()

        logger.info(f"Daily metrics calculation completed: {result.get('status', 'unknown')}")
        return result

    except Exception as e:
        logger.error(f"Failed to run daily metrics calculation: {e}", exc_info=True)
        return {
            "status": "error",
            "message": f"Scheduler execution failed: {str(e)}"
        }


def _serve_spa() -> HTMLResponse | None:
    """Read SPA index.html and inject API token, return None if SPA not built"""
    index_path = SPA_DIR / "index.html"
    if not index_path.exists():
        return None
    html = index_path.read_text()
    token_script = f'<script>window.__API_TOKEN__="{settings.API_TOKEN}";</script>'
    html = html.replace('</head>', f'{token_script}</head>')
    return HTMLResponse(content=html)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Admin interface — serves React SPA if built, falls back to Jinja2 template"""
    spa_response = _serve_spa()
    if spa_response:
        return spa_response
    # Fallback to old Jinja2 template
    api_token = settings.API_TOKEN
    return templates.TemplateResponse(
        "admin.html",
        {"request": request, "api_token": api_token}
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def serve_spa_routes(request: Request, full_path: str):
    """Catch-all route for React Router client-side navigation"""
    # Don't intercept API or health routes (they should 404 via FastAPI)
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(status_code=404)
    spa_response = _serve_spa()
    if spa_response:
        return spa_response
    # No SPA built — redirect to root which shows Jinja2 fallback
    raise HTTPException(status_code=404)
