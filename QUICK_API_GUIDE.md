# Quick API Guide - Sales Forecast

## 🚀 Quick Start

**Base URL:** `https://aqniet.site/api/forecast`

## 📊 Main Endpoints

### 1. Get Forecast for Date Range
```bash
GET /batch?from_date=2025-07-01&to_date=2025-07-07&department_id=BRANCH_UUID
```

**Example:**
```bash
curl "https://aqniet.site/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07"
```

**Response:**
```json
[
  {
    "date": "2025-07-01",
    "department_id": "uuid",
    "department_name": "Branch Name",
    "predicted_sales": 125000.50
  }
]
```

### 2. Get Enhanced Forecast (with confidence intervals)
```bash
GET /batch_with_postprocessing?from_date=2025-07-01&to_date=2025-07-07
```

**Response includes:**
- `processed_prediction` - Adjusted forecast
- `confidence_interval` - 95% confidence bounds
- `adjustments_applied` - What corrections were made
- `is_anomaly` - Anomaly detection flag

### 3. Compare Forecast vs Actual
```bash
GET /comparison?from_date=2025-06-01&to_date=2025-06-30
```

**Response:**
```json
[
  {
    "date": "2025-06-01",
    "department_name": "Branch Name",
    "predicted_sales": 125000.50,
    "actual_sales": 122500.00,
    "error": 2500.50,
    "error_percentage": 2.04
  }
]
```

### 4. Export to CSV
```bash
GET /export/csv?from_date=2025-07-01&to_date=2025-07-31&include_actual=true
```

### 5. Model Information
```bash
GET /model/info
```

**Response:**
```json
{
  "model_type": "LGBMRegressor",
  "n_features": 61,
  "training_metrics": {
    "test_mape": 8.65,
    "test_r2": 0.9954
  }
}
```

## 🔧 Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `from_date` | string | Yes | Start date (YYYY-MM-DD) |
| `to_date` | string | Yes | End date (YYYY-MM-DD) |
| `department_id` | string | No | Branch UUID (optional filter) |
| `apply_postprocessing` | boolean | No | Enable advanced processing |
| `include_actual` | boolean | No | Include actual sales for comparison |

## 💡 Quick Examples

### Python
```python
import requests

# Get 7-day forecast
response = requests.get(
    "https://aqniet.site/api/forecast/batch",
    params={
        "from_date": "2025-07-01",
        "to_date": "2025-07-07"
    }
)
forecasts = response.json()
```

### JavaScript
```javascript
const response = await fetch(
    'https://aqniet.site/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07'
);
const forecasts = await response.json();
```

### cURL
```bash
# Get tomorrow's forecast for all branches
TOMORROW=$(date -d "tomorrow" +%Y-%m-%d)
curl "https://aqniet.site/api/forecast/batch?from_date=$TOMORROW&to_date=$TOMORROW"
```

## 📈 Model Performance
- **Accuracy:** 8.65% MAPE (Mean Absolute Percentage Error)
- **Features:** 61 engineered features including momentum, lags, seasonality
- **Update:** Automatically retrained weekly
- **Coverage:** All restaurant branches in the system

## 🔍 Available Branches
To get list of available branches:
```bash
curl "https://aqniet.site/api/departments/?limit=10"
```

## ⚡ Response Times
- Single forecast: ~100ms
- Batch forecast (7 days): ~500ms
- Monthly export: ~2-3 seconds

## 🚨 Error Handling
- `400` - Invalid date format or parameters
- `404` - Branch not found
- `500` - Server error

```json
{
  "detail": "Error message"
}
```

## 📞 Support
For technical issues or questions about the API, please refer to the full documentation or contact the development team.