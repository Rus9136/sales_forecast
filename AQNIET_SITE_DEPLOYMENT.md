# 🌐 AQNIET.SITE - Sales Forecast + 1C Exchange Deployment

## 📋 Обзор системы

**Домен**: https://aqniet.site/
**Назначение**: Sales Forecast управление + 1C Exchange Service API
**Дата развертывания**: 2025-06-23

## 🏗️ Архитектура системы

### 📊 Компоненты
```
https://aqniet.site/
├── / → Sales Forecast Admin Panel (порт 8002)
├── /api/ → Sales Forecast API (порт 8002)
├── /api/exchange/ → 1C Exchange Service (порт 8000)
├── /docs → 1C Exchange Documentation (порт 8000)
└── /openapi.json → 1C Exchange OpenAPI Schema (порт 8000)
```

### 🐳 Сервисы

#### 1. Sales Forecast (порт 8002)
- **Тип**: FastAPI приложение
- **Путь**: `/root/projects/SalesForecast/sales_forecast/`
- **База данных**: PostgreSQL на порту 5435
- **Функции**: 
  - Управление филиалами организаций
  - Синхронизация с внешним API
  - Веб-интерфейс администратора

#### 2. 1C Exchange Service (порт 8000)
- **Тип**: FastAPI приложение
- **Путь**: `/root/projects/1c-exchange-service/`
- **Функции**:
  - API для обмена данными с 1С
  - Swagger документация
  - RESTful endpoints

## 🔧 Конфигурация NGINX

### Основной файл
**Путь**: `/root/projects/hr-miniapp/nginx.conf`

### Конфигурация для aqniet.site
```nginx
# HTTP → HTTPS redirect
server {
    listen 80;
    server_name aqniet.site www.aqniet.site;
    
    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }
    
    location / {
        return 301 https://$server_name$request_uri;
    }
}

# HTTPS server
server {
    listen 443 ssl http2;
    server_name aqniet.site www.aqniet.site;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/aqniet.site/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aqniet.site/privkey.pem;
    
    # 1C Exchange Service API (высокий приоритет)
    location /api/exchange/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 1C Exchange Documentation
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # OpenAPI Schema
    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Sales Forecast API
    location /api/ {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Sales Forecast Admin Panel (default)
    location / {
        proxy_pass http://127.0.0.1:8002;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## 🚀 Запуск сервисов

### 1. Sales Forecast
```bash
cd /root/projects/SalesForecast/sales_forecast
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8002 > sales_forecast.log 2>&1 &
```

### 2. 1C Exchange Service
```bash
cd /root/projects/1c-exchange-service
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > 1c-exchange.log 2>&1 &
```

### 3. PostgreSQL для Sales Forecast
```bash
docker run -d --name sales-forecast-db \
  -e POSTGRES_DB=sales_forecast \
  -e POSTGRES_USER=sales_user \
  -e POSTGRES_PASSWORD=sales_password \
  -p 5435:5432 \
  postgres:15
```

## 🔐 SSL сертификаты

### Получение сертификата
```bash
docker run --rm --name certbot \
  -v "/root/projects/infra/infra/certbot/conf:/etc/letsencrypt" \
  -v "/root/projects/infra/infra/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  --email admin@aqniet.site --agree-tos --no-eff-email \
  -d aqniet.site -d www.aqniet.site
```

### Расположение сертификатов
- **Сертификат**: `/root/projects/infra/infra/certbot/conf/live/aqniet.site/fullchain.pem`
- **Приватный ключ**: `/root/projects/infra/infra/certbot/conf/live/aqniet.site/privkey.pem`
- **Срок действия**: до 26 июня 2025

## 🧪 Тестирование

### Основные эндпоинты
```bash
# Главная страница (Sales Forecast Admin)
curl -I https://aqniet.site/

# Sales Forecast API
curl https://aqniet.site/api/branches/

# 1C Exchange Documentation
curl -I https://aqniet.site/docs

# 1C Exchange API
curl https://aqniet.site/api/exchange/

# OpenAPI Schema
curl https://aqniet.site/openapi.json
```

### Проверка сервисов напрямую
```bash
# Sales Forecast (порт 8002)
curl http://127.0.0.1:8002/

# 1C Exchange (порт 8000)
curl http://127.0.0.1:8000/docs
```

## 📊 Sales Forecast - Функции

### Управление филиалами
- **Главная страница**: Таблица всех филиалов с фильтрацией
- **Синхронизация**: Кнопка "Sync Branches from API"
- **Обновление**: Кнопка "Refresh List"

### API эндпоинты
- `GET /api/branches/` - список всех филиалов
- `POST /api/branches/sync` - синхронизация с внешним API
- `GET /api/branches/{id}` - получение конкретного филиала

### Источник данных
- **Внешний API**: `http://tco.aqnietgroup.com:5555/v1/objects`
- **Локальная БД**: PostgreSQL с кэшированием

## 🔧 1C Exchange Service - Функции

### API эндпоинты
Полная документация доступна по адресу: https://aqniet.site/docs

### Swagger UI
- **URL**: https://aqniet.site/docs
- **Интерактивная документация** с возможностью тестирования
- **OpenAPI 3.0** схема

## 📝 Логи и мониторинг

### Логи сервисов
```bash
# Sales Forecast
tail -f /root/projects/SalesForecast/sales_forecast/sales_forecast.log

# 1C Exchange Service
tail -f /root/projects/1c-exchange-service/1c-exchange.log

# Nginx (общий)
docker logs hr-nginx
```

### Проверка статуса
```bash
# Процессы
ps aux | grep -E "(8000|8002)" | grep -v grep

# Порты
netstat -tlnp | grep -E ":(8000|8002)"

# Подключения к базе
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c "\dt"
```

## 🔄 Управление и обслуживание

### Перезапуск сервисов
```bash
# Найти и остановить процессы
pkill -f "uvicorn.*8000"
pkill -f "uvicorn.*8002"

# Запустить заново
cd /root/projects/1c-exchange-service && nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > 1c-exchange.log 2>&1 &
cd /root/projects/SalesForecast/sales_forecast && nohup ./venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8002 > sales_forecast.log 2>&1 &
```

### Обновление конфигурации Nginx
```bash
# После изменения /root/projects/hr-miniapp/nginx.conf
docker exec hr-nginx nginx -t
docker exec hr-nginx nginx -s reload
```

### Резервное копирование
```bash
# Базы данных
docker exec sales-forecast-db pg_dump -U sales_user sales_forecast > sales_forecast_backup.sql

# Конфигурации
cp /root/projects/hr-miniapp/nginx.conf /root/projects/hr-miniapp/nginx.conf.backup.$(date +%Y%m%d)
```

## ⚠️ Troubleshooting

### Проблема: 502 Bad Gateway
**Причина**: Сервис не запущен или недоступен на localhost
**Решение**: 
```bash
# Проверить запущенные процессы
ps aux | grep uvicorn
# Перезапустить нужный сервис
```

### Проблема: SSL сертификат истек
**Решение**:
```bash
# Обновить сертификат
docker run --rm -v "/root/projects/infra/infra/certbot/conf:/etc/letsencrypt" -v "/root/projects/infra/infra/certbot/www:/var/www/certbot" certbot/certbot renew
# Перезагрузить nginx
docker exec hr-nginx nginx -s reload
```

### Проблема: База данных недоступна
**Решение**:
```bash
# Проверить контейнер
docker ps | grep sales-forecast-db
# Перезапустить если нужно
docker restart sales-forecast-db
```

## 🎯 Финальный статус

**✅ AQNIET.SITE ПОЛНОСТЬЮ РАЗВЕРНУТ И РАБОТАЕТ!**

- ✅ Sales Forecast Admin Panel - управление филиалами
- ✅ Sales Forecast API - RESTful интерфейс
- ✅ 1C Exchange Service - API для обмена с 1С
- ✅ Swagger документация - интерактивные API docs
- ✅ SSL сертификаты - безопасное HTTPS соединение
- ✅ Nginx маршрутизация - правильное разделение сервисов
- ✅ PostgreSQL - база данных для Sales Forecast
- ✅ Логирование и мониторинг

**Дата завершения**: 2025-06-23
**Ответственный**: Claude Code AI Assistant