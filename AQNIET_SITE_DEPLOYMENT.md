# 🌐 AQNIET.SITE - Sales Forecast + 1C Exchange Deployment

## 📋 Обзор системы

**Домен**: https://aqniet.space/
**Назначение**: Sales Forecast управление + 1C Exchange Service API
**Дата развертывания**: 2025-06-23
**Последнее обновление**: 2025-07-02 (Исправление Docker networking)

## ⚠️ КРИТИЧЕСКИ ВАЖНО - Docker Networking

### 🔥 Основная проблема 502 Bad Gateway
**Причина**: Nginx контейнер не может подключиться к Sales Forecast контейнеру из-за разных Docker сетей.

**Симптомы**:
- Сайт показывает "502 Bad Gateway" 
- В nginx логах: `connect() failed (111: Connection refused) while connecting to upstream`
- Nginx пытается подключиться к `127.0.0.1:8002`, но контейнер недоступен

**Решение**: Использовать имена контейнеров вместо localhost и обеспечить сетевую связность.

## 🏗️ Архитектура системы

### 📊 Текущая рабочая архитектура (ОБНОВЛЕНО 2025-07-13)
```
NGINX Container (hr-nginx) - мульти-сетевой режим
├── hr-miniapp_hr-network → для madlen.space, n8n.sandyq.space
└── sales_forecast_default → для aqniet.space
    ├── /api/exchange/ → 127.0.0.1:8000 (1C Exchange Service) ✅
    ├── /docs, /openapi.json → 127.0.0.1:8000 (1C Exchange Docs) ✅
    ├── /api/ → sales-forecast-app:8000 (Sales Forecast API) ✅
    └── / → sales-forecast-app:8000 (Sales Forecast Admin) ✅

⚠️ **Особенность**: Смешанная сетевая модель - 1C Exchange использует localhost, а Sales Forecast - имя контейнера
```

### 🐳 Docker Сервисы

#### 1. Sales Forecast Stack
- **Контейнер**: `sales-forecast-app` (порт 8002→8000)
- **БД контейнер**: `sales-forecast-db` (порт 5435→5432)
- **Сеть**: `sales_forecast_default`
- **Docker Compose**: `/root/projects/SalesForecast/sales_forecast/docker-compose.prod.yml`

#### 2. 1C Exchange Service
- **Контейнер**: `exchange-service` (порт 8000)
- **Сеть**: `sales_forecast_default` 
- **Docker Compose**: тот же файл

#### 3. HR System + Nginx
- **Контейнер**: `hr-nginx` (порты 80, 443)
- **Основная сеть**: `hr-miniapp_hr-network`
- **Дополнительная сеть**: `sales_forecast_default` (для доступа к aqniet.space)
- **Docker Compose**: `/root/projects/hr-miniapp/docker-compose.yml`

## 🔧 Конфигурация NGINX

### Основной файл
**Путь**: `/root/projects/hr-miniapp/nginx.conf`

### ✅ ПРАВИЛЬНАЯ конфигурация для aqniet.space (исправлено 2025-07-02)
```nginx
# HTTPS server for aqniet.space
server {
    listen 443 ssl http2;
    server_name aqniet.space www.aqniet.space;

    # SSL configuration
    ssl_certificate /etc/letsencrypt/live/aqniet.space/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/aqniet.space/privkey.pem;
    
    # 1C Exchange Service API (высокий приоритет)
    location /api/exchange/ {
        proxy_pass http://exchange-service:8000;  # ✅ Имя контейнера!
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 1C Exchange Documentation
    location /docs {
        proxy_pass http://exchange-service:8000;  # ✅ Имя контейнера!
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # OpenAPI Schema
    location /openapi.json {
        proxy_pass http://exchange-service:8000;  # ✅ Имя контейнера!
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Sales Forecast API
    location /api/ {
        proxy_pass http://sales-forecast-app:8000;  # ✅ Имя контейнера + внутренний порт!
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Sales Forecast Admin Panel (default)
    location / {
        proxy_pass http://sales-forecast-app:8000;  # ✅ Имя контейнера + внутренний порт!
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### ❌ НЕПРАВИЛЬНАЯ конфигурация (причина 502 ошибок)
```nginx
# ❌ НЕ ИСПОЛЬЗУЙТЕ ЭТО - НЕ РАБОТАЕТ В DOCKER:
location /api/ {
    proxy_pass http://127.0.0.1:8002;  # ❌ Localhost недоступен из контейнера
}
location / {
    proxy_pass http://127.0.0.1:8002;  # ❌ Localhost недоступен из контейнера  
}
```

## 🚨 БЫСТРОЕ УСТРАНЕНИЕ 502 BAD GATEWAY

### 🔥 Если сайт не работает - выполните ЭТИ команды:

#### 1. Проверка статуса контейнеров
```bash
# Проверить что все контейнеры запущены
docker ps | grep -E "(sales-forecast|exchange-service|hr-nginx)"

# Должны быть 4 контейнера:
# - sales-forecast-app (Up X hours, 0.0.0.0:8002->8000/tcp)
# - sales-forecast-db (Up X hours, 0.0.0.0:5435->5432/tcp)  
# - exchange-service (Up X hours, 0.0.0.0:8000->8000/tcp)
# - hr-nginx (Up X hours, 0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp)
```

#### 2. Проверка сетевой связности (ОСНОВНАЯ ПРОБЛЕМА)
```bash
# Проверить что nginx может подключиться к sales-forecast-app
docker exec hr-nginx wget -q --spider http://sales-forecast-app:8000/ || echo "❌ НЕТ СВЯЗИ"

# Если ошибка "НЕТ СВЯЗИ" - добавить nginx в сеть sales_forecast:
docker network connect sales_forecast_default hr-nginx

# Проверить еще раз
docker exec hr-nginx wget -q --spider http://sales-forecast-app:8000/ && echo "✅ СВЯЗЬ ВОССТАНОВЛЕНА"
```

#### 3. Проверка конфигурации nginx
```bash
# Проверить что в nginx.conf используются имена контейнеров, а не localhost
grep -n "127.0.0.1:8002" /root/projects/hr-miniapp/nginx.conf
# Если что-то найдено - ОШИБКА! Должно быть "sales-forecast-app:8000"

# Проверить правильную конфигурацию
grep -n "sales-forecast-app:8000" /root/projects/hr-miniapp/nginx.conf
# Должно найти минимум 2 строки для /api/ и / location
```

#### 4. Исправление конфигурации (если нужно)
```bash
# ЗАМЕНА неправильных адресов на правильные
sed -i 's/127\.0\.0\.1:8002/sales-forecast-app:8000/g' /root/projects/hr-miniapp/nginx.conf
sed -i 's/127\.0\.0\.1:8000/exchange-service:8000/g' /root/projects/hr-miniapp/nginx.conf

# Перезапуск nginx
docker-compose -f /root/projects/hr-miniapp/docker-compose.yml restart nginx
```

#### 5. Финальная проверка
```bash
# Проверить сайт
curl -I https://aqniet.space/ --insecure
# Должно вернуть: HTTP/2 200 или HTTP/2 405 (не 502!)

# Проверить API
curl -s "https://aqniet.space/api/departments/" --insecure | head -c 50
# Должно вернуть JSON или {"detail":"Not authenticated"} (не HTML ошибки!)
```

### 🛠️ Диагностика в деталях

#### Логи для анализа проблемы:
```bash
# Nginx логи (основные ошибки)
docker logs hr-nginx --tail 20

# Sales Forecast логи  
docker logs sales-forecast-app --tail 10

# 1C Exchange логи
docker logs exchange-service --tail 10
```

#### Сетевая диагностика:
```bash
# Показать все сети Docker
docker network ls

# Показать контейнеры в сети sales_forecast_default
docker network inspect sales_forecast_default | grep -A5 "Containers"

# Показать контейнеры в сети hr-miniapp_hr-network  
docker network inspect hr-miniapp_hr-network | grep -A5 "Containers"
```

## 🚀 Запуск сервисов (Docker Mode - РЕКОМЕНДУЕТСЯ)

### ✅ Правильный способ - через Docker Compose

#### 1. Запуск Sales Forecast Stack
```bash
cd /root/projects/SalesForecast/sales_forecast
docker-compose -f docker-compose.prod.yml up -d

# Проверить статус
docker-compose -f docker-compose.prod.yml ps
```

#### 2. Подключение nginx к сети Sales Forecast
```bash
# КРИТИЧЕСКИ ВАЖНО - без этого будет 502 ошибка!
docker network connect sales_forecast_default hr-nginx

# Проверить подключение
docker exec hr-nginx wget -q --spider http://sales-forecast-app:8000/ && echo "✅ СВЯЗЬ OK"
```

#### 3. Обновление конфигурации nginx (если нужно)
```bash
# Проверить текущую конфигурацию
grep -E "(127\.0\.0\.1:800[02]|sales-forecast-app)" /root/projects/hr-miniapp/nginx.conf

# Если найдены 127.0.0.1 адреса - исправить:
sed -i 's/127\.0\.0\.1:8002/sales-forecast-app:8000/g' /root/projects/hr-miniapp/nginx.conf
sed -i 's/127\.0\.0\.1:8000/exchange-service:8000/g' /root/projects/hr-miniapp/nginx.conf

# Перезапустить nginx
docker-compose -f /root/projects/hr-miniapp/docker-compose.yml restart nginx
```

### 🔧 Альтернативный способ - без Docker Compose

#### 1. Sales Forecast (прямой запуск)
```bash
cd /root/projects/SalesForecast/sales_forecast
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8002 > sales_forecast.log 2>&1 &
```

#### 2. 1C Exchange Service (прямой запуск)
```bash
cd /root/projects/1c-exchange-service
source venv/bin/activate  
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > 1c-exchange.log 2>&1 &
```

#### 3. PostgreSQL (контейнер)
```bash
docker run -d --name sales-forecast-db \
  -e POSTGRES_DB=sales_forecast \
  -e POSTGRES_USER=sales_user \
  -e POSTGRES_PASSWORD=sales_password \
  -p 5435:5432 \
  postgres:15
```

⚠️ **При прямом запуске используйте localhost адреса в nginx.conf!**

## 🔐 SSL сертификаты

### Получение сертификата
```bash
docker run --rm --name certbot \
  -v "/root/projects/infra/infra/certbot/conf:/etc/letsencrypt" \
  -v "/root/projects/infra/infra/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  --email admin@aqniet.space --agree-tos --no-eff-email \
  -d aqniet.space -d www.aqniet.space
```

### Расположение сертификатов
- **Сертификат**: `/root/projects/infra/infra/certbot/conf/live/aqniet.space/fullchain.pem`
- **Приватный ключ**: `/root/projects/infra/infra/certbot/conf/live/aqniet.space/privkey.pem`
- **Срок действия**: до 30 сентября 2025 (обновлено 2025-07-02)

## 🧪 Тестирование

### Основные эндпоинты
```bash
# Главная страница (Sales Forecast Admin)
curl -I https://aqniet.space/

# Sales Forecast API
curl https://aqniet.space/api/branches/

# 1C Exchange Documentation
curl -I https://aqniet.space/docs

# 1C Exchange API
curl https://aqniet.space/api/exchange/

# OpenAPI Schema
curl https://aqniet.space/openapi.json
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
Полная документация доступна по адресу: https://aqniet.space/docs

### Swagger UI
- **URL**: https://aqniet.space/docs
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

### Проблема: 502 Bad Gateway ⭐ САМАЯ ЧАСТАЯ
**Причина**: Nginx не может подключиться к Sales Forecast контейнеру
**Симптомы**: 
- Сайт показывает "502 Bad Gateway"
- В nginx логах: `connect() failed (111: Connection refused)`

**Решение**:
```bash
# 1. Убедиться что контейнеры запущены
docker ps | grep sales-forecast-app

# 2. Добавить nginx в сеть sales_forecast (ГЛАВНОЕ!)
docker network connect sales_forecast_default hr-nginx

# 3. Проверить конфигурацию nginx
grep "127.0.0.1:8002" /root/projects/hr-miniapp/nginx.conf
# Если найдено - исправить на sales-forecast-app:8000

# 4. Перезапустить nginx
docker-compose -f /root/projects/hr-miniapp/docker-compose.yml restart nginx
```

### Проблема: Конфигурация nginx сбрасывается
**Причина**: Docker контейнеры пересоздаются, сетевые соединения теряются
**Решение**: Добавить постоянное подключение к docker-compose.yml

В файл `/root/projects/hr-miniapp/docker-compose.yml` добавить:
```yaml
  nginx:
    # ... существующая конфигурация ...
    networks:
      - hr-network
      - sales_forecast_default  # Добавить эту строку!

networks:
  hr-network:
    driver: bridge
  sales_forecast_default:  # Добавить эту секцию!
    external: true
```

### Проблема: SSL сертификат истек
**Решение (обновлено 2025-07-02)**:
```bash
# Проверить статус всех сертификатов
openssl x509 -in /root/projects/infra/infra/certbot/conf/live/aqniet.space/fullchain.pem -dates -noout
openssl x509 -in /root/projects/infra/infra/certbot/conf/live/madlen.space/fullchain.pem -dates -noout
openssl x509 -in /root/projects/infra/infra/certbot/conf/live/n8n.sandyq.space/fullchain.pem -dates -noout

# Принудительно обновить ВСЕ сертификаты
docker run --rm -v "/root/projects/infra/infra/certbot/conf:/etc/letsencrypt" -v "/root/projects/infra/infra/certbot/www:/var/www/certbot" certbot/certbot renew --force-renewal

# Перезагрузить nginx
docker exec hr-nginx nginx -s reload

# Проверить успешность обновления
curl -I https://aqniet.space/
curl -I https://madlen.space/
curl -I https://n8n.sandyq.space/
```

#### ✅ Автоматическое обновление SSL (настроено 2025-07-02)
**Добавлена cron задача для предотвращения повторения проблем:**
```bash
# Проверить cron задачу
crontab -l | grep certbot

# Результат должен показать:
# 0 3 * * 1 docker run --rm -v "/root/projects/infra/infra/certbot/conf:/etc/letsencrypt" -v "/root/projects/infra/infra/certbot/www:/var/www/certbot" certbot/certbot renew && docker exec hr-nginx nginx -s reload
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
- ✅ SSL сертификаты - безопасное HTTPS соединение (обновлено 2025-07-02)
- ✅ Автоматическое обновление SSL - предотвращение истечения сертификатов
- ✅ Nginx маршрутизация - правильное разделение сервисов
- ✅ PostgreSQL - база данных для Sales Forecast
- ✅ Логирование и мониторинг

**Дата завершения**: 2025-06-23
**SSL Security Update**: 2025-07-02
**Ответственный**: Claude Code AI Assistant

---

## Stage 7 Deployment: Автоматическое переобучение и мониторинг

### Обзор изменений

Этап 7 добавляет комплексную систему автоматического переобучения и мониторинга модели машинного обучения.

### Новые компоненты

#### 1. Сервисы
- `app/services/model_retraining_service.py` - Автоматическое переобучение
- `app/services/model_monitoring_service.py` - Мониторинг качества

#### 2. API Router
- `app/routers/monitoring.py` - REST API для мониторинга и управления

#### 3. База данных
- `migrations/002_add_model_versioning.sql` - Схема версионирования моделей

#### 4. UI компоненты
- Новый раздел "МОНИТОРИНГ МОДЕЛЕЙ" в админ панели (4 подстраницы)

### Шаги развертывания Stage 7

#### 1. Остановите текущий сервер
```bash
# Если запущен в Docker
docker-compose -f docker-compose.prod.yml down

# Или если запущен в development режиме
# Ctrl+C для остановки uvicorn
```

#### 2. Выполните миграцию базы данных
```bash
# Подключитесь к PostgreSQL
docker exec -it sales-forecast-db psql -U sales_user -d sales_forecast

# Выполните миграцию
\i /app/migrations/002_add_model_versioning.sql

# Проверьте созданные таблицы
\dt model_*

# Выйдите из psql
\q
```

#### 3. Пересоберите Docker контейнер
```bash
# Пересборка с новым кодом
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# Запуск сервиса
docker-compose -f docker-compose.prod.yml up -d

# Проверка логов
docker-compose -f docker-compose.prod.yml logs -f sales-forecast-app
```

### Проверка развертывания Stage 7

#### 1. Проверьте scheduler
```bash
# В логах должно быть сообщение:
# "✅ Background scheduler started - Daily sales sync at 2:00 AM, Weekly model retraining on Sundays at 3:00 AM"
```

#### 2. Проверьте API endpoints
```bash
# Проверка статуса переобучения
curl http://localhost:8002/api/monitoring/retrain/status

# Проверка здоровья модели
curl http://localhost:8002/api/monitoring/health

# Проверка метрик производительности
curl "http://localhost:8002/api/monitoring/performance/summary?days=30"
```

#### 3. Проверьте Admin Panel
1. Откройте http://localhost:8002/
2. В сайдбаре должен появиться раздел "МОНИТОРИНГ МОДЕЛЕЙ"
3. Проверьте 4 подстраницы:
   - 📊 Статус модели
   - 📈 Метрики производительности
   - 📋 История обучения
   - 🔄 Ручное переобучение

### Новые возможности Stage 7

#### Автоматическое переобучение
- **Расписание**: Каждое воскресенье в 3:00 AM
- **Логика**: Модель переобучается только при наличии достаточных данных
- **Развертывание**: Автоматическое только при улучшении метрик
- **Архивирование**: Старые модели сохраняются в папке archive/

#### Мониторинг качества
- **Ежедневные метрики**: MAPE, MAE, RMSE автоматически рассчитываются
- **Health checks**: Комплексная проверка состояния модели
- **Алерты**: Автоматические уведомления при деградации
- **Trend analysis**: Отслеживание тенденций производительности

#### Ручное управление
- **Внеплановое переобучение**: Через UI с настраиваемыми параметрами
- **Принудительное развертывание**: Опция для экстренных случаев
- **Детальные отчеты**: Полная информация о процессе и результатах

### Команды для тестирования Stage 7

```bash
# Ручное переобучение
curl -X POST "http://localhost:8002/api/monitoring/retrain/manual" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Тестовое переобучение",
    "performance_threshold": 10.0,
    "force_deploy": false
  }'

# Расчет ежедневных метрик
curl -X POST "http://localhost:8002/api/monitoring/performance/calculate-daily"

# Получение уведомлений
curl "http://localhost:8002/api/monitoring/alerts/recent?days=7"
```