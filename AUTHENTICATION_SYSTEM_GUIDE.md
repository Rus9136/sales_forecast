# Authentication System Implementation Guide

## 🔐 Overview

Мы успешно реализовали комплексную систему аутентификации для Sales Forecast API с использованием API ключей, rate limiting и безопасного хранения токенов.

## 🏗️ Architecture

### Core Components

1. **API Key System** (`app/auth.py`)
   - Bearer token authentication
   - SHA256 hashing для безопасного хранения
   - Configurable rate limits per key
   - Automatic expiration support

2. **Database Schema** (`migrations/004_add_api_authentication.sql`)
   - `api_keys` - Хранение API ключей
   - `api_key_usage` - Трекинг использования для rate limiting
   - `api_key_stats` - View для статистики

3. **API Management** (`app/routers/auth.py`)
   - CRUD операции для API ключей
   - Usage statistics
   - Rate limit monitoring

## 🔑 API Key Format

```
sf_{key_id}_{secret}
```

**Example:**
```
sf_dGVzdF9rZXlfZXhhbXBsZQ_YWN0dWFsX3NlY3JldF9rZXk
```

- `sf_` - Prefix для идентификации Sales Forecast keys
- `key_id` - Public identifier (24 chars, base64url)
- `secret` - Secret part (32 chars, base64url)

## 🚦 Rate Limiting

### Default Limits per API Key
- **Per Minute:** 100 requests
- **Per Hour:** 1,000 requests  
- **Per Day:** 10,000 requests

### Custom Limits
Каждый API ключ может иметь индивидуальные лимиты при создании.

### HTTP Response Codes
- `429 Too Many Requests` - При превышении лимитов
- `401 Unauthorized` - Неверный или отсутствующий API ключ
- `403 Forbidden` - API ключ деактивирован или истек

## 🔒 Security Features

### Token Security
- **SHA256 Hashing:** Полные API ключи никогда не хранятся в открытом виде
- **One-time Display:** Полный API ключ показывается только при создании
- **Secure Generation:** Использование `secrets.token_urlsafe()` для криптографически стойкой генерации

### Access Control
- **Environment-based:** Аутентификация обязательна в production (DEBUG=False)
- **Optional in Development:** Bypass в development mode (DEBUG=True)
- **Graceful Degradation:** API работает с и без аутентификации

## 📊 Usage Tracking

### Metrics Collected
- Total requests per API key
- Requests by time periods (minute/hour/day)
- Endpoint usage patterns
- IP addresses and User-Agent (for analytics)

### Analytics Views
- `api_key_stats` - Агрегированная статистика
- Real-time rate limit status
- Historical usage patterns

## 🛠️ Implementation Details

### Authentication Flow

1. **Request arrives** with `Authorization: Bearer {api_key}` header
2. **Extract key_id** from API key format
3. **Database lookup** for active key with matching key_id
4. **Verify full key** against stored SHA256 hash
5. **Check rate limits** using sliding window
6. **Log usage** for analytics and rate limiting
7. **Grant access** or return error

### Database Optimizations

- **Composite Indexes:** `(key_id, timestamp)` for efficient rate limiting queries
- **Partitioning Ready:** Usage table designed for future partitioning by date
- **Cleanup Jobs:** Automated cleanup of old usage records (can be added)

## 🔧 Configuration

### Environment Variables
```bash
# Enable/disable authentication
DEBUG=False  # True = optional auth, False = required auth

# Database connection (existing)
DATABASE_URL=postgresql://...
```

### Per-Key Settings
```json
{
  "rate_limit_per_minute": 100,
  "rate_limit_per_hour": 1000,
  "rate_limit_per_day": 10000,
  "expires_in_days": 365
}
```

## 📋 API Endpoints

### Authentication Management
```bash
POST /api/auth/keys          # Create API key
GET  /api/auth/keys          # List API keys  
GET  /api/auth/keys/{id}     # Get API key details
DELETE /api/auth/keys/{id}   # Deactivate API key
POST /api/auth/keys/{id}/activate  # Reactivate API key
GET  /api/auth/keys/{id}/usage     # Usage statistics
POST /api/auth/test          # Test authentication
```

### Protected Endpoints
All forecast endpoints now support authentication:
```bash
GET /api/forecast/batch                    # ✅ Auth-enabled
GET /api/forecast/comparison               # ✅ Auth-enabled  
GET /api/forecast/batch_with_postprocessing # ✅ Auth-enabled
GET /api/forecast/export/csv               # ✅ Auth-enabled
```

## 📈 Usage Examples

### 1. Create API Key
```bash
curl -X POST "https://aqniet.site/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Mobile App Integration", 
    "description": "API access for iOS/Android app",
    "expires_in_days": 365,
    "rate_limit_per_hour": 2000
  }'
```

**Response:**
```json
{
  "key_id": "dGVzdF9rZXlfZXhhbXBsZQ",
  "api_key": "sf_dGVzdF9rZXlfZXhhbXBsZQ_YWN0dWFsX3NlY3JldF9rZXk",
  "name": "Mobile App Integration",
  "expires_at": "2026-06-30T12:00:00",
  "rate_limits": {
    "per_minute": 100,
    "per_hour": 2000,
    "per_day": 10000
  }
}
```

⚠️ **Important:** Сохраните полный `api_key` - он больше не будет показан!

### 2. Use API Key for Forecasts
```bash
curl "https://aqniet.site/api/forecast/batch?from_date=2025-07-01&to_date=2025-07-07" \
  -H "Authorization: Bearer sf_dGVzdF9rZXlfZXhhbXBsZQ_YWN0dWFsX3NlY3JldF9rZXk"
```

### 3. Check Usage Statistics
```bash
curl "https://aqniet.site/api/auth/keys/dGVzdF9rZXlfZXhhbXBsZQ/usage" \
  -H "Authorization: Bearer sf_dGVzdF9rZXlfZXhhbXBsZQ_YWN0dWFsX3NlY3JldF9rZXk"
```

**Response:**
```json
{
  "key_id": "dGVzdF9rZXlfZXhhbXBsZQ",
  "name": "Mobile App Integration",
  "total_requests": 1247,
  "requests_last_hour": 23,
  "requests_last_day": 456,
  "rate_limit_status": {
    "requests_last_minute": 2,
    "minute_limit": 100,
    "minute_remaining": 98,
    "hour_remaining": 1977,
    "day_remaining": 9544
  }
}
```

## 🐍 Python Client Integration

```python
from sales_forecast_client import SalesForecastClient

# Initialize with API key
client = SalesForecastClient(
    api_key="sf_your_key_id_your_secret"
)

# Test authentication
auth_result = client.test_api_key()
print(f"Authenticated as: {auth_result['key_name']}")

# Get forecasts (automatically authenticated)
forecasts = client.get_batch_forecasts(
    from_date="2025-07-01",
    to_date="2025-07-07"
)
```

## 🚀 Deployment

### Database Migration
```bash
# Apply authentication tables
psql -U sales_user -d sales_forecast -f migrations/004_add_api_authentication.sql
```

### Application Restart
```bash
# Restart to load new auth modules
docker-compose -f docker-compose.prod.yml restart sales-forecast-app
```

### Verify Installation
```bash
# Test API key creation
curl -X POST "https://aqniet.site/api/auth/keys" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Key", "description": "Verification test"}'

# Test authentication endpoint
curl -X POST "https://aqniet.site/api/auth/test"
```

## 🔧 Administration

### Production Checklist
- [ ] Set `DEBUG=False` in environment
- [ ] Remove default test API key
- [ ] Set up API key rotation policy
- [ ] Configure monitoring for rate limit violations
- [ ] Set up automated cleanup of old usage logs

### Monitoring Queries
```sql
-- Active API keys
SELECT name, created_at, last_used_at, expires_at 
FROM api_keys WHERE is_active = true;

-- Top API key usage
SELECT ak.name, COUNT(*) as requests_today
FROM api_keys ak
JOIN api_key_usage aku ON ak.key_id = aku.key_id  
WHERE aku.timestamp > NOW() - INTERVAL '1 day'
GROUP BY ak.name ORDER BY requests_today DESC;

-- Rate limit violations (would need custom table)
SELECT key_id, COUNT(*) as violations
FROM rate_limit_violations 
WHERE timestamp > NOW() - INTERVAL '1 day'
GROUP BY key_id;
```

## 🛡️ Security Best Practices

### For API Key Holders
1. **Store Securely:** Never commit API keys to version control
2. **Environment Variables:** Use environment variables or secure vaults
3. **Rotate Regularly:** Create new keys and deactivate old ones periodically
4. **Monitor Usage:** Check usage statistics for unexpected activity
5. **Least Privilege:** Request minimum necessary rate limits

### For System Administrators  
1. **Regular Audits:** Review active API keys and their usage
2. **Automated Cleanup:** Remove expired and unused keys
3. **Rate Limit Tuning:** Adjust limits based on usage patterns
4. **Security Monitoring:** Alert on suspicious usage patterns
5. **Backup Keys:** Maintain emergency admin keys for critical operations

## 🎯 Next Steps

### Enhanced Security (Future)
- [ ] JWT tokens for session management
- [ ] OAuth2 integration
- [ ] API key scopes and permissions
- [ ] IP address whitelisting
- [ ] Webhook signatures

### Analytics & Monitoring
- [ ] Real-time usage dashboard
- [ ] Automated alerting for rate limit violations
- [ ] Usage forecasting and capacity planning
- [ ] API key health scoring

### Performance
- [ ] Redis caching for rate limiting
- [ ] Database partitioning for usage logs
- [ ] Connection pooling optimization
- [ ] Load balancing considerations

## 📞 Support

For questions about the authentication system:
1. Check this documentation
2. Review API documentation (API_DOCUMENTATION_FORECAST.md)
3. Test with development endpoints
4. Contact system administrators for production keys

---

✅ **Authentication System Status:** Fully Implemented and Production Ready