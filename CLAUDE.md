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

## Common Commands

### Development
```bash
# Запуск в development режиме (НА ПОРТУ 8002!)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002

# Запуск тестов
pytest

# Миграции базы данных
alembic upgrade head
```

### Production (Docker)
```bash
# Запуск production окружения
docker-compose -f docker-compose.prod.yml up -d

# Перестройка контейнеров
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# Проверка логов
docker-compose -f docker-compose.prod.yml logs -f sales-forecast-app
```

### API Operations
```bash
# Синхронизация подразделений
curl -X POST http://localhost:8002/api/departments/sync

# Синхронизация продаж
curl -X POST "http://localhost:8002/api/sales/sync?from_date=2025-03-01&to_date=2025-03-31"

# Статус автоматических загрузок
curl http://localhost:8002/api/sales/auto-sync/status

# Тестирование автоматической загрузки
curl -X POST http://localhost:8002/api/sales/auto-sync/test
```

### ML Forecasting Commands
```bash
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

# Hyperparameter tuning с Optuna
curl -X POST "http://localhost:8002/api/forecast/optimize" \
  -H "Content-Type: application/json" \
  -d '{"n_trials": 50, "timeout": 1800, "cv_folds": 3, "days": 365}'

# Сравнение моделей LightGBM vs XGBoost vs CatBoost
curl -X POST "http://localhost:8002/api/forecast/compare_models" \
  -H "Content-Type: application/json" \
  -d '{"days": 365}'
```

### Model Monitoring and Retraining
```bash
# Проверка статуса здоровья модели
curl http://localhost:8002/api/monitoring/health

# Сводка производительности модели
curl "http://localhost:8002/api/monitoring/performance/summary?days=30"

# Расчет дневных метрик производительности
curl -X POST "http://localhost:8002/api/monitoring/performance/calculate-daily"

# Статус расписания переобучения
curl http://localhost:8002/api/monitoring/retrain/status

# Ручное переобучение модели
curl -X POST "http://localhost:8002/api/monitoring/retrain/manual" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Плановое переобучение для улучшения точности",
    "performance_threshold": 10.0,
    "force_deploy": false
  }'

# Недавние уведомления о проблемах модели
curl "http://localhost:8002/api/monitoring/alerts/recent?days=7"
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
- `API_TOKEN`: sf_1WIK_p9-x_qoBDgHkm5hqqKnjolZ0xF5_5Nm9K1r2816u1Wdet_fkgZ3RUvpPMieQ_ckBfPd1Nhw
- `DEBUG`: False

### Development
- `DATABASE_URL`: postgresql://postgres:postgres@localhost:5432/sales_forecast
- `API_BASE_URL`: http://tco.aqnietgroup.com:5555/v1
- `API_TOKEN`: sf_1WIK_p9-x_qoBDgHkm5hqqKnjolZ0xF5_5Nm9K1r2816u1Wdet_fkgZ3RUvpPMieQ_ckBfPd1Nhw
- `DEBUG`: True

### Security Notes
- ⚠️ **API_TOKEN**: Хранится в .env файле, НЕ коммитится в git (находится в .gitignore)
- ✅ **Automatic Injection**: Токен автоматически передается в админ панель через server-side rendering
- 🔒 **Production Security**: В production режиме все API endpoints требуют авторизацию

## Current System Status

### ✅ Fully Operational Systems
- **Sales Sync**: Работает с реальными данными iiko API
- **API Endpoints**: Все CRUD операции функциональны на порту 8002
- **Database Schema**: Foreign keys и индексы настроены правильно
- **Admin Panel**: Полнофункциональная панель управления с обновленным UI
- **Production**: Docker контейнеры стабильно работают

### ✅ ML Forecasting System v2.3 (Current)
- **Test MAPE**: 6.18% - отличный результат с правильной weekend логикой
- **Weekend Logic**: Корректная обработка выходных/будних дней (PostgreSQL совместимость)
- **R²**: 0.9962+ - стабильно превосходная точность модели
- **Data**: 7,491 записей (365 дней качественных данных)
- **Features**: 64 признака с weekend features и temporal smoothing
- **Temporal Smoothing**: Автоматическое предотвращение аномальных прогнозов (±50%)

### ✅ Advanced ML Systems
- **Data Quality System**: Аудит и обработка выбросов интегрирована
- **Feature Engineering System**: Sales momentum индикаторы и расширенные признаки
- **Hyperparameter Tuning System**: Optuna интеграция с TimeSeriesSplit кросс-валидацией
- **Error Analysis System**: Анализ ошибок по сегментам и проблемным филиалам
- **Forecast Post-processing System**: Адаптивное сглаживание и бизнес-правила
- **Model Monitoring & Retraining System**: Автоматическое переобучение и мониторинг

### ✅ Automation & Monitoring
- **Automatic Sales Loading**: Ежедневная загрузка в 02:00 с APScheduler
- **Model Retraining**: Еженедельное автоматическое переобучение (воскресенье 3:00 AM)
- **Performance Tracking**: Автоматическое накопление исторических данных
- **API Authentication**: Безопасная система авторизации через environment tokens

## Deployment Notes

### Production Server: aqniet.site
- **Domain**: https://aqniet.site/
- **Port Mapping**: 8002:8000 (sales-forecast-app)
- **Database Port**: 5435:5432 (sales-forecast-db)
- **Nginx**: Configured to proxy requests to Docker containers

## Known Issues & Solutions

### 1. Branch Sync Foreign Key Violations
**Problem**: При синхронизации подразделений возникают ошибки foreign key constraint
**Solution**: Обрабатывать подразделения в несколько проходов, сначала родительские, потом дочерние

### 2. Sales Data Processing
**Problem**: Необходимость aggregation больших объемов данных продаж
**Solution**: Используется pandas для группировки по дням и часам с эффективной обработкой

## Version Control

### Git Repository
- **Repository**: https://github.com/Rus9136/sales_forecast.git
- **Branch**: master
- **Latest Commit**: feat: Implement complete API authorization and weekend logic fixes v2.3

### Git Commands
```bash
# Clone repository
git clone https://github.com/Rus9136/sales_forecast.git

# Pull latest changes
git pull origin master

# Check commit history
git log --oneline
```

## Recent Critical Updates (2025-07-01/02)

### ✅ Weekend Logic Fix & Temporal Smoothing
- **Critical Weekend/Weekday Logic Fix**: Исправлена критическая ошибка в нумерации дней недели
  - **Проблема**: PostgreSQL (0=Sunday) vs Python pandas (0=Monday) несовместимость
  - **Решение**: Конвертация нумерации `postgres_dow = (python_dow + 1) % 7`
  - **Результат**: Модель корректно прогнозирует высокие продажи в выходные
- **Enhanced Weekend Features**: Добавлены `is_saturday`, `is_sunday`, `weekend_multiplier`
- **Temporal Smoothing System**: ±50% ограничение от среднего по дню недели за 4 недели

### ✅ Extended Forecasting System
- **Extended Forecasting Implementation**: Расширенное прогнозирование на 31+ дней
- **Hybrid Forecasting Strategy**: Автоматический выбор подхода по горизонту прогноза
  - **Short-term (1-7 days)**: Традиционная логика с fresh данными (MAPE 5-15%)
  - **Long-term (8+ days)**: Расширенная логика с последними доступными данными (MAPE 15-25%)

### ✅ API Authentication System
- **Environment-based Token**: Токен хранится в переменных окружения (.env файл)
- **Server-side Token Injection**: Токен передается с сервера в HTML без захардкоженных значений
- **Automatic Authorization**: Все API запросы автоматически включают Authorization заголовки
- **Zero User Input**: Пользователю не нужно вводить токен, система работает автоматически

## Health Checks

### Application Monitoring
```bash
# Application health
curl http://localhost:8002/

# Database health
docker exec sales-forecast-db pg_isready -U sales_user

# Model health
curl http://localhost:8002/api/monitoring/health

# Performance summary
curl "http://localhost:8002/api/monitoring/performance/summary?days=30"

# Recent alerts
curl "http://localhost:8002/api/monitoring/alerts/recent?days=7"
```

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