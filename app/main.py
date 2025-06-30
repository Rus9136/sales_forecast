from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from .config import settings
from .db import engine, Base
from .routers import branch, department, sales, forecast, monitoring, auth
from .services.scheduled_sales_loader import run_auto_sync
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
        
        scheduler.start()
        logger.info("✅ Background scheduler started - Daily sales sync at 2:00 AM, Weekly model retraining on Sundays at 3:00 AM, Daily metrics calculation at 4:00 AM")
        
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
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
        <meta http-equiv="Pragma" content="no-cache">
        <meta http-equiv="Expires" content="0">
        <title>AI Модуль - v2.3 (Hourly Charts)</title>
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
                background-color: #d4a574;
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
                background-color: #c49660;
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
                    <li><a href="#экспорт-прогноза" onclick="showForecastExport()">📤 Экспорт прогноза</a></li>
                    <li><a href="#пост-обработка" onclick="showForecastPostprocessing()">🔧 Пост-обработка прогнозов</a></li>
                    <li><a href="#анализ" class="section-header">АНАЛИЗ ОШИБОК</a></li>
                    <li><a href="#ошибки-по-сегментам" onclick="showErrorAnalysisBySegment()">📊 Ошибки по сегментам</a></li>
                    <li><a href="#проблемные-филиалы" onclick="showProblematicBranches()">⚠️ Проблемные филиалы</a></li>
                    <li><a href="#временной-анализ" onclick="showTemporalAnalysis()">📈 Временной анализ</a></li>
                    <li><a href="#распределение-ошибок" onclick="showErrorDistribution()">📋 Распределение ошибок</a></li>
                    <li><a href="#мониторинг" class="section-header">МОНИТОРИНГ МОДЕЛЕЙ</a></li>
                    <li><a href="#статус-модели" onclick="showModelStatus()">📊 Статус модели</a></li>
                    <li><a href="#метрики-производительности" onclick="showPerformanceMetrics()">📈 Метрики производительности</a></li>
                    <li><a href="#история-обучения" onclick="showTrainingHistory()">📋 История обучения</a></li>
                    <li><a href="#ручное-переобучение" onclick="showManualRetraining()">🔄 Ручное переобучение</a></li>
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
                            <select class="filter-select" id="company-filter">
                                <option value="">Все компании</option>
                            </select>
                            
                            <input type="text" class="search-input" id="search-input" placeholder="Поиск по названию...">
                            
                            <button class="sync-btn" onclick="syncBranches()">Синхронизировать</button>
                            <button class="refresh-btn" onclick="loadBranches()">Обновить</button>
                            <button class="add-btn" onclick="showDepartmentForm()">Добавить</button>
                            
                            <span class="loading" id="loading">Загрузка...</span>
                            
                            <div class="total-count" id="total-count">Всего: 0</div>
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

                <!-- Error Analysis by Segment Page -->
                <div id="page-error-analysis-segment" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📊 Анализ ошибок по сегментам</h1>
                        <p class="page-description">Анализ точности прогнозов в разрезе различных сегментов: филиалы, дни недели, месяцы и локации</p>
                    </div>
                    
                    <div class="form-container">
                        <form id="error-segment-form">
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="error-from-date">Дата с:</label>
                                    <input type="date" id="error-from-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="error-to-date">Дата по:</label>
                                    <input type="date" id="error-to-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="segment-type">Тип сегментации:</label>
                                    <select id="segment-type" class="form-input">
                                        <option value="department">По филиалам</option>
                                        <option value="day_of_week">По дням недели</option>
                                        <option value="month">По месяцам</option>
                                        <option value="location">По городам</option>
                                    </select>
                                </div>
                                
                                <button type="submit" class="action-btn">Анализировать</button>
                            </div>
                        </form>
                        
                        <div id="error-segment-loading" class="loading-indicator" style="display: none;">
                            <div class="spinner"></div>
                            <span>Анализ ошибок...</span>
                        </div>
                        
                        <div id="error-segment-results" style="display: none;">
                            <h3>Результаты анализа</h3>
                            <div id="error-segment-summary" class="stats-grid"></div>
                            <div class="table-container">
                                <table id="error-segment-table">
                                    <thead>
                                        <tr>
                                            <th>Сегмент</th>
                                            <th>Количество прогнозов</th>
                                            <th>Средний MAPE (%)</th>
                                            <th>Стандартное отклонение</th>
                                            <th>Средние продажи</th>
                                        </tr>
                                    </thead>
                                    <tbody></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Problematic Branches Page -->
                <div id="page-problematic-branches" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">⚠️ Проблемные филиалы</h1>
                        <p class="page-description">Выявление филиалов с постоянно высокими ошибками прогнозирования для целенаправленного улучшения</p>
                    </div>
                    
                    <div class="form-container">
                        <form id="problematic-branches-form">
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="prob-from-date">Дата с:</label>
                                    <input type="date" id="prob-from-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="prob-to-date">Дата по:</label>
                                    <input type="date" id="prob-to-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="min-samples">Мин. прогнозов:</label>
                                    <input type="number" id="min-samples" class="form-input" value="5" min="1">
                                </div>
                                
                                <div class="form-group">
                                    <label for="mape-threshold">MAPE порог (%):</label>
                                    <input type="number" id="mape-threshold" class="form-input" value="15" min="1" max="100" step="0.1">
                                </div>
                                
                                <button type="submit" class="action-btn">Найти проблемные</button>
                            </div>
                        </form>
                        
                        <div id="problematic-loading" class="loading-indicator" style="display: none;">
                            <div class="spinner"></div>
                            <span>Поиск проблемных филиалов...</span>
                        </div>
                        
                        <div id="problematic-results" style="display: none;">
                            <h3>Проблемные филиалы</h3>
                            <div id="problematic-summary" class="stats-grid"></div>
                            <div class="table-container">
                                <table id="problematic-table">
                                    <thead>
                                        <tr>
                                            <th>Филиал</th>
                                            <th>Прогнозов</th>
                                            <th>Средний MAPE (%)</th>
                                            <th>Мин/Макс MAPE (%)</th>
                                            <th>Средние продажи</th>
                                            <th>Средняя ошибка</th>
                                        </tr>
                                    </thead>
                                    <tbody></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Temporal Analysis Page -->
                <div id="page-temporal-analysis" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📈 Временной анализ ошибок</h1>
                        <p class="page-description">Исследование паттернов ошибок прогнозирования во временных рядах: тренды по дням, неделям и месяцам</p>
                    </div>
                    
                    <div class="form-container">
                        <form id="temporal-analysis-form">
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="temp-from-date">Дата с:</label>
                                    <input type="date" id="temp-from-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="temp-to-date">Дата по:</label>
                                    <input type="date" id="temp-to-date" class="form-input" required>
                                </div>
                                
                                <button type="submit" class="action-btn">Анализировать</button>
                            </div>
                        </form>
                        
                        <div id="temporal-loading" class="loading-indicator" style="display: none;">
                            <div class="spinner"></div>
                            <span>Временной анализ...</span>
                        </div>
                        
                        <div id="temporal-results" style="display: none;">
                            <h3>Анализ ошибок по времени</h3>
                            <div id="temporal-summary" class="stats-grid"></div>
                            
                            <!-- Chart for temporal trends -->
                            <div class="chart-container">
                                <canvas id="temporal-chart" width="800" height="400"></canvas>
                            </div>
                            
                            <div class="analysis-tabs">
                                <button class="tab-btn active" onclick="showTemporalTab('daily')">По дням</button>
                                <button class="tab-btn" onclick="showTemporalTab('weekday')">По дням недели</button>
                                <button class="tab-btn" onclick="showTemporalTab('monthly')">По месяцам</button>
                            </div>
                            
                            <div class="table-container">
                                <table id="temporal-table">
                                    <thead id="temporal-table-head"></thead>
                                    <tbody id="temporal-table-body"></tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Error Distribution Page -->
                <div id="page-error-distribution" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📋 Распределение ошибок</h1>
                        <p class="page-description">Статистический анализ распределения ошибок прогнозирования с выявлением выбросов и аномалий</p>
                    </div>
                    
                    <div class="form-container">
                        <form id="error-distribution-form">
                            <div class="form-row">
                                <div class="form-group">
                                    <label for="dist-from-date">Дата с:</label>
                                    <input type="date" id="dist-from-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="dist-to-date">Дата по:</label>
                                    <input type="date" id="dist-to-date" class="form-input" required>
                                </div>
                                
                                <div class="form-group">
                                    <label for="dist-department">Филиал (опционально):</label>
                                    <select id="dist-department" class="form-input">
                                        <option value="">Все филиалы</option>
                                    </select>
                                </div>
                                
                                <button type="submit" class="action-btn">Анализировать</button>
                            </div>
                        </form>
                        
                        <div id="distribution-loading" class="loading-indicator" style="display: none;">
                            <div class="spinner"></div>
                            <span>Анализ распределения...</span>
                        </div>
                        
                        <div id="distribution-results" style="display: none;">
                            <h3>Статистика распределения ошибок</h3>
                            <div id="distribution-stats" class="stats-grid"></div>
                            
                            <!-- Distribution chart -->
                            <div class="chart-container">
                                <canvas id="distribution-chart" width="800" height="400"></canvas>
                            </div>
                            
                            <div class="table-container">
                                <h4>Распределение по диапазонам точности</h4>
                                <table id="distribution-ranges-table">
                                    <thead>
                                        <tr>
                                            <th>Диапазон MAPE</th>
                                            <th>Уровень точности</th>
                                            <th>Количество</th>
                                            <th>Процент</th>
                                        </tr>
                                    </thead>
                                    <tbody></tbody>
                                </table>
                            </div>
                        </div>
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
                                    <div class="form-group checkbox-group">
                                        <label class="checkbox-label">
                                            <input type="checkbox" id="clear-existing" name="clear-existing">
                                            <span class="checkmark"></span>
                                            Очистить существующие данные за период
                                        </label>
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

                <!-- Forecast Export Page -->
                <div id="page-forecast-export" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Экспорт прогноза</h1>
                    </div>
                    
                    <div class="form-container">
                        <div class="form-section">
                            <h2 class="form-section-title">Параметры экспорта</h2>
                            
                            <form id="export-form" class="export-form">
                                <div class="form-row">
                                    <div class="form-group">
                                        <label for="export-start-date">Дата начала:</label>
                                        <input type="date" id="export-start-date" name="start-date" required>
                                    </div>
                                    
                                    <div class="form-group">
                                        <label for="export-end-date">Дата окончания:</label>
                                        <input type="date" id="export-end-date" name="end-date" required>
                                    </div>
                                </div>
                                
                                <div class="form-row">
                                    <div class="form-group">
                                        <label for="export-department">Подразделение:</label>
                                        <select class="filter-select" id="export-department" style="width: 100%;">
                                            <option value="">Все подразделения</option>
                                        </select>
                                    </div>
                                </div>
                                
                                <div class="form-row">
                                    <div class="form-group checkbox-group">
                                        <label class="checkbox-label">
                                            <input type="checkbox" id="include-actual" name="include-actual">
                                            <span class="checkmark"></span>
                                            Включить фактические данные для сравнения
                                        </label>
                                    </div>
                                </div>
                                
                                <div class="form-actions">
                                    <button type="button" class="load-btn" onclick="exportForecast()">
                                        📥 Экспорт в CSV
                                    </button>
                                    <button type="button" class="cancel-btn" onclick="showDepartments()">
                                        Отмена
                                    </button>
                                </div>
                                
                                <div class="result-section result-success" id="export-result" style="display: none;">
                                    <div class="result-content">
                                        <h3>✅ Экспорт начат</h3>
                                        <p>Файл будет загружен автоматически.</p>
                                    </div>
                                </div>
                            </form>
                        </div>
                        
                        <div class="form-section" style="margin-top: 30px;">
                            <h2 class="form-section-title">Информация о модели</h2>
                            <div id="model-info" style="padding: 20px; background-color: #f8f9fa; border-radius: 8px;">
                                <p>Загрузка информации о модели...</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Forecast Post-processing Page -->
                <div id="page-forecast-postprocessing" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Пост-обработка прогнозов</h1>
                        <p class="page-description">Настройка и применение правил обработки прогнозов для повышения их надёжности</p>
                    </div>

                    <!-- Configuration Panel -->
                    <div class="form-container" style="margin-bottom: 30px;">
                        <h3 style="margin-bottom: 20px;">⚙️ Настройки пост-обработки</h3>
                        
                        <div class="cards-grid">
                            <!-- Smoothing Options -->
                            <div class="config-section">
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">🔄 Сглаживание</h4>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-smoothing" checked> 
                                    Включить сглаживание прогнозов
                                </label>
                                <div style="margin-left: 20px;">
                                    <label style="display: block; margin-bottom: 5px;">Максимальное изменение (%):</label>
                                    <input type="number" id="max-change-percent" value="50" min="10" max="200" style="width: 100px;">
                                </div>
                            </div>

                            <!-- Business Rules -->
                            <div class="config-section">
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">🏢 Бизнес-правила</h4>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-business-rules" checked> 
                                    Применять бизнес-ограничения
                                </label>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-weekend-adjustment" checked> 
                                    Корректировка выходных дней
                                </label>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-holiday-adjustment" checked> 
                                    Корректировка праздников
                                </label>
                            </div>

                            <!-- Anomaly Detection -->
                            <div class="config-section">
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">🔍 Обнаружение аномалий</h4>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-anomaly-detection" checked> 
                                    Включить обнаружение аномалий
                                </label>
                                <div style="margin-left: 20px;">
                                    <label style="display: block; margin-bottom: 5px;">Z-score порог:</label>
                                    <input type="number" id="anomaly-threshold" value="3.0" min="1.0" max="5.0" step="0.1" style="width: 100px;">
                                </div>
                            </div>

                            <!-- Confidence Intervals -->
                            <div class="config-section">
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">📊 Доверительные интервалы</h4>
                                <label style="display: block; margin-bottom: 10px;">
                                    <input type="checkbox" id="enable-confidence" checked> 
                                    Рассчитывать интервалы
                                </label>
                                <div style="margin-left: 20px;">
                                    <label style="display: block; margin-bottom: 5px;">Уровень доверия (%):</label>
                                    <select id="confidence-level" style="width: 100px;">
                                        <option value="0.90">90%</option>
                                        <option value="0.95" selected>95%</option>
                                        <option value="0.99">99%</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Save Settings Button -->
                        <div style="text-align: center; margin-top: 20px;">
                            <button onclick="savePostprocessingSettings()" class="btn btn-success" style="padding: 10px 30px; font-size: 16px;">
                                💾 Сохранить настройки
                            </button>
                            <div id="save-settings-status" style="margin-top: 10px; font-weight: bold;"></div>
                        </div>
                    </div>

                    <!-- Testing Section -->
                    <div class="form-container" style="margin-bottom: 30px;">
                        <h3 style="margin-bottom: 20px;">🧪 Тестирование пост-обработки</h3>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 30px;">
                            <!-- Input Panel -->
                            <div>
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">Параметры тестирования</h4>
                                <div style="margin-bottom: 15px;">
                                    <label for="test-department">Филиал:</label>
                                    <select id="test-department" style="width: 100%; margin-top: 5px;"></select>
                                </div>
                                <div style="margin-bottom: 15px;">
                                    <label for="test-date">Дата прогноза:</label>
                                    <input type="date" id="test-date" style="width: 100%; margin-top: 5px;">
                                </div>
                                <div style="margin-bottom: 15px;">
                                    <label for="test-prediction">Сырой прогноз:</label>
                                    <input type="number" id="test-prediction" placeholder="Введите значение прогноза" style="width: 100%; margin-top: 5px;">
                                </div>
                                <button onclick="testPostprocessing()" class="btn btn-primary" style="width: 100%;">
                                    Протестировать
                                </button>
                            </div>

                            <!-- Results Panel -->
                            <div>
                                <h4 style="color: #2c3e50; margin-bottom: 15px;">Результаты обработки</h4>
                                <div id="test-results" style="background: #f8f9fa; padding: 15px; border-radius: 5px; min-height: 200px;">
                                    <p style="color: #6c757d; text-align: center;">Результаты появятся после тестирования</p>
                                </div>
                            </div>
                        </div>
                    </div>

                    <!-- Batch Processing Section -->
                    <div class="form-container" style="margin-bottom: 30px;">
                        <h3 style="margin-bottom: 20px;">📦 Массовая обработка</h3>
                        
                        <div class="cards-grid-2">
                            <div>
                                <label for="batch-from-date">Дата начала:</label>
                                <input type="date" id="batch-from-date" style="width: 100%; margin-top: 5px;">
                            </div>
                            <div>
                                <label for="batch-to-date">Дата окончания:</label>
                                <input type="date" id="batch-to-date" style="width: 100%; margin-top: 5px;">
                            </div>
                            <div>
                                <label for="batch-department">Филиал (опционально):</label>
                                <select id="batch-department" style="width: 100%; margin-top: 5px;">
                                    <option value="">Все подразделения</option>
                                </select>
                            </div>
                        </div>

                        <div style="text-align: center;">
                            <button onclick="runBatchPostprocessing()" class="btn btn-primary" style="margin-right: 10px;">
                                🚀 Запустить обработку
                            </button>
                            <button onclick="downloadBatchResults()" class="btn btn-secondary" id="download-batch-btn" style="display: none;">
                                📥 Скачать результаты
                            </button>
                        </div>

                        <div id="batch-progress" style="margin-top: 20px; display: none;">
                            <div class="progress-bar" style="background: #e9ecef; border-radius: 10px; overflow: hidden;">
                                <div id="batch-progress-bar" style="background: #007bff; height: 20px; width: 0%; transition: width 0.3s;"></div>
                            </div>
                            <p id="batch-status" style="text-align: center; margin-top: 10px;"></p>
                        </div>

                        <div id="batch-results" style="margin-top: 20px; display: none;">
                            <h4 style="color: #2c3e50; margin-bottom: 15px;">Результаты массовой обработки</h4>
                            <div id="batch-results-content"></div>
                        </div>
                    </div>
                </div>

                <!-- Model Status Page -->
                <div id="page-model-status" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📊 Статус модели</h1>
                        <p class="page-description">Текущее состояние и здоровье ML модели прогнозирования</p>
                    </div>
                    
                    <!-- Model Health Cards -->
                    <div class="cards-grid">
                        <div class="card">
                            <h3 style="color: #2c3e50; margin-bottom: 15px;">🏥 Общее состояние</h3>
                            <div id="model-health-status">
                                <div style="text-align: center; padding: 20px;">
                                    <div class="loading-spinner"></div>
                                    <p>Проверка состояния модели...</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h3 style="color: #2c3e50; margin-bottom: 15px;">📈 Текущие метрики</h3>
                            <div id="current-metrics">
                                <div style="text-align: center; padding: 20px;">
                                    <div class="loading-spinner"></div>
                                    <p>Загрузка метрик...</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h3 style="color: #2c3e50; margin-bottom: 15px;">ℹ️ Информация о модели</h3>
                            <div id="model-info">
                                <div style="text-align: center; padding: 20px;">
                                    <div class="loading-spinner"></div>
                                    <p>Загрузка информации...</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Detailed Health Checks -->
                    <div class="card">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">🔍 Детальные проверки</h3>
                        <div id="detailed-health-checks"></div>
                    </div>
                </div>

                <!-- Performance Metrics Page -->
                <div id="page-performance-metrics" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📈 Метрики производительности</h1>
                        <p class="page-description">Анализ производительности модели за различные периоды</p>
                    </div>
                    
                    <!-- Time Period Selector -->
                    <div class="card" style="margin-bottom: 20px;">
                        <div style="display: flex; gap: 20px; align-items: center; flex-wrap: wrap;">
                            <label><strong>Период анализа:</strong></label>
                            <select id="metrics-period" style="padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px;">
                                <option value="7">Последние 7 дней</option>
                                <option value="30" selected>Последние 30 дней</option>
                                <option value="90">Последние 90 дней</option>
                                <option value="365">Последний год</option>
                            </select>
                            <button onclick="loadPerformanceMetrics()" class="load-btn">Обновить</button>
                        </div>
                    </div>
                    
                    <!-- Performance Summary -->
                    <div class="cards-grid-2">
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Средний MAPE</h4>
                            <div id="avg-mape" style="font-size: 2em; font-weight: bold; color: #3498db;">--%</div>
                        </div>
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Лучший день</h4>
                            <div id="best-mape" style="font-size: 2em; font-weight: bold; color: #27ae60;">--%</div>
                        </div>
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Худший день</h4>
                            <div id="worst-mape" style="font-size: 2em; font-weight: bold; color: #e74c3c;">--%</div>
                        </div>
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Тренд</h4>
                            <div id="mape-trend" style="font-size: 2em; font-weight: bold;">--</div>
                        </div>
                    </div>
                    
                    <!-- Performance Chart -->
                    <div class="card">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">📊 График производительности</h3>
                        <div id="performance-chart-container" style="height: 400px;">
                            <canvas id="performance-chart"></canvas>
                        </div>
                    </div>
                    
                    <!-- Recent Alerts -->
                    <div class="card">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">⚠️ Недавние уведомления</h3>
                        <div id="recent-alerts"></div>
                    </div>
                </div>

                <!-- Training History Page -->
                <div id="page-training-history" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">📋 История обучения</h1>
                        <p class="page-description">Журнал переобучений модели и расписание</p>
                    </div>
                    
                    <!-- Current Schedule -->
                    <div class="card" style="margin-bottom: 20px;">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">⏰ Текущее расписание</h3>
                        <div id="retraining-schedule"></div>
                    </div>
                    
                    <!-- Last Retraining Info -->
                    <div class="cards-grid">
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Последнее переобучение</h4>
                            <div id="last-retrain-info">
                                <div style="text-align: center; padding: 20px;">
                                    <div class="loading-spinner"></div>
                                    <p>Загрузка информации...</p>
                                </div>
                            </div>
                        </div>
                        
                        <div class="card">
                            <h4 style="color: #2c3e50; margin-bottom: 10px;">Статистика версий</h4>
                            <div id="version-stats">
                                <div style="text-align: center; padding: 20px;">
                                    <div class="loading-spinner"></div>
                                    <p>Загрузка статистики...</p>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Training History Table -->
                    <div class="card">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">📝 История переобучений</h3>
                        <div style="overflow-x: auto;">
                            <table id="training-history-table" class="table">
                                <thead>
                                    <tr>
                                        <th>Дата</th>
                                        <th>Тип</th>
                                        <th>Предыдущий MAPE</th>
                                        <th>Новый MAPE</th>
                                        <th>Улучшение</th>
                                        <th>Решение</th>
                                        <th>Статус</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    <tr>
                                        <td colspan="7" style="text-align: center; padding: 20px;">
                                            <div class="loading-spinner"></div>
                                            <p>Загрузка истории...</p>
                                        </td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <!-- Manual Retraining Page -->
                <div id="page-manual-retraining" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">🔄 Ручное переобучение</h1>
                        <p class="page-description">Запуск переобучения модели вне графика</p>
                    </div>
                    
                    <!-- Retraining Form -->
                    <div class="card" style="margin-bottom: 20px;">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">⚙️ Параметры переобучения</h3>
                        <div style="display: grid; gap: 20px;">
                            <div class="form-group">
                                <label for="retrain-reason"><strong>Причина переобучения:</strong></label>
                                <textarea id="retrain-reason" placeholder="Опишите причину ручного переобучения..." 
                                         style="padding: 10px; border: 1px solid #ddd; border-radius: 4px; height: 80px; resize: vertical;"></textarea>
                            </div>
                            
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                                <div class="form-group">
                                    <label for="performance-threshold"><strong>Порог производительности (MAPE %):</strong></label>
                                    <input type="number" id="performance-threshold" value="10.0" step="0.1" min="0" max="50"
                                           style="padding: 8px; border: 1px solid #ddd; border-radius: 4px;">
                                </div>
                                
                                <div class="form-group">
                                    <label><strong>Принудительное развертывание:</strong></label>
                                    <label style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
                                        <input type="checkbox" id="force-deploy">
                                        <span>Развернуть даже при ухудшении</span>
                                    </label>
                                </div>
                            </div>
                            
                            <div style="display: flex; gap: 10px; justify-content: flex-end;">
                                <button onclick="startManualRetraining()" class="load-btn" id="retrain-btn">🔄 Начать переобучение</button>
                                <button onclick="checkRetrainingStatus()" class="cancel-btn">📊 Проверить статус</button>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Current Model Status -->
                    <div class="card" style="margin-bottom: 20px;">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">📊 Текущая модель</h3>
                        <div id="current-model-status">
                            <div style="text-align: center; padding: 20px;">
                                <div class="loading-spinner"></div>
                                <p>Загрузка информации о текущей модели...</p>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Retraining Progress -->
                    <div id="retraining-progress" class="card" style="display: none;">
                        <h3 style="color: #2c3e50; margin-bottom: 15px;">🔄 Ход переобучения</h3>
                        <div class="progress-section">
                            <div class="progress-bar">
                                <div id="retrain-progress-fill" class="progress-fill"></div>
                            </div>
                            <div id="retrain-progress-text" class="progress-text">Инициализация...</div>
                        </div>
                        <div id="retrain-logs" style="margin-top: 15px; padding: 15px; background-color: #f8f9fa; border-radius: 6px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto;"></div>
                    </div>
                    
                    <!-- Retraining Results -->
                    <div id="retraining-results" style="display: none; margin-top: 20px;">
                        <div class="result-section">
                            <h3 style="color: #2c3e50; margin-bottom: 15px;">📋 Результаты переобучения</h3>
                            <div id="retrain-results-content" class="result-content"></div>
                        </div>
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
            let allBranches = [];
            let filteredBranches = [];
            
            async function loadBranches() {
                document.getElementById('loading').style.display = 'inline';
                try {
                    const response = await fetch('/api/departments/');
                    allBranches = await response.json();
                    
                    // Populate company filter
                    populateCompanyFilter();
                    
                    // Apply current filters
                    applyFilters();
                    
                } catch (error) {
                    console.error('Error loading branches:', error);
                    document.getElementById('branches-tbody').innerHTML = 
                        '<tr><td colspan="4" class="no-data">Ошибка загрузки данных</td></tr>';
                } finally {
                    document.getElementById('loading').style.display = 'none';
                }
            }
            
            function populateCompanyFilter() {
                const companies = [...new Set(allBranches.filter(b => b.type === 'JURPERSON').map(b => b.name))].sort();
                const filter = document.getElementById('company-filter');
                
                // Clear existing options except "Все компании"
                filter.innerHTML = '<option value="">Все компании</option>';
                
                companies.forEach(company => {
                    if (company) {
                        const option = document.createElement('option');
                        option.value = company;
                        option.textContent = company;
                        filter.appendChild(option);
                    }
                });
            }
            
            function applyFilters() {
                const searchTerm = document.getElementById('search-input').value.toLowerCase();
                const selectedCompany = document.getElementById('company-filter').value;
                
                filteredBranches = allBranches.filter(branch => {
                    const matchesSearch = !searchTerm || 
                        branch.name.toLowerCase().includes(searchTerm) ||
                        (branch.code && branch.code.toLowerCase().includes(searchTerm)) ||
                        branch.id.toLowerCase().includes(searchTerm);
                    
                    // Find parent company for filtering
                    let parentCompany = '';
                    if (branch.type === 'JURPERSON') {
                        parentCompany = branch.name;
                    } else if (branch.parent_id) {
                        const parent = allBranches.find(b => b.id === branch.parent_id);
                        if (parent && parent.type === 'JURPERSON') {
                            parentCompany = parent.name;
                        }
                    }
                    
                    const matchesCompany = !selectedCompany || parentCompany === selectedCompany;
                    
                    return matchesSearch && matchesCompany;
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
                        <button class="delete-btn" onclick="deleteDepartment('${branch.id}')">
                            Удалить
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
                    const response = await fetch('/api/branches/sync', { method: 'POST' });
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
                        method: 'DELETE'
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
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify(departmentData)
                        });
                    } else {
                        // Create new department
                        response = await fetch('/api/departments/', {
                            method: 'POST',
                            headers: {
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
            }
            
            // Sales Sync Functions
            async function handleSalesSync(event) {
                event.preventDefault();
                
                const startDate = document.getElementById('start-date').value;
                const endDate = document.getElementById('end-date').value;
                const clearExisting = document.getElementById('clear-existing').checked;
                
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
                    // If clear existing is checked, first delete existing data
                    if (clearExisting) {
                        updateProgress(20, 'Очистка существующих данных...');
                        await clearExistingData(startDate, endDate);
                    }
                    
                    // Sync sales data
                    updateProgress(50, 'Синхронизация данных продаж...');
                    const response = await fetch(`/api/sales/sync?from_date=${startDate}&to_date=${endDate}`, {
                        method: 'POST'
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
            
            async function clearExistingData(startDate, endDate) {
                // This would require implementing delete endpoints with date ranges
                // For now, we'll just simulate the operation
                await new Promise(resolve => setTimeout(resolve, 1000));
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
                document.getElementById('page-forecast-export').style.display = 'none';
                document.getElementById('page-forecast-postprocessing').style.display = 'none';
                // Error analysis pages
                document.getElementById('page-error-analysis-segment').style.display = 'none';
                document.getElementById('page-problematic-branches').style.display = 'none';
                document.getElementById('page-temporal-analysis').style.display = 'none';
                document.getElementById('page-error-distribution').style.display = 'none';
                // Model monitoring pages
                document.getElementById('page-model-status').style.display = 'none';
                document.getElementById('page-performance-metrics').style.display = 'none';
                document.getElementById('page-training-history').style.display = 'none';
                document.getElementById('page-manual-retraining').style.display = 'none';
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
                
                // Populate daily sales department filter
                const dailyFilter = document.getElementById('daily-department-filter');
                if (dailyFilter) {
                    dailyFilter.innerHTML = '<option value="">Все подразделения</option>';
                    departments.forEach(dept => {
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
                    departments.forEach(dept => {
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
                    
                    const response = await fetch(url);
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
                    
                    const response = await fetch(url);
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
            
            function showForecastExport() {
                hideAllPages();
                document.getElementById('page-forecast-export').style.display = 'block';
                updateSidebarActive('#экспорт-прогноза');
                window.scrollTo(0, 0);
                
                // Set default dates
                const today = new Date();
                const nextMonth = new Date(today);
                nextMonth.setDate(today.getDate() + 30);
                
                document.getElementById('export-start-date').value = today.toISOString().split('T')[0];
                document.getElementById('export-end-date').value = nextMonth.toISOString().split('T')[0];
                
                // Populate department filter
                populateForecastDepartmentFilters();
                
                // Load model info
                loadModelInfo();
            }

            function showForecastPostprocessing() {
                hideAllPages();
                document.getElementById('page-forecast-postprocessing').style.display = 'block';
                updateSidebarActive('#пост-обработка');
                window.scrollTo(0, 0);
                
                // Set default dates (today + 7 days)
                const today = new Date();
                const tomorrow = new Date(today);
                tomorrow.setDate(today.getDate() + 1);
                const nextWeek = new Date(today);
                nextWeek.setDate(today.getDate() + 7);
                
                document.getElementById('test-date').value = tomorrow.toISOString().split('T')[0];
                document.getElementById('batch-from-date').value = tomorrow.toISOString().split('T')[0];
                document.getElementById('batch-to-date').value = nextWeek.toISOString().split('T')[0];
                
                // Populate department filters
                populateForecastDepartmentFilters();
                populatePostprocessingDepartmentFilters();
                
                // Load saved settings
                loadPostprocessingSettings();
            }
            
            // Error Analysis Functions
            function showErrorAnalysisBySegment() {
                hideAllPages();
                document.getElementById('page-error-analysis-segment').style.display = 'block';
                updateSidebarActive('#ошибки-по-сегментам');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('error-from-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('error-to-date').value = today.toISOString().split('T')[0];
            }
            
            function showProblematicBranches() {
                hideAllPages();
                document.getElementById('page-problematic-branches').style.display = 'block';
                updateSidebarActive('#проблемные-филиалы');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('prob-from-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('prob-to-date').value = today.toISOString().split('T')[0];
            }
            
            function showTemporalAnalysis() {
                hideAllPages();
                document.getElementById('page-temporal-analysis').style.display = 'block';
                updateSidebarActive('#временной-анализ');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('temp-from-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('temp-to-date').value = today.toISOString().split('T')[0];
            }
            
            function showErrorDistribution() {
                hideAllPages();
                document.getElementById('page-error-distribution').style.display = 'block';
                updateSidebarActive('#распределение-ошибок');
                window.scrollTo(0, 0);
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('dist-from-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('dist-to-date').value = today.toISOString().split('T')[0];
                
                // Populate department filter
                populateErrorDistributionDepartments();
            }
            
            function populateErrorDistributionDepartments() {
                const departments = allBranches || [];
                const select = document.getElementById('dist-department');
                if (select) {
                    select.innerHTML = '<option value="">Все филиалы</option>';
                    departments.forEach(dept => {
                        const option = document.createElement('option');
                        option.value = dept.id;
                        option.textContent = dept.name || dept.code || dept.id;
                        select.appendChild(option);
                    });
                }
            }
            
            // MODEL MONITORING NAVIGATION FUNCTIONS
            function showModelStatus() {
                hideAllPages();
                document.getElementById('page-model-status').style.display = 'block';
                updateSidebarActive('#статус-модели');
                window.scrollTo(0, 0);
                
                // Load model status
                loadModelHealthStatus();
                loadCurrentModelMetrics();
                loadModelInfo();
            }
            
            function showPerformanceMetrics() {
                hideAllPages();
                document.getElementById('page-performance-metrics').style.display = 'block';
                updateSidebarActive('#метрики-производительности');
                window.scrollTo(0, 0);
                
                // Load performance metrics with default period (30 days)
                loadPerformanceMetrics();
            }
            
            function showTrainingHistory() {
                hideAllPages();
                document.getElementById('page-training-history').style.display = 'block';
                updateSidebarActive('#история-обучения');
                window.scrollTo(0, 0);
                
                // Load training history and schedule
                loadRetrainingSchedule();
                loadTrainingHistory();
            }
            
            function showManualRetraining() {
                hideAllPages();
                document.getElementById('page-manual-retraining').style.display = 'block';
                updateSidebarActive('#ручное-переобучение');
                window.scrollTo(0, 0);
                
                // Load current model status
                loadCurrentModelStatusForRetraining();
                
                // Reset form and hide progress/results
                resetRetrainingForm();
            }
            
            function populateForecastDepartmentFilters() {
                const departments = allBranches || [];
                
                // Forecast page filter
                const forecastFilter = document.getElementById('forecast-department-filter');
                if (forecastFilter) {
                    forecastFilter.innerHTML = '<option value="">Все подразделения</option>';
                    departments.forEach(dept => {
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
                    departments.forEach(dept => {
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
                    departments.forEach(dept => {
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
                    
                    const response = await fetch(url);
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
                    
                    const response = await fetch(url);
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
            
            async function exportForecast() {
                const startDate = document.getElementById('export-start-date').value;
                const endDate = document.getElementById('export-end-date').value;
                const departmentId = document.getElementById('export-department').value;
                const includeActual = document.getElementById('include-actual').checked;
                
                if (!startDate || !endDate) {
                    alert('Пожалуйста, укажите даты начала и окончания');
                    return;
                }
                
                try {
                    let url = `/api/forecast/export/csv?from_date=${startDate}&to_date=${endDate}`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    if (includeActual) {
                        url += `&include_actual=true`;
                    }
                    
                    // Show success message
                    document.getElementById('export-result').style.display = 'block';
                    
                    // Trigger download
                    window.location.href = url;
                    
                    // Hide success message after 3 seconds
                    setTimeout(() => {
                        document.getElementById('export-result').style.display = 'none';
                    }, 3000);
                    
                } catch (error) {
                    console.error('Error exporting forecast:', error);
                    alert('Ошибка при экспорте данных');
                }
            }
            
            async function loadModelInfo() {
                try {
                    const response = await fetch('/api/forecast/model/info');
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
                    const response = await fetch('/api/forecast/retrain', { method: 'POST' });
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
            
            // =============================================================
            // MODEL MONITORING UTILITY FUNCTIONS
            // =============================================================
            
            async function loadModelHealthStatus() {
                const healthDiv = document.getElementById('model-health-status');
                try {
                    healthDiv.innerHTML = '<div style="text-align: center; padding: 20px;"><div class="loading-spinner"></div><p>Проверка состояния модели...</p></div>';
                    
                    const response = await fetch('/api/monitoring/health');
                    const health = await response.json();
                    
                    const statusColor = health.overall_status === 'healthy' ? '#27ae60' : 
                                       health.overall_status === 'warning' ? '#f39c12' : '#e74c3c';
                    const statusIcon = health.overall_status === 'healthy' ? '✅' : 
                                      health.overall_status === 'warning' ? '⚠️' : '❌';
                    
                    healthDiv.innerHTML = `
                        <div style="text-align: center; margin-bottom: 20px;">
                            <div style="font-size: 3em; margin-bottom: 10px;">${statusIcon}</div>
                            <h3 style="color: ${statusColor}; margin: 0;">${health.overall_status.toUpperCase()}</h3>
                            <p style="color: #666; margin: 5px 0;">Проверено: ${new Date(health.check_time).toLocaleString('ru-RU')}</p>
                        </div>
                        <div style="text-align: left;">
                            <p><strong>Недавний MAPE:</strong> ${health.summary.recent_mape.toFixed(2)}%</p>
                            <p><strong>Возраст модели:</strong> ${health.summary.model_age_days} дней</p>
                            <p><strong>Проблемных филиалов:</strong> ${health.summary.problematic_branches_count}</p>
                        </div>
                    `;
                } catch (error) {
                    healthDiv.innerHTML = '<p style="color: #e74c3c;">❌ Ошибка загрузки состояния модели</p>';
                }
            }
            
            async function loadCurrentModelMetrics() {
                const metricsDiv = document.getElementById('current-metrics');
                try {
                    const response = await fetch('/api/monitoring/performance/summary?days=7');
                    const summary = await response.json();
                    
                    if (summary.status === 'no_data') {
                        metricsDiv.innerHTML = '<p style="color: #666;">Недостаточно данных за последние 7 дней</p>';
                        return;
                    }
                    
                    const trendColor = summary.mape_trend > 0 ? '#e74c3c' : '#27ae60';
                    const trendIcon = summary.mape_trend > 0 ? '📈' : '📉';
                    
                    metricsDiv.innerHTML = `
                        <div style="text-align: center; margin-bottom: 15px;">
                            <div style="font-size: 2.5em; font-weight: bold; color: #3498db;">
                                ${summary.avg_mape.toFixed(1)}%
                            </div>
                            <p style="color: #666; margin: 0;">Средний MAPE за 7 дней</p>
                        </div>
                        <div style="text-align: left; font-size: 14px;">
                            <p><strong>Лучший день:</strong> ${summary.min_mape.toFixed(1)}%</p>
                            <p><strong>Худший день:</strong> ${summary.max_mape.toFixed(1)}%</p>
                            <p style="color: ${trendColor};"><strong>Тренд:</strong> ${trendIcon} ${summary.mape_trend.toFixed(2)}</p>
                        </div>
                    `;
                } catch (error) {
                    metricsDiv.innerHTML = '<p style="color: #e74c3c;">❌ Ошибка загрузки метрик</p>';
                }
            }
            
            async function loadPerformanceMetrics() {
                const period = document.getElementById('metrics-period').value;
                
                try {
                    // Update summary cards
                    const response = await fetch(`/api/monitoring/performance/summary?days=${period}`);
                    const summary = await response.json();
                    
                    if (summary.status === 'no_data') {
                        document.getElementById('avg-mape').textContent = 'N/A';
                        document.getElementById('best-mape').textContent = 'N/A';
                        document.getElementById('worst-mape').textContent = 'N/A';
                        document.getElementById('mape-trend').textContent = 'N/A';
                        return;
                    }
                    
                    document.getElementById('avg-mape').textContent = `${summary.avg_mape.toFixed(1)}%`;
                    document.getElementById('best-mape').textContent = `${summary.min_mape.toFixed(1)}%`;
                    document.getElementById('worst-mape').textContent = `${summary.max_mape.toFixed(1)}%`;
                    
                    const trendText = summary.mape_trend > 0 ? `+${summary.mape_trend.toFixed(2)}%` : `${summary.mape_trend.toFixed(2)}%`;
                    const trendColor = summary.mape_trend > 0 ? '#e74c3c' : '#27ae60';
                    document.getElementById('mape-trend').innerHTML = `<span style="color: ${trendColor};">${trendText}</span>`;
                    
                    // Create performance chart
                    createPerformanceChart(summary.time_series);
                    
                    // Load recent alerts
                    loadRecentAlerts(period);
                    
                } catch (error) {
                    console.error('Error loading performance metrics:', error);
                }
            }
            
            function createPerformanceChart(timeSeries) {
                const canvas = document.getElementById('performance-chart');
                const ctx = canvas.getContext('2d');
                
                // Destroy existing chart if exists
                if (window.performanceChart) {
                    window.performanceChart.destroy();
                }
                
                const labels = timeSeries.map(item => new Date(item.date).toLocaleDateString('ru-RU'));
                const data = timeSeries.map(item => item.mape);
                
                window.performanceChart = new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'MAPE (%)',
                            data: data,
                            borderColor: '#3498db',
                            backgroundColor: 'rgba(52, 152, 219, 0.1)',
                            borderWidth: 2,
                            fill: true,
                            tension: 0.1
                        }]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            y: {
                                beginAtZero: true,
                                title: {
                                    display: true,
                                    text: 'MAPE (%)'
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Дата'
                                }
                            }
                        },
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top'
                            }
                        }
                    }
                });
            }
            
            async function loadRecentAlerts(days = 7) {
                const alertsDiv = document.getElementById('recent-alerts');
                try {
                    const response = await fetch(`/api/monitoring/alerts/recent?days=${days}`);
                    const alertsData = await response.json();
                    
                    if (alertsData.total_alert_days === 0) {
                        alertsDiv.innerHTML = '<p style="color: #27ae60;">✅ Никаких уведомлений за указанный период</p>';
                        return;
                    }
                    
                    let html = `<p><strong>Дней с уведомлениями:</strong> ${alertsData.total_alert_days} из ${alertsData.period_days}</p>`;
                    
                    alertsData.daily_alerts.forEach(dayAlerts => {
                        html += `
                            <div style="margin: 10px 0; padding: 10px; border-left: 3px solid #f39c12; background: #fff3cd;">
                                <strong>${new Date(dayAlerts.date).toLocaleDateString('ru-RU')}</strong> (MAPE: ${dayAlerts.daily_mape.toFixed(1)}%)
                                <ul style="margin: 5px 0 0 20px;">
                        `;
                        
                        dayAlerts.alerts.forEach(alert => {
                            const color = alert.type === 'critical' ? '#e74c3c' : '#f39c12';
                            html += `<li style="color: ${color};">${alert.message}</li>`;
                        });
                        
                        html += '</ul></div>';
                    });
                    
                    alertsDiv.innerHTML = html;
                } catch (error) {
                    alertsDiv.innerHTML = '<p style="color: #e74c3c;">❌ Ошибка загрузки уведомлений</p>';
                }
            }
            
            async function loadRetrainingSchedule() {
                const scheduleDiv = document.getElementById('retraining-schedule');
                try {
                    const response = await fetch('/api/monitoring/retrain/status');
                    const status = await response.json();
                    
                    let html = '<div style="display: grid; gap: 15px;">';
                    
                    status.scheduled_jobs.forEach(job => {
                        const nextRun = job.next_run ? new Date(job.next_run).toLocaleString('ru-RU') : 'Не запланирован';
                        html += `
                            <div style="padding: 15px; border: 1px solid #ddd; border-radius: 6px; background: #f8f9fa;">
                                <h4 style="margin: 0 0 10px 0; color: #2c3e50;">${job.name}</h4>
                                <p style="margin: 5px 0;"><strong>Следующий запуск:</strong> ${nextRun}</p>
                                <p style="margin: 5px 0;"><strong>Расписание:</strong> ${job.trigger}</p>
                            </div>
                        `;
                    });
                    
                    html += '</div>';
                    scheduleDiv.innerHTML = html;
                } catch (error) {
                    scheduleDiv.innerHTML = '<p style="color: #e74c3c;">❌ Ошибка загрузки расписания</p>';
                }
            }
            
            async function loadTrainingHistory() {
                const tableBody = document.querySelector('#training-history-table tbody');
                try {
                    // For now, show placeholder data since retraining log table isn't implemented yet
                    tableBody.innerHTML = `
                        <tr>
                            <td colspan="7" style="text-align: center; padding: 20px; color: #666;">
                                История переобучений будет доступна после создания таблиц версионирования модели.<br>
                                <small>Выполните миграцию: migrations/002_add_model_versioning.sql</small>
                            </td>
                        </tr>
                    `;
                } catch (error) {
                    tableBody.innerHTML = '<tr><td colspan="7" style="color: #e74c3c; text-align: center; padding: 20px;">❌ Ошибка загрузки истории</td></tr>';
                }
            }
            
            async function loadCurrentModelStatusForRetraining() {
                const statusDiv = document.getElementById('current-model-status');
                try {
                    const response = await fetch('/api/forecast/model/info');
                    const info = await response.json();
                    
                    if (info.status === 'loaded') {
                        statusDiv.innerHTML = `
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                                <div>
                                    <h4 style="margin: 0 0 10px 0; color: #2c3e50;">Информация о модели</h4>
                                    <p><strong>Тип:</strong> ${info.model_type}</p>
                                    <p><strong>Признаков:</strong> ${info.n_features}</p>
                                    <p><strong>Путь:</strong> ${info.model_path}</p>
                                </div>
                                <div>
                                    <h4 style="margin: 0 0 10px 0; color: #2c3e50;">Метрики</h4>
                                    <p><strong>Test MAPE:</strong> ${info.training_metrics?.test_mape?.toFixed(2)}%</p>
                                    <p><strong>Test R²:</strong> ${info.training_metrics?.test_r2?.toFixed(4)}</p>
                                    <p><strong>Обучающих данных:</strong> ${info.training_metrics?.train_samples}</p>
                                </div>
                            </div>
                        `;
                    } else {
                        statusDiv.innerHTML = '<p style="color: #e74c3c;">❌ Модель не загружена</p>';
                    }
                } catch (error) {
                    statusDiv.innerHTML = '<p style="color: #e74c3c;">❌ Ошибка загрузки информации о модели</p>';
                }
            }
            
            async function startManualRetraining() {
                const reason = document.getElementById('retrain-reason').value.trim();
                const threshold = parseFloat(document.getElementById('performance-threshold').value);
                const forceDeploy = document.getElementById('force-deploy').checked;
                
                if (!reason) {
                    alert('Пожалуйста, укажите причину переобучения');
                    return;
                }
                
                if (!confirm(`Начать переобучение модели?\\n\\nПричина: ${reason}\\nПорог: ${threshold}%\\nПринудительное развертывание: ${forceDeploy ? 'Да' : 'Нет'}`)) {
                    return;
                }
                
                // Show progress
                const progressDiv = document.getElementById('retraining-progress');
                const resultsDiv = document.getElementById('retraining-results');
                const btn = document.getElementById('retrain-btn');
                
                progressDiv.style.display = 'block';
                resultsDiv.style.display = 'none';
                btn.disabled = true;
                btn.textContent = '⏳ Переобучение...';
                
                const progressFill = document.getElementById('retrain-progress-fill');
                const progressText = document.getElementById('retrain-progress-text');
                const logs = document.getElementById('retrain-logs');
                
                // Simulate progress
                let progress = 0;
                const progressInterval = setInterval(() => {
                    progress += Math.random() * 15;
                    if (progress > 90) progress = 90;
                    progressFill.style.width = progress + '%';
                    progressText.textContent = `Переобучение... ${Math.round(progress)}%`;
                }, 1000);
                
                try {
                    logs.innerHTML = 'Инициализация переобучения...\\n';
                    
                    const response = await fetch('/api/monitoring/retrain/manual', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            reason: reason,
                            force_deploy: forceDeploy,
                            performance_threshold: threshold
                        })
                    });
                    
                    const result = await response.json();
                    
                    clearInterval(progressInterval);
                    progressFill.style.width = '100%';
                    progressText.textContent = 'Завершено!';
                    
                    // Show results
                    setTimeout(() => {
                        showRetrainingResults(result);
                        btn.disabled = false;
                        btn.textContent = '🔄 Начать переобучение';
                    }, 1000);
                    
                } catch (error) {
                    clearInterval(progressInterval);
                    progressText.textContent = 'Ошибка!';
                    logs.innerHTML += `ОШИБКА: ${error.message}\\n`;
                    
                    btn.disabled = false;
                    btn.textContent = '🔄 Начать переобучение';
                }
            }
            
            function showRetrainingResults(result) {
                const resultsDiv = document.getElementById('retraining-results');
                const contentDiv = document.getElementById('retrain-results-content');
                
                if (result.status === 'success') {
                    const improvement = result.metrics.improvement;
                    const improvementPercent = result.metrics.improvement_percent;
                    const deploymentClass = result.deployment_decision === 'deployed' ? 'result-success' : 'result-error';
                    
                    contentDiv.innerHTML = `
                        <div class="${deploymentClass}">
                            <h4>Результаты переобучения</h4>
                            <p><strong>Новая версия:</strong> ${result.new_version_id}</p>
                            <p><strong>Решение:</strong> ${result.deployment_decision}</p>
                            <p><strong>Причина:</strong> ${result.decision_reason}</p>
                            
                            <div style="margin: 15px 0; padding: 15px; background: rgba(255,255,255,0.8); border-radius: 6px;">
                                <h5>Сравнение метрик:</h5>
                                <p><strong>Предыдущий MAPE:</strong> ${result.metrics.previous_mape}%</p>
                                <p><strong>Новый MAPE:</strong> ${result.metrics.new_mape}%</p>
                                <p><strong>Улучшение:</strong> ${improvement.toFixed(2)} MAPE (${improvementPercent.toFixed(1)}%)</p>
                            </div>
                            
                            <div style="margin: 15px 0; padding: 15px; background: rgba(255,255,255,0.8); border-radius: 6px;">
                                <h5>Детали обучения:</h5>
                                <p><strong>Образцов данных:</strong> ${result.training_details.samples}</p>
                                <p><strong>Признаков:</strong> ${result.training_details.features}</p>
                                <p><strong>Время выполнения:</strong> ${result.training_details.execution_time} сек</p>
                            </div>
                        </div>
                    `;
                } else {
                    contentDiv.innerHTML = `
                        <div class="result-error">
                            <h4>Ошибка переобучения</h4>
                            <p><strong>Статус:</strong> ${result.status}</p>
                            <p><strong>Сообщение:</strong> ${result.message}</p>
                            ${result.error_type ? `<p><strong>Тип ошибки:</strong> ${result.error_type}</p>` : ''}
                        </div>
                    `;
                }
                
                resultsDiv.style.display = 'block';
                
                // Refresh current model status
                setTimeout(() => {
                    loadCurrentModelStatusForRetraining();
                }, 2000);
            }
            
            function resetRetrainingForm() {
                document.getElementById('retrain-reason').value = '';
                document.getElementById('performance-threshold').value = '10.0';
                document.getElementById('force-deploy').checked = false;
                document.getElementById('retraining-progress').style.display = 'none';
                document.getElementById('retraining-results').style.display = 'none';
            }
            
            async function checkRetrainingStatus() {
                try {
                    const response = await fetch('/api/monitoring/retrain/status');
                    const status = await response.json();
                    
                    alert(`Статус системы переобучения:\\n\\nТекущее время: ${new Date(status.current_time).toLocaleString('ru-RU')}\\n\\nЗапланированные задачи: ${status.scheduled_jobs.length}\\n\\nПоследнее переобучение: ${status.last_retrain.status}`);
                } catch (error) {
                    alert('Ошибка проверки статуса: ' + error.message);
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
            // ERROR ANALYSIS EVENT HANDLERS
            // =============================================================
            
            // Error Analysis by Segment Form Handler
            document.addEventListener('DOMContentLoaded', function() {
                const errorSegmentForm = document.getElementById('error-segment-form');
                if (errorSegmentForm) {
                    errorSegmentForm.addEventListener('submit', async function(e) {
                        e.preventDefault();
                        
                        const fromDate = document.getElementById('error-from-date').value;
                        const toDate = document.getElementById('error-to-date').value;
                        const segmentType = document.getElementById('segment-type').value;
                        
                        if (!fromDate || !toDate) {
                            alert('Пожалуйста, укажите даты');
                            return;
                        }
                        
                        await analyzeErrorsBySegment(fromDate, toDate, segmentType);
                    });
                }
                
                // Problematic Branches Form Handler
                const problematicForm = document.getElementById('problematic-branches-form');
                if (problematicForm) {
                    problematicForm.addEventListener('submit', async function(e) {
                        e.preventDefault();
                        
                        const fromDate = document.getElementById('prob-from-date').value;
                        const toDate = document.getElementById('prob-to-date').value;
                        const minSamples = document.getElementById('min-samples').value;
                        const mapeThreshold = document.getElementById('mape-threshold').value;
                        
                        if (!fromDate || !toDate) {
                            alert('Пожалуйста, укажите даты');
                            return;
                        }
                        
                        await identifyProblematicBranches(fromDate, toDate, minSamples, mapeThreshold);
                    });
                }
                
                // Temporal Analysis Form Handler
                const temporalForm = document.getElementById('temporal-analysis-form');
                if (temporalForm) {
                    temporalForm.addEventListener('submit', async function(e) {
                        e.preventDefault();
                        
                        const fromDate = document.getElementById('temp-from-date').value;
                        const toDate = document.getElementById('temp-to-date').value;
                        
                        if (!fromDate || !toDate) {
                            alert('Пожалуйста, укажите даты');
                            return;
                        }
                        
                        await analyzeTemporalErrors(fromDate, toDate);
                    });
                }
                
                // Error Distribution Form Handler
                const distributionForm = document.getElementById('error-distribution-form');
                if (distributionForm) {
                    distributionForm.addEventListener('submit', async function(e) {
                        e.preventDefault();
                        
                        const fromDate = document.getElementById('dist-from-date').value;
                        const toDate = document.getElementById('dist-to-date').value;
                        const departmentId = document.getElementById('dist-department').value;
                        
                        if (!fromDate || !toDate) {
                            alert('Пожалуйста, укажите даты');
                            return;
                        }
                        
                        await analyzeErrorDistribution(fromDate, toDate, departmentId);
                    });
                }
            });
            
            // Error Analysis API Functions
            async function analyzeErrorsBySegment(fromDate, toDate, segmentType) {
                const loading = document.getElementById('error-segment-loading');
                const results = document.getElementById('error-segment-results');
                
                loading.style.display = 'block';
                results.style.display = 'none';
                
                try {
                    const response = await fetch(
                        `/api/forecast/error-analysis/errors_by_segment?from_date=${fromDate}&to_date=${toDate}&segment_type=${segmentType}`
                    );
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        displayErrorSegmentResults(data.analysis);
                    } else {
                        alert('Ошибка при анализе: ' + (data.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    console.error('Error analyzing errors by segment:', error);
                    alert('Ошибка при выполнении анализа');
                } finally {
                    loading.style.display = 'none';
                }
            }
            
            async function identifyProblematicBranches(fromDate, toDate, minSamples, mapeThreshold) {
                const loading = document.getElementById('problematic-loading');
                const results = document.getElementById('problematic-results');
                
                loading.style.display = 'block';
                results.style.display = 'none';
                
                try {
                    const response = await fetch(
                        `/api/forecast/error-analysis/problematic_branches?from_date=${fromDate}&to_date=${toDate}&min_samples=${minSamples}&mape_threshold=${mapeThreshold}`
                    );
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        displayProblematicBranchesResults(data);
                    } else {
                        alert('Ошибка при анализе: ' + (data.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    console.error('Error identifying problematic branches:', error);
                    alert('Ошибка при выполнении анализа');
                } finally {
                    loading.style.display = 'none';
                }
            }
            
            async function analyzeTemporalErrors(fromDate, toDate) {
                const loading = document.getElementById('temporal-loading');
                const results = document.getElementById('temporal-results');
                
                loading.style.display = 'block';
                results.style.display = 'none';
                
                try {
                    const response = await fetch(
                        `/api/forecast/error-analysis/temporal_errors?from_date=${fromDate}&to_date=${toDate}`
                    );
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        displayTemporalAnalysisResults(data.temporal_analysis);
                    } else {
                        alert('Ошибка при анализе: ' + (data.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    console.error('Error analyzing temporal errors:', error);
                    alert('Ошибка при выполнении анализа');
                } finally {
                    loading.style.display = 'none';
                }
            }
            
            async function analyzeErrorDistribution(fromDate, toDate, departmentId) {
                const loading = document.getElementById('distribution-loading');
                const results = document.getElementById('distribution-results');
                
                loading.style.display = 'block';
                results.style.display = 'none';
                
                try {
                    let url = `/api/forecast/error-analysis/error_distribution?from_date=${fromDate}&to_date=${toDate}`;
                    if (departmentId) {
                        url += `&department_id=${departmentId}`;
                    }
                    
                    const response = await fetch(url);
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        displayErrorDistributionResults(data.error_distribution);
                    } else {
                        alert('Ошибка при анализе: ' + (data.detail || 'Неизвестная ошибка'));
                    }
                } catch (error) {
                    console.error('Error analyzing error distribution:', error);
                    alert('Ошибка при выполнении анализа');
                } finally {
                    loading.style.display = 'none';
                }
            }
            
            // Display Functions for Error Analysis Results
            function displayErrorSegmentResults(analysis) {
                const summary = document.getElementById('error-segment-summary');
                const table = document.getElementById('error-segment-table');
                const results = document.getElementById('error-segment-results');
                
                // Display summary
                if (analysis.summary) {
                    summary.innerHTML = `
                        <div class="stat-card">
                            <div class="stat-label">Общий MAPE</div>
                            <div class="stat-value">${analysis.summary.avg_mape}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Лучший сегмент</div>
                            <div class="stat-value">${analysis.summary.best_department || analysis.summary.best_day || analysis.summary.best_month || analysis.summary.best_location || 'N/A'}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Худший сегмент</div>
                            <div class="stat-value">${analysis.summary.worst_department || analysis.summary.worst_day || analysis.summary.worst_month || analysis.summary.worst_location || 'N/A'}</div>
                        </div>
                    `;
                }
                
                // Display table
                const tbody = table.querySelector('tbody');
                tbody.innerHTML = '';
                
                if (analysis.analysis && analysis.analysis.length > 0) {
                    analysis.analysis.forEach(item => {
                        const row = tbody.insertRow();
                        const segmentName = item.department_name || item.day_of_week || item.month_name || item.location || 'Unknown';
                        
                        row.innerHTML = `
                            <td>${segmentName}</td>
                            <td>${item.count_error_percentage || 'N/A'}</td>
                            <td>${item.mean_error_percentage || 'N/A'}%</td>
                            <td>${item.std_error_percentage || 'N/A'}</td>
                            <td>${(item.mean_actual_sales || 0).toLocaleString()}</td>
                        `;
                    });
                }
                
                results.style.display = 'block';
            }
            
            function displayProblematicBranchesResults(data) {
                const summary = document.getElementById('problematic-summary');
                const table = document.getElementById('problematic-table');
                const results = document.getElementById('problematic-results');
                
                // Display summary
                summary.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-label">Проблемных филиалов</div>
                        <div class="stat-value">${data.problematic_branches_count}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">Мин. прогнозов</div>
                        <div class="stat-value">${data.criteria.min_samples}</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-label">MAPE порог</div>
                        <div class="stat-value">${data.criteria.mape_threshold}%</div>
                    </div>
                `;
                
                // Display table
                const tbody = table.querySelector('tbody');
                tbody.innerHTML = '';
                
                if (data.problematic_branches && data.problematic_branches.length > 0) {
                    data.problematic_branches.forEach(branch => {
                        const row = tbody.insertRow();
                        row.innerHTML = `
                            <td>${branch.department_name}</td>
                            <td>${branch.predictions_count}</td>
                            <td>${branch.avg_mape}%</td>
                            <td>${branch.min_mape}% / ${branch.max_mape}%</td>
                            <td>${branch.avg_actual_sales.toLocaleString()}</td>
                            <td>${branch.avg_error.toLocaleString()}</td>
                        `;
                    });
                } else {
                    const row = tbody.insertRow();
                    row.innerHTML = '<td colspan="6" style="text-align: center;">Проблемных филиалов не найдено</td>';
                }
                
                results.style.display = 'block';
            }
            
            function displayTemporalAnalysisResults(analysis) {
                const summary = document.getElementById('temporal-summary');
                const results = document.getElementById('temporal-results');
                
                // Display summary
                if (analysis.overall_stats) {
                    summary.innerHTML = `
                        <div class="stat-card">
                            <div class="stat-label">Общий MAPE</div>
                            <div class="stat-value">${analysis.overall_stats.avg_mape}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Лучший день</div>
                            <div class="stat-value">${analysis.overall_stats.best_day_mape}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Худший день</div>
                            <div class="stat-value">${analysis.overall_stats.worst_day_mape}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Всего прогнозов</div>
                            <div class="stat-value">${analysis.overall_stats.total_predictions}</div>
                        </div>
                    `;
                }
                
                // Set current temporal data and show default tab
                currentTemporalData = analysis;
                showTemporalTab('weekday');
                
                results.style.display = 'block';
            }
            
            function displayErrorDistributionResults(distribution) {
                const stats = document.getElementById('distribution-stats');
                const rangesTable = document.getElementById('distribution-ranges-table');
                const results = document.getElementById('distribution-results');
                
                // Display statistics
                if (distribution.statistics) {
                    const s = distribution.statistics;
                    stats.innerHTML = `
                        <div class="stat-card">
                            <div class="stat-label">Средний MAPE</div>
                            <div class="stat-value">${s.mean}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Медиана</div>
                            <div class="stat-value">${s.median}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Стд. отклонение</div>
                            <div class="stat-value">${s.std}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">95-й процентиль</div>
                            <div class="stat-value">${s.percentiles.p95}%</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Отличных прогнозов</div>
                            <div class="stat-value">${s.outliers.low_error_count}</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-label">Плохих прогнозов</div>
                            <div class="stat-value">${s.outliers.high_error_count}</div>
                        </div>
                    `;
                }
                
                // Display ranges table
                const tbody = rangesTable.querySelector('tbody');
                tbody.innerHTML = '';
                
                if (distribution.range_distribution) {
                    distribution.range_distribution.forEach(range => {
                        const row = tbody.insertRow();
                        const rangeClass = getRangeClass(range.label);
                        row.innerHTML = `
                            <td>${range.range}</td>
                            <td class="${rangeClass}">${range.label}</td>
                            <td>${range.count}</td>
                            <td>${range.percentage}%</td>
                        `;
                    });
                }
                
                results.style.display = 'block';
            }
            
            function getRangeClass(label) {
                switch(label.toLowerCase()) {
                    case 'excellent': return 'error-range-excellent';
                    case 'good': return 'error-range-good';
                    case 'acceptable': return 'error-range-acceptable';
                    case 'poor': return 'error-range-poor';
                    case 'very poor': return 'error-range-very-poor';
                    default: return '';
                }
            }
            
            // Temporal Analysis Tab Functions
            let currentTemporalData = null;
            
            function showTemporalTab(tabType) {
                // Update tab buttons
                document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
                event.target.classList.add('active');
                
                if (!currentTemporalData) return;
                
                const table = document.getElementById('temporal-table');
                const thead = document.getElementById('temporal-table-head');
                const tbody = document.getElementById('temporal-table-body');
                
                let data, headers;
                
                switch(tabType) {
                    case 'daily':
                        data = currentTemporalData.daily_errors || [];
                        headers = ['Дата', 'Прогнозов', 'Средний MAPE (%)', 'Стд. откл.', 'Продажи'];
                        break;
                    case 'weekday':
                        data = currentTemporalData.day_of_week_errors || [];
                        headers = ['День недели', 'Прогнозов', 'Средний MAPE (%)', 'Стд. откл.', 'Средние продажи'];
                        break;
                    case 'monthly':
                        data = currentTemporalData.monthly_errors || [];
                        headers = ['Месяц', 'Прогнозов', 'Средний MAPE (%)', 'Стд. откл.'];
                        break;
                    default:
                        return;
                }
                
                // Update table headers
                thead.innerHTML = '<tr>' + headers.map(h => `<th>${h}</th>`).join('') + '</tr>';
                
                // Update table body
                tbody.innerHTML = '';
                data.forEach(item => {
                    const row = tbody.insertRow();
                    
                    if (tabType === 'daily') {
                        row.innerHTML = `
                            <td>${new Date(item.date).toLocaleDateString()}</td>
                            <td>${item.count_error_percentage}</td>
                            <td>${item.mean_error_percentage}%</td>
                            <td>${item.std_error_percentage || 'N/A'}</td>
                            <td>${(item.sum_actual_sales || 0).toLocaleString()}</td>
                        `;
                    } else if (tabType === 'weekday') {
                        row.innerHTML = `
                            <td>${item.day_name}</td>
                            <td>${item.count_error_percentage}</td>
                            <td>${item.mean_error_percentage}%</td>
                            <td>${item.std_error_percentage || 'N/A'}</td>
                            <td>${(item.mean_actual_sales || 0).toLocaleString()}</td>
                        `;
                    } else if (tabType === 'monthly') {
                        row.innerHTML = `
                            <td>${item.month}</td>
                            <td>${item.count_error_percentage}</td>
                            <td>${item.mean_error_percentage}%</td>
                            <td>${item.std_error_percentage || 'N/A'}</td>
                        `;
                    }
                });
            }
            
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
                    const response = await fetch('/api/sales/auto-sync/status');
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
                    
                    const response = await fetch('/api/sales/auto-sync/test', { method: 'POST' });
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

            // POST-PROCESSING FUNCTIONS
            async function populatePostprocessingDepartmentFilters() {
                const testDeptSelect = document.getElementById('test-department');
                const batchDeptSelect = document.getElementById('batch-department');
                
                // Clear existing options
                testDeptSelect.innerHTML = '<option value="">Выберите филиал</option>';
                batchDeptSelect.innerHTML = '<option value="">Все подразделения</option>';
                
                try {
                    console.log('Загрузка подразделений для пост-обработки...');
                    // Fetch departments from API
                    const response = await fetch('/api/departments/');
                    const departments = await response.json();
                    
                    console.log('Получено подразделений:', departments.length);
                    
                    if (Array.isArray(departments)) {
                        departments.forEach(dept => {
                            if (dept.type === 'DEPARTMENT') {  // Only show departments, not organizations
                                const testOption = document.createElement('option');
                                testOption.value = dept.id;
                                testOption.textContent = dept.name;
                                testDeptSelect.appendChild(testOption);
                                
                                const batchOption = document.createElement('option');
                                batchOption.value = dept.id;
                                batchOption.textContent = dept.name;
                                batchDeptSelect.appendChild(batchOption);
                            }
                        });
                        
                        console.log(`Загружено ${departments.filter(d => d.type === 'DEPARTMENT').length} подразделений в списки пост-обработки`);
                    }
                } catch (error) {
                    console.error('Ошибка загрузки подразделений для пост-обработки:', error);
                    
                    // Add error options
                    const errorOption1 = document.createElement('option');
                    errorOption1.value = '';
                    errorOption1.textContent = 'Ошибка загрузки подразделений';
                    testDeptSelect.appendChild(errorOption1);
                    
                    const errorOption2 = document.createElement('option');
                    errorOption2.value = '';
                    errorOption2.textContent = 'Ошибка загрузки подразделений';
                    batchDeptSelect.appendChild(errorOption2);
                }
            }

            // Postprocessing Settings Functions
            async function loadPostprocessingSettings() {
                try {
                    const response = await fetch('/api/forecast/postprocessing/settings');
                    
                    if (response.ok) {
                        const settings = await response.json();
                        
                        // Load settings into form
                        document.getElementById('enable-smoothing').checked = settings.enable_smoothing;
                        document.getElementById('max-change-percent').value = settings.max_change_percent;
                        document.getElementById('enable-business-rules').checked = settings.enable_business_rules;
                        document.getElementById('enable-weekend-adjustment').checked = settings.enable_weekend_adjustment;
                        document.getElementById('enable-holiday-adjustment').checked = settings.enable_holiday_adjustment;
                        document.getElementById('enable-anomaly-detection').checked = settings.enable_anomaly_detection;
                        document.getElementById('anomaly-threshold').value = settings.anomaly_threshold;
                        document.getElementById('enable-confidence').checked = settings.enable_confidence;
                        document.getElementById('confidence-level').value = settings.confidence_level;
                        
                        console.log('Настройки загружены из базы данных:', settings);
                    } else if (response.status === 404) {
                        console.log('Настройки не найдены, используются значения по умолчанию');
                    } else {
                        console.error('Ошибка загрузки настроек:', response.status);
                    }
                } catch (error) {
                    console.error('Ошибка при загрузке настроек:', error);
                }
            }

            async function savePostprocessingSettings() {
                const statusDiv = document.getElementById('save-settings-status');
                statusDiv.innerHTML = '<span style="color: #007bff;">Сохранение...</span>';
                
                try {
                    // Collect settings from form
                    const settings = {
                        enable_smoothing: document.getElementById('enable-smoothing').checked,
                        max_change_percent: parseFloat(document.getElementById('max-change-percent').value),
                        enable_business_rules: document.getElementById('enable-business-rules').checked,
                        enable_weekend_adjustment: document.getElementById('enable-weekend-adjustment').checked,
                        enable_holiday_adjustment: document.getElementById('enable-holiday-adjustment').checked,
                        enable_anomaly_detection: document.getElementById('enable-anomaly-detection').checked,
                        anomaly_threshold: parseFloat(document.getElementById('anomaly-threshold').value),
                        enable_confidence: document.getElementById('enable-confidence').checked,
                        confidence_level: parseFloat(document.getElementById('confidence-level').value)
                    };
                    
                    const response = await fetch('/api/forecast/postprocessing/settings', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(settings)
                    });
                    
                    if (response.ok) {
                        const savedSettings = await response.json();
                        statusDiv.innerHTML = `<span style="color: #28a745;">✅ Настройки сохранены (ID: ${savedSettings.id})</span>`;
                        
                        // Auto-hide success message after 3 seconds
                        setTimeout(() => {
                            statusDiv.innerHTML = '';
                        }, 3000);
                        
                        console.log('Настройки сохранены:', savedSettings);
                    } else {
                        const errorData = await response.json();
                        statusDiv.innerHTML = `<span style="color: #dc3545;">❌ Ошибка: ${errorData.detail}</span>`;
                    }
                } catch (error) {
                    statusDiv.innerHTML = `<span style="color: #dc3545;">❌ Ошибка сети: ${error.message}</span>`;
                    console.error('Ошибка при сохранении настроек:', error);
                }
            }

            async function testPostprocessing() {
                const branchId = document.getElementById('test-department').value;
                const forecastDate = document.getElementById('test-date').value;
                const rawPrediction = document.getElementById('test-prediction').value;
                const resultsDiv = document.getElementById('test-results');
                
                if (!branchId || !forecastDate || !rawPrediction) {
                    resultsDiv.innerHTML = '<p style="color: #dc3545;">Заполните все поля</p>';
                    return;
                }
                
                // Get post-processing settings
                const applySmoothing = document.getElementById('enable-smoothing').checked;
                const applyBusinessRules = document.getElementById('enable-business-rules').checked;
                const applyAnomalyDetection = document.getElementById('enable-anomaly-detection').checked;
                const calculateConfidence = document.getElementById('enable-confidence').checked;
                
                resultsDiv.innerHTML = '<p style="color: #007bff;">Обработка...</p>';
                
                try {
                    // Build URL with query parameters
                    const url = new URL('/api/forecast/postprocess', window.location.origin);
                    url.searchParams.append('branch_id', branchId);
                    url.searchParams.append('forecast_date', forecastDate);
                    url.searchParams.append('raw_prediction', parseFloat(rawPrediction));
                    url.searchParams.append('apply_smoothing', applySmoothing);
                    url.searchParams.append('apply_business_rules', applyBusinessRules);
                    url.searchParams.append('apply_anomaly_detection', applyAnomalyDetection);
                    url.searchParams.append('calculate_confidence', calculateConfidence);
                    
                    const response = await fetch(url, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        }
                    });
                    
                    if (!response.ok) {
                        const errorData = await response.json().catch(() => ({}));
                        throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
                    }
                    
                    const data = await response.json();
                    
                    if (data.status === 'success') {
                        displayTestResults(data.result);
                    } else {
                        resultsDiv.innerHTML = `<p style="color: #dc3545;">Ошибка: ${data.detail || 'Неизвестная ошибка API'}</p>`;
                    }
                } catch (error) {
                    console.error('Error in testPostprocessing:', error);
                    resultsDiv.innerHTML = `<p style="color: #dc3545;">Ошибка сети: ${error.message || 'Неизвестная ошибка сети'}</p>`;
                }
            }

            function displayTestResults(result) {
                const resultsDiv = document.getElementById('test-results');
                
                let html = '<div style="font-size: 14px;">';
                
                // Main results
                html += `<div style="margin-bottom: 15px;">`;
                html += `<strong>📊 Результаты обработки:</strong><br>`;
                html += `<span style="color: #6c757d;">Исходный прогноз:</span> ${result.raw_prediction?.toFixed(2) || 'N/A'} ₸<br>`;
                html += `<span style="color: #28a745; font-weight: bold;">Обработанный прогноз:</span> ${result.processed_prediction?.toFixed(2) || 'N/A'} ₸`;
                html += `</div>`;
                
                // Adjustments applied
                if (result.adjustments_applied && result.adjustments_applied.length > 0) {
                    html += `<div style="margin-bottom: 15px;">`;
                    html += `<strong>🔧 Примененные корректировки:</strong><br>`;
                    result.adjustments_applied.forEach(adj => {
                        html += `<div style="margin-left: 15px; margin-bottom: 5px;">`;
                        html += `• ${adj.type}: ${adj.original?.toFixed(2)} → ${adj.adjusted?.toFixed(2)} (${adj.reason})`;
                        html += `</div>`;
                    });
                    html += `</div>`;
                } else {
                    html += `<div style="margin-bottom: 15px; color: #28a745;">✅ Корректировки не требуются</div>`;
                }
                
                // Anomaly detection
                if (result.anomaly_score !== null) {
                    const anomalyColor = result.is_anomaly ? '#dc3545' : '#28a745';
                    const anomalyIcon = result.is_anomaly ? '⚠️' : '✅';
                    html += `<div style="margin-bottom: 15px;">`;
                    html += `<strong>🔍 Обнаружение аномалий:</strong><br>`;
                    html += `<span style="color: ${anomalyColor};">${anomalyIcon} Z-score: ${result.anomaly_score?.toFixed(2)} (${result.is_anomaly ? 'аномалия' : 'норма'})</span>`;
                    html += `</div>`;
                }
                
                // Confidence interval
                if (result.confidence_interval) {
                    const ci = result.confidence_interval;
                    html += `<div style="margin-bottom: 15px;">`;
                    html += `<strong>📈 Доверительный интервал (${(ci.confidence_level * 100).toFixed(0)}%):</strong><br>`;
                    html += `${ci.lower_bound?.toFixed(2)} ₸ - ${ci.upper_bound?.toFixed(2)} ₸`;
                    html += `</div>`;
                }
                
                // Business flags
                if (result.business_flags && result.business_flags.length > 0) {
                    html += `<div style="margin-bottom: 15px;">`;
                    html += `<strong>🏢 Бизнес-контекст:</strong><br>`;
                    html += `<div style="margin-left: 15px;">`;
                    result.business_flags.forEach(flag => {
                        const flagEmoji = getFlagEmoji(flag);
                        html += `<span style="margin-right: 10px; color: #6c757d;">${flagEmoji} ${flag}</span>`;
                    });
                    html += `</div></div>`;
                }
                
                html += '</div>';
                resultsDiv.innerHTML = html;
            }

            function getFlagEmoji(flag) {
                const emojiMap = {
                    'weekend': '🎮',
                    'friday': '🍻',
                    'monday': '😴',
                    'month_start': '📅',
                    'month_end': '💰',
                    'near_holiday': '🎉',
                    'holiday': '🎊',
                    'limited_recent_data': '📊',
                    'high_recent_volatility': '📈',
                    'anomaly_detected': '⚠️'
                };
                return emojiMap[flag] || '🏷️';
            }

            async function runBatchPostprocessing() {
                const fromDate = document.getElementById('batch-from-date').value;
                const toDate = document.getElementById('batch-to-date').value;
                const departmentId = document.getElementById('batch-department').value;
                
                if (!fromDate || !toDate) {
                    alert('Укажите даты начала и окончания');
                    return;
                }
                
                // Show progress
                const progressDiv = document.getElementById('batch-progress');
                const resultsDiv = document.getElementById('batch-results');
                const statusP = document.getElementById('batch-status');
                const progressBar = document.getElementById('batch-progress-bar');
                
                progressDiv.style.display = 'block';
                resultsDiv.style.display = 'none';
                statusP.textContent = 'Получение прогнозов...';
                progressBar.style.width = '20%';
                
                try {
                    // Get batch forecasts with post-processing
                    const url = new URL('/api/forecast/batch_with_postprocessing', window.location.origin);
                    url.searchParams.append('from_date', fromDate);
                    url.searchParams.append('to_date', toDate);
                    url.searchParams.append('apply_postprocessing', 'true');
                    if (departmentId) {
                        url.searchParams.append('department_id', departmentId);
                    }
                    
                    statusP.textContent = 'Применение пост-обработки...';
                    progressBar.style.width = '60%';
                    
                    const response = await fetch(url);
                    const data = await response.json();
                    
                    statusP.textContent = 'Обработка завершена';
                    progressBar.style.width = '100%';
                    
                    if (Array.isArray(data)) {
                        displayBatchResults(data);
                        
                        // Store results for download
                        window.batchResultsData = data;
                        document.getElementById('download-batch-btn').style.display = 'inline-block';
                    } else {
                        throw new Error(data.detail || 'Неизвестная ошибка');
                    }
                    
                } catch (error) {
                    statusP.textContent = `Ошибка: ${error.message}`;
                    progressBar.style.width = '0%';
                }
            }

            function displayBatchResults(results) {
                const resultsDiv = document.getElementById('batch-results');
                const contentDiv = document.getElementById('batch-results-content');
                
                // Calculate summary statistics
                const processedResults = results.filter(r => r.processed_prediction !== null);
                const totalForecasts = processedResults.length;
                const adjustmentsCount = processedResults.filter(r => r.adjustments_applied && r.adjustments_applied.length > 0).length;
                const anomaliesCount = processedResults.filter(r => r.is_anomaly).length;
                
                let html = '<div style="margin-bottom: 20px;">';
                html += '<h5>📊 Сводка по обработке</h5>';
                html += `<p><strong>Всего прогнозов:</strong> ${totalForecasts}</p>`;
                html += `<p><strong>С корректировками:</strong> ${adjustmentsCount} (${(adjustmentsCount/totalForecasts*100).toFixed(1)}%)</p>`;
                html += `<p><strong>Обнаружено аномалий:</strong> ${anomaliesCount} (${(anomaliesCount/totalForecasts*100).toFixed(1)}%)</p>`;
                html += '</div>';
                
                // Show first 10 results
                html += '<h5>📋 Примеры результатов (первые 10)</h5>';
                html += '<div style="max-height: 400px; overflow-y: auto;">';
                html += '<table style="width: 100%; border-collapse: collapse; font-size: 12px;">';
                html += '<thead><tr style="background: #f8f9fa;">';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Дата</th>';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Филиал</th>';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Исходный</th>';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Обработанный</th>';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Корректировки</th>';
                html += '<th style="border: 1px solid #dee2e6; padding: 8px;">Аномалия</th>';
                html += '</tr></thead><tbody>';
                
                processedResults.slice(0, 10).forEach(result => {
                    html += '<tr>';
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.forecast_date || result.date}</td>`;
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.department_name || 'N/A'}</td>`;
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.raw_prediction?.toFixed(0) || 'N/A'}</td>`;
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.processed_prediction?.toFixed(0) || 'N/A'}</td>`;
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.adjustments_applied?.length || 0}</td>`;
                    html += `<td style="border: 1px solid #dee2e6; padding: 8px;">${result.is_anomaly ? '⚠️' : '✅'}</td>`;
                    html += '</tr>';
                });
                
                html += '</tbody></table></div>';
                
                contentDiv.innerHTML = html;
                resultsDiv.style.display = 'block';
            }

            function downloadBatchResults() {
                if (!window.batchResultsData) {
                    alert('Нет данных для скачивания');
                    return;
                }
                
                // Convert to CSV
                const headers = ['Date', 'Department', 'Raw_Prediction', 'Processed_Prediction', 'Adjustments_Count', 'Is_Anomaly', 'Anomaly_Score', 'Confidence_Lower', 'Confidence_Upper'];
                const csvContent = [
                    headers.join(','),
                    ...window.batchResultsData.map(row => [
                        row.forecast_date || row.date,
                        (row.department_name || '').replace(/,/g, ';'),
                        row.raw_prediction || '',
                        row.processed_prediction || '',
                        row.adjustments_applied?.length || 0,
                        row.is_anomaly ? 'Yes' : 'No',
                        row.anomaly_score || '',
                        row.confidence_interval?.lower_bound || '',
                        row.confidence_interval?.upper_bound || ''
                    ].join(','))
                ].join('\\n');
                
                // Download file
                const blob = new Blob([csvContent], { type: 'text/csv' });
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `forecast_postprocessing_${new Date().toISOString().split('T')[0]}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
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


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}