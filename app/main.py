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
                    <li><a href="#справочники">СПРАВОЧНИКИ</a></li>
                    <li><a href="#сотрудники">Сотрудники</a></li>
                    <li><a href="#подразделения" class="active">Подразделения</a></li>
                    <li><a href="#должности">Должности</a></li>
                </ul>
            </div>
            
            <!-- Main Content -->
            <div class="main-content">
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
            
            // Event listeners
            document.getElementById('search-input').addEventListener('input', applyFilters);
            document.getElementById('company-filter').addEventListener('change', applyFilters);
            
            // Load data on page load
            window.onload = loadBranches;
        </script>
    </body>
    </html>
    """


@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": settings.VERSION}