from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from .config import settings
from .db import engine, Base
from .routers import branch, department, sales, forecast
from .services.scheduled_sales_loader import run_auto_sync
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
        
        scheduler.start()
        logger.info("✅ Background scheduler started - Daily sales sync scheduled for 2:00 AM")
        
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
        <title>Админ панель - v2.2 (Smart Outliers)</title>
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
            }
            
            .sidebar-menu a {
                display: block;
                padding: 15px 20px;
                color: #bbb;
                text-decoration: none;
                transition: all 0.3s;
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
                background-color: #34495e !important;
                pointer-events: none;
                margin-top: 10px;
            }
            
            .sidebar-menu .section-header:first-child {
                margin-top: 0;
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
                margin-bottom: 20px;
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
            }
            
            .search-input {
                padding: 10px;
                border: 1px solid #ddd;
                border-radius: 4px;
                font-size: 14px;
                min-width: 300px;
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
        </style>
        
        <!-- Chart.js library -->
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <div class="container">
            <!-- Sidebar -->
            <div class="sidebar">
                <div class="sidebar-header">
                    <div class="sidebar-title">Админ панель</div>
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
                                    <th>ИНН</th>
                                </tr>
                            </thead>
                            <tbody id="branches-tbody">
                                <tr>
                                    <td colspan="4" class="no-data">Загрузка данных...</td>
                                </tr>
                            </tbody>
                        </table>
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

                <!-- Auto Sync Status Page -->
                <div id="page-auto-sync" class="page-content" style="display: none;">
                    <div class="page-header">
                        <h1 class="page-title">Автоматическая загрузка продаж</h1>
                    </div>
                    
                    <!-- Status Cards -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px; margin-bottom: 30px;">
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
                    tbody.innerHTML = '<tr><td colspan="4" class="no-data">Нет данных для отображения</td></tr>';
                    return;
                }
                
                tbody.innerHTML = '';
                filteredBranches.forEach(branch => {
                    const row = tbody.insertRow();
                    row.insertCell(0).textContent = branch.code || '-';
                    row.insertCell(1).textContent = branch.name || '-';
                    row.insertCell(2).textContent = branch.type || '-';
                    row.insertCell(3).textContent = branch.taxpayer_id_number || '-';
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
            
            // Page Navigation Functions
            function showDepartments() {
                hideAllPages();
                document.getElementById('page-departments').style.display = 'block';
                updateSidebarActive('#подразделения');
            }
            
            function showDataLoading() {
                hideAllPages();
                document.getElementById('page-data-loading').style.display = 'block';
                updateSidebarActive('#загрузка-данных');
                
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
                document.getElementById('page-departments').style.display = 'none';
                document.getElementById('page-data-loading').style.display = 'none';
                document.getElementById('page-daily-sales').style.display = 'none';
                document.getElementById('page-hourly-sales').style.display = 'none';
                document.getElementById('page-forecast-branch').style.display = 'none';
                document.getElementById('page-forecast-comparison').style.display = 'none';
                document.getElementById('page-forecast-export').style.display = 'none';
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
                
                // Set default dates (last 30 days)
                const today = new Date();
                const monthAgo = new Date(today);
                monthAgo.setDate(today.getDate() - 30);
                
                document.getElementById('comparison-start-date').value = monthAgo.toISOString().split('T')[0];
                document.getElementById('comparison-end-date').value = today.toISOString().split('T')[0];
                
                // Populate department filter
                populateForecastDepartmentFilters();
            }
            
            function showForecastExport() {
                hideAllPages();
                document.getElementById('page-forecast-export').style.display = 'block';
                updateSidebarActive('#экспорт-прогноза');
                
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

            // Load data on page load
            window.onload = loadBranches;
        </script>
    </body>
    </html>
    """


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}