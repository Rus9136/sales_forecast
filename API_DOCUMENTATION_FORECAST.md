# API Documentation - Sales Forecast Endpoints

## Base URL
```
https://aqniet.site/api/forecast
```

## Authentication
Currently, the API does not require authentication. In production, you should implement proper authentication mechanisms.

## Main Forecast Endpoints

### 1. Get Single Day Forecast for a Branch
**Endpoint:** `GET /api/forecast/{date}/{branch_id}`

**Description:** Get sales forecast for a specific branch on a specific date.

**Parameters:**
- `date` (path, required): Date in ISO format (YYYY-MM-DD)
- `branch_id` (path, required): UUID of the branch/department

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/2025-07-01/0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

**Response:**
```json
{
  "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
  "date": "2025-07-01",
  "predicted_sales": 125000.50
}
```

### 2. Get Batch Forecasts for Date Range
**Endpoint:** `GET /api/forecast/batch`

**Description:** Get forecasts for multiple dates and optionally filter by department.

**Query Parameters:**
- `from_date` (required): Start date in ISO format (YYYY-MM-DD)
- `to_date` (required): End date in ISO format (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department to filter

**Example Request:**
```bash
# Get forecasts for all branches for a week
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07"

# Get forecasts for specific branch for a week
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

**Response:**
```json
[
  {
    "date": "2025-07-01",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": 125000.50
  },
  {
    "date": "2025-07-02",
    "department_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "department_name": "Мадлен Plaza",
    "predicted_sales": 132000.75
  }
  // ... more records
]
```

### 3. Get Batch Forecasts with Post-processing
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
  // ... more records
]
```

### 4. Compare Forecasts with Actual Sales
**Endpoint:** `GET /api/forecast/comparison`

**Description:** Compare forecasted values with actual sales to analyze model performance.

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
  // ... more records
]
```

### 5. Export Forecasts to CSV
**Endpoint:** `GET /api/forecast/export/csv`

**Description:** Export forecast data to CSV format.

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `department_id` (optional): UUID of specific department
- `include_actual` (optional, default=false): Include actual sales in export

**Example Request:**
```bash
# Export forecasts only
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31" -o forecast_july.csv

# Export with actual sales comparison
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-06-01&to_date=2025-06-30&include_actual=true" -o comparison_june.csv
```

**Response:** CSV file download

## Post-processing Endpoints

### 6. Apply Post-processing to Single Forecast
**Endpoint:** `POST /api/forecast/postprocess`

**Description:** Apply advanced post-processing to a raw forecast value.

**Request Body (form-data or JSON):**
```json
{
  "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
  "forecast_date": "2025-07-01",
  "raw_prediction": 125000.50,
  "apply_smoothing": true,
  "apply_business_rules": true,
  "apply_anomaly_detection": true,
  "calculate_confidence": true
}
```

**Example Request:**
```bash
curl -X POST "https://aqniet.site/api/forecast/postprocess" \
  -H "Content-Type: application/json" \
  -d '{
    "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
    "forecast_date": "2025-07-01",
    "raw_prediction": 125000.50
  }'
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

### 7. Batch Post-processing
**Endpoint:** `POST /api/forecast/postprocess/batch`

**Description:** Apply post-processing to multiple forecasts at once.

**Request Body:**
```json
{
  "forecasts": [
    {
      "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
      "forecast_date": "2025-07-01",
      "prediction": 125000.50
    },
    {
      "branch_id": "0d30c200-87b5-45a5-89f0-eb76e2892b4a",
      "forecast_date": "2025-07-02",
      "prediction": 132000.75
    }
  ],
  "apply_smoothing": true,
  "apply_business_rules": true,
  "apply_anomaly_detection": true,
  "calculate_confidence": true
}
```

## Model Information Endpoints

### 8. Get Model Information
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
  "model_type": "LightGBM v2.2",
  "features_count": 61,
  "training_date": "2025-06-30T06:15:23",
  "training_samples": 7491,
  "important_features": [
    {"feature": "sales_momentum_7d", "importance": 15.2},
    {"feature": "lag_2d_sales", "importance": 12.8},
    {"feature": "rolling_3d_avg_sales", "importance": 11.5}
  ],
  "training_metrics": {
    "test_mape": 4.92,
    "validation_mape": 7.62,
    "r2_score": 0.9954,
    "mae": 12500.35
  }
}
```

## Error Analysis Endpoints

### 9. Analyze Errors by Segment
**Endpoint:** `GET /api/forecast/error-analysis/errors_by_segment`

**Query Parameters:**
- `from_date` (required): Start date (YYYY-MM-DD)
- `to_date` (required): End date (YYYY-MM-DD)
- `segment_type` (required): One of: "department", "day_of_week", "month", "location"

**Example Request:**
```bash
curl -X GET "https://aqniet.site/api/forecast/error-analysis/errors_by_segment?from_date=2025-06-01&to_date=2025-06-30&segment_type=department"
```

### 10. Identify Problematic Branches
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

## Integration Examples

### Python Example
```python
import requests
from datetime import date, timedelta

# Base URL
BASE_URL = "https://aqniet.site/api/forecast"

# Get forecast for next 7 days for a specific branch
branch_id = "0d30c200-87b5-45a5-89f0-eb76e2892b4a"
start_date = date.today()
end_date = start_date + timedelta(days=7)

response = requests.get(
    f"{BASE_URL}/batch",
    params={
        "from_date": start_date.isoformat(),
        "to_date": end_date.isoformat(),
        "department_id": branch_id
    }
)

forecasts = response.json()
for forecast in forecasts:
    print(f"{forecast['date']}: {forecast['predicted_sales']:,.2f} тенге")
```

### JavaScript Example
```javascript
const BASE_URL = 'https://aqniet.site/api/forecast';

// Get forecast with post-processing
async function getForecastWithPostProcessing(fromDate, toDate, branchId) {
    const params = new URLSearchParams({
        from_date: fromDate,
        to_date: toDate,
        department_id: branchId,
        apply_postprocessing: true
    });
    
    const response = await fetch(`${BASE_URL}/batch_with_postprocessing?${params}`);
    const forecasts = await response.json();
    
    return forecasts;
}

// Usage
getForecastWithPostProcessing('2025-07-01', '2025-07-07', '0d30c200-87b5-45a5-89f0-eb76e2892b4a')
    .then(forecasts => {
        forecasts.forEach(f => {
            console.log(`${f.date}: ${f.processed_prediction} (${f.confidence_interval.lower} - ${f.confidence_interval.upper})`);
        });
    });
```

### cURL Examples for Common Use Cases

#### Get tomorrow's forecast for all branches
```bash
TOMORROW=$(date -d "tomorrow" +%Y-%m-%d)
curl -X GET "https://aqniet.site/api/forecast/batch?from_date=$TOMORROW&to_date=$TOMORROW"
```

#### Get weekly forecast for specific branch with post-processing
```bash
curl -X GET "https://aqniet.site/api/forecast/batch_with_postprocessing?from_date=2025-07-01&to_date=2025-07-07&department_id=0d30c200-87b5-45a5-89f0-eb76e2892b4a"
```

#### Export monthly forecast to CSV
```bash
curl -X GET "https://aqniet.site/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-31" -o july_forecast.csv
```

## Error Handling

All endpoints return standard HTTP status codes:
- `200 OK`: Successful request
- `400 Bad Request`: Invalid parameters or request data
- `404 Not Found`: Resource not found
- `500 Internal Server Error`: Server error

Error response format:
```json
{
  "detail": "Error message describing what went wrong"
}
```

## Rate Limiting
Currently no rate limiting is implemented. In production, consider implementing rate limits to prevent abuse.

## Notes
1. All dates should be in ISO format (YYYY-MM-DD)
2. Branch/Department IDs are UUIDs
3. Sales amounts are in Kazakhstani Tenge (KZT)
4. The model is retrained weekly on Sundays at 3:00 AM
5. Post-processing includes smoothing, anomaly detection, and business rule adjustments