# API Testing Plan - Authentication System

## 🧪 Comprehensive Test Plan

После успешного деплоя системы аутентификации, выполните следующие тесты:

## 1. 🔐 Authentication Tests

### Test 1.1: Development Mode (DEBUG=True)
```bash
# Test without authentication - should work
curl -X GET "http://localhost:8002/api/forecast/model/info"

# Expected: 200 OK with model information
```

### Test 1.2: Production Mode (DEBUG=False) 
```bash
# Test without authentication - should fail
curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03"

# Expected: 401 Unauthorized {"detail": "API key required"}
```

## 2. 🔑 API Key Management Tests

### Test 2.1: Create API Key
```bash
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Integration Key",
    "description": "Testing API key functionality",
    "expires_in_days": 30,
    "rate_limit_per_minute": 50,
    "rate_limit_per_hour": 500,
    "rate_limit_per_day": 5000
  }'

# Expected: 200 OK with API key response
# Save the returned "api_key" value for subsequent tests
```

### Test 2.2: List API Keys
```bash
curl -X GET "http://localhost:8002/api/auth/keys"

# Expected: 200 OK with array of API keys (without secret values)
```

### Test 2.3: Test API Key Authentication
```bash
# Use the API key from Test 2.1
API_KEY="sf_your_key_id_from_test_2.1"

curl -X POST "http://localhost:8002/api/auth/test" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK with authentication confirmation
```

## 3. 📊 Forecast API Tests with Authentication

### Test 3.1: Batch Forecasts with API Key
```bash
API_KEY="sf_your_key_id_from_test_2.1"

curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK with forecast data
```

### Test 3.2: Post-processed Forecasts
```bash
curl -X GET "http://localhost:8002/api/forecast/batch_with_postprocessing?from_date=2025-07-01&to_date=2025-07-03" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK with enhanced forecast data including confidence intervals
```

### Test 3.3: Forecast Comparison
```bash
curl -X GET "http://localhost:8002/api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-05" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK with comparison data (if historical data exists)
```

### Test 3.4: CSV Export
```bash
curl -X GET "http://localhost:8002/api/forecast/export/csv?from_date=2025-07-01&to_date=2025-07-07" \
  -H "Authorization: Bearer $API_KEY" \
  -o test_forecast.csv

# Expected: CSV file downloaded successfully
# Verify: file test_forecast.csv has forecast data
```

## 4. 🚦 Rate Limiting Tests

### Test 4.1: Normal Usage Within Limits
```bash
# Make 10 requests quickly (should all succeed)
for i in {1..10}; do
  curl -X GET "http://localhost:8002/api/forecast/model/info" \
    -H "Authorization: Bearer $API_KEY" \
    -w "Request $i: %{http_code}\n"
done

# Expected: All requests return 200 OK
```

### Test 4.2: Rate Limit Exceeded (if limits are low)
```bash
# Make many requests quickly to trigger rate limit
for i in {1..120}; do
  curl -X GET "http://localhost:8002/api/forecast/model/info" \
    -H "Authorization: Bearer $API_KEY" \
    -w "Request $i: %{http_code}\n" \
    -s -o /dev/null
done

# Expected: Some requests return 429 Too Many Requests
```

### Test 4.3: Check Usage Statistics
```bash
# Get the key_id from your API key (part between sf_ and second _)
KEY_ID="your_key_id_here"

curl -X GET "http://localhost:8002/api/auth/keys/$KEY_ID/usage" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK with usage statistics showing recent requests
```

## 5. 🔒 Security Tests

### Test 5.1: Invalid API Key Format
```bash
curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03" \
  -H "Authorization: Bearer invalid_key_format"

# Expected: 401 Unauthorized "Invalid API key format"
```

### Test 5.2: Non-existent API Key
```bash
curl -X GET "http://localhost:8002/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-03" \
  -H "Authorization: Bearer sf_nonexistent_key_fake_secret"

# Expected: 401 Unauthorized "Invalid API key"
```

### Test 5.3: Deactivated API Key
```bash
# First deactivate the key
curl -X DELETE "http://localhost:8002/api/auth/keys/$KEY_ID"

# Then try to use it
curl -X GET "http://localhost:8002/api/forecast/model/info" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 401 Unauthorized "Invalid API key"
```

### Test 5.4: Reactivate API Key
```bash
# Reactivate the key
curl -X POST "http://localhost:8002/api/auth/keys/$KEY_ID/activate"

# Then try to use it again
curl -X GET "http://localhost:8002/api/forecast/model/info" \
  -H "Authorization: Bearer $API_KEY"

# Expected: 200 OK (key should work again)
```

## 6. 🐍 Python Client Integration Test

```python
# Save this as test_python_client.py
import sys
sys.path.append('.')
from integration_example import SalesForecastClient
from datetime import date, timedelta

def test_python_integration():
    # Replace with your actual API key
    api_key = "sf_your_key_id_your_secret"
    
    client = SalesForecastClient(
        base_url="http://localhost:8002/api/forecast",
        api_key=api_key
    )
    
    # Test authentication
    print("1. Testing authentication...")
    auth_result = client.test_api_key()
    print(f"   ✅ {auth_result}")
    
    # Test model info
    print("2. Getting model info...")
    model_info = client.get_model_info()
    print(f"   ✅ Model: {model_info.get('model_type', 'Unknown')}")
    
    # Test forecasts
    print("3. Getting forecasts...")
    tomorrow = date.today() + timedelta(days=1)
    week_later = tomorrow + timedelta(days=7)
    
    forecasts = client.get_batch_forecasts(tomorrow, week_later)
    print(f"   ✅ Got {len(forecasts)} forecasts")
    
    # Test post-processing
    print("4. Getting post-processed forecasts...")
    processed = client.get_forecasts_with_postprocessing(tomorrow, week_later)
    print(f"   ✅ Got {len(processed)} processed forecasts")
    
    print("\n🎉 All tests passed!")

if __name__ == "__main__":
    test_python_integration()
```

Run with: `python3 test_python_client.py`

## 7. 📈 Database Verification Tests

### Test 7.1: Check API Key Storage
```bash
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c \
  "SELECT key_id, name, is_active, created_at FROM api_keys;"

# Expected: Show created API keys without exposing secrets
```

### Test 7.2: Check Usage Logging
```bash
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c \
  "SELECT key_id, endpoint, timestamp FROM api_key_usage ORDER BY timestamp DESC LIMIT 10;"

# Expected: Show recent API usage logs
```

### Test 7.3: Check Statistics View
```bash
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c \
  "SELECT * FROM api_key_stats WHERE name = 'Test Integration Key';"

# Expected: Show aggregated statistics for the test key
```

## 8. 🔧 Configuration Tests

### Test 8.1: Environment Variable Override
```bash
# Test with DEBUG=True (should bypass auth)
DEBUG=True curl -X GET "http://localhost:8002/api/forecast/model/info"

# Expected: 200 OK without authentication
```

### Test 8.2: Rate Limit Configuration
```bash
# Create key with custom limits
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Custom Limits Key",
    "rate_limit_per_minute": 5,
    "rate_limit_per_hour": 50,
    "rate_limit_per_day": 500
  }'

# Test the custom limits with rapid requests
```

## 9. 📋 Performance Tests

### Test 9.1: Authentication Overhead
```bash
# Time requests with vs without authentication
time curl -X GET "http://localhost:8002/api/forecast/model/info"
time curl -X GET "http://localhost:8002/api/forecast/model/info" \
  -H "Authorization: Bearer $API_KEY"

# Compare response times
```

### Test 9.2: Concurrent Requests
```bash
# Test multiple simultaneous authenticated requests
for i in {1..5}; do
  curl -X GET "http://localhost:8002/api/forecast/model/info" \
    -H "Authorization: Bearer $API_KEY" &
done
wait

# Expected: All requests should complete successfully
```

## 10. 🚨 Error Handling Tests

### Test 10.1: Malformed JSON in API Key Creation
```bash
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test", invalid_json}'

# Expected: 422 Unprocessable Entity
```

### Test 10.2: Missing Required Fields
```bash
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{}'

# Expected: 422 Unprocessable Entity with validation errors
```

### Test 10.3: Expired API Key (if expiration set)
```bash
# Create a key that expires quickly for testing
curl -X POST "http://localhost:8002/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Expiring Key",
    "expires_in_days": 0
  }'

# Try to use the expired key
# Expected: 401 Unauthorized "API key expired"
```

## ✅ Test Results Checklist

After running all tests, verify:

- [ ] API key creation works correctly
- [ ] Authentication is enforced in production mode
- [ ] Rate limiting functions properly
- [ ] Usage statistics are tracked accurately
- [ ] All forecast endpoints work with authentication
- [ ] Database tables are created and populated correctly
- [ ] Error handling is appropriate for various scenarios
- [ ] Python client integration works seamlessly
- [ ] Performance is acceptable with authentication overhead
- [ ] Security measures prevent unauthorized access

## 🚀 Production Readiness

Once all tests pass:

1. **Set DEBUG=False** in production environment
2. **Remove test API keys** from database
3. **Set up monitoring** for rate limit violations
4. **Configure automated cleanup** of old usage logs
5. **Document API key distribution process** for users
6. **Set up backup/restore procedures** for API key data

---

**Testing Status:** Ready for execution after deployment ✅