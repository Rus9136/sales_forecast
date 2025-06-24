# CLAUDE.md - Sales Forecast API Project

## Project Overview
Sales Forecast API - это система прогнозирования продаж, построенная на FastAPI с использованием LightGBM для машинного обучения. Проект интегрируется с внешними API для получения данных о подразделениях и организациях.

## ⚠️ ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ
**НЕ ТРОГАЙТЕ 1C Exchange Service на порту 8000!** Это отдельный независимый проект, который работает параллельно с Sales Forecast. 

### Разделение портов:
- **Порт 8000**: 1C Exchange Service (ОТДЕЛЬНЫЙ ПРОЕКТ - НЕ ТРОГАТЬ!)
- **Порт 8002**: Sales Forecast API (ЭТОТ ПРОЕКТ)
- **Порт 5435**: PostgreSQL для Sales Forecast
- **Порт 5433**: PostgreSQL для других проектов

## Architecture
- **Backend**: FastAPI (Python)
- **Database**: PostgreSQL
- **ML Framework**: LightGBM
- **Deployment**: Docker + Docker Compose
- **Frontend**: HTML/JavaScript (встроенная админ панель)

## Key Components

### 1. Database Models
- **Department**: Подразделения и организации
- **SalesSummary**: Дневные итоги продаж по подразделениям
- **SalesByHour**: Почасовые данные продаж
- **Forecast**: Прогнозы продаж
- **ForecastAccuracyLog**: Логи точности прогнозов
- **AutoSyncLog**: Логи автоматических загрузок продаж

### 2. Services
- **IikoDepartmentLoaderService**: Синхронизация подразделений с 1C Exchange API
- **IikoSalesLoaderService**: Загрузка продаж из iiko API с pandas обработкой
- **IikoAuthService**: Аутентификация в iiko системах
- **ScheduledSalesLoaderService**: Автоматическая ежедневная загрузка продаж
- **ML Services**: Обработка и прогнозирование данных

### 3. API Endpoints
- `/api/departments/` - Управление подразделениями
- `/api/departments/sync` - Синхронизация подразделений с внешним API
- `/api/sales/sync` - Синхронизация продаж из iiko API
- `/api/sales/summary` - Дневные итоги продаж
- `/api/sales/hourly` - Почасовые данные продаж
- `/api/sales/stats` - Статистика продаж
- `/api/sales/auto-sync/status` - Статус автоматических загрузок
- `/api/sales/auto-sync/test` - Тестовый запуск автоматической загрузки
- Admin panel на `/` - Веб-интерфейс управления
  - **Подразделения**: Управление департаментами и организациями
  - **Продажи по дням**: Таблица дневных итогов с фильтрацией
  - **Продажи по часам**: Таблица почасовых данных с расширенными фильтрами
  - **Загрузка данных**: Форма синхронизации продаж с прогресс-баром
  - **⏰ Автоматическая загрузка**: Мониторинг автоматических синхронизаций

## External Dependencies

### 1C Exchange Service
- **URL**: http://tco.aqnietgroup.com:5555/v1/objects
- **API Key**: SdSWhiCAv8nZR67
- **Purpose**: Получение данных о подразделениях и организациях

### iiko API Integration
- **Domains**: sandy-co-co.iiko.it, madlen-group-so.iiko.it
- **Authentication**: Username/password with 1-hour token refresh
- **Endpoints**: /resto/api/auth, /resto/api/v2/reports/olap
- **Purpose**: Загрузка данных о продажах с aggregation через pandas

## Development Guidelines

### Database Operations
- Всегда используйте транзакции для критических операций
- При bulk операциях обрабатывайте записи по одной для избежания конфликтов foreign key
- Используйте dependency injection для получения DB сессий

### API Design
- Следуйте REST принципам
- Используйте Pydantic модели для валидации
- Включайте proper error handling с HTTP status codes

### Testing
- Тестируйте синхронизацию данных с внешними API
- Проверяйте корректность обработки parent-child relationships в подразделениях
- Убедитесь в правильности ML прогнозов

## Common Commands

### ⚠️ ВАЖНО: Порты и проекты
```bash
# Sales Forecast API (ЭТОТ ПРОЕКТ) - порт 8002
curl http://localhost:8002/

# 1C Exchange Service (ДРУГОЙ ПРОЕКТ) - порт 8000 
# НЕ ТРОГАТЬ! НЕ ОСТАНАВЛИВАТЬ! НЕ ИЗМЕНЯТЬ!
curl http://localhost:8000/
```

### Development
```bash
# Запуск в development режиме (НА ПОРТУ 8002!)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

# Запуск тестов
pytest

# Миграции базы данных (если используется Alembic)
alembic upgrade head
```

### Production (Docker)
```bash
# Запуск production окружения
docker-compose -f docker-compose.prod.yml up -d

# Перестройка контейнеров (ТОЛЬКО Sales Forecast!)
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# Проверка логов
docker-compose -f docker-compose.prod.yml logs -f sales-forecast-app

# Синхронизация подразделений (НА ПОРТУ 8002!)
curl -X POST http://localhost:8002/api/departments/sync

# Синхронизация продаж из iiko (НА ПОРТУ 8002!)
curl -X POST "http://localhost:8002/api/sales/sync?from_date=2025-03-01&to_date=2025-03-31"

# Тестирование автоматической загрузки
curl -X POST http://localhost:8002/api/sales/auto-sync/test

# Статус автоматических загрузок
curl http://localhost:8002/api/sales/auto-sync/status
```

### ML Forecasting Commands
```bash
# Обучение модели
python test_model_training.py

# Получить прогноз для филиала на дату
curl "http://localhost:8002/api/forecast/2025-07-01/branch-uuid"

# Массовые прогнозы
curl "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07"

# Сравнение прогнозов с фактом
curl "http://localhost:8002/api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-30"

# Переобучение модели
curl -X POST http://localhost:8002/api/forecast/retrain

# Экспорт прогнозов в CSV
curl "http://localhost:8002/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31"

# Информация о модели
curl http://localhost:8002/api/forecast/model/info

# Тестирование графика (данные для одного филиала)
curl "http://localhost:8002/api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-05&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

### Chart Testing
```bash
# Тестирование функциональности графика
python3 test_chart_functionality.py

# Ручное тестирование графика в браузере:
# 1. Откройте http://localhost:8002/
# 2. ПРОГНОЗ ПРОДАЖ → Сравнение факт/прогноз  
# 3. Установите: 2025-06-01 до 2025-06-05
# 4. Выберите: Мадлен Plaza (или любой филиал)
# 5. Нажмите: "Загрузить"
# Ожидаемый результат: график с синей (прогноз) и зелёной (факт) линиями
```

### Database
```bash
# Подключение к PostgreSQL в Docker
docker exec -it sales-forecast-db psql -U sales_user -d sales_forecast

# Проверка количества записей
SELECT COUNT(*) FROM departments;
SELECT COUNT(*) FROM sales_summary;
SELECT COUNT(*) FROM sales_by_hour;
```

## Environment Variables

### Production
- `DATABASE_URL`: postgresql://sales_user:sales_password@sales-forecast-db:5432/sales_forecast
- `API_BASE_URL`: http://tco.aqnietgroup.com:5555/v1
- `DEBUG`: False

### Development
- `DATABASE_URL`: postgresql://postgres:postgres@localhost:5432/sales_forecast
- `API_BASE_URL`: http://tco.aqnietgroup.com:5555/v1
- `DEBUG`: True

## Known Issues & Solutions

### 1. Branch Sync Foreign Key Violations
**Problem**: При синхронизации подразделений возникают ошибки foreign key constraint
**Solution**: Обрабатывать подразделения в несколько проходов, сначала родительские, потом дочерние

### 2. Admin Panel Pagination
**Problem**: В админ панели отображаются только первые 100 подразделений
**Solution**: Увеличен лимит по умолчанию до 10000 в API endpoint

### 3. API Key Configuration
**Problem**: 1C Exchange Service требует правильный API ключ
**Solution**: Убедиться что API_KEY=SdSWhiCAv8nZR67 в environment variables

### 4. ~~iiko API 409 Conflict Error~~ ✅ RESOLVED
**Problem**: При запросе данных продаж возникает ошибка 409 для определенных дат
**Solution**: ✅ Исправлен парсинг дат с помощью pandas format='mixed', убраны mock данные, система работает с реальными API данными

### 5. Sales Data Processing
**Problem**: Необходимость aggregation больших объемов данных продаж
**Solution**: Используется pandas для группировки по дням и часам с эффективной обработкой

## Deployment Notes

### Production Server: aqniet.site
- **Domain**: https://aqniet.site/
- **Port Mapping**: 8002:8000 (sales-forecast-app)
- **Database Port**: 5435:5432 (sales-forecast-db)
- **Nginx**: Configured to proxy requests to Docker containers

### Multi-Service Setup
Сервер также хостит madlen.space, поэтому при изменении nginx конфигурации нужно быть осторожным.

## Monitoring

### Health Checks
- Application: `curl http://localhost:8002/`
- Database: `docker exec sales-forecast-db pg_isready -U sales_user`
- Departments Sync: `curl -X POST http://localhost:8002/api/departments/sync`
- Sales Sync: `curl -X POST http://localhost:8002/api/sales/sync`
- Sales Stats: `curl http://localhost:8002/api/sales/stats`
- Auto Sync Status: `curl http://localhost:8002/api/sales/auto-sync/status`
- Auto Sync Test: `curl -X POST http://localhost:8002/api/sales/auto-sync/test`

### Logs
```bash
# Application logs
docker logs sales-forecast-app

# Database logs  
docker logs sales-forecast-db

# All services
docker-compose -f docker-compose.prod.yml logs
```

## Security Considerations
- API endpoints защищены стандартными HTTP методами
- Database credentials хранятся в environment variables
- External API key используется для аутентификации с 1C системой
- iiko API credentials конфигурируются через environment variables
- Production режим (DEBUG=False) скрывает детальную информацию об ошибках

## Data Processing Pipeline

### Sales Data Flow
1. **Authentication**: Получение токена из iiko API (обновление каждые 55 минут)
2. **Data Fetching**: Запрос OLAP отчетов по продажам через POST /resto/api/v2/reports/olap
3. **Data Processing**: 
   - Pandas DataFrame загрузка JSON данных
   - Парсинг CloseTime для извлечения даты и часа
   - GroupBy aggregation для дневных итогов
   - GroupBy aggregation для почасовых данных
4. **Database Sync**: Insert/Update операции с проверкой foreign keys
5. **Result Response**: JSON ответ с количеством обработанных записей

### Data Aggregation Logic
```python
# Дневная группировка
daily_summary = df.groupby(['Department.Id', 'date']).agg(
    total_sales=('DishSumInt', 'sum')
).reset_index()

# Почасовая группировка  
hourly_data = df.groupby(['Department.Id', 'date', 'hour']).agg(
    sales_amount=('DishSumInt', 'sum')
).reset_index()
```

## Version Control

### Git Repository
- **Repository**: https://github.com/Rus9136/sales_forecast.git
- **Branch**: master
- **Latest Commit**: feat: Implement sales loading system from iiko API with pandas processing

### Git Commands
```bash
# Clone repository
git clone https://github.com/Rus9136/sales_forecast.git

# Pull latest changes
git pull origin master

# Check commit history
git log --oneline
```

## Automatic Sales Loading (NEW!)

### ⏰ Scheduled Background Tasks
- **APScheduler Integration**: Фоновый планировщик задач встроен в FastAPI приложение
- **Daily Auto-Sync**: Каждый день в 02:00 автоматическая загрузка продаж за предыдущий день
- **Background Processing**: Scheduler работает в отдельных потоках, не блокируя основное приложение

### 📊 Auto-Sync Monitoring
- **AutoSyncLog Table**: Полная история автоматических загрузок
- **Success/Error Tracking**: Детальная статистика успешных и неудачных попыток
- **Real-time Status**: API endpoints для мониторинга статуса автоматических загрузок

### 🛠️ Auto-Sync Commands
```bash
# Проверка статуса планировщика
curl http://localhost:8002/api/sales/auto-sync/status

# Тестовый запуск автоматической загрузки
curl -X POST http://localhost:8002/api/sales/auto-sync/test

# Проверка логов автоматических загрузок в БД
docker exec -it sales-forecast-db psql -U sales_user -d sales_forecast -c "SELECT * FROM auto_sync_log ORDER BY executed_at DESC LIMIT 10;"
```

### 🎯 Technical Implementation
- **ScheduledSalesLoaderService**: Сервис для выполнения автоматических загрузок
- **AsyncIO Compatibility**: Корректная обработка async функций в scheduler контексте
- **Thread Safety**: Использование ThreadPoolExecutor для избежания конфликтов event loop
- **Error Handling**: Graceful обработка ошибок без остановки scheduler
- **Logging**: Детальное логирование всех операций и результатов

## Recent Updates (2025-06-24)

### ✅ Sales Loading System Implementation
- **New Tables**: sales_summary, sales_by_hour с proper indexing
- **New Service**: IikoSalesLoaderService с pandas integration
- **New API Endpoints**: /api/sales/* для управления данными продаж
- **Mock Data**: Временная реализация для обхода 409 ошибок API
- **Production Deploy**: Успешный деплой в Docker с тестированием
- **Git Repository**: Создан и настроен GitHub репозиторий с полной историей

### ✅ Admin Panel Sales Module Enhancement (19:54:33)
- **New Sales Block**: Добавлен блок ПРОДАЖИ в админ панель
- **Daily Sales Table**: Таблица продаж по дням с фильтрацией
- **Hourly Sales Table**: Таблица продаж по часам с расширенными фильтрами
- **UI/UX Improvements**: Responsive дизайн, форматирование валюты, индикаторы загрузки
- **JavaScript Enhancement**: Унифицированная навигация и управление данными

### Current Status
- **Sales Sync**: ✅ Работает с реальными данными iiko API (стабильная загрузка больших объемов)
- **Authentication**: ✅ Принудительное обновление токенов решает проблемы авторизации
- **Data Aggregation**: ✅ Pandas обработка корректно группирует данные с format='mixed' для дат  
- **API Endpoints**: ✅ Все CRUD операции функциональны на порту 8002
- **Database Schema**: ✅ Foreign keys и индексы настроены правильно
- **Version Control**: ✅ Git репозиторий настроен и синхронизирован
- **Admin Panel**: ✅ Полнофункциональная панель управления продажами с обновленным UI
- **Production**: ✅ Docker контейнеры пересобраны и протестированы
- **ML Forecasting**: ✅ Полная система прогнозирования с LightGBM интегрирована
- **Forecast API**: ✅ REST endpoints для прогнозов, сравнения и экспорта
- **Forecast UI**: ✅ Раздел "ПРОГНОЗ ПРОДАЖ" с тремя подстраницами в админ панели
- **Model Management**: ✅ Обучение, сохранение и переобучение модели через UI
- **Chart Visualization**: ✅ Интерактивный график "Факт vs Прогноз" с Chart.js интеграцией

### Session Logs
- **SESSION_LOG_20250624_113111.md**: Первоначальная настройка системы
- **SESSION_LOG_20250624_122543.md**: Реализация системы загрузки продаж
- **SESSION_LOG_20250624_195433.md**: Добавление модуля продаж в админ панель
- **SESSION_LOG_20250624_201835.md**: Реализация ML системы прогнозирования с LightGBM

### ✅ Latest Updates (2025-06-24 Evening Session)
- **Real API Integration**: ✅ Убраны mock данные, система работает с реальными iiko API данными
- **Date Parsing Fix**: ✅ Исправлен парсинг дат с pandas format='mixed' для обработки разных форматов
- **UI/UX Improvements**: ✅ Убраны валютные символы, добавлено округление сумм, улучшен дизайн сайдбара
- **Admin Panel Cleanup**: ✅ Убраны кнопки "Назад" и пустые пункты меню (Сотрудники, Должности)
- **Section Headers**: ✅ Заголовки разделов в сайдбаре визуально отличаются от кнопок подпунктов

### ✅ Critical Bug Fixes (2025-06-24 Latest Session)
- **Token Authentication Issue**: ✅ Исправлена ошибка "Unexpected token" при загрузке продаж
  - Теперь токен принудительно обновляется перед каждым запросом к iiko API
  - Добавлена валидация JSON ответов с детальным логированием ошибок
  - Улучшена обработка HTTP ошибок с показом статуса ответа
- **Production Deployment**: ✅ Пересобран Docker контейнер с исправлениями
  - Применены все изменения в production окружении
  - Протестирована загрузка данных за март (135,833 записей успешно обработаны)
  - Подтверждена работа на правильном порту 8002

### ✅ ML Forecasting System (2025-06-24 Evening Session)
- **ML Pipeline**: ✅ Полный pipeline прогнозирования продаж
  - TrainingDataService для подготовки данных с feature engineering
  - SalesForecasterAgent с LightGBM моделью
  - 15 признаков включая rolling averages и временные метки
- **Forecast API**: ✅ REST API endpoints для прогнозирования
  - GET /api/forecast/{date}/{branch_id} - прогноз для филиала
  - GET /api/forecast/batch - массовые прогнозы
  - GET /api/forecast/comparison - сравнение факт/прогноз
  - GET /api/forecast/export/csv - экспорт в CSV
  - POST /api/forecast/retrain - переобучение модели
- **Admin Panel Forecast Module**: ✅ Новый раздел "ПРОГНОЗ ПРОДАЖ"
  - 📈 Прогноз по филиалам - таблица прогнозов с фильтрами
  - 📊 Сравнение факт/прогноз - анализ точности с сортировкой + интерактивный график
  - 📤 Экспорт прогноза - CSV экспорт с опциями
  - Интерфейс обучения модели с отображением метрик
- **Model Persistence**: ✅ Сохранение/загрузка модели
  - Модель сохраняется в models/lgbm_model.pkl
  - Автоматическая загрузка при старте приложения
  - Поддержка переобучения через UI

### ✅ Chart Visualization Update (2025-06-24 Latest Session)
- **Interactive Chart**: ✅ Добавлен интерактивный график "Факт vs Прогноз"
  - **Technology**: Chart.js библиотека для визуализации данных
  - **Location**: Страница "Сравнение факт/прогноз" (между фильтрами и таблицей)
  - **Features**: Линейный график с двумя сериями данных
    - 🔵 Синяя линия: Прогнозные значения
    - 🟢 Зелёная линия: Фактические продажи
    - 📅 Ось X: Даты в формате ДД.ММ.ГГГГ
    - 💰 Ось Y: Сумма продаж с форматированием в тенге
    - 🔍 Интерактивные подсказки при наведении
  - **Smart Display Logic**: 
    - График показывается только при выборе конкретного филиала
    - Скрывается при выборе "Все подразделения"
    - Автоматически обновляется при загрузке новых данных
    - Обновляется при сортировке таблицы
  - **Responsive Design**: Адаптивный дизайн для разных экранов
  - **Testing**: Протестирован с реальными данными за июнь 2025 (190 записей, 38 филиалов)

### ✅ Automatic Daily Sales Loading (2025-06-24 Latest Session)
- **APScheduler Integration**: ✅ Встроен планировщик фоновых задач в FastAPI приложение
  - Scheduler запускается автоматически при старте приложения
  - Graceful shutdown при остановке сервиса
  - Ежедневное расписание: 02:00 утра для загрузки данных предыдущего дня
- **ScheduledSalesLoaderService**: ✅ Новый сервис для автоматических загрузок
  - AsyncIO совместимость через ThreadPoolExecutor
  - Корректная обработка event loop конфликтов  
  - Детальное логирование всех операций
- **AutoSyncLog Model**: ✅ Новая таблица для истории автоматических загрузок
  - Логирование успешных и неудачных попыток
  - Хранение метрик: количество записей, время выполнения, ошибки
  - Статистика за различные периоды
- **Auto-Sync API**: ✅ REST endpoints для мониторинга автоматических загрузок
  - GET /api/sales/auto-sync/status - статистика и история
  - POST /api/sales/auto-sync/test - тестовый запуск
  - Полная совместимость с существующими manual sync операциями
- **Admin Panel Auto-Sync**: ✅ Новый раздел "⏰ Автоматическая загрузка"
  - Статистика успешности за 30 дней
  - История всех автоматических загрузок в таблице
  - Информация о последней успешной и неудачной загрузке
  - Кнопка тестового запуска с real-time результатами
- **Production Deployment**: ✅ Система протестирована и развернута
  - Docker контейнеры пересобраны с новой функциональностью
  - Scheduler автоматически запускается при старте приложения
  - Тестовые запуски подтверждают корректную работу

### Next Steps
- [x] ✅ Добавить веб-форму для выбора диапазона дат
- [x] ✅ Создать админ панель для управления продажами
- [x] ✅ Убрать mock данные и решить проблему 409 с реальными датами
- [x] ✅ Улучшить UI/UX админ панели
- [x] ✅ Исправить ошибки авторизации с iiko API
- [x] ✅ Пересобрать production Docker контейнеры
- [x] ✅ Интегрировать sales данные в ML модель прогнозирования (LightGBM)
- [x] ✅ Добавить экспорт данных в CSV
- [x] ✅ Создать полнофункциональный раздел прогнозирования в админ панели
- [x] ✅ Добавить график "Факт vs Прогноз" на страницу сравнения
- [x] ✅ Реализовать автоматическую ежедневную загрузку продаж
- [ ] Добавить автоматическое переобучение модели по расписанию
- [ ] Реализовать ensemble модели для повышения точности
- [ ] Добавить интервалы доверия для прогнозов
- [ ] Настроить CI/CD pipeline для автоматического деплоя
- [ ] Добавить real-time мониторинг точности прогнозов
- [ ] Реализовать role-based доступ к данным
- [ ] Добавить объяснения прогнозов (SHAP values)
- [ ] Создать мобильную версию интерфейса прогнозов