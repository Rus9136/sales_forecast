# Sales Forecast API

ML-проект для прогнозирования продаж с использованием FastAPI и LightGBM.

## Запуск проекта

1. Клонируйте репозиторий
2. Запустите через Docker Compose:

```bash
docker-compose up -d
```

3. Откройте браузер:
   - API документация: http://localhost:8000/docs
   - Админ-интерфейс: http://localhost:8000/

## Первоначальная настройка

1. Синхронизируйте справочник подразделений:
   - Откройте админ-интерфейс
   - Нажмите кнопку "Sync Branches from API"

## API Endpoints

- `GET /api/branches/` - Получить список подразделений
- `GET /api/branches/{branch_id}` - Получить информацию о подразделении
- `POST /api/branches/sync` - Синхронизировать справочник из внешнего API
- `PUT /api/branches/{branch_id}` - Обновить информацию о подразделении

## Структура базы данных

### Таблица `branches`
- `branch_id` - Код подразделения
- `name` - Название
- `parent_id` - Код родительского подразделения
- `organization_name` - Название организации
- `organization_bin` - БИН организации

### Таблица `sales`
- `id` - ID записи
- `branch_id` - Код подразделения
- `date` - Дата продажи
- `amount` - Сумма продажи

### Таблица `forecasts`
- `id` - ID записи
- `branch_id` - Код подразделения  
- `forecast_date` - Дата прогноза
- `predicted_amount` - Прогнозируемая сумма
- `model_version` - Версия модели

### Таблица `forecast_accuracy_log`
- `id` - ID записи
- `branch_id` - Код подразделения
- `forecast_date` - Дата прогноза
- `predicted_amount` - Прогнозируемая сумма
- `actual_amount` - Фактическая сумма
- `mae` - Mean Absolute Error
- `mape` - Mean Absolute Percentage Error

## Технологии

- FastAPI
- PostgreSQL
- SQLAlchemy
- LightGBM
- Docker & Docker Compose