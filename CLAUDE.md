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

### 2. Services
- **IikoDepartmentLoaderService**: Синхронизация подразделений с 1C Exchange API
- **IikoSalesLoaderService**: Загрузка продаж из iiko API с pandas обработкой
- **IikoAuthService**: Аутентификация в iiko системах
- **ML Services**: Обработка и прогнозирование данных

### 3. API Endpoints
- `/api/departments/` - Управление подразделениями
- `/api/departments/sync` - Синхронизация подразделений с внешним API
- `/api/sales/sync` - Синхронизация продаж из iiko API
- `/api/sales/summary` - Дневные итоги продаж
- `/api/sales/hourly` - Почасовые данные продаж
- `/api/sales/stats` - Статистика продаж
- Admin panel на `/` - Веб-интерфейс управления
  - **Подразделения**: Управление департаментами и организациями
  - **Продажи по дням**: Таблица дневных итогов с фильтрацией
  - **Продажи по часам**: Таблица почасовых данных с расширенными фильтрами
  - **Загрузка данных**: Форма синхронизации продаж с прогресс-баром

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

### Session Logs
- **SESSION_LOG_20250624_113111.md**: Первоначальная настройка системы
- **SESSION_LOG_20250624_122543.md**: Реализация системы загрузки продаж
- **SESSION_LOG_20250624_195433.md**: Добавление модуля продаж в админ панель

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

### Next Steps
- [x] ✅ Добавить веб-форму для выбора диапазона дат
- [x] ✅ Создать админ панель для управления продажами
- [x] ✅ Убрать mock данные и решить проблему 409 с реальными датами
- [x] ✅ Улучшить UI/UX админ панели
- [x] ✅ Исправить ошибки авторизации с iiko API
- [x] ✅ Пересобрать production Docker контейнеры
- [ ] Добавить экспорт данных в CSV/Excel
- [ ] Добавить графики и визуализацию продаж
- [ ] Добавить batch processing для больших объемов данных
- [ ] Интегрировать sales данные в ML модель прогнозирования
- [ ] Настроить CI/CD pipeline для автоматического деплоя
- [ ] Добавить real-time обновления через WebSocket
- [ ] Реализовать role-based доступ к данным