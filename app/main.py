from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from .config import settings
from .db import engine, Base
from .routers import branch, department, sales, forecast, monitoring, auth
from .services.scheduled_sales_loader import run_auto_sync, run_gap_check
from .services.model_retraining_service import run_auto_retrain
from .services.model_monitoring_service import get_model_monitoring_service
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

# Initialize scheduler for automatic sales loading
scheduler = BackgroundScheduler()

@app.on_event("startup")
async def startup_event():
    """Initialize background scheduler on application startup"""
    try:
        # Schedule daily automatic sales loading at 2:00 AM
        scheduler.add_job(
            func=run_auto_sync,
            trigger="cron", 
            hour=2,
            minute=0,
            id='daily_sales_sync',
            name='Daily Sales Auto-Sync',
            replace_existing=True
        )
        
        # Schedule weekly model retraining on Sundays at 3:00 AM
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
        
        # Schedule daily performance metrics calculation at 4:00 AM
        scheduler.add_job(
            func=run_daily_metrics_calculation,
            trigger="cron",
            hour=4,
            minute=0,
            id='daily_metrics_calculation',
            name='Daily Performance Metrics Calculation',
            replace_existing=True
        )

        # Schedule gap check at 10:00 AM to fill any missing data from earlier sync
        # (restaurants may close their shift late in the morning)
        scheduler.add_job(
            func=run_gap_check,
            trigger="cron",
            hour=10,
            minute=0,
            id='daily_gap_check',
            name='Daily Sales Gap Check',
            replace_existing=True
        )

        scheduler.start()
        logger.info("✅ Background scheduler started - Daily sales sync at 2:00 AM, Gap check at 10:00 AM, Weekly model retraining on Sundays at 3:00 AM, Daily metrics calculation at 4:00 AM")
        
        # Register shutdown handler
        atexit.register(lambda: scheduler.shutdown() if scheduler.running else None)
        
    except Exception as e:
        logger.error(f"❌ Failed to start scheduler: {e}")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up scheduler on application shutdown"""
    try:
        if scheduler.running:
            scheduler.shutdown()
            logger.info("✅ Background scheduler shut down successfully")
    except Exception as e:
        logger.error(f"❌ Error shutting down scheduler: {e}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(branch.router, prefix="/api")
app.include_router(department.router, prefix="/api")
app.include_router(sales.router, prefix="/api")
app.include_router(forecast.router, prefix="/api")
app.include_router(monitoring.router, prefix="/api")
app.include_router(auth.router, prefix="/api")

from fastapi.responses import FileResponse
import os

@app.get("/favicon.ico")
async def favicon():
    """Serve favicon.ico file"""
    favicon_path = os.path.join(os.path.dirname(__file__), "..", "favicon.ico")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/x-icon")
    else:
        # Return 404 if favicon doesn't exist
        from fastapi import HTTPException
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
        import threading
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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Admin interface with sidebar"""
    api_token = settings.API_TOKEN
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <title>AI Прогноз Продаж</title>
        <link rel="icon" type="image/x-icon" href="/favicon.ico?v=1.0">
        <link rel="shortcut icon" type="image/x-icon" href="/favicon.ico?v=1.0">
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                background-color: #f5f5f5;
                color: #333;
            }
            
            .container {
                display: flex;
                height: 100vh;
            }
            
            /* Sidebar */
            .sidebar {
                width: 300px;
                background-color: #2c3e50;
                color: white;
                padding: 0;
                flex-shrink: 0;
            }
            
            .sidebar-header {
                padding: 20px;
                background-color: #34495e;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-bottom: 1px solid #4a5568;
            }
            
            .sidebar-title {
                font-size: 18px;
                font-weight: 600;
            }
            
            .logout-btn {
                background-color: #e53e3e;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .logout-btn:hover {
                background-color: #c53030;
            }
            
            .sidebar-menu {
                list-style: none;
                padding: 0;
            }
            
            .sidebar-menu li {
                border-bottom: 1px solid #4a5568;
                background-color: #2c3e50;
            }
            
            .sidebar-menu a {
                display: block;
                padding: 15px 20px;
                color: #bbb;
                text-decoration: none;
                transition: all 0.3s;
                background-color: transparent;
            }
            
            .sidebar-menu a:hover {
                background-color: #34495e;
                color: white;
            }
            
            .sidebar-menu a.active {
                background-color: #3498db;
                color: white;
            }
            
            /* Section headers styling */
            .sidebar-menu .section-header {
                font-weight: 600;
                font-size: 11px;
                text-transform: uppercase;
                letter-spacing: 1px;
                color: #95a5a6 !important;
                background-color: #2c3e50 !important;
                pointer-events: none;
                margin-top: 10px;
            }
            
            .sidebar-menu .section-header:first-child {
                margin-top: 0;
            }
            
            /* Ensure all sidebar elements are dark */
            .sidebar * {
                background-color: inherit;
            }
            
            .sidebar ul, .sidebar li {
                background-color: #2c3e50 !important;
            }
            
            /* Main content */
            .main-content {
                flex: 1;
                padding: 30px;
                overflow-y: auto;
            }
            
            .page-header {
                margin-bottom: 30px;
            }
            
            .page-title {
                font-size: 24px;
                font-weight: 600;
                margin-bottom: 10px;
                color: #333;
            }
            
            .page-description {
                font-size: 14px;
                color: #666;
                margin-bottom: 25px;
                line-height: 1.5;
            }
            
            .filters-row {
                display: flex;
                gap: 20px;
                align-items: center;
                margin-bottom: 20px;
                flex-wrap: wrap;
            }
            
            .filter-select {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                min-width: 200px;
                background-color: white;
                color: #333;
            }
            
            .search-input {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                min-width: 300px;
                background-color: white;
                color: #333;
            }
            
            /* Universal light theme for all inputs and selects */
            input[type="text"], input[type="number"], input[type="date"], 
            input[type="email"], input[type="password"], textarea, select {
                background-color: white !important;
                color: #333 !important;
                border: 1px solid #ddd !important;
                border-radius: 4px !important;
                padding: 8px 12px !important;
            }
            
            input[type="text"]:focus, input[type="number"]:focus, input[type="date"]:focus,
            input[type="email"]:focus, input[type="password"]:focus, textarea:focus, select:focus {
                border-color: #3498db !important;
                outline: none !important;
                box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2) !important;
            }
            
            /* Labels and form elements */
            label {
                color: #333 !important;
                font-weight: 500;
            }
            
            /* Headings */
            h1, h2, h3, h4, h5, h6 {
                color: #333 !important;
            }
            
            /* Paragraphs and general text */
            p {
                color: #666;
            }
            
            .total-count {
                margin-left: auto;
                font-size: 14px;
                color: #666;
            }
            
            .filter-hint {
                font-size: 12px;
                color: #28a745;
                font-style: italic;
                margin-left: 10px;
                padding: 2px 8px;
                background-color: #d4edda;
                border-radius: 3px;
                border: 1px solid #c3e6cb;
            }
            
            .sync-btn {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                margin-right: 10px;
            }
            
            .sync-btn:hover {
                background-color: #2980b9;
            }
            
            .refresh-btn {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .refresh-btn:hover {
                background-color: #229954;
            }
            
            /* Table */
            .table-container {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            
            table {
                width: 100%;
                border-collapse: collapse;
            }
            
            th {
                background-color: #f8f9fa;
                padding: 12px;
                text-align: left;
                font-weight: 600;
                color: #555;
                border-bottom: 2px solid #dee2e6;
            }
            
            td {
                padding: 12px;
                border-bottom: 1px solid #dee2e6;
            }
            
            tr:hover {
                background-color: #f8f9fa;
            }
            
            .loading {
                display: none;
                margin-left: 10px;
                color: #666;
            }
            
            .no-data {
                text-align: center;
                padding: 40px;
                color: #666;
            }
            
            /* Form Styles */
            .form-container {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 30px;
                max-width: 800px;
            }
            
            .form-section {
                margin-bottom: 30px;
            }
            
            .form-section-title {
                font-size: 20px;
                font-weight: 600;
                color: #333;
                margin-bottom: 20px;
                padding-bottom: 10px;
                border-bottom: 2px solid #e9ecef;
            }
            
            .form-row {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
            }
            
            .form-group {
                flex: 1;
            }
            
            .form-group label {
                display: block;
                margin-bottom: 8px;
                font-weight: 500;
                color: #555;
            }
            
            .form-group input[type="date"] {
                width: 100%;
                padding: 10px 12px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                transition: border-color 0.3s;
            }
            
            .form-group input[type="date"]:focus {
                outline: none;
                border-color: #3498db;
                box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
            }
            
            .checkbox-group {
                display: flex;
                align-items: center;
            }
            
            .checkbox-label {
                display: flex;
                align-items: center;
                cursor: pointer;
                font-size: 14px;
                color: #555;
            }
            
            .checkbox-label input[type="checkbox"] {
                margin-right: 10px;
                transform: scale(1.2);
            }
            
            .form-actions {
                display: flex;
                gap: 15px;
                margin-top: 30px;
            }
            
            .load-btn {
                background-color: #27ae60;
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: background-color 0.3s;
            }
            
            .load-btn:hover {
                background-color: #219a52;
            }
            
            .load-btn:disabled {
                background-color: #95a5a6;
                cursor: not-allowed;
            }
            
            .cancel-btn {
                background-color: #95a5a6;
                color: white;
                border: none;
                padding: 12px 30px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
                transition: background-color 0.3s;
            }
            
            .cancel-btn:hover {
                background-color: #7f8c8d;
            }
            
            /* Progress Bar */
            .progress-section {
                margin-top: 30px;
                padding: 20px;
                background-color: #f8f9fa;
                border-radius: 8px;
            }
            
            .progress-bar {
                width: 100%;
                height: 8px;
                background-color: #e9ecef;
                border-radius: 4px;
                overflow: hidden;
                margin-bottom: 10px;
            }
            
            .progress-fill {
                height: 100%;
                background-color: #3498db;
                width: 0%;
                transition: width 0.3s ease;
            }
            
            .progress-text {
                text-align: center;
                font-size: 14px;
                color: #666;
            }
            
            /* Results */
            .result-section {
                margin-top: 20px;
                padding: 20px;
                border-radius: 8px;
            }
            
            .result-content {
                font-size: 14px;
                line-height: 1.6;
            }
            
            .result-success {
                background-color: #d4edda;
                border: 1px solid #c3e6cb;
                color: #155724;
            }
            
            .result-error {
                background-color: #f8d7da;
                border: 1px solid #f5c6cb;
                color: #721c24;
            }
            
            /* Chart container optimization */
            #forecast-chart-wrapper {
                max-width: 1200px;
                margin: 20px auto;
                width: 100%;
            }
            
            #forecast-chart-wrapper .chart-container {
                position: relative;
                height: 400px;
                width: 100%;
            }
            
            #forecastChart {
                max-width: 100%;
                height: 400px !important;
            }
            
            /* Error Analysis Styles */
            .analysis-tabs {
                margin: 20px 0;
                border-bottom: 1px solid #ddd;
            }
            
            .tab-btn {
                background: none;
                border: none;
                padding: 10px 20px;
                margin-right: 10px;
                cursor: pointer;
                font-size: 14px;
                border-bottom: 2px solid transparent;
                transition: all 0.3s;
            }
            
            .tab-btn:hover {
                background-color: #f5f5f5;
            }
            
            .tab-btn.active {
                color: #3498db;
                border-bottom-color: #3498db;
                font-weight: 600;
            }
            
            .chart-container {
                position: relative;
                height: 400px;
                width: 100%;
                margin: 20px 0;
                background: white;
                border-radius: 8px;
                padding: 20px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            }
            
            .error-distribution-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .error-range-excellent { color: #27ae60; }
            .error-range-good { color: #2ecc71; }
            .error-range-acceptable { color: #f39c12; }
            .error-range-poor { color: #e74c3c; }
            .error-range-very-poor { color: #c0392b; }
            
            /* Modal Styles */
            .modal {
                position: fixed;
                z-index: 1000;
                left: 0;
                top: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0,0,0,0.5);
                overflow-y: auto;
            }
            
            .modal-content {
                background-color: #fefefe;
                margin: 5% auto;
                border-radius: 8px;
                width: 600px;
                max-width: 90%;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }
            
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 20px;
                background-color: #f8f9fa;
                border-bottom: 1px solid #dee2e6;
                border-radius: 8px 8px 0 0;
            }
            
            .modal-header h2 {
                margin: 0;
                color: #333;
            }
            
            .close {
                color: #aaa;
                font-size: 28px;
                font-weight: bold;
                cursor: pointer;
                line-height: 1;
            }
            
            .close:hover,
            .close:focus {
                color: #000;
                text-decoration: none;
            }
            
            /* Department Form Styles */
            .department-form {
                padding: 20px;
            }
            
            .form-row {
                display: flex;
                gap: 20px;
                margin-bottom: 20px;
            }
            
            .form-group {
                flex: 1;
                display: flex;
                flex-direction: column;
            }
            
            .form-group label {
                margin-bottom: 5px;
                font-weight: 600;
                color: #333;
            }
            
            .form-group input,
            .form-group select {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
            }
            
            .form-group input:focus,
            .form-group select:focus {
                outline: none;
                border-color: #3498db;
                box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
            }
            
            /* Season Fields */
            .season-fields {
                border: 1px solid #e9ecef;
                border-radius: 6px;
                padding: 15px;
                margin: 20px 0;
                background-color: #f8f9fa;
            }
            
            .season-title {
                margin: 0 0 15px 0;
                color: #495057;
                font-size: 16px;
            }
            
            /* Form Actions */
            .form-actions {
                display: flex;
                gap: 10px;
                justify-content: flex-end;
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #dee2e6;
            }
            
            .save-btn {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .save-btn:hover {
                background-color: #218838;
            }
            
            .cancel-btn {
                background-color: #6c757d;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .cancel-btn:hover {
                background-color: #5a6268;
            }
            
            .add-btn {
                background-color: #28a745;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 14px;
            }
            
            .add-btn:hover {
                background-color: #218838;
            }
            
            /* Action buttons in table */
            .edit-btn {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 6px 15px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                margin-right: 5px;
                min-width: 80px;
            }
            
            .edit-btn:hover {
                background-color: #2980b9;
            }
            
            .delete-btn {
                background-color: #c67e5c;
                color: white;
                border: none;
                padding: 6px 15px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 12px;
                min-width: 80px;
            }
            
            .delete-btn:hover {
                background-color: #b56d4f;
            }
            
            /* Card styles for monitoring pages */
            .card {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
                margin-bottom: 20px;
            }
            
            .stat-card {
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 15px;
                text-align: center;
                margin-bottom: 15px;
            }
            
            .stat-card h4 {
                margin: 0 0 10px 0;
                color: #2c3e50;
                font-size: 14px;
                font-weight: 600;
            }
            
            .stat-card .value {
                font-size: 24px;
                font-weight: bold;
                color: #3498db;
                margin: 5px 0;
            }
            
            .stat-card .label {
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
            }
            
            /* Loading spinner */
            .loading-spinner {
                border: 3px solid #f3f3f3;
                border-top: 3px solid #3498db;
                border-radius: 50%;
                width: 30px;
                height: 30px;
                animation: spin 1s linear infinite;
                margin: 0 auto 10px auto;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            /* Status indicators */
            .status-healthy {
                color: #27ae60;
                font-weight: bold;
            }
            
            .status-warning {
                color: #f39c12;
                font-weight: bold;
            }
            
            .status-error {
                color: #e74c3c;
                font-weight: bold;
            }
            
            /* Grid layout for cards */
            .cards-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }
            
            .cards-grid-2 {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            /* Progress bars */
            .progress-bar-container {
                background-color: #f0f0f0;
                border-radius: 10px;
                padding: 3px;
                margin: 10px 0;
            }
            
            .progress-bar-fill {
                background-color: #3498db;
                height: 20px;
                border-radius: 8px;
                transition: width 0.3s ease;
                display: flex;
                align-items: center;
                justify-content: center;
                color: white;
                font-size: 12px;
                font-weight: bold;
            }
            
            /* Configuration sections */
            .config-section {
                background: #f8f9fa;
                border: 1px solid #e9ecef;
                border-radius: 6px;
                padding: 15px;
                margin-bottom: 10px;
            }
            
            .config-section h4 {
                margin: 0 0 10px 0;
                color: #2c3e50;
                font-size: 16px;
                font-weight: 600;
            }
            
            /* Analysis tabs */
            .analysis-tabs {
                display: flex;
                gap: 10px;
                margin: 20px 0;
            }
            
            .tab-btn {
                background: #e9ecef;
                border: none;
                border-radius: 5px;
                padding: 8px 16px;
                cursor: pointer;
                font-size: 14px;
                transition: all 0.3s;
            }
            
            .tab-btn.active {
                background: #3498db;
                color: white;
            }
            
            .tab-btn:hover {
                background: #dee2e6;
            }
            
            .tab-btn.active:hover {
                background: #2980b9;
            }
        </style>
        
        <!-- Chart.js library -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <div class="container">
            <!-- Sidebar -->
            <div class="sidebar">
                <div class="sidebar-header">
                    <div class="sidebar-title">AI Модуль</div>
                    <button class="logout-btn">Выйти</button>
                </div>
                <ul class="sidebar-menu">
                    <li><a href="#справочники" class="section-header">СПРАВОЧНИКИ</a></li>
                    <li><a href="#подразделения" class="active">Подразделения</a></li>
                    <li><a href="#продажи" class="section-header">ПРОДАЖИ</a></li>
                    <li><a href="#продажи-по-дням" onclick="showDailySales()">Продажи по дням</a></li>
                    <li><a href="#продажи-по-часам" onclick="showHourlySales()">Продажи по часам</a></li>
                    <li><a href="#прогноз" class="section-header">ПРОГНОЗ ПРОДАЖ</a></li>
                    <li><a href="#прогноз-по-филиалам" onclick="showForecastByBranch()">📈 Прогноз по филиалам</a></li>
                    <li><a href="#сравнение-факт-прогноз" onclick="showForecastComparison()">📊 Сравнение факт / прогноз</a></li>
                    <li><a href="#сервис" class="section-header">СЕРВИС</a></li>
                    <li><a href="#загрузка-данных" onclick="showDataLoading()">Загрузка данных</a></li>
                    <li><a href="#авто-загрузка" onclick="showAutoSyncStatus()">⏰ Автоматическая загрузка</a></li>
                </ul>
            </div>
            
            <!-- Main Content -->
            <div class="main-content">
                <!-- Departments Page -->
                <div id="page-departments" class="page-content">
                    <div class="page-header">
                        <h1 class="page-title">Подразделения</h1>
                        
                        <div class="filters-row">
                            <select class="filter-select" id="type-filter" onchange="applyFilters()">
                                <option value="DEPARTMENT">🏪 Только торговые точки (рекомендуется)</option>
                                <option value="JURPERSON">🏛️ Только юридические лица</option>
                                <option value="CORPORATION">🏢 Только корпорации</option>
                                <option value="ALL">📋 Все типы подразделений</option>
                            </select>
                            
                            <select class="filter-select" id="company-filter">
                                <option value="">Все компании</option>
                            </select>
                            
                            <input type="text" class="search-input" id="search-input" placeholder="Поиск по названию...">
                            
                            <button class="sync-btn" onclick="syncBranches()">Синхронизировать</button>
                            <button class="refresh-btn" onclick="loadBranches()">Обновить</button>
                            <button class="add-btn" onclick="showDepartmentForm()">Добавить</button>
                            
                            <span class="loading" id="loading">Загрузка...</span>
                            
                            <div class="total-count" id="total-count">Всего: 0</div>
                            <div class="filter-hint" id="filter-hint">Показаны только торговые точки с данными о продажах</div>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table id="branches-table">
                            <thead>
                                <tr>
                                    <th>Код</th>
                                    <th>Название</th>
                                    <th>Тип</th>
                                    <th>Сегмент</th>
                                    <th>ИНН</th>
                                    <th>Сезон</th>
                                    <th>Действия</th>
                                </tr>
                            </thead>
                            <tbody id="branches-tbody">
                                <tr>
                                    <td colspan="7" class="no-data">Загрузка данных...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Department Edit/Create Form Modal -->
                <div id="department-modal" class="modal" style="display: none;">
                    <div class="modal-content">
                        <div class="modal-header">
                            <h2 id="modal-title">Редактирование подразделения</h2>
                            <span class="close" onclick="closeDepartmentModal()">&times;</span>
                        </div>
                        
                        <form id="department-form" class="department-form">
                            <input type="hidden" id="department-id" name="id">
                            
                            <!-- Read-only ID field -->
                            <div class="form-row" id="id-field-row" style="display: none;">
                                <div class="form-group">
                                    <label for="department-id-display">ID подразделения:</label>
                                    <input type="text" id="department-id-display" readonly style="background-color: #f5f5f5; cursor: not-allowed;">
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="department-name">Название подразделения:</label>
                                    <input type="text" id="department-name" name="name" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="department-code">Код:</label>
                                    <input type="text" id="department-code" name="code">
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="department-type">Тип подразделения:</label>
                                    <select id="department-type" name="type">
                                        <option value="DEPARTMENT">Подразделение</option>
                                        <option value="JURPERSON">Юридическое лицо</option>
                                        <option value="ORGANIZATION">Организация</option>
                                    </select>
                                </div>
                                
                                <div class="form-group">
                                    <label for="department-segment">Сегмент бизнеса:</label>
                                    <select id="department-segment" name="segment_type" onchange="toggleSeasonFields()">
                                        <option value="restaurant">Ресторан</option>
                                        <option value="coffeehouse">Кофейня</option>
                                        <option value="confectionery">Кондитерская</option>
                                        <option value="food_court">Фудкорт в ТРЦ</option>
                                        <option value="store">Магазин</option>
                                        <option value="fast_food">Фаст-фуд</option>
                                        <option value="bakery">Пекарня</option>
                                        <option value="cafe">Кафе</option>
                                        <option value="bar">Бар</option>
                                    </select>
                                </div>
                            </div>
                            
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="department-inn">ИНН:</label>
                                    <input type="text" id="department-inn" name="taxpayer_id_number">
                                </div>
                                
                                <div class="form-group">
                                    <label for="department-code-tco">Код TCO:</label>
                                    <input type="text" id="department-code-tco" name="code_tco">
                                </div>
                            </div>
                            
                            <!-- Seasonal fields - visible only for coffeehouses -->
                            <div id="season-fields" class="season-fields" style="display: none;">
                                <h3 class="season-title">Сезонные настройки (для кофеен)</h3>
                                <div class="form-row">
                                    <div class="form-group">
                                        <label for="season-start">Дата начала сезона:</label>
                                        <input type="date" id="season-start" name="season_start_date">
                                    </div>
                                    
                                    <div class="form-group">
                                        <label for="season-end">Дата окончания сезона:</label>
                                        <input type="date" id="season-end" name="season_end_date">
                                    </div>
                                </div>
                            </div>
                            
                            <div class="form-actions">
                                <button type="submit" class="save-btn" id="save-department-btn">
                                    Сохранить
                                </button>
                                <button type="button" class="cancel-btn" onclick="closeDepartmentModal()">
                                    Отмена
                                </button>
                            </div>
                        </form>
                    </div>
                </div>

                <!-- Data Loading Page -->
                <div id="page-data-loading" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Загрузка данных</h1>
                    </div>
                    
                    <div class="form-container">
                        <div class="form-section">
                            <h2 class="form-section-title">Синхронизация продаж</h2>
                            
                            <form id="sales-sync-form" class="sync-form">
                                <div class="form-row">
                                    <div class="form-group">
                                        <label for="start-date">Дата начала:</label>
                                        <input type="date" id="start-date" name="start-date" required>
                                    </div>

                                    <div class="form-group">
                                        <label for="end-date">Дата окончания:</label>
                                        <input type="date" id="end-date" name="end-date" required>
                                    </div>
                                </div>

                                <div class="form-row">
                                    <div class="form-group" style="flex: 1;">
                                        <label for="sync-department-filter">Подразделение:</label>
                                        <select class="filter-select" id="sync-department-filter" name="department" style="width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px;">
                                            <option value="">Все подразделения</option>
                                        </select>
                                    </div>
                                </div>

                                <div class="form-actions">
                                    <button type="submit" class="load-btn" id="load-btn">
                                        Загрузить
                                    </button>
                                    <button type="button" class="cancel-btn" onclick="showDepartments()">
                                        Отмена
                                    </button>
                                </div>
                                
                                <div class="progress-section" id="progress-section" style="display: none;">
                                    <div class="progress-bar">
                                        <div class="progress-fill" id="progress-fill"></div>
                                    </div>
                                    <div class="progress-text" id="progress-text">Загрузка...</div>
                                </div>
                                
                                <div class="result-section" id="result-section" style="display: none;">
                                    <div class="result-content" id="result-content"></div>
                                </div>
                            </form>
                        </div>
                    </div>
                </div>

                <!-- Daily Sales Page -->
                <div id="page-daily-sales" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Продажи по дням</h1>
                        
                        <div class="filters-row">
                            <input type="date" class="filter-select" id="daily-start-date" placeholder="Дата начала">
                            <input type="date" class="filter-select" id="daily-end-date" placeholder="Дата окончания">
                            <select class="filter-select" id="daily-department-filter">
                                <option value="">Все подразделения</option>
                            </select>
                            
                            <button class="refresh-btn" onclick="loadDailySales()">Загрузить</button>
                            
                            <span class="loading" id="daily-loading">Загрузка...</span>
                            
                            <div class="total-count" id="daily-total-count">Всего: 0</div>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table id="daily-sales-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Подразделение</th>
                                    <th>Дата</th>
                                    <th>Сумма продаж</th>
                                    <th>Создано</th>
                                    <th>Синхронизировано</th>
                                </tr>
                            </thead>
                            <tbody id="daily-sales-tbody">
                                <tr>
                                    <td colspan="6" class="no-data">Загрузка данных...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Hourly Sales Page -->
                <div id="page-hourly-sales" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Продажи по часам</h1>
                        
                        <div class="filters-row">
                            <input type="date" class="filter-select" id="hourly-start-date" placeholder="Дата начала">
                            <input type="date" class="filter-select" id="hourly-end-date" placeholder="Дата окончания">
                            <select class="filter-select" id="hourly-department-filter">
                                <option value="">Все подразделения</option>
                            </select>
                            <select class="filter-select" id="hourly-hour-filter">
                                <option value="">Все часы</option>
                            </select>
                            
                            <button class="refresh-btn" onclick="loadHourlySales()">Загрузить</button>
                            
                            <span class="loading" id="hourly-loading">Загрузка...</span>
                            
                            <div class="total-count" id="hourly-total-count">Всего: 0</div>
                        </div>
                    </div>
                    
                    <!-- Hourly Sales Chart -->
                    <div id="hourly-chart-wrapper" style="margin: 20px 0; display: none;">
                        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <h3 id="hourly-chart-title" style="margin-bottom: 15px; color: #2c3e50;">Почасовая выручка</h3>
                            <div id="hourly-chart-no-data" style="background: #f8d7da; color: #721c24; padding: 20px; border-radius: 4px; text-align: center; display: none;">
                                📊 Нет данных для выбранного подразделения
                            </div>
                            <div class="chart-container" style="height: 400px;">
                                <canvas id="hourlySalesChart"></canvas>
                            </div>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table id="hourly-sales-table">
                            <thead>
                                <tr>
                                    <th>ID</th>
                                    <th>Подразделение</th>
                                    <th>Дата</th>
                                    <th>Час</th>
                                    <th>Сумма продаж</th>
                                    <th>Создано</th>
                                    <th>Синхронизировано</th>
                                </tr>
                            </thead>
                            <tbody id="hourly-sales-tbody">
                                <tr>
                                    <td colspan="7" class="no-data">Загрузка данных...</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Forecast by Branch Page -->
                <div id="page-forecast-branch" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Прогноз по филиалам</h1>
                        
                        <div class="filters-row">
                            <input type="date" class="filter-select" id="forecast-start-date" placeholder="Дата начала">
                            <input type="date" class="filter-select" id="forecast-end-date" placeholder="Дата окончания">
                            <select class="filter-select" id="forecast-department-filter">
                                <option value="">Все подразделения</option>
                            </select>
                            
                            <button class="refresh-btn" onclick="loadForecasts()">Обновить прогноз</button>
                            
                            <span class="loading" id="forecast-loading" style="display: none;">Загрузка...</span>
                            
                            <div class="total-count" id="forecast-total-count">Всего: 0</div>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table id="forecast-table">
                            <thead>
                                <tr>
                                    <th>Дата</th>
                                    <th>Филиал</th>
                                    <th>Прогноз выручки</th>
                                </tr>
                            </thead>
                            <tbody id="forecast-tbody">
                                <tr>
                                    <td colspan="3" class="no-data">Выберите период и нажмите "Обновить прогноз"</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Forecast Comparison Page -->
                <div id="page-forecast-comparison" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Сравнение факт / прогноз</h1>
                        
                        <div class="filters-row">
                            <input type="date" class="filter-select" id="comparison-start-date" placeholder="Дата начала">
                            <input type="date" class="filter-select" id="comparison-end-date" placeholder="Дата окончания">
                            <select class="filter-select" id="comparison-department-filter">
                                <option value="">Все подразделения</option>
                            </select>
                            
                            <button class="refresh-btn" onclick="loadComparison()">Загрузить</button>
                            
                            <span class="loading" id="comparison-loading" style="display: none;">Загрузка...</span>
                            
                            <div class="total-count" id="comparison-total-count">Всего: 0</div>
                        </div>
                    </div>
                    
                    <!-- Chart Container -->
                    <div id="forecast-chart-wrapper" style="margin: 20px 0; display: none;">
                        <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                            <h3 style="margin-bottom: 15px; color: #2c3e50;">График "Факт vs Прогноз"</h3>
                            <div id="chart-warning" style="background: #fff3cd; color: #856404; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 14px; display: none;">
                                ⚠️ Для удобства отображения на графике показаны последние 30 дат. Используйте фильтр по датам для детализации.
                            </div>
                            <div id="chart-outliers-warning" style="background: #ffeaa7; color: #d63031; padding: 10px; border-radius: 4px; margin-bottom: 15px; font-size: 14px; display: none;">
                                📈 Внимание: График использует логарифмическую шкалу из-за больших разрывов в данных (разница более чем в 5 раз).
                            </div>
                            <div id="chart-no-data" style="background: #f8d7da; color: #721c24; padding: 20px; border-radius: 4px; text-align: center; display: none;">
                                📊 Нет данных для отображения графика
                            </div>
                            <div class="chart-container">
                                <canvas id="forecastChart"></canvas>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Average Error Display -->
                    <div id="average-error-display" style="display: none; margin: 20px 0; padding: 15px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 24px;">📊</span>
                            <div>
                                <div style="font-size: 14px; opacity: 0.9;">Точность прогнозирования</div>
                                <div id="average-error-text" style="font-size: 18px; font-weight: 600;"></div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="table-container">
                        <table id="comparison-table">
                            <thead>
                                <tr>
                                    <th onclick="sortComparison('date')">Дата ↕</th>
                                    <th onclick="sortComparison('department')">Филиал ↕</th>
                                    <th onclick="sortComparison('predicted')">Прогноз ↕</th>
                                    <th onclick="sortComparison('actual')">Факт ↕</th>
                                    <th onclick="sortComparison('error')">Δ отклонение ↕</th>
                                    <th onclick="sortComparison('error_pct')">% ошибка ↕</th>
                                </tr>
                            </thead>
                            <tbody id="comparison-tbody">
                                <tr>
                                    <td colspan="6" class="no-data">Выберите период и нажмите "Загрузить"</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Auto Sync Status Page -->
                <div id="page-auto-sync" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Автоматическая загрузка продаж</h1>
                    </div>
                    
                    <!-- Status Cards -->
                    <div class="cards-grid-2">
                        <div class="form-container" style="padding: 20px;">
                            <h3 style="margin-bottom: 15px; color: #2c3e50;">⏰ Расписание</h3>
                            <p><strong>Время запуска:</strong> Каждый день в 02:00</p>
                            <p><strong>Период загрузки:</strong> Предыдущий день</p>
                            <p><strong>Статус планировщика:</strong> <span id="scheduler-status" style="color: #27ae60;">✅ Активен</span></p>
                        </div>
                        
                        <div class="form-container" style="padding: 20px;">
                            <h3 style="margin-bottom: 15px; color: #2c3e50;">📊 Статистика (30 дней)</h3>
                            <p><strong>Успешных загрузок:</strong> <span id="success-count">-</span></p>
                            <p><strong>Ошибок:</strong> <span id="error-count">-</span></p>
                            <p><strong>Успешность:</strong> <span id="success-rate">-</span>%</p>
                        </div>
                        
                        <div class="form-container" style="padding: 20px;">
                            <h3 style="margin-bottom: 15px; color: #2c3e50;">🔧 Управление</h3>
                            <button class="sync-btn" onclick="testAutoSync()" style="margin-bottom: 10px;">🧪 Тестовый запуск</button>
                            <button class="refresh-btn" onclick="loadAutoSyncStatus()" style="margin-bottom: 10px;">🔄 Обновить</button>
                        </div>
                    </div>
                    
                    <!-- Latest Status -->
                    <div class="form-container" style="margin-bottom: 30px;">
                        <h2 style="margin-bottom: 20px; color: #2c3e50;">Последняя загрузка</h2>
                        <div id="latest-sync-info">
                            <p>Загрузка информации...</p>
                        </div>
                    </div>
                    
                    <!-- Logs Table -->
                    <div class="form-container">
                        <h2 style="margin-bottom: 20px; color: #2c3e50;">История автоматических загрузок</h2>
                        
                        <div class="table-container">
                            <table id="auto-sync-table">
                                <thead>
                                    <tr>
                                        <th>Дата выполнения</th>
                                        <th>Период данных</th>
                                        <th>Тип</th>
                                        <th>Статус</th>
                                        <th>Загружено записей</th>
                                        <th>Сообщение</th>
                                    </tr>
                                </thead>
                                <tbody id="auto-sync-tbody">
                                    <tr>
                                        <td colspan="6" class="no-data">Загрузка логов...</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <script>
            // API Authorization Token from server
            const API_TOKEN = '{api_token}';
            const AUTH_HEADERS = {
                'Authorization': `Bearer ${API_TOKEN}`
            };
            
            let allBranches = [];
            let filteredBranches = [];
            
            async function loadBranches() {
                document.getElementById('loading').style.display = 'inline';
                try {
                    const selectedType = document.getElementById('type-filter').value;
                    let apiUrl = '/api/departments/';
                    
                    // Always load all types to properly populate filters
                    // We'll filter on the client side for better UX
                    apiUrl = '/api/departments/?show_all_types=true';
                    
                    const response = await fetch(apiUrl, { headers: AUTH_HEADERS });
                    const responseData = await response.json();
                    
                    // Handle different response formats
                    if (responseData.departments) {
                        allBranches = responseData.departments; // sales-points endpoint
                    } else {
                        allBranches = responseData; // regular departments endpoint
                    }
                    
                    // Populate company filter
                    populateCompanyFilter();
                    
                    // Apply current filters
                    applyFilters();
                    
                    // Update filter hint
                    updateFilterHint();
                    
                } catch (error) {
                    console.error('Error loading branches:', error);
                    document.getElementById('branches-tbody').innerHTML = 
                        '<tr><td colspan="8" class="no-data">Ошибка загрузки данных</td></tr>';
                } finally {
                    document.getElementById('loading').style.display = 'none';
                }
            }
            
            function updateFilterHint() {
                const selectedType = document.getElementById('type-filter').value;
                const hintElement = document.getElementById('filter-hint');
                
                const hints = {
                    'DEPARTMENT': 'Показаны только торговые точки с данными о продажах',
                    'JURPERSON': 'Показаны юридические лица (организационные единицы)',
                    'CORPORATION': 'Показаны корпорации (верхний уровень управления)',
                    'ALL': 'Показаны все типы подразделений'
                };
                
                hintElement.textContent = hints[selectedType] || '';
            }
            
            function populateCompanyFilter() {
                const selectedType = document.getElementById('type-filter').value;
                const filter = document.getElementById('company-filter');
                
                // Clear existing options
                filter.innerHTML = '<option value="">Все компании</option>';
                
                // Update label based on selected type
                const labels = {
                    'DEPARTMENT': 'Все торговые точки',
                    'JURPERSON': 'Все юридические лица',
                    'CORPORATION': 'Все корпорации',
                    'ALL': 'Все организации'
                };
                filter.options[0].textContent = labels[selectedType] || 'Все компании';
                
                // Only populate dropdown for types that make sense
                if (selectedType === 'DEPARTMENT' || selectedType === 'ALL') {
                    // For departments, show parent companies (JURPERSON)
                    const parentCompanies = [...new Set(allBranches
                        .filter(b => b.type === 'JURPERSON')
                        .map(b => b.name))].sort();
                    
                    parentCompanies.forEach(company => {
                        if (company) {
                            const option = document.createElement('option');
                            option.value = company;
                            option.textContent = company;
                            filter.appendChild(option);
                        }
                    });
                } else if (selectedType === 'JURPERSON') {
                    // For JURPERSON, show parent corporations
                    const parentCorporations = [...new Set(allBranches
                        .filter(b => b.type === 'CORPORATION')
                        .map(b => b.name))].sort();
                    
                    parentCorporations.forEach(corp => {
                        if (corp) {
                            const option = document.createElement('option');
                            option.value = corp;
                            option.textContent = corp;
                            filter.appendChild(option);
                        }
                    });
                } else if (selectedType === 'CORPORATION') {
                    // For corporations, no parent filter needed - disable dropdown
                    filter.disabled = true;
                    filter.innerHTML = '<option value="">Нет родительских компаний</option>';
                    return;
                }
                
                // Re-enable dropdown if it was disabled
                filter.disabled = false;
            }
            
            function applyFilters() {
                const searchTerm = document.getElementById('search-input').value.toLowerCase();
                const selectedCompany = document.getElementById('company-filter').value;
                
                const selectedType = document.getElementById('type-filter').value;
                
                filteredBranches = allBranches.filter(branch => {
                    // First filter by type
                    const matchesType = selectedType === 'ALL' || branch.type === selectedType;
                    
                    const matchesSearch = !searchTerm || 
                        branch.name.toLowerCase().includes(searchTerm) ||
                        (branch.code && branch.code.toLowerCase().includes(searchTerm)) ||
                        branch.id.toLowerCase().includes(searchTerm);
                    
                    // Find parent entity for filtering based on selected type
                    let parentEntity = '';
                    
                    if (selectedType === 'DEPARTMENT' || selectedType === 'ALL') {
                        // For departments, filter by parent JURPERSON
                        if (branch.parent_id) {
                            const parent = allBranches.find(b => b.id === branch.parent_id);
                            if (parent && parent.type === 'JURPERSON') {
                                parentEntity = parent.name;
                            }
                        }
                    } else if (selectedType === 'JURPERSON') {
                        // For JURPERSON, filter by parent CORPORATION
                        if (branch.parent_id) {
                            const parent = allBranches.find(b => b.id === branch.parent_id);
                            if (parent && parent.type === 'CORPORATION') {
                                parentEntity = parent.name;
                            }
                        }
                    }
                    // For CORPORATION type, no parent filtering is needed
                    
                    const matchesCompany = !selectedCompany || parentEntity === selectedCompany;
                    
                    return matchesType && matchesSearch && matchesCompany;
                });
                
                renderTable();
                updateTotalCount();
            }
            
            function renderTable() {
                const tbody = document.getElementById('branches-tbody');
                
                if (filteredBranches.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="no-data">Нет данных для отображения</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                filteredBranches.forEach(branch => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = branch.code || '-';
                    row.insertCell(1).textContent = branch.name || '-';
                    row.insertCell(2).textContent = branch.type || '-';
                    
                    // Segment type with Russian labels
                    const segmentLabels = {
                        'restaurant': 'Ресторан',
                        'coffeehouse': 'Кофейня',
                        'confectionery': 'Кондитерская',
                        'food_court': 'Фудкорт в ТРЦ',
                        'store': 'Магазин',
                        'fast_food': 'Фаст-фуд',
                        'bakery': 'Пекарня',
                        'cafe': 'Кафе',
                        'bar': 'Бар'
                    };
                    row.insertCell(3).textContent = segmentLabels[branch.segment_type] || branch.segment_type || '-';
                    
                    row.insertCell(4).textContent = branch.taxpayer_id_number || '-';
                    
                    // Season dates
                    let seasonText = '-';
                    if (branch.season_start_date && branch.season_end_date) {
                        const startDate = new Date(branch.season_start_date).toLocaleDateString('ru-RU');
                        const endDate = new Date(branch.season_end_date).toLocaleDateString('ru-RU');
                        seasonText = `${startDate} - ${endDate}`;
                    } else if (branch.season_start_date || branch.season_end_date) {
                        seasonText = 'Частично задан';
                    }
                    row.insertCell(5).textContent = seasonText;
                    
                    // Actions column
                    const actionsCell = row.insertCell(6);
                    actionsCell.innerHTML = `
                        <button class="edit-btn" onclick="editDepartment('${branch.id}')">
                            Редактировать
                        </button>
                    `;
                });
            }
            
            function updateTotalCount() {
                document.getElementById('total-count').textContent = `Всего: ${filteredBranches.length}`;
            }
            
            async function syncBranches() {
                if (!confirm('Это синхронизирует подразделения из внешнего API. Продолжить?')) return;
                
                document.getElementById('loading').style.display = 'inline';
                try {
                    const response = await fetch('/api/branches/sync', { method: 'POST', headers: AUTH_HEADERS });
                    const result = await response.json();
                    alert(result.message);
                    loadBranches();
                } catch (error) {
                    alert('Ошибка синхронизации: ' + error);
                } finally {
                    document.getElementById('loading').style.display = 'none';
                }
            }
            
            // Department Modal Functions
            function showDepartmentForm(departmentId = null) {
                const modal = document.getElementById('department-modal');
                const form = document.getElementById('department-form');
                const title = document.getElementById('modal-title');
                
                if (departmentId) {
                    title.textContent = 'Редактирование подразделения';
                    const department = allBranches.find(d => d.id === departmentId);
                    if (department) {
                        fillDepartmentForm(department);
                    }
                } else {
                    title.textContent = 'Создание подразделения';
                    form.reset();
                    document.getElementById('department-id').value = '';
                    // Hide ID field for new departments
                    document.getElementById('id-field-row').style.display = 'none';
                }
                
                // Show/hide season fields based on segment type
                toggleSeasonFields();
                modal.style.display = 'block';
            }
            
            function fillDepartmentForm(department) {
                document.getElementById('department-id').value = department.id || '';
                document.getElementById('department-name').value = department.name || '';
                document.getElementById('department-code').value = department.code || '';
                document.getElementById('department-type').value = department.type || 'DEPARTMENT';
                document.getElementById('department-segment').value = department.segment_type || 'restaurant';
                document.getElementById('department-inn').value = department.taxpayer_id_number || '';
                document.getElementById('department-code-tco').value = department.code_tco || '';
                document.getElementById('season-start').value = department.season_start_date || '';
                document.getElementById('season-end').value = department.season_end_date || '';
                
                // Fill and show the ID display field for editing existing departments
                if (department.id) {
                    document.getElementById('department-id-display').value = department.id;
                    document.getElementById('id-field-row').style.display = 'block';
                } else {
                    document.getElementById('id-field-row').style.display = 'none';
                }
            }
            
            function closeDepartmentModal() {
                document.getElementById('department-modal').style.display = 'none';
            }
            
            function toggleSeasonFields() {
                const segmentSelect = document.getElementById('department-segment');
                const seasonFields = document.getElementById('season-fields');
                
                if (segmentSelect.value === 'coffeehouse') {
                    seasonFields.style.display = 'block';
                } else {
                    seasonFields.style.display = 'none';
                }
            }
            
            function editDepartment(departmentId) {
                showDepartmentForm(departmentId);
            }
            
            async function deleteDepartment(departmentId) {
                const department = allBranches.find(d => d.id === departmentId);
                const departmentName = department ? department.name : 'подразделение';
                
                if (!confirm(`Удалить ${departmentName}?`)) return;
                
                try {
                    const response = await fetch(`/api/departments/${departmentId}`, {
                        method: 'DELETE',
                        headers: AUTH_HEADERS
                    });
                    
                    if (response.ok) {
                        alert('Подразделение удалено');
                        loadBranches();
                    } else {
                        const error = await response.json();
                        alert('Ошибка удаления: ' + (error.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    alert('Ошибка удаления: ' + error.message);
                }
            }
            
            // Department form submission
            document.getElementById('department-form').addEventListener('submit', async function(e) {
                e.preventDefault();
                
                const formData = new FormData(e.target);
                const departmentData = {};
                
                // Convert FormData to object
                for (let [key, value] of formData.entries()) {
                    if (value !== '') {
                        departmentData[key] = value;
                    }
                }
                
                // Remove id from data for create operations
                const departmentId = departmentData.id;
                delete departmentData.id;
                
                try {
                    let response;
                    if (departmentId) {
                        // Update existing department
                        response = await fetch(`/api/departments/${departmentId}`, {
                            method: 'PUT',
                            headers: {
                                ...AUTH_HEADERS,
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(departmentData)
                        });
                    } else {
                        // Create new department
                        response = await fetch('/api/departments/', {
                            method: 'POST',
                            headers: {
                                ...AUTH_HEADERS,
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(departmentData)
                        });
                    }
                    
                    if (response.ok) {
                        alert(departmentId ? 'Подразделение обновлено' : 'Подразделение создано');
                        closeDepartmentModal();
                        loadBranches();
                    } else {
                        const error = await response.json();
                        alert('Ошибка сохранения: ' + (error.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    alert('Ошибка сохранения: ' + error.message);
                }
            });
            
            // Close modal when clicking outside
            window.onclick = function(event) {
                const modal = document.getElementById('department-modal');
                if (event.target === modal) {
                    closeDepartmentModal();
                }
            }
            
            // Page Navigation Functions
            function showDepartments() {
                hideAllPages();
                document.getElementById('page-departments').style.display = 'block';
                updateSidebarActive('#подразделения');
                window.scrollTo(0, 0);
            }
            
            function showDataLoading() {
                hideAllPages();
                document.getElementById('page-data-loading').style.display = 'block';
                updateSidebarActive('#загрузка-данных');
                window.scrollTo(0, 0);

                // Set default dates (last 7 days)
                const today = new Date();
                const weekAgo = new Date(today);
                weekAgo.setDate(today.getDate() - 7);

                document.getElementById('end-date').value = today.toISOString().split('T')[0];
                document.getElementById('start-date').value = weekAgo.toISOString().split('T')[0];

                // Load departments for sync filter
                loadSyncDepartments();
            }

            async function loadSyncDepartments() {
                try {
                    const response = await fetch('/api/departments/', {
                        headers: AUTH_HEADERS
                    });
                    const departments = await response.json();

                    const select = document.getElementById('sync-department-filter');
                    // Keep first option (Все подразделения)
                    select.innerHTML = '<option value="">Все подразделения</option>';

                    // Filter only DEPARTMENT type and sort by name
                    const filteredDepartments = departments.filter(dept => dept.type === 'DEPARTMENT');
                    filteredDepartments.sort((a, b) => (a.name || '').localeCompare(b.name || ''));

                    filteredDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.id;
                        select.appendChild(option);
                    });
                } catch (error) {
                    console.error('Error loading departments for sync:', error);
                }
            }
            
            // Sales Sync Functions
            async function handleSalesSync(event) {
                event.preventDefault();

                const startDate = document.getElementById('start-date').value;
                const endDate = document.getElementById('end-date').value;
                const departmentId = document.getElementById('sync-department-filter').value;

                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }

                if (new Date(startDate) > new Date(endDate)) {
                    alert('Дата начала не может быть больше даты окончания');
                    return;
                }

                // Show progress
                showProgress();

                try {
                    // Sync sales data
                    updateProgress(50, 'Синхронизация данных продаж...');

                    // Build URL with optional department_id parameter
                    let syncUrl = `/api/sales/sync?from_date=${startDate}&to_date=${endDate}`;
                    if (departmentId) {
                        syncUrl += `&department_id=${departmentId}`;
                    }

                    const response = await fetch(syncUrl, {
                        method: 'POST',
                        headers: AUTH_HEADERS
                    });
                    
                    const result = await response.json();
                    
                    // Check if the result indicates success or error
                    if (result.status === 'success') {
                        updateProgress(100, 'Загрузка завершена успешно!');
                        showResult(true, result);
                    } else if (result.status === 'error') {
                        // API returned error status
                        updateProgress(100, 'Ошибка при загрузке данных');
                        showResult(false, result);
                    } else if (!response.ok) {
                        // HTTP error
                        throw new Error(result.detail || result.message || 'HTTP ошибка сервера');
                    } else {
                        // Unexpected response format
                        updateProgress(100, 'Загрузка завершена успешно!');
                        showResult(true, result);
                    }
                    
                } catch (error) {
                    console.error('Sync error:', error);
                    updateProgress(100, 'Произошла ошибка');
                    
                    // Create error object with details
                    const errorData = {
                        message: error.message || 'Неизвестная ошибка сети',
                        details: `Ошибка подключения к серверу. ${error.name ? `Тип: ${error.name}` : ''} Проверьте подключение к интернету и повторите попытку.`,
                        error_type: error.name || 'NetworkError',
                        total_raw_records: 0,
                        summary_records: 0,
                        hourly_records: 0,
                        from_date: startDate,
                        to_date: endDate
                    };
                    
                    showResult(false, errorData);
                } finally {
                    // Re-enable form
                    document.getElementById('load-btn').disabled = false;
                    document.getElementById('load-btn').textContent = 'Загрузить';
                }
            }
            
            function showProgress() {
                document.getElementById('progress-section').style.display = 'block';
                document.getElementById('result-section').style.display = 'none';
                document.getElementById('load-btn').disabled = true;
                document.getElementById('load-btn').textContent = 'Загружается...';
                updateProgress(0, 'Подготовка к загрузке...');
            }
            
            function updateProgress(percentage, message) {
                document.getElementById('progress-fill').style.width = percentage + '%';
                document.getElementById('progress-text').textContent = message;
            }
            
            function showResult(success, data) {
                const resultSection = document.getElementById('result-section');
                const resultContent = document.getElementById('result-content');
                
                resultSection.style.display = 'block';
                resultSection.className = 'result-section ' + (success ? 'result-success' : 'result-error');
                
                if (success) {
                    resultContent.innerHTML = `
                        <h3>✅ Синхронизация успешно завершена</h3>
                        <p><strong>Сообщение:</strong> ${data.message}</p>
                        <p><strong>Период:</strong> ${data.from_date} - ${data.to_date}</p>
                        <p><strong>Обработано записей:</strong> ${data.total_raw_records}</p>
                        <p><strong>Дневных сводок:</strong> ${data.summary_records}</p>
                        <p><strong>Почасовых записей:</strong> ${data.hourly_records}</p>
                        ${data.details ? `<p><strong>Детали:</strong> ${data.details}</p>` : ''}
                    `;
                } else {
                    resultContent.innerHTML = `
                        <h3>❌ Ошибка синхронизации</h3>
                        <p><strong>Основная ошибка:</strong> ${data.message || 'Неизвестная ошибка'}</p>
                        ${data.details ? `<p><strong>Подробности:</strong> ${data.details}</p>` : ''}
                        ${data.error_type ? `<p><strong>Тип ошибки:</strong> ${data.error_type}</p>` : ''}
                        ${data.from_date && data.to_date ? `<p><strong>Период:</strong> ${data.from_date} - ${data.to_date}</p>` : ''}
                        <p><strong>Статистика:</strong></p>
                        <ul style="margin-left: 20px;">
                            <li>Обработано записей: ${data.total_raw_records || 0}</li>
                            <li>Дневных сводок: ${data.summary_records || 0}</li>
                            <li>Почасовых записей: ${data.hourly_records || 0}</li>
                        </ul>
                        <p style="margin-top: 15px;"><strong>Рекомендации:</strong></p>
                        <ul style="margin-left: 20px;">
                            <li>Проверьте подключение к интернету</li>
                            <li>Убедитесь что указанные даты корректны</li>
                            <li>Попробуйте уменьшить диапазон дат</li>
                            <li>Если ошибка повторяется, обратитесь к администратору</li>
                        </ul>
                    `;
                }
            }
            
            // Sales Pages Navigation Functions
            function showDailySales() {
                hideAllPages();
                document.getElementById('page-daily-sales').style.display = 'block';
                updateSidebarActive('#продажи-по-дням');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('daily-end-date').value = today.toISOString().split('T')[0];
                document.getElementById('daily-start-date').value = monthAgo.toISOString().split('T')[0];
                
                // Populate department filter
                populateDepartmentFilters();
            }
            
            function showHourlySales() {
                hideAllPages();
                document.getElementById('page-hourly-sales').style.display = 'block';
                updateSidebarActive('#продажи-по-часам');
                window.scrollTo(0, 0);
                
                // Set default dates (last 7 days)
                const today = new Date();
                const weekAgo = new Date(today);
                weekAgo.setDate(today.getDate() - 7);
                
                document.getElementById('hourly-end-date').value = today.toISOString().split('T')[0];
                document.getElementById('hourly-start-date').value = weekAgo.toISOString().split('T')[0];
                
                // Populate filters
                populateDepartmentFilters();
                populateHourFilter();
            }
            
            function hideAllPages() {
                // Main pages
                document.getElementById('page-departments').style.display = 'none';
                document.getElementById('page-data-loading').style.display = 'none';
                document.getElementById('page-daily-sales').style.display = 'none';
                document.getElementById('page-hourly-sales').style.display = 'none';
                // Forecast pages
                document.getElementById('page-forecast-branch').style.display = 'none';
                document.getElementById('page-forecast-comparison').style.display = 'none';
                // Service pages
                document.getElementById('page-auto-sync').style.display = 'none';
            }
            
            function updateSidebarActive(selector) {
                document.querySelectorAll('.sidebar-menu a').forEach(a => a.classList.remove('active'));
                const activeLink = document.querySelector(`a[href="${selector}"]`);
                if (activeLink) {
                    activeLink.classList.add('active');
                }
            }
            
            function populateDepartmentFilters() {
                const departments = allBranches || [];
                // Filter only DEPARTMENT type (sales points)
                const salesPointDepartments = departments.filter(dept => dept.type === 'DEPARTMENT');

                // Populate daily sales department filter
                const dailyFilter = document.getElementById('daily-department-filter');
                if (dailyFilter) {
                    dailyFilter.innerHTML = '<option value="">Все подразделения</option>';
                    salesPointDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        dailyFilter.appendChild(option);
                    });
                }

                // Populate hourly sales department filter
                const hourlyFilter = document.getElementById('hourly-department-filter');
                if (hourlyFilter) {
                    hourlyFilter.innerHTML = '<option value="">Все подразделения</option>';
                    salesPointDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        hourlyFilter.appendChild(option);
                    });
                }
            }
            
            function populateHourFilter() {
                const hourFilter = document.getElementById('hourly-hour-filter');
                if (hourFilter) {
                    hourFilter.innerHTML = '<option value="">Все часы</option>';
                    for (let hour = 0; hour < 24; hour++) {
                        const option = document.createElement('option');
                        option.value = hour;
                        option.textContent = `${hour.toString().padStart(2, '0')}:00`;
                        hourFilter.appendChild(option);
                    }
                }
            }
            
            // Sales Data Loading Functions
            async function loadDailySales() {
                const startDate = document.getElementById('daily-start-date').value;
                const endDate = document.getElementById('daily-end-date').value;
                const departmentId = document.getElementById('daily-department-filter').value;
                
                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }
                
                document.getElementById('daily-loading').style.display = 'inline';
                
                try {
                    let url = `/api/sales/summary?from_date=${startDate}&to_date=${endDate}&limit=1000`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    
                    const response = await fetch(url, { headers: AUTH_HEADERS });
                    const salesData = await response.json();
                    
                    renderDailySalesTable(salesData);
                    document.getElementById('daily-total-count').textContent = `Всего: ${salesData.length}`;
                    
                } catch (error) {
                    console.error('Error loading daily sales:', error);
                    document.getElementById('daily-sales-tbody').innerHTML = 
                        '<tr><td colspan="6" class="no-data">Ошибка загрузки данных</td></tr>';
                } finally {
                    document.getElementById('daily-loading').style.display = 'none';
                }
            }
            
            async function loadHourlySales() {
                const startDate = document.getElementById('hourly-start-date').value;
                const endDate = document.getElementById('hourly-end-date').value;
                const departmentId = document.getElementById('hourly-department-filter').value;
                const hour = document.getElementById('hourly-hour-filter').value;
                
                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }
                
                document.getElementById('hourly-loading').style.display = 'inline';
                
                try {
                    let url = `/api/sales/hourly?from_date=${startDate}&to_date=${endDate}&limit=1000`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    if (hour !== '') {
                        url += `&hour=${hour}`;
                    }
                    
                    const response = await fetch(url, { headers: AUTH_HEADERS });
                    const salesData = await response.json();
                    
                    renderHourlySalesTable(salesData);
                    document.getElementById('hourly-total-count').textContent = `Всего: ${salesData.length}`;
                    
                    // Update chart if department is selected
                    updateHourlySalesChart(salesData, departmentId);
                    
                } catch (error) {
                    console.error('Error loading hourly sales:', error);
                    document.getElementById('hourly-sales-tbody').innerHTML = 
                        '<tr><td colspan="7" class="no-data">Ошибка загрузки данных</td></tr>';
                } finally {
                    document.getElementById('hourly-loading').style.display = 'none';
                }
            }
            
            function renderDailySalesTable(salesData) {
                const tbody = document.getElementById('daily-sales-tbody');
                
                if (salesData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="no-data">Нет данных для отображения</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                salesData.forEach(sale => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = sale.id;
                    
                    // Find department name
                    const dept = allBranches.find(b => b.id === sale.department_id);
                    row.insertCell(1).textContent = dept ? (dept.name || dept.code) : sale.department_id;
                    
                    row.insertCell(2).textContent = new Date(sale.date).toLocaleDateString('ru-RU');
                    row.insertCell(3).textContent = Math.round(Number(sale.total_sales)).toLocaleString('ru-RU');
                    row.insertCell(4).textContent = new Date(sale.created_at).toLocaleString('ru-RU');
                    row.insertCell(5).textContent = sale.synced_at ? new Date(sale.synced_at).toLocaleString('ru-RU') : '-';
                });
            }
            
            function renderHourlySalesTable(salesData) {
                const tbody = document.getElementById('hourly-sales-tbody');
                
                if (salesData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="7" class="no-data">Нет данных для отображения</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                salesData.forEach(sale => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = sale.id;
                    
                    // Find department name
                    const dept = allBranches.find(b => b.id === sale.department_id);
                    row.insertCell(1).textContent = dept ? (dept.name || dept.code) : sale.department_id;
                    
                    row.insertCell(2).textContent = new Date(sale.date).toLocaleDateString('ru-RU');
                    row.insertCell(3).textContent = `${sale.hour.toString().padStart(2, '0')}:00`;
                    row.insertCell(4).textContent = Math.round(Number(sale.sales_amount)).toLocaleString('ru-RU');
                    row.insertCell(5).textContent = new Date(sale.created_at).toLocaleString('ru-RU');
                    row.insertCell(6).textContent = sale.synced_at ? new Date(sale.synced_at).toLocaleString('ru-RU') : '-';
                });
            }
            
            // Global variable for hourly chart
            let hourlySalesChart = null;
            
            function updateHourlySalesChart(salesData, departmentId) {
                const chartWrapper = document.getElementById('hourly-chart-wrapper');
                const chartTitle = document.getElementById('hourly-chart-title');
                const chartNoData = document.getElementById('hourly-chart-no-data');
                const canvas = document.getElementById('hourlySalesChart');
                
                // Hide chart if no department selected
                if (!departmentId) {
                    chartWrapper.style.display = 'none';
                    return;
                }
                
                // Show chart wrapper
                chartWrapper.style.display = 'block';
                
                // Filter data for selected department
                const departmentData = salesData.filter(sale => sale.department_id === departmentId);
                
                // Get department name
                const dept = allBranches.find(b => b.id === departmentId);
                const departmentName = dept ? (dept.name || dept.code) : departmentId;
                
                // Get date range for title
                const startDate = document.getElementById('hourly-start-date').value;
                const endDate = document.getElementById('hourly-end-date').value;
                let dateRange = '';
                if (startDate && endDate) {
                    if (startDate === endDate) {
                        dateRange = `дата: ${new Date(startDate).toLocaleDateString('ru-RU')}`;
                    } else {
                        dateRange = `период: ${new Date(startDate).toLocaleDateString('ru-RU')} - ${new Date(endDate).toLocaleDateString('ru-RU')}`;
                    }
                }
                
                // Update title
                chartTitle.textContent = `Почасовая выручка, подразделение: ${departmentName}${dateRange ? ', ' + dateRange : ''}`;
                
                if (departmentData.length === 0) {
                    chartNoData.style.display = 'block';
                    canvas.style.display = 'none';
                    return;
                }
                
                chartNoData.style.display = 'none';
                canvas.style.display = 'block';
                
                // Prepare chart data
                const hourlyStats = {};
                
                // Aggregate data by hour
                departmentData.forEach(sale => {
                    const hour = sale.hour;
                    if (!hourlyStats[hour]) {
                        hourlyStats[hour] = 0;
                    }
                    hourlyStats[hour] += Number(sale.sales_amount || 0);
                });
                
                // Create arrays for chart (0-23 hours)
                const hours = [];
                const amounts = [];
                
                for (let h = 0; h < 24; h++) {
                    hours.push(`${h.toString().padStart(2, '0')}:00`);
                    amounts.push(hourlyStats[h] || 0);
                }
                
                // Destroy existing chart
                if (hourlySalesChart) {
                    hourlySalesChart.destroy();
                }
                
                // Create new chart
                const ctx = canvas.getContext('2d');
                hourlySalesChart = new Chart(ctx, {
                    type: 'bar',
                    data: {
                        labels: hours,
                        datasets: [{
                            label: 'Выручка',
                            data: amounts,
                            backgroundColor: 'rgba(52, 152, 219, 0.6)',
                            borderColor: 'rgba(52, 152, 219, 1)',
                            borderWidth: 1,
                            borderRadius: 4,
                            borderSkipped: false
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            title: {
                                display: false
                            },
                            legend: {
                                display: false
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const value = context.parsed.y;
                                        return 'Выручка: ₸ ' + Math.round(value).toLocaleString('ru-RU');
                                    }
                                }
                            }
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Час дня'
                                },
                                grid: {
                                    display: false
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Сумма продаж (₸)'
                                },
                                beginAtZero: true,
                                ticks: {
                                    callback: function(value) {
                                        return Math.round(value).toLocaleString('ru-RU');
                                    }
                                }
                            }
                        },
                        interaction: {
                            intersect: false,
                            mode: 'index'
                        }
                    }
                });
            }
            
            // Event listeners
            document.getElementById('search-input').addEventListener('input', applyFilters);
            document.getElementById('company-filter').addEventListener('change', applyFilters);
            
            // =============================================================
            // FORECAST FUNCTIONS v2.1 - LOGARITHMIC SCALE EDITION
            // Updated: 2025-06-24 | Auto Log/Linear Scale Detection
            // =============================================================
            let comparisonData = [];
            let sortColumn = 'date';
            let sortDirection = 'asc';
            let forecastChart = null;
            
            function showForecastByBranch() {
                hideAllPages();
                document.getElementById('page-forecast-branch').style.display = 'block';
                updateSidebarActive('#прогноз-по-филиалам');
                window.scrollTo(0, 0);
                
                // Set default dates (next 7 days)
                const today = new Date();
                const nextWeek = new Date(today);
                nextWeek.setDate(today.getDate() + 7);
                
                document.getElementById('forecast-start-date').value = today.toISOString().split('T')[0];
                document.getElementById('forecast-end-date').value = nextWeek.toISOString().split('T')[0];
                
                // Populate department filter
                populateForecastDepartmentFilters();
            }
            
            function showForecastComparison() {
                hideAllPages();
                document.getElementById('page-forecast-comparison').style.display = 'block';
                updateSidebarActive('#сравнение-факт-прогноз');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days with actual data)
                // Use yesterday as end date since today might not have actual sales data yet
                const today = new Date();
                const yesterday = new Date(today);
                yesterday.setDate(today.getDate() - 1);
                const monthAgo = new Date(yesterday);
                monthAgo.setDate(yesterday.getDate() - 30);
                
                document.getElementById('comparison-start-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('comparison-end-date').value = yesterday.toISOString().split('T')[0];
                
                // Populate department filter
                populateForecastDepartmentFilters();
            }
            
            function populateForecastDepartmentFilters() {
                const departments = allBranches || [];
                // Filter only DEPARTMENT type (sales points)
                const salesPointDepartments = departments.filter(dept => dept.type === 'DEPARTMENT');

                // Forecast page filter
                const forecastFilter = document.getElementById('forecast-department-filter');
                if (forecastFilter) {
                    forecastFilter.innerHTML = '<option value="">Все подразделения</option>';
                    salesPointDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        forecastFilter.appendChild(option);
                    });
                }

                // Comparison page filter
                const comparisonFilter = document.getElementById('comparison-department-filter');
                if (comparisonFilter) {
                    comparisonFilter.innerHTML = '<option value="">Все подразделения</option>';
                    salesPointDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        comparisonFilter.appendChild(option);
                    });
                }

                // Export page filter
                const exportFilter = document.getElementById('export-department');
                if (exportFilter) {
                    exportFilter.innerHTML = '<option value="">Все подразделения</option>';
                    salesPointDepartments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        exportFilter.appendChild(option);
                    });
                }
            }
            
            async function loadForecasts() {
                const startDate = document.getElementById('forecast-start-date').value;
                const endDate = document.getElementById('forecast-end-date').value;
                const departmentId = document.getElementById('forecast-department-filter').value;
                
                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }
                
                document.getElementById('forecast-loading').style.display = 'inline';
                
                try {
                    let url = `/api/forecast/batch?from_date=${startDate}&to_date=${endDate}`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    
                    const response = await fetch(url, { headers: AUTH_HEADERS });
                    const forecastData = await response.json();
                    
                    renderForecastTable(forecastData);
                    document.getElementById('forecast-total-count').textContent = `Всего: ${forecastData.length}`;
                    
                } catch (error) {
                    console.error('Error loading forecasts:', error);
                    document.getElementById('forecast-tbody').innerHTML = 
                        '<tr><td colspan="3" class="no-data">Ошибка загрузки данных</td></tr>';
                } finally {
                    document.getElementById('forecast-loading').style.display = 'none';
                }
            }
            
            function renderForecastTable(forecastData) {
                const tbody = document.getElementById('forecast-tbody');
                
                if (forecastData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="3" class="no-data">Нет данных для отображения</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                forecastData.forEach(forecast => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = new Date(forecast.date).toLocaleDateString('ru-RU');
                    row.insertCell(1).textContent = forecast.department_name;
                    
                    const salesCell = row.insertCell(2);
                    if (forecast.predicted_sales !== null) {
                        salesCell.textContent = '₸ ' + Math.round(forecast.predicted_sales).toLocaleString('ru-RU');
                    } else {
                        salesCell.textContent = 'Недостаточно данных';
                        salesCell.style.color = '#999';
                    }
                });
            }
            
            async function loadComparison() {
                const startDate = document.getElementById('comparison-start-date').value;
                const endDate = document.getElementById('comparison-end-date').value;
                const departmentId = document.getElementById('comparison-department-filter').value;
                
                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }
                
                document.getElementById('comparison-loading').style.display = 'inline';
                
                try {
                    let url = `/api/forecast/comparison?from_date=${startDate}&to_date=${endDate}`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    
                    const response = await fetch(url, { headers: AUTH_HEADERS });
                    comparisonData = await response.json();
                    
                    renderComparisonTable();
                    updateForecastChart();
                    calculateAndDisplayAverageError();
                    document.getElementById('comparison-total-count').textContent = `Всего: ${comparisonData.length}`;
                    
                } catch (error) {
                    console.error('Error loading comparison:', error);
                    document.getElementById('comparison-tbody').innerHTML = 
                        '<tr><td colspan="6" class="no-data">Ошибка загрузки данных</td></tr>';
                    // Скрываем блок средней ошибки при ошибке
                    document.getElementById('average-error-display').style.display = 'none';
                } finally {
                    document.getElementById('comparison-loading').style.display = 'none';
                }
            }
            
            function renderComparisonTable() {
                const tbody = document.getElementById('comparison-tbody');
                
                if (comparisonData.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="no-data">Нет данных для отображения</td></tr>';
                    // Скрываем блок средней ошибки если нет данных
                    document.getElementById('average-error-display').style.display = 'none';
                    return;
                }
                
                tbody.innerHTML = '';
                comparisonData.forEach(item => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = new Date(item.date).toLocaleDateString('ru-RU');
                    row.insertCell(1).textContent = item.department_name;
                    row.insertCell(2).textContent = '₸ ' + Math.round(item.predicted_sales).toLocaleString('ru-RU');
                    row.insertCell(3).textContent = '₸ ' + Math.round(item.actual_sales).toLocaleString('ru-RU');
                    
                    const errorCell = row.insertCell(4);
                    const error = item.error;
                    errorCell.textContent = (error >= 0 ? '+' : '') + Math.round(error).toLocaleString('ru-RU');
                    errorCell.style.color = error >= 0 ? '#27ae60' : '#e74c3c';
                    
                    const errorPctCell = row.insertCell(5);
                    errorPctCell.textContent = item.error_percentage.toFixed(1) + '%';
                    if (item.error_percentage > 20) {
                        errorPctCell.style.color = '#e74c3c';
                        errorPctCell.style.fontWeight = 'bold';
                    }
                });
            }
            
            function sortComparison(column) {
                const columnMap = {
                    'date': 'date',
                    'department': 'department_name',
                    'predicted': 'predicted_sales',
                    'actual': 'actual_sales',
                    'error': 'error',
                    'error_pct': 'error_percentage'
                };
                
                const sortKey = columnMap[column];
                
                if (sortColumn === sortKey) {
                    sortDirection = sortDirection === 'asc' ? 'desc' : 'asc';
                } else {
                    sortColumn = sortKey;
                    sortDirection = 'asc';
                }
                
                comparisonData.sort((a, b) => {
                    let aVal = a[sortKey];
                    let bVal = b[sortKey];
                    
                    if (sortKey === 'date') {
                        aVal = new Date(aVal);
                        bVal = new Date(bVal);
                    }
                    
                    if (sortDirection === 'asc') {
                        return aVal > bVal ? 1 : -1;
                    } else {
                        return aVal < bVal ? 1 : -1;
                    }
                });
                
                renderComparisonTable();
                updateForecastChart();
                calculateAndDisplayAverageError();
            }
            
            // =============================================================
            // AVERAGE ERROR CALCULATION FUNCTION
            // Calculates and displays average error percentage
            // =============================================================
            function calculateAndDisplayAverageError() {
                const avgErrorDisplay = document.getElementById('average-error-display');
                const avgErrorText = document.getElementById('average-error-text');
                
                if (!comparisonData || comparisonData.length === 0) {
                    avgErrorDisplay.style.display = 'none';
                    return;
                }
                
                // Извлекаем валидные значения % ошибки
                const validErrorPercentages = comparisonData
                    .map(item => item.error_percentage)
                    .filter(value => 
                        value !== null && 
                        value !== undefined && 
                        !isNaN(value) && 
                        isFinite(value)
                    );
                
                if (validErrorPercentages.length === 0) {
                    avgErrorText.textContent = 'Нет данных для расчёта средней ошибки';
                    avgErrorDisplay.style.display = 'block';
                    return;
                }
                
                // Вычисляем среднее значение
                const averageError = validErrorPercentages.reduce((sum, value) => sum + Math.abs(value), 0) / validErrorPercentages.length;
                
                // Форматируем результат
                const formattedAverage = averageError.toFixed(1);
                avgErrorText.textContent = `Средний % ошибки за выбранный период: ${formattedAverage}%`;
                
                // Показываем блок
                avgErrorDisplay.style.display = 'block';
            }
            
            // =============================================================
            // LOGARITHMIC SCALE CHART FUNCTION v2.1
            // Auto-detects data outliers and switches between linear/log scale
            // Trigger: ratio > 5x = logarithmic scale + warning
            // =============================================================
            function updateForecastChart() {
                const chartWrapper = document.getElementById('forecast-chart-wrapper');
                const departmentFilter = document.getElementById('comparison-department-filter');
                const chartWarning = document.getElementById('chart-warning');
                const chartOutliersWarning = document.getElementById('chart-outliers-warning');
                const chartNoData = document.getElementById('chart-no-data');
                const chartCanvas = document.getElementById('forecastChart');
                
                // Скрываем все элементы по умолчанию
                chartWarning.style.display = 'none';
                chartOutliersWarning.style.display = 'none';
                chartNoData.style.display = 'none';
                chartCanvas.style.display = 'block';
                
                // Проверяем: выбран ли только один филиал (не "Все подразделения")
                if (!departmentFilter.value || comparisonData.length === 0) {
                    chartWrapper.style.display = 'none';
                    if (forecastChart) {
                        forecastChart.destroy();
                        forecastChart = null;
                    }
                    return;
                }
                
                chartWrapper.style.display = 'block';
                
                // Группируем данные по датам для одного филиала
                const chartData = {};
                comparisonData.forEach(item => {
                    const date = new Date(item.date).toLocaleDateString('ru-RU');
                    if (!chartData[date]) {
                        chartData[date] = {
                            predicted: item.predicted_sales,
                            actual: item.actual_sales
                        };
                    }
                });
                
                // Сортируем даты по возрастанию
                const allDates = Object.keys(chartData).sort((a, b) => {
                    const dateA = new Date(a.split('.').reverse().join('-'));
                    const dateB = new Date(b.split('.').reverse().join('-'));
                    return dateA - dateB;
                });
                
                // Проверяем наличие данных
                if (allDates.length === 0) {
                    chartNoData.style.display = 'block';
                    chartCanvas.style.display = 'none';
                    if (forecastChart) {
                        forecastChart.destroy();
                        forecastChart = null;
                    }
                    return;
                }
                
                // ОПТИМИЗАЦИЯ: Ограничиваем количество точек для производительности
                const MAX_POINTS = 30;
                let dates, showWarning = false;
                
                if (allDates.length > MAX_POINTS) {
                    // Показываем последние 30 дат
                    dates = allDates.slice(-MAX_POINTS);
                    showWarning = true;
                } else {
                    dates = allDates;
                }
                
                // Показываем предупреждение если данных много
                if (showWarning) {
                    chartWarning.style.display = 'block';
                }
                
                // Подготавливаем данные для графика
                const predictedValues = dates.map(date => chartData[date].predicted);
                const actualValues = dates.map(date => chartData[date].actual);
                
                // ============= ИНТЕЛЛЕКТУАЛЬНАЯ ОБРАБОТКА ВЫБРОСОВ =============
                
                // Собираем все значения (исключаем null/undefined)
                const allValues = [...predictedValues, ...actualValues].filter(v => v != null && v > 0);
                
                if (allValues.length === 0) {
                    chartNoData.style.display = 'block';
                    chartCanvas.style.display = 'none';
                    return;
                }
                
                // Функция для вычисления процентилей
                function percentile(arr, p) {
                    const sorted = [...arr].sort((a, b) => a - b);
                    const index = (p / 100) * (sorted.length - 1);
                    const lower = Math.floor(index);
                    const upper = Math.ceil(index);
                    const weight = index % 1;
                    return sorted[lower] * (1 - weight) + sorted[upper] * weight;
                }
                
                // Вычисляем 5-й и 95-й процентили для обрезки экстремальных значений
                const p5 = percentile(allValues, 5);
                const p95 = percentile(allValues, 95);
                const originalRange = Math.max(...allValues) - Math.min(...allValues);
                const clippedRange = p95 - p5;
                
                // Определяем есть ли значительные выбросы (>3x от нормального диапазона)
                const hasExtremeOutliers = originalRange / clippedRange > 3;
                
                // Подготавливаем данные для отображения
                let displayPredicted, displayActual, clippedCount = 0;
                let minValue, maxValue;
                
                if (hasExtremeOutliers) {
                    // Ограничиваем данные процентилями для лучшей читаемости
                    displayPredicted = predictedValues.map(v => {
                        if (v == null) return null;
                        if (v < p5 || v > p95) {
                            clippedCount++;
                            return v < p5 ? p5 : p95;
                        }
                        return v;
                    });
                    
                    displayActual = actualValues.map(v => {
                        if (v == null) return null;
                        if (v < p5 || v > p95) {
                            clippedCount++;
                            return v < p5 ? p5 : p95;
                        }
                        return v;
                    });
                    
                    minValue = p5 * 0.95;
                    maxValue = p95 * 1.05;
                    
                    // Показываем предупреждение об использовании логарифмической шкалы
                    chartOutliersWarning.innerHTML = `
                        📈 <strong>Логарифмическая шкала:</strong> 
                        График использует логарифмическую шкалу для лучшей читаемости данных с большими различиями. 
                        ${clippedCount} экстремальных значений ограничены границами 
                        ${p5.toLocaleString('ru-RU')}₸ - ${p95.toLocaleString('ru-RU')}₸.
                    `;
                    chartOutliersWarning.style.display = 'block';
                } else {
                    // Используем исходные данные
                    displayPredicted = predictedValues;
                    displayActual = actualValues;
                    minValue = Math.min(...allValues) * 0.95;
                    maxValue = Math.max(...allValues) * 1.05;
                }
                
                // Конфигурация оси Y с интеллектуальным выбором шкалы
                let yAxisConfig = {
                    type: hasExtremeOutliers ? 'logarithmic' : 'linear',
                    beginAtZero: false,
                    min: hasExtremeOutliers ? Math.max(1, Math.min(...allValues) * 0.8) : minValue,
                    max: hasExtremeOutliers ? Math.max(...allValues) * 1.2 : maxValue,
                    title: {
                        display: true,
                        text: hasExtremeOutliers ? 'Сумма продаж (₸) - логарифмическая шкала' : 'Сумма продаж (₸)'
                    },
                    ticks: {
                        callback: function(value) {
                            if (value >= 1000000) {
                                return '₸ ' + (value / 1000000).toFixed(1) + 'М';
                            } else if (value >= 1000) {
                                return '₸ ' + (value / 1000).toFixed(0) + 'К';
                            } else {
                                return '₸ ' + value.toLocaleString('ru-RU');
                            }
                        },
                        maxTicksLimit: hasExtremeOutliers ? 6 : 8
                    }
                };
                
                
                // ============= СОЗДАНИЕ ГРАФИКА =============
                
                // Уничтожаем предыдущий график
                if (forecastChart) {
                    forecastChart.destroy();
                }
                
                // Создаем новый график с оптимизированными настройками
                const ctx = document.getElementById('forecastChart').getContext('2d');
                forecastChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: dates,
                        datasets: [
                            {
                                label: 'Прогноз',
                                data: displayPredicted,
                                borderColor: '#3498db',
                                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                borderWidth: 2,
                                fill: false,
                                tension: 0.1,
                                pointRadius: dates.length > 15 ? 2 : 4,
                                pointHoverRadius: 6
                            },
                            {
                                label: 'Факт',
                                data: displayActual,
                                borderColor: '#27ae60',
                                backgroundColor: 'rgba(39, 174, 96, 0.1)',
                                borderWidth: 2,
                                fill: false,
                                tension: 0.1,
                                pointRadius: dates.length > 15 ? 2 : 4,
                                pointHoverRadius: 6
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        aspectRatio: 3,
                        interaction: {
                            intersect: false,
                            mode: 'index'
                        },
                        // ОПТИМИЗАЦИЯ: Отключаем анимацию для производительности
                        animation: {
                            duration: dates.length > 15 ? 0 : 750
                        },
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Дата'
                                },
                                ticks: {
                                    // ОПТИМИЗАЦИЯ: Читаемые подписи дат
                                    maxTicksLimit: Math.min(dates.length, 12),
                                    maxRotation: 45,
                                    minRotation: 0,
                                    callback: function(value, index, values) {
                                        // Форматируем дату как ДД.ММ
                                        const label = this.getLabelForValue(value);
                                        return label ? label.slice(0, 5) : '';
                                    }
                                }
                            },
                            y: yAxisConfig
                        },
                        plugins: {
                            title: {
                                display: false
                            },
                            legend: {
                                display: true,
                                position: 'top'
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        // Показываем реальные значения в подсказках (до ограничения)
                                        const dataIndex = context.dataIndex;
                                        const datasetIndex = context.datasetIndex;
                                        let originalValue;
                                        
                                        if (datasetIndex === 0) {
                                            // Прогноз
                                            originalValue = predictedValues[dataIndex];
                                        } else {
                                            // Факт
                                            originalValue = actualValues[dataIndex];
                                        }
                                        
                                        if (originalValue == null) {
                                            return context.dataset.label + ': Нет данных';
                                        }
                                        
                                        const displayValue = context.parsed.y;
                                        const isClipped = Math.abs(originalValue - displayValue) > 1;
                                        
                                        let label = context.dataset.label + ': ₸ ' + originalValue.toLocaleString('ru-RU');
                                        
                                        if (isClipped) {
                                            label += ' (на графике: ₸ ' + displayValue.toLocaleString('ru-RU') + ')';
                                        }
                                        
                                        return label;
                                    }
                                }
                            },
                            // ОПТИМИЗАЦИЯ: Включаем decimation для больших данных
                            decimation: {
                                enabled: dates.length > 20,
                                algorithm: 'lttb',
                                samples: 20
                            }
                        }
                    }
                });
            }
            
            async function loadModelInfo() {
                try {
                    const response = await fetch('/api/forecast/model/info', { headers: AUTH_HEADERS });
                    const modelInfo = await response.json();
                    
                    const infoDiv = document.getElementById('model-info');
                    if (modelInfo.status === 'loaded') {
                        let html = `
                            <p><strong>Статус модели:</strong> <span style="color: #27ae60;">✅ Загружена</span></p>
                            <p><strong>Тип модели:</strong> ${modelInfo.model_type}</p>
                            <p><strong>Количество признаков:</strong> ${modelInfo.n_features}</p>
                            <p><strong>Путь к модели:</strong> ${modelInfo.model_path}</p>
                        `;
                        
                        // Если есть метрики обучения, показываем их
                        if (modelInfo.training_metrics) {
                            const metrics = modelInfo.training_metrics;
                            html += `
                                <div style="margin-top: 20px; padding: 15px; background: #f0f8ff; border-radius: 8px; border: 1px solid #b0d4f0;">
                                    <h4 style="margin-top: 0; color: #2c3e50;">📊 Метрики последнего обучения (Модель v2.0):</h4>
                                    
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 15px 0;">
                                        <div style="background: #fff3cd; padding: 12px; border-radius: 6px; border: 1px solid #ffeaa7;">
                                            <h5 style="margin: 0 0 8px 0; color: #856404;">📈 Validation (контроль обучения):</h5>
                                            <div style="font-size: 13px;">
                                                <p style="margin: 3px 0;"><strong>MAE:</strong> ${metrics.val_mae ? metrics.val_mae.toFixed(2) : 'N/A'}</p>
                                                <p style="margin: 3px 0;"><strong>MAPE:</strong> ${metrics.val_mape ? metrics.val_mape.toFixed(2) + '%' : 'N/A'}</p>
                                                <p style="margin: 3px 0;"><strong>R²:</strong> ${metrics.val_r2 ? metrics.val_r2.toFixed(4) : 'N/A'}</p>
                                                <p style="margin: 3px 0;"><strong>RMSE:</strong> ${metrics.val_rmse ? metrics.val_rmse.toFixed(2) : 'N/A'}</p>
                                            </div>
                                        </div>
                                        
                                        <div style="background: #d1ecf1; padding: 12px; border-radius: 6px; border: 1px solid #7dd3fc;">
                                            <h5 style="margin: 0 0 8px 0; color: #0c5460;">🎯 Test (честная оценка):</h5>
                                            <div style="font-size: 13px;">
                                                <p style="margin: 3px 0;"><strong>MAE:</strong> ${metrics.test_mae ? metrics.test_mae.toFixed(2) : metrics.mae.toFixed(2)}</p>
                                                <p style="margin: 3px 0;"><strong>MAPE:</strong> ${metrics.test_mape ? metrics.test_mape.toFixed(2) + '%' : metrics.mape.toFixed(2) + '%'}</p>
                                                <p style="margin: 3px 0;"><strong>R²:</strong> ${metrics.test_r2 ? metrics.test_r2.toFixed(4) : metrics.r2.toFixed(4)}</p>
                                                <p style="margin: 3px 0;"><strong>RMSE:</strong> ${metrics.test_rmse ? metrics.test_rmse.toFixed(2) : metrics.rmse.toFixed(2)}</p>
                                            </div>
                                        </div>
                                    </div>
                                    
                                    <div style="margin-top: 15px; padding: 10px; background: #e7f3ff; border-radius: 6px; border-left: 4px solid #2196F3;">
                                        <p style="margin: 5px 0; font-size: 14px; color: #1976D2;">
                                            <strong>📍 Объяснение:</strong><br>
                                            • <strong>Validation</strong> - данные для контроля обучения (early stopping)<br>
                                            • <strong>Test</strong> - честная оценка на данных, которые модель никогда не видела<br>
                                            • Test метрики показывают реальную производительность на новых данных
                                        </p>
                                    </div>
                                    
                                    <div style="margin-top: 10px; font-size: 13px; color: #666;">
                                        <p style="margin: 2px 0;"><strong>📊 Размеры выборок:</strong></p>
                                        <p style="margin: 2px 0;">• Обучение: ${metrics.train_samples} записей</p>
                                        <p style="margin: 2px 0;">• Validation: ${metrics.val_samples || 'N/A'} записей</p>
                                        <p style="margin: 2px 0;">• Test: ${metrics.test_samples} записей</p>
                                    </div>
                                </div>
                            `;
                        }
                        
                        html += `
                            <div style="margin-top: 15px;">
                                <button class="sync-btn" onclick="retrainModel()">🔄 Переобучить модель</button>
                            </div>
                        `;
                        
                        infoDiv.innerHTML = html;
                    } else {
                        infoDiv.innerHTML = `
                            <p><strong>Статус модели:</strong> <span style="color: #e74c3c;">❌ Не загружена</span></p>
                            <p>Необходимо обучить модель перед использованием прогнозов.</p>
                            <div style="margin-top: 15px;">
                                <button class="sync-btn" onclick="retrainModel()">🚀 Обучить модель</button>
                            </div>
                        `;
                    }
                } catch (error) {
                    console.error('Error loading model info:', error);
                    document.getElementById('model-info').innerHTML = 
                        '<p style="color: #e74c3c;">Ошибка загрузки информации о модели</p>';
                }
            }
            
            async function retrainModel() {
                if (!confirm('Переобучение модели может занять несколько минут. Продолжить?')) return;
                
                const infoDiv = document.getElementById('model-info');
                const originalContent = infoDiv.innerHTML;
                infoDiv.innerHTML = '<p>⏳ Идет обучение модели...</p>';
                
                try {
                    const response = await fetch('/api/forecast/retrain', { method: 'POST', headers: AUTH_HEADERS });
                    const result = await response.json();
                    
                    if (result.status === 'success') {
                        // Показываем временное сообщение об успешном обучении
                        infoDiv.innerHTML = `
                            <div style="padding: 15px; background: #d4edda; border-radius: 8px; border: 1px solid #c3e6cb; margin-bottom: 20px;">
                                <p style="color: #155724; margin: 0;"><strong>✅ Модель успешно обучена!</strong></p>
                            </div>
                        `;
                        
                        // Сразу загружаем обновленную информацию о модели
                        setTimeout(() => {
                            loadModelInfo();
                        }, 2000);
                    } else {
                        throw new Error(result.detail || 'Ошибка обучения');
                    }
                } catch (error) {
                    console.error('Error retraining model:', error);
                    infoDiv.innerHTML = `
                        <div style="padding: 15px; background: #f8d7da; border-radius: 8px; border: 1px solid #f5c6cb; margin-bottom: 20px;">
                            <p style="color: #721c24; margin: 0;">❌ Ошибка обучения модели: ${error.message}</p>
                        </div>
                        ${originalContent}
                    `;
                }
            }
            
            // Initialize form handler when DOM is loaded
            document.addEventListener('DOMContentLoaded', function() {
                const salesForm = document.getElementById('sales-sync-form');
                if (salesForm) {
                    salesForm.addEventListener('submit', handleSalesSync);
                }
            });

            // =============================================================
            // AUTO SYNC FUNCTIONS
            // =============================================================
            
            function showAutoSyncStatus() {
                hideAllPages();
                document.getElementById('page-auto-sync').style.display = 'block';
                updateSidebarActive('#авто-загрузка');
                window.scrollTo(0, 0);
                
                // Load auto sync status on page show
                loadAutoSyncStatus();
            }
            
            async function loadAutoSyncStatus() {
                try {
                    const response = await fetch('/api/sales/auto-sync/status', { headers: AUTH_HEADERS });
                    const data = await response.json();
                    
                    // Update statistics
                    document.getElementById('success-count').textContent = data.statistics.success_count_30d;
                    document.getElementById('error-count').textContent = data.statistics.error_count_30d;
                    document.getElementById('success-rate').textContent = data.statistics.success_rate_30d;
                    
                    // Update latest sync info
                    updateLatestSyncInfo(data.statistics);
                    
                    // Render logs table
                    renderAutoSyncTable(data.logs);
                    
                } catch (error) {
                    console.error('Error loading auto sync status:', error);
                    document.getElementById('latest-sync-info').innerHTML = 
                        '<p style="color: #e74c3c;">Ошибка загрузки данных</p>';
                }
            }
            
            function updateLatestSyncInfo(statistics) {
                const infoDiv = document.getElementById('latest-sync-info');
                
                if (statistics.latest_success) {
                    const successInfo = statistics.latest_success;
                    infoDiv.innerHTML = `
                        <div style="background: #d4edda; border: 1px solid #c3e6cb; color: #155724; padding: 15px; border-radius: 8px; margin-bottom: 15px;">
                            <h4 style="margin-bottom: 10px;">✅ Последняя успешная загрузка</h4>
                            <p><strong>Дата данных:</strong> ${new Date(successInfo.date).toLocaleDateString('ru-RU')}</p>
                            <p><strong>Время выполнения:</strong> ${new Date(successInfo.executed_at).toLocaleString('ru-RU')}</p>
                            <p><strong>Загружено записей:</strong> ${successInfo.records.toLocaleString('ru-RU')}</p>
                            <p><strong>Сообщение:</strong> ${successInfo.message}</p>
                        </div>
                    `;
                } else {
                    infoDiv.innerHTML = `
                        <div style="background: #f8d7da; border: 1px solid #f5c6cb; color: #721c24; padding: 15px; border-radius: 8px;">
                            <p>🚫 Успешных автоматических загрузок пока не было</p>
                        </div>
                    `;
                }
                
                if (statistics.latest_error) {
                    const errorInfo = statistics.latest_error;
                    infoDiv.innerHTML += `
                        <div style="background: #fff3cd; border: 1px solid #ffeaa7; color: #856404; padding: 15px; border-radius: 8px;">
                            <h4 style="margin-bottom: 10px;">⚠️ Последняя ошибка</h4>
                            <p><strong>Дата данных:</strong> ${new Date(errorInfo.date).toLocaleDateString('ru-RU')}</p>
                            <p><strong>Время выполнения:</strong> ${new Date(errorInfo.executed_at).toLocaleString('ru-RU')}</p>
                            <p><strong>Ошибка:</strong> ${errorInfo.message}</p>
                            ${errorInfo.error_details ? `<p><strong>Детали:</strong> ${errorInfo.error_details}</p>` : ''}
                        </div>
                    `;
                }
            }
            
            function renderAutoSyncTable(logs) {
                const tbody = document.getElementById('auto-sync-tbody');
                
                if (logs.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="6" class="no-data">Логов автоматических загрузок пока нет</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                logs.forEach(log => {
                    const row = tbody.insertRow();
                    
                    // Executed At
                    row.insertCell(0).textContent = new Date(log.executed_at).toLocaleString('ru-RU');
                    
                    // Sync Date (data period)
                    row.insertCell(1).textContent = new Date(log.sync_date).toLocaleDateString('ru-RU');
                    
                    // Sync Type
                    const typeCell = row.insertCell(2);
                    typeCell.textContent = log.sync_type === 'daily_auto' ? 'Автоматически' : 'Вручную';
                    
                    // Status
                    const statusCell = row.insertCell(3);
                    if (log.status === 'success') {
                        statusCell.innerHTML = '<span style="color: #27ae60; font-weight: bold;">✅ Успешно</span>';
                    } else {
                        statusCell.innerHTML = '<span style="color: #e74c3c; font-weight: bold;">❌ Ошибка</span>';
                    }
                    
                    // Records count
                    const recordsCell = row.insertCell(4);
                    const totalRecords = (log.summary_records || 0) + (log.hourly_records || 0);
                    recordsCell.textContent = totalRecords.toLocaleString('ru-RU');
                    
                    // Message
                    const messageCell = row.insertCell(5);
                    messageCell.textContent = log.message || '-';
                    messageCell.style.maxWidth = '300px';
                    messageCell.style.overflow = 'hidden';
                    messageCell.style.textOverflow = 'ellipsis';
                    messageCell.style.whiteSpace = 'nowrap';
                    
                    if (log.error_details) {
                        messageCell.title = log.error_details; // Show full error on hover
                    }
                });
            }
            
            async function testAutoSync() {
                if (!confirm('Это запустит тестовую автоматическую загрузку продаж. Продолжить?')) return;
                
                try {
                    const button = event.target;
                    button.disabled = true;
                    button.textContent = '⏳ Выполняется...';
                    
                    const response = await fetch('/api/sales/auto-sync/test', { method: 'POST', headers: AUTH_HEADERS });
                    const result = await response.json();
                    
                    if (result.result && result.result.status === 'success') {
                        alert(`✅ Тестовая загрузка выполнена успешно!\n\nЗагружено записей: ${result.result.total_raw_records || 0}\nДневных сводок: ${result.result.summary_records || 0}\nПочасовых записей: ${result.result.hourly_records || 0}`);
                    } else {
                        alert(`⚠️ Тестовая загрузка завершилась с ошибкой:\n\n${result.result?.message || result.message || 'Неизвестная ошибка'}`);
                    }
                    
                    // Reload status
                    loadAutoSyncStatus();
                    
                } catch (error) {
                    console.error('Error testing auto sync:', error);
                    alert('❌ Ошибка при выполнении тестовой загрузки: ' + error.message);
                } finally {
                    const button = event.target;
                    button.disabled = false;
                    button.textContent = '🧪 Тестовый запуск';
                }
            }

            // Load data on page load
            window.onload = function() {
                // Show departments page by default
                showDepartments();
                // Load departments data
                loadBranches();
            };
        </script>
    </body>
    </html>
    """
    
    return html_content.replace('{api_token}', api_token)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}