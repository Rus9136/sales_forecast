# Project State - Sales Forecast API

## Current Status: PRODUCTION READY v2.3

**Last Updated**: 2025-07-03
**Environment**: Production (https://aqniet.site/)
**Deployment**: Docker-based

## System Overview

### ML Forecasting System v2.3
- **Test MAPE**: 6.18% - excellent result with correct weekend logic
- **Weekend Logic**: Correct handling of weekends/weekdays (PostgreSQL compatibility)
- **R2**: 0.9962+ - consistently excellent model accuracy
- **Data**: 7,491 records (365 days of quality data)
- **Features**: 64 features with weekend features and temporal smoothing
- **Temporal Smoothing**: Automatic prevention of anomalous predictions (+-50%)

### Application Services
- **Sales Forecast App**: Running on port 8002
- **1C Exchange Service**: Running on port 8000
- **Database**: PostgreSQL on port 5435

### Key Features
- **Sales Sync**: Works with real iiko API data
- **API Endpoints**: All CRUD operations functional on port 8002
- **Database Schema**: Foreign keys and indexes properly configured
- **Admin Panel**: Fully functional management panel with updated UI
- **Production**: Docker containers running stably

## Technical Configuration

### Production Environment
```yaml
Services:
  - sales-forecast-app: localhost:8002 -> container:8000
  - sales-forecast-db: localhost:5435 -> container:5432
  - exchange-service: localhost:8000 -> container:8000

Environment Variables:
  - DATABASE_URL: postgresql://sales_user:sales_password@sales-forecast-db:5432/sales_forecast
  - API_BASE_URL: http://tco.aqnietgroup.com:5555/v1
  - API_TOKEN: (stored in .env file)
  - DEBUG: False
```

### Network Configuration
- **Domain**: https://aqniet.site/
- **Nginx**: Configured to proxy to Docker containers

## Automation & Monitoring

### Currently Running
- **Automatic Sales Loading**: Daily at 02:00 with APScheduler
- **Model Retraining**: Weekly automatic retraining (Sunday 3:00 AM)
- **Performance Tracking**: Automatic historical data accumulation
- **API Authentication**: Secure authorization system via environment tokens

### Manual Operations Required
- **Container Updates**: Manual rebuild when code changes
- **Database Backups**: Not currently automated

## Recent Critical Updates (2025-07-01/02)

### Weekend Logic Fix & Temporal Smoothing
- **Critical Weekend/Weekday Logic Fix**: Fixed critical error in day of week numbering
  - **Problem**: PostgreSQL (0=Sunday) vs Python pandas (0=Monday) incompatibility
  - **Solution**: Numbering conversion `postgres_dow = (python_dow + 1) % 7`
  - **Result**: Model correctly predicts high sales on weekends
- **Enhanced Weekend Features**: Added `is_saturday`, `is_sunday`, `weekend_multiplier`
- **Temporal Smoothing System**: +-50% constraint from average by day of week over 4 weeks

### Extended Forecasting System
- **Extended Forecasting Implementation**: Extended forecasting for 31+ days
- **Hybrid Forecasting Strategy**: Automatic approach selection by forecast horizon
  - **Short-term (1-7 days)**: Traditional logic with fresh data (MAPE 5-15%)
  - **Long-term (8+ days)**: Extended logic with latest available data (MAPE 15-25%)

### API Authentication System
- **Environment-based Token**: Token stored in environment variables (.env file)
- **Server-side Token Injection**: Token passed from server to HTML without hardcoded values
- **Automatic Authorization**: All API requests automatically include Authorization headers
- **Zero User Input**: User doesn't need to enter token, system works automatically

## Key Files

### Core Application
- `app/services/branch_loader.py` - Multi-pass dependency resolution
- `app/routers/branch.py` - Pagination limit
- `app/config.py` - Production database credentials

### Infrastructure
- `docker-compose.prod.yml` - Production orchestration
- `Dockerfile` - Application containerization
- `CLAUDE.md` - Documentation and guidelines

## Deployment Workflow

### For Code Changes
```bash
# 1. Stop services
docker-compose -f docker-compose.prod.yml down

# 2. Rebuild application
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# 3. Start services
docker-compose -f docker-compose.prod.yml up -d

# 4. Verify functionality
curl -X POST http://localhost:8002/api/departments/sync
```

## Health Checks

```bash
# Application health
curl http://localhost:8002/

# Database health
docker exec sales-forecast-db pg_isready -U sales_user

# Model health
curl http://localhost:8002/api/monitoring/health

# Performance summary
curl "http://localhost:8002/api/monitoring/performance/summary?days=30"
```

---

**Project Status**: HEALTHY & PRODUCTION READY
**Confidence Level**: High - All critical functionality working correctly
