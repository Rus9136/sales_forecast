#!/bin/bash

# 🐳 Migration script: AQNIET.SITE to Docker Production
# This script migrates Sales Forecast and 1C Exchange to Docker
# while preserving madlen.space configuration

echo "🚀 Starting migration to Docker for aqniet.site..."

# Step 1: Stop existing uvicorn processes
echo "📴 Stopping existing uvicorn processes..."
pkill -f "uvicorn.*8000" 2>/dev/null || echo "No process on port 8000"
pkill -f "uvicorn.*8002" 2>/dev/null || echo "No process on port 8002"

# Wait for processes to stop
sleep 3

# Step 2: Stop existing PostgreSQL container if running
echo "🗄️ Managing PostgreSQL containers..."
docker stop sales-forecast-db 2>/dev/null || echo "PostgreSQL container not running"
docker rm sales-forecast-db 2>/dev/null || echo "PostgreSQL container not found"

# Step 3: Build and start Docker services
echo "🔨 Building and starting Docker services..."
cd /root/projects/SalesForecast/sales_forecast

# Build and start services
docker-compose -f docker-compose.prod.yml up -d --build

# Step 4: Wait for services to be ready
echo "⏳ Waiting for services to start..."
sleep 10

# Step 5: Check service status
echo "🔍 Checking service status..."
docker-compose -f docker-compose.prod.yml ps

# Step 6: Test endpoints locally
echo "🧪 Testing local endpoints..."
echo "Testing Sales Forecast..."
curl -s -I http://localhost:8002/ || echo "❌ Sales Forecast not responding"

echo "Testing 1C Exchange..."
curl -s -I http://localhost:8000/docs || echo "❌ 1C Exchange not responding"

# Step 7: Test through nginx (external)
echo "🌐 Testing through nginx..."
echo "Testing aqniet.site main page..."
curl -s -I https://aqniet.site/ || echo "❌ aqniet.site not responding"

echo "Testing aqniet.site API..."
curl -s -I https://aqniet.site/api/branches/ || echo "❌ aqniet.site API not responding"

echo "Testing 1C Exchange docs..."
curl -s -I https://aqniet.site/docs || echo "❌ 1C Exchange docs not responding"

# Step 8: Show logs if there are issues
echo "📋 Recent logs:"
echo "=== Sales Forecast logs ==="
docker logs sales-forecast-app --tail 5

echo "=== 1C Exchange logs ==="
docker logs exchange-service --tail 5

echo "=== PostgreSQL logs ==="
docker logs sales-forecast-db --tail 3

echo ""
echo "✅ Migration completed!"
echo ""
echo "🔧 Service URLs:"
echo "  - Sales Forecast Admin: https://aqniet.site/"
echo "  - Sales Forecast API: https://aqniet.site/api/branches/"
echo "  - 1C Exchange API: https://aqniet.site/api/exchange/"
echo "  - 1C Exchange Docs: https://aqniet.site/docs"
echo ""
echo "🐳 Docker management:"
echo "  - Status: docker-compose -f docker-compose.prod.yml ps"
echo "  - Logs: docker-compose -f docker-compose.prod.yml logs -f"
echo "  - Restart: docker-compose -f docker-compose.prod.yml restart"
echo "  - Stop: docker-compose -f docker-compose.prod.yml down"
echo ""
echo "🔄 To rollback to uvicorn processes:"
echo "  - docker-compose -f docker-compose.prod.yml down"
echo "  - cd /root/projects/1c-exchange-service && nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > 1c-exchange.log 2>&1 &"
echo "  - cd /root/projects/SalesForecast/sales_forecast && nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002 > sales_forecast.log 2>&1 &"