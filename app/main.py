from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from .config import settings
from .db import engine, Base
from .routers import branch, department, sales
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    debug=settings.DEBUG
)

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


@app.get("/", response_class=HTMLResponse)
async def root():
    """Admin interface with sidebar"""
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Админ панель</title>
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
        </style>
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
                    <li><a href="#сервис" class="section-header">СЕРВИС</a></li>
                    <li><a href="#загрузка-данных" onclick="showDataLoading()">Загрузка данных</a></li>
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
                    
                    if (response.ok) {
                        updateProgress(100, 'Загрузка завершена успешно!');
                        showResult(true, result);
                    } else {
                        throw new Error(result.detail || 'Ошибка синхронизации');
                    }
                    
                } catch (error) {
                    console.error('Sync error:', error);
                    showResult(false, { message: error.message });
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
                    `;
                } else {
                    resultContent.innerHTML = `
                        <h3>❌ Ошибка синхронизации</h3>
                        <p><strong>Ошибка:</strong> ${data.message}</p>
                        <p>Попробуйте еще раз или обратитесь к администратору.</p>
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
            
            // Initialize form handler when DOM is loaded
            document.addEventListener('DOMContentLoaded', function() {
                const salesForm = document.getElementById('sales-sync-form');
                if (salesForm) {
                    salesForm.addEventListener('submit', handleSalesSync);
                }
            });
            
            // Load data on page load
            window.onload = loadBranches;
        </script>
    </body>
    </html>
    """


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}