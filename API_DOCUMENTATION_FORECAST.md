# API Documentation - Sales Forecast System

## Quick Start

**Base URL:** `https://aqniet.site/api/forecast`

### Quick Authentication
**API Key Required in Production:** Include in Authorization header
```bash
Authorization: Bearer sf_your_key_id_your_secret
```
**Development Mode:** Authentication optional when DEBUG=True

### Quick Examples

#### Get Forecast for Date Range
```bash
# Without authentication (development)
curl "https://aqniet.site/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10"

# With API key (production)
curl "https://aqniet.site/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

#### Python Quick Example
```python
import requests

response = requests.get(
    "https://aqniet.site/api/forecast/batch",
    params={"from_date": "2026-05-04", "to_date": "2026-05-10"}
)
forecasts = response.json()
```

#### JavaScript Quick Example
```javascript
const response = await fetch(
    'https://aqniet.site/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10'
);
const forecasts = await response.json();
```

### Model Performance (ML v2.3)
- **Accuracy:** 6.18% MAPE (Mean Absolute Percentage Error)
- **R²:** 0.9962+
- **Features:** 64 engineered features (lags, weekend features, temporal smoothing, momentum, seasonality)
- **Hybrid horizon:** short-term 1-7 дней (MAPE 5-15%) / long-term 8+ дней (MAPE 15-25%)
- **Per-segment models:** на каждый `segment_type` подразделения тренируется отдельный LightGBM (`models/segments/<segment>.pkl`); для unknown / редких сегментов используется global fallback
- **Update:** автоматическое переобучение по воскресеньям 03:00
- **Coverage:** активные DEPARTMENT (с продажами за последние 30 дней)

### Active department filter
Endpoints `/forecast/batch` и `/forecast/comparison` **скрывают «мёртвые точки»** — DEPARTMENT-подразделения без записей в `sales_summary` за последние **30 дней** (`INACTIVE_THRESHOLD_DAYS` в `app/routers/department.py`). Чтобы посмотреть архивную точку, передайте `department_id` явно — фильтр пропускается.

### Response Times
- Single forecast: ~100ms
- Batch forecast (7 days): ~500ms
- Monthly export: ~2-3 seconds

---

## Base URL
```
https://aqniet.site/api
```

## Authentication

The API uses Bearer token authentication with API keys for external access.

### Getting an API Key
Contact your system administrator to obtain an API key, or use the API key management endpoints if you have access.

### API Key Format
```
sf_{key_id}_{secret}
```

### Authentication Headers
Include your API key in the Authorization header:
```
Authorization: Bearer sf_your_key_id_your_secret
```

### Development Mode
In development mode (DEBUG=True), authentication is optional. In production, API keys are required for all endpoints.

---

## Sales Data Endpoints

### 1. Get Sales Summary (Daily Sales)
**Endpoint:** `GET /api/sales/summary`

**Description:** Get daily sales data with flexible filtering options.

**Query Parameters:**
- `department_id` (optional): UUID of specific department to filter
- `from_date` (optional): Start date in ISO format (YYYY-MM-DD)
- `to_date` (optional): End date in ISO format (YYYY-MM-DD)
- `skip` (optional, default=0): Number of records to skip (pagination)
- `limit` (optional, default=1000, max=10000): Maximum records to return

**Example Requests:**
```bash
# Get all sales for the last 1000 records
curl -X GET "https://aqniet.site/api/sales/summary"

# Get sales for specific department
curl -X GET "https://aqniet.site/api/sales/summary?department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"

# Get sales for date range
curl -X GET "https://aqniet.site/api/sales/summary?from_date=2025-01-01&to_date=2025-01-31"

# Get sales for specific department and date range
curl -X GET "https://aqniet.site/api/sales/summary?department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a&from_date=2025-01-01&to_date=2025-01-31"

# With pagination
curl -X GET "https://aqniet.site/api/sales/summary?skip=100&limit=50"

# With API key authentication (production)
curl -X GET "https://aqniet.site/api/sales/summary?from_date=2025-01-01&to_date=2025-01-31" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

**Response:**
```json
[
  {
    "id": 12345,
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "date": "2025-01-15",
    "total_sales": 125000.50,
    "created_at": "2025-01-16T02:30:00",
    "updated_at": "2025-01-16T02:30:00",
    "synced_at": "2025-01-16T02:30:00"
  }
]
```

### 2. Get Hourly Sales Data
**Endpoint:** `GET /api/sales/hourly`

**Description:** Get hourly sales breakdown with filtering options.

**Query Parameters:**
- `department_id` (optional): UUID of specific department
- `from_date` (optional): Start date (YYYY-MM-DD)
- `to_date` (optional): End date (YYYY-MM-DD)
- `hour` (optional, 0-23): Filter by specific hour
- `skip` (optional, default=0): Pagination offset
- `limit` (optional, default=1000, max=10000): Maximum records

**Example Requests:**
```bash
# Get hourly sales for specific department
curl -X GET "https://aqniet.site/api/sales/hourly?department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a&from_date=2025-01-01&to_date=2025-01-31"

# Get sales for specific hour (e.g., 14:00-15:00)
curl -X GET "https://aqniet.site/api/sales/hourly?hour=14&from_date=2025-01-01&to_date=2025-01-31"
```

**Response:**
```json
[
  {
    "id": 67890,
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "date": "2025-01-15",
    "hour": 14,
    "sales_amount": 8500.25,
    "created_at": "2025-01-16T02:30:00",
    "updated_at": "2025-01-16T02:30:00",
    "synced_at": "2025-01-16T02:30:00"
  }
]
```

### 2a. Get Checks (Receipts) Per Hour
**Endpoint:** `GET /api/sales/checks-hourly`

**Description:** Транзакционная нагрузка по часам — закрытые чеки, позиции, гости, средний чек.
Создан для калибровки штата в TCO: выручка скрывает нагрузку (банкет на 200 000 ₸ — это один чек
и одна касса, а 200 000 ₸ розницы — очередь). Данные — из заголовков чеков (`receipt`).

**Query Parameters:**
- `department_id` (**required**): UUID подразделения
- `from_date` (**required**): начало периода (YYYY-MM-DD, включительно)
- `to_date` (**required**): конец периода (YYYY-MM-DD, включительно). Макс. диапазон — 31 день

**Семантика:**
- `hour` — 0–23 в зоне **Asia/Almaty** (час закрытия `CloseTime`, хранится локально — тот же
  источник, что и `sales_by_hour`). Чек попадает в час закрытия на своём учётном дне (`open_date`).
- `items_count` — число позиций (строк чека, `receipt.items_count`), не сумма количеств.
- `guests_count` — сумма гостей по чекам часа; `null`, если ни один чек часа не нёс данных о гостях.
- `avg_check` — `AVG(total_sum)` в ₸; `null` при отсутствии чеков.
- Часы без закрытых чеков **пропускаются** (без нулевого заполнения).

**Example Request:**
```bash
curl -H "Authorization: Bearer $API_TOKEN" \
  "https://aqniet.site/api/sales/checks-hourly?department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a&from_date=2026-06-09&to_date=2026-06-09"
```

**Response:**
```json
[
  {
    "date": "2026-06-09",
    "hour": 13,
    "checks_count": 47,
    "items_count": 132,
    "guests_count": 81,
    "avg_check": 4830.5
  }
]
```

**Errors:**
- `400` — `department_id` не UUID; `to_date < from_date`; диапазон > 31 дня
- `422` — отсутствует обязательный query-параметр

> **Связанный эндпоинт:** разбивку позиций по часам **в разрезе категорий** (загрузка цехов)
> отдаёт `GET /api/labor-demand/{department_id}/category-load-hourly` — см. `API_DOCUMENTATION_LABOR_DEMAND.md` §4.

### 3. Get Sales Statistics
**Endpoint:** `GET /api/sales/stats`

**Description:** Get aggregated sales statistics.

**Query Parameters:**
- `department_id` (optional): UUID of specific department
- `from_date` (optional): Start date (YYYY-MM-DD)
- `to_date` (optional): End date (YYYY-MM-DD)

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/sales/stats?from_date=2025-01-01&to_date=2025-01-31"
```

### 4. Sync Sales Data from iiko API
**Endpoint:** `POST /api/sales/sync`

**Description:** Manually trigger sales data synchronization from iiko API.

**Query Parameters:**
- `from_date` (optional): Start date for sync (default: yesterday)
- `to_date` (optional): End date for sync (default: same as from_date)

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/sales/sync?from_date=2025-01-01&to_date=2025-01-31"
```

**Response:**
```json
{
  "status": "success",
  "message": "Sync completed successfully",
  "from_date": "2025-01-01",
  "to_date": "2025-01-31",
  "summary_records": 450,
  "hourly_records": 10800,
  "total_raw_records": 11250
}
```

---

## Forecast Endpoints

### 5. Get Batch Forecasts for Date Range
**Endpoint:** `GET /api/forecast/batch`

**Description:** Прогноз продаж по дням × подразделениям. Используется per-segment LightGBM (с fallback на global). `predicted_sales` будет `null`, если для подразделения недостаточно истории, чтобы посчитать признаки.

**Query Parameters:**
- `from_date` (required): Start date in ISO format (YYYY-MM-DD)
- `to_date` (required): End date in ISO format (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department. Если не указан — отдаются ВСЕ активные подразделения. **DEPARTMENT-подразделения без продаж за последние 30 дней автоматически исключаются.** Чтобы получить архивную точку — передайте её UUID явно.

**Example Requests:**
```bash
# Get forecasts for all active branches for a week
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10"

# Get forecasts for specific branch for a week
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=2026-05-04&to_date=2026-05-10&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

**Response:**
```json
[
  {
    "date": "2026-05-04",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": 125000.50
  },
  {
    "date": "2026-05-05",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": null
  }
]
```

**Errors:**
- `404 Not Found` — `No departments found` (фильтр не вернул ни одного подразделения)

### 6. Get Batch Forecasts with Post-processing
**Endpoint:** `GET /api/forecast/batch_with_postprocessing`

**Description:** Get forecasts with advanced post-processing applied (smoothing, anomaly detection, confidence intervals).

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department
- `apply_postprocessing` (optional, default=true): Whether to apply post-processing

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/batch_with_postprocessing?from_date=2025-07-01&to_date=2025-07-07&apply_postprocessing=true"
```

**Response:**
```json
[
  {
    "date": "2025-07-01",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": 125000.50,
    "raw_prediction": 125000.50,
    "processed_prediction": 123500.25,
    "adjustments_applied": ["smoothing", "weekend_adjustment"],
    "confidence_interval": {
      "lower": 117825.23,
      "upper": 129175.27
    },
    "anomaly_score": 0.85,
    "is_anomaly": false,
    "business_flags": ["weekend", "end_of_month"]
  }
]
```

### 7. Compare Forecasts with Actual Sales
**Endpoint:** `GET /api/forecast/comparison`

**Description:** Сравнение прогноза с фактом из `sales_summary`. Возвращает только те даты × подразделения, по которым **есть факт** — т.е. это retrospective comparison, не forward-looking. **Тот же фильтр «мёртвых точек»**, что и в `/batch` (DEPARTMENT без продаж за 30 дней скрываются, если `department_id` не задан).

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-30&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

**Response:**
```json
[
  {
    "date": "2025-06-01",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": 125000.50,
    "actual_sales": 122500.00,
    "error": 2500.50,
    "error_percentage": 2.04
  }
]
```

### 8. Export Forecasts to CSV
**Endpoint:** `GET /api/forecast/export/csv`

**Description:** Export forecast data to CSV format.

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department
- `include_actual` (optional, default=false): Include actual sales in export

**Example Requests:**
```bash
# Export forecasts only
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31" -o forecast_july.csv

# Export with actual sales comparison
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-06-01&to_date=2025-06-30&include_actual=true" -o comparison_june.csv
```

**Response:** CSV file download

---

## Post-processing Endpoints

### 9. Apply Post-processing to Single Forecast
**Endpoint:** `POST /api/forecast/postprocess`

**Description:** Apply advanced post-processing to a raw forecast value.

**⚠️ Параметры передаются как query string, НЕ в JSON body.**

**Query Parameters:**
- `branch_id` (required): UUID подразделения
- `forecast_date` (required): дата прогноза (YYYY-MM-DD)
- `raw_prediction` (required): сырое значение прогноза (float, тенге)
- `apply_smoothing` (optional, default=true)
- `apply_business_rules` (optional, default=true)
- `apply_anomaly_detection` (optional, default=true)
- `calculate_confidence` (optional, default=true)

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/forecast/postprocess?branch_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a&forecast_date=2026-05-04&raw_prediction=125000.50"
```

**Response:**
```json
{
  "status": "success",
  "result": {
    "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "forecast_date": "2025-07-01",
    "raw_prediction": 125000.50,
    "processed_prediction": 123500.25,
    "adjustments_applied": ["smoothing", "weekend_adjustment"],
    "confidence_interval": {
      "lower": 117825.23,
      "upper": 129175.27
    },
    "anomaly_score": 0.85,
    "is_anomaly": false,
    "business_flags": ["weekend"]
  }
}
```

### 10. Batch Post-processing
**Endpoint:** `POST /api/forecast/postprocess/batch`

**Description:** Apply post-processing to multiple forecasts at once.

**⚠️ Body — это плоский JSON-массив прогнозов. Опции передаются как query string.**

**Query Parameters (опции):**
- `apply_smoothing` (default=true)
- `apply_business_rules` (default=true)
- `apply_anomaly_detection` (default=true)
- `calculate_confidence` (default=true)

**Request Body** (`List[Dict[str, Any]]`):
```json
[
  {
    "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "forecast_date": "2026-05-04",
    "prediction": 125000.50
  },
  {
    "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "forecast_date": "2026-05-05",
    "prediction": 132000.75
  }
]
```

**Example:**
```bash
curl -X POST "https://aqniet.site/api/forecast/postprocess/batch?apply_smoothing=true&calculate_confidence=true" \
  -H "Content-Type: application/json" \
  -d '[{"branch_id":"0d30c200-...","forecast_date":"2026-05-04","prediction":125000.50}]'
```

**Response:**
```json
{
  "status": "success",
  "processed_count": 2,
  "results": [ /* per-forecast processed objects */ ]
}
```

### 11. Get Postprocessing Settings
**Endpoint:** `GET /api/forecast/postprocessing/settings`

**Description:** Get current active postprocessing settings.

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/postprocessing/settings"
```

### 11a. Test Temporal Smoothing
**Endpoint:** `POST /api/forecast/test_smoothing`

**Description:** Прогоняет прогноз для одной даты × точки и применяет temporal smoothing (±50% от среднего по дню недели за 4 недели). Используется для отладки настроек сглаживания. Возвращает raw + smoothed prediction + историю последних 10 дней.

**⚠️ `branch_id` и `forecast_date` — query params; параметры сглаживания — JSON body (опционально).**

**Query Parameters:**
- `branch_id` (required): UUID подразделения
- `forecast_date` (required): дата прогноза (YYYY-MM-DD)

**Request Body** (`TemporalSmoothingRequest`, опционально):
```json
{
  "max_change_threshold": 0.5,
  "lookback_weeks": 4,
  "enable_smoothing": true
}
```

**Example:**
```bash
curl -X POST "https://aqniet.site/api/forecast/test_smoothing?branch_id=0d30c200-...&forecast_date=2026-05-04" \
  -H "Content-Type: application/json" \
  -d '{"max_change_threshold": 0.3}'
```

**Response:**
```json
{
  "status": "success",
  "branch_id": "0d30c200-...",
  "forecast_date": "2026-05-04",
  "raw_prediction": 132500.00,
  "smoothed_prediction": 121300.00,
  "smoothing_applied": true,
  "change_percent": -8.45,
  "parameters": {"max_change_threshold": 0.3, "threshold_percent": "30.0%"},
  "historical_context": [
    {"date": "2026-04-27", "sales": 119500.00},
    {"date": "2026-04-20", "sales": 122100.00}
  ]
}
```

---

### 12. Save Postprocessing Settings
**Endpoint:** `POST /api/forecast/postprocessing/settings`

**Description:** Save new postprocessing settings.

**Request Body:**
```json
{
  "enable_smoothing": true,
  "max_change_percent": 50.0,
  "enable_business_rules": true,
  "enable_weekend_adjustment": true,
  "enable_holiday_adjustment": true,
  "enable_anomaly_detection": true,
  "anomaly_threshold": 3.0,
  "enable_confidence": true,
  "confidence_level": 0.95
}
```

---

## Model Management Endpoints

### 13. Retrain Model
**Endpoint:** `POST /api/forecast/retrain`

**Description:** Retrain the sales forecasting model with latest data.

**Request Body (optional):**
```json
{
  "handle_outliers": true,
  "outlier_method": "winsorize",
  "days": 365
}
```

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/forecast/retrain" \
  -H "Content-Type: application/json" \
  -d '{"handle_outliers": true, "days": 365}'
```

**Response:**
```json
{
  "status": "success",
  "message": "Model retrained successfully",
  "metrics": {
    "test_mape": 6.18,
    "validation_mape": 7.62,
    "r2_score": 0.9954
  },
  "timestamp": "2025-07-01T10:30:00"
}
```

### 13a. Retrain Per-Segment Models
**Endpoint:** `POST /api/forecast/retrain-segmented`

**Description:** Тренирует отдельный LightGBM-агент на каждый `segment_type` подразделения (mall food court, street, в офисе и т.п.). Глобальная модель остаётся работать как fallback для подразделений с unknown сегментом или недостаточным числом сэмплов в сегменте.

Файлы моделей складываются в `models/segments/<segment>.pkl`.

**Request Body** (опционально, тот же формат, что и у `/retrain`):
```json
{
  "handle_outliers": true,
  "outlier_method": "winsorize",
  "days": 365
}
```

**Example:**
```bash
curl -X POST "https://aqniet.site/api/forecast/retrain-segmented" \
  -H "Content-Type: application/json" \
  -d '{"days": 365}'
```

**Response:**
```json
{
  "status": "success",
  "message": "Trained 4 per-segment models",
  "per_segment_metrics": {
    "mall_food_court": {"test_mape": 5.92, "r2_score": 0.997, "samples": 2103},
    "street":          {"test_mape": 6.41, "r2_score": 0.994, "samples": 1840}
  },
  "timestamp": "2026-05-03T10:30:00"
}
```

---

### 14. Get Model Information
**Endpoint:** `GET /api/forecast/model/info`

**Description:** Get current model status, version, and performance metrics.

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/model/info"
```

**Response:**
```json
{
  "model_exists": true,
  "model_type": "LightGBM v2.3",
  "features_count": 64,
  "training_date": "2025-06-30T06:15:23",
  "training_samples": 7491,
  "important_features": [
    {"feature": "sales_momentum_7d", "importance": 15.2},
    {"feature": "lag_2d_sales", "importance": 12.8},
    {"feature": "rolling_3d_avg_sales", "importance": 11.5}
  ],
  "training_metrics": {
    "test_mape": 6.18,
    "validation_mape": 7.62,
    "r2_score": 0.9954,
    "mae": 12500.35
  }
}
```

### 15. Optimize Hyperparameters
**Endpoint:** `POST /api/forecast/optimize`

**Description:** Optimize model hyperparameters using Optuna.

**Request Body (optional):**
```json
{
  "n_trials": 50,
  "timeout": 1800,
  "cv_folds": 3,
  "days": 365
}
```

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/forecast/optimize" \
  -H "Content-Type: application/json" \
  -d '{"n_trials": 50, "timeout": 1800}'
```

### 16. Compare Models
**Endpoint:** `POST /api/forecast/compare_models`

**Description:** Compare LightGBM, XGBoost, and CatBoost models.

**Request Body (optional):**
```json
{
  "days": 365
}
```

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/forecast/compare_models" \
  -H "Content-Type: application/json" \
  -d '{"days": 365}'
```

---

## Error Analysis Endpoints

### 17. Analyze Errors by Segment
**Endpoint:** `GET /api/forecast/error-analysis/errors_by_segment`

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `segment_type` (required): One of: "department", "day_of_week", "month", "location"

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/error-analysis/errors_by_segment?from_date=2025-06-01&to_date=2025-06-30&segment_type=department"
```

### 18. Identify Problematic Branches
**Endpoint:** `GET /api/forecast/error-analysis/problematic_branches`

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `min_samples` (optional, default=5): Minimum predictions required
- `mape_threshold` (optional, default=15.0): MAPE threshold for problematic

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/error-analysis/problematic_branches?from_date=2025-06-01&to_date=2025-06-30&mape_threshold=10.0"
```

### 19. Analyze Temporal Errors
**Endpoint:** `GET /api/forecast/error-analysis/temporal_errors`

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/error-analysis/temporal_errors?from_date=2025-06-01&to_date=2025-06-30"
```

### 20. Get Error Distribution
**Endpoint:** `GET /api/forecast/error-analysis/error_distribution`

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/error-analysis/error_distribution?from_date=2025-06-01&to_date=2025-06-30"
```

---

## Model Monitoring Endpoints

### 21. Get Model Health
**Endpoint:** `GET /api/monitoring/health`

**Description:** Get comprehensive model health status.

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/monitoring/health"
```

**Response:**
```json
{
  "overall_status": "healthy",
  "model_exists": true,
  "model_age_days": 7,
  "recent_performance": {
    "mape_7d": 6.5,
    "mape_30d": 7.2
  },
  "data_quality": {
    "missing_data_days": 0,
    "last_sync": "2025-07-01T02:00:00"
  },
  "alerts": []
}
```

### 22. Get Performance Summary
**Endpoint:** `GET /api/monitoring/performance/summary`

**Query Parameters:**
- `days` (optional, default=30, range=1-365): Number of days to analyze

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/monitoring/performance/summary?days=30"
```

**Response:**
```json
{
  "period_days": 30,
  "average_mape": 7.2,
  "average_mae": 12500.35,
  "predictions_count": 450,
  "time_series": [
    {
      "date": "2025-06-01",
      "mape": 6.8,
      "mae": 12000.50
    }
  ]
}
```

### 23. Calculate Daily Metrics
**Endpoint:** `POST /api/monitoring/performance/calculate-daily`

**Description:** Calculate and store daily performance metrics.

**Query Parameters:**
- `target_date` (optional): Date to calculate metrics for (default: yesterday)

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/monitoring/performance/calculate-daily?target_date=2025-06-30"
```

### 24. Get Retrain Status
**Endpoint:** `GET /api/monitoring/retrain/status`

**Description:** Get status of automatic retraining schedule.

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/monitoring/retrain/status"
```

### 25. Manual Model Retraining
**Endpoint:** `POST /api/monitoring/retrain/manual`

**Description:** Manually trigger model retraining.

**Request Body:**
```json
{
  "reason": "Manual retraining for accuracy improvement",
  "performance_threshold": 10.0,
  "force_deploy": false
}
```

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/monitoring/retrain/manual" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Manual retraining",
    "performance_threshold": 10.0,
    "force_deploy": false
  }'
```

### 26. Get Recent Alerts
**Endpoint:** `GET /api/monitoring/alerts/recent`

**Query Parameters:**
- `days` (optional, default=7): Number of days to look back

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/monitoring/alerts/recent?days=7"
```

---

## API Key Management Endpoints

### 27. Create API Key
**Endpoint:** `POST /api/auth/keys`

**Description:** Create a new API key for external access.

**Request Body:**
```json
{
  "name": "My App Integration",
  "description": "API key for mobile app integration",
  "expires_in_days": 365,
  "rate_limit_per_minute": 100,
  "rate_limit_per_hour": 1000,
  "rate_limit_per_day": 10000,
  "created_by": "admin@example.com"
}
```

**Response:**
```json
{
  "key_id": "dGVzdF9rZXlfZXhhbXBsZQ",
  "api_key": "sf_dGVzdF9rZXlfZXhhbXBsZQ_YWN0dWFsX3NlY3JldF9rZXk",
  "name": "My App Integration",
  "expires_at": "2026-06-30T12:00:00",
  "rate_limits": {
    "per_minute": 100,
    "per_hour": 1000,
    "per_day": 10000
  }
}
```

⚠️ **Important:** The full API key is shown only once and cannot be retrieved again!

### 28. List API Keys
**Endpoint:** `GET /api/auth/keys`

**Query Parameters:**
- `include_inactive` (optional, default=false): Include inactive keys

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/auth/keys"
```

### 29. Get API Key Details
**Endpoint:** `GET /api/auth/keys/{key_id}`

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/auth/keys/dGVzdF9rZXlfZXhhbXBsZQ"
```

### 30. Get API Key Usage Stats
**Endpoint:** `GET /api/auth/keys/{key_id}/usage`

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/auth/keys/dGVzdF9rZXlfZXhhbXBsZQ/usage"
```

**Response:**
```json
{
  "key_id": "dGVzdF9rZXlfZXhhbXBsZQ",
  "name": "My App Integration",
  "total_requests": 15420,
  "requests_last_hour": 85,
  "requests_last_day": 1250,
  "last_used_at": "2025-07-01T10:30:00",
  "rate_limit_status": {
    "requests_last_minute": 5,
    "minute_limit": 100,
    "minute_remaining": 95,
    "requests_last_hour": 85,
    "hour_limit": 1000,
    "hour_remaining": 915,
    "requests_last_day": 1250,
    "day_limit": 10000,
    "day_remaining": 8750
  }
}
```

### 31. Deactivate API Key
**Endpoint:** `DELETE /api/auth/keys/{key_id}`

**Example Request:**
```bash
curl -X DELETE "https://aqniet.site/api/auth/keys/dGVzdF9rZXlfZXhhbXBsZQ"
```

### 32. Activate API Key
**Endpoint:** `POST /api/auth/keys/{key_id}/activate`

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/auth/keys/dGVzdF9rZXlfZXhhbXBsZQ/activate"
```

### 33. Test API Key
**Endpoint:** `POST /api/auth/test`

**Example:**
```bash
curl -X POST "https://aqniet.site/api/auth/test" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

**Response:**
```json
{
  "message": "API key authentication successful",
  "key_name": "My App Integration",
  "key_id": "dGVzdF9rZXlfZXhhbXBsZQ"
}
```

---

## Integration Examples

### Python Example
```python
import requests
from datetime import date, timedelta

# Base URL
BASE_URL = "https://aqniet.site/api"
API_KEY = "sf_your_key_id_your_secret"

# Headers with authentication
headers = {
    "Authorization": f"Bearer {API_KEY}"
}

# Example 1: Get sales data for a department
department_id = "0d30c200-87b5-45a5-89f0-eb76e2892b4a"
response = requests.get(
    f"{BASE_URL}/sales/summary",
    params={
        "department_id": department_id,
        "from_date": "2025-01-01",
        "to_date": "2025-01-31"
    },
    headers=headers
)
sales_data = response.json()
print(f"Found {len(sales_data)} sales records")

# Example 2: Get forecast for next 7 days
start_date = date.today()
end_date = start_date + timedelta(days=7)

response = requests.get(
    f"{BASE_URL}/forecast/batch",
    params={
        "from_date": start_date.isoformat(),
        "to_date": end_date.isoformat(),
        "department_id": department_id
    },
    headers=headers
)

forecasts = response.json()
for forecast in forecasts:
    print(f"{forecast['date']}: {forecast['predicted_sales']:,.2f} тенге")
```

### JavaScript Example
```javascript
const BASE_URL = 'https://aqniet.site/api';
const API_KEY = 'sf_your_key_id_your_secret';

// Example 1: Get sales data
async function getSalesData(departmentId, fromDate, toDate) {
    const params = new URLSearchParams({
        department_id: departmentId,
        from_date: fromDate,
        to_date: toDate
    });

    const response = await fetch(`${BASE_URL}/sales/summary?${params}`, {
        headers: {
            'Authorization': `Bearer ${API_KEY}`
        }
    });

    const salesData = await response.json();
    return salesData;
}

// Example 2: Get forecast with post-processing
async function getForecastWithPostProcessing(fromDate, toDate, branchId) {
    const params = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        department_id: branchId,
        apply_postprocessing: true
    });

    const response = await fetch(`${BASE_URL}/forecast/batch_with_postprocessing?${params}`, {
        headers: {
            'Authorization': `Bearer ${API_KEY}`
        }
    });

    const forecasts = await response.json();
    return forecasts;
}

// Usage
getSalesData('0d30c200-87b5-45a5-89f0-eb76e2892b4a', '2025-01-01', '2025-01-31')
    .then(data => console.log(`Retrieved ${data.length} sales records`));

getForecastWithPostProcessing('2025-07-01', '2025-07-07', '0d30c200-87b5-45a5-89f0-eb76e2892b4a')
    .then(forecasts => {
        forecasts.forEach(f => {
            console.log(`${f.date}: ${f.processed_prediction} (${f.confidence_interval.lower} - ${f.confidence_interval.upper})`);
        });
    });
```

### cURL Examples for Common Use Cases

#### Get today's sales for all branches
```bash
TODAY=$(date +%Y-%m-%d)
curl -X GET "https://aqniet.site/api/sales/summary?from_date=$TODAY&to_date=$TODAY" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

#### Get tomorrow's forecast for all branches
```bash
TOMORROW=$(date -d "tomorrow" +%Y-%m-%d)
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=$TOMORROW&to_date=$TOMORROW" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

#### Get weekly forecast for specific branch with post-processing
```bash
curl -X GET "https://aqniet.site/api/forecast/batch_with_postprocessing?from_date=2025-07-01&to_date=2025-07-07&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a" \
  -H "Authorization: Bearer sf_your_key_id_your_secret"
```

#### Export monthly forecast to CSV
```bash
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31" \
  -H "Authorization: Bearer sf_your_key_id_your_secret" \
  -o july_forecast.csv
```

---

## Error Handling

All endpoints return standard HTTP status codes:
- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters or request data
- `401 Unauthorized`: Missing or invalid API key
- `404 Not Found`: Resource not found
- `429 Too Many Requests`: Rate limit exceeded
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Rate Limiting

Rate limits are configured per API key:
- Default: 100 requests/minute, 1000 requests/hour, 10000 requests/day
- Rate limit information is returned in response headers
- Exceeding rate limits results in 429 status code

Check your current rate limit status using the `/api/auth/keys/{key_id}/usage` endpoint.

---

## Important Notes

1. **Date Format**: All dates must be in ISO format (YYYY-MM-DD)
2. **Department/Branch IDs**: Use UUID format (e.g., "0d30c200-87b5-45a5-89f0-eb76e2892b4a")
3. **Currency**: All sales amounts are in Kazakhstani Tenge (KZT)
4. **Timezone**: All timestamps are in UTC
5. **Automatic Sync**: Sales data is automatically loaded daily at 02:00 AM
6. **Model Retraining**: The ML model is automatically retrained weekly on Sundays at 3:00 AM
7. **Pagination**: Use `skip` and `limit` parameters for large datasets
8. **Authentication**: Production environment requires API keys for all endpoints

---

## Automated Schedules

The system runs the following automated tasks:

- **Daily Sales Sync**: 02:00 AM - Automatically loads sales data from iiko API
- **Weekly Model Retraining**: Sundays at 03:00 AM - Retrains ML model with latest data
- **Daily Metrics Calculation**: 04:00 AM - Calculates performance metrics for monitoring

---

## Support

For API support, issues, or feature requests:
- GitHub: https://github.com/Rus9136/sales_forecast
- Documentation: See CLAUDE.md in the repository

**Документ актуализирован:** 2026-05-03 (синхронизирован с `app/routers/forecast/` — добавлены `/retrain-segmented`, `/test_smoothing`; исправлены сигнатуры `/postprocess` и `/postprocess/batch` — query params вместо JSON body; задокументирован фильтр неактивных подразделений на `/batch` и `/comparison`).

---

## Testing Plan

### Authentication Tests

#### Development Mode (DEBUG=True)
```bash
# Test without authentication - should work
curl -X GET "http://localhost:8002/api/forecast/model/info"
# Expected: 200 OK with model information
```

#### Production Mode (DEBUG=False)
```bash
# Test without authentication - should fail
curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03"
# Expected: 401 Unauthorized {"detail": "API key required"}
```

### API Key Management Tests

#### Create API Key
```bash
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Integration Key",
    "description": "Testing API key functionality",
    "expires_in_days": 30,
    "rate_limit_per_minute": 50
  }'
# Expected: 200 OK with API key response
```

#### Test API Key Authentication
```bash
API_KEY="sf_your_key_id_from_test"

curl -X POST "http://localhost:8002/api/auth/test" \
  -H "Authorization: Bearer $API_KEY"
# Expected: 200 OK with authentication confirmation
```

### Rate Limiting Tests

#### Normal Usage Within Limits
```bash
for i in {1..10}; do
  curl -X GET "http://localhost:8002/api/forecast/model/info" \
    -H "Authorization: Bearer $API_KEY" \
    -w "Request $i: %{http_code}\n"
done
# Expected: All requests return 200 OK
```

### Security Tests

#### Invalid API Key Format
```bash
curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03" \
  -H "Authorization: Bearer invalid_key_format"
# Expected: 401 Unauthorized "Invalid API key format"
```

### Database Verification

```bash
# Check API Key Storage
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c \
  "SELECT key_id, name, is_active, created_at FROM api_keys;"

# Check Usage Logging
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c \
  "SELECT key_id, endpoint, timestamp FROM api_key_usage ORDER BY timestamp DESC LIMIT 10;"
```

### Test Results Checklist

After running all tests, verify:
- [ ] API key creation works correctly
- [ ] Authentication is enforced in production mode
- [ ] Rate limiting functions properly
- [ ] Usage statistics are tracked accurately
- [ ] All forecast endpoints work with authentication
- [ ] Error handling is appropriate for various scenarios
