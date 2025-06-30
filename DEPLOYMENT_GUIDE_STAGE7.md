# Руководство по развертыванию Этапа 7: Автоматическое переобучение и мониторинг

## Обзор изменений

Этап 7 добавляет комплексную систему автоматического переобучения и мониторинга модели машинного обучения.

## Новые компоненты

### 1. Сервисы
- `app/services/model_retraining_service.py` - Автоматическое переобучение
- `app/services/model_monitoring_service.py` - Мониторинг качества

### 2. API Router
- `app/routers/monitoring.py` - REST API для мониторинга и управления

### 3. База данных
- `migrations/002_add_model_versioning.sql` - Схема версионирования моделей

### 4. UI компоненты
- Новый раздел "МОНИТОРИНГ МОДЕЛЕЙ" в админ панели (4 подстраницы)

## Шаги развертывания

### 1. Остановите текущий сервер
```bash
# Если запущен в Docker
docker-compose -f docker-compose.prod.yml down

# Или если запущен в development режиме
# Ctrl+C для остановки uvicorn
```

### 2. Выполните миграцию базы данных
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

### 3. Пересоберите Docker контейнер (Production)
```bash
# Пересборка с новым кодом
docker-compose -f docker-compose.prod.yml build --no-cache sales-forecast-app

# Запуск сервиса
docker-compose -f docker-compose.prod.yml up -d

# Проверка логов
docker-compose -f docker-compose.prod.yml logs -f sales-forecast-app
```

### 4. Запуск в Development режиме
```bash
# Установите зависимости (если нужно)
pip install -r requirements.txt

# Запустите сервер
uvicorn app.main:app --reload --host 0.0.0.0 --port 8002
```

## Проверка развертывания

### 1. Проверьте scheduler
```bash
# В логах должно быть сообщение:
# "✅ Background scheduler started - Daily sales sync at 2:00 AM, Weekly model retraining on Sundays at 3:00 AM"
```

### 2. Проверьте API endpoints
```bash
# Проверка статуса переобучения
curl http://localhost:8002/api/monitoring/retrain/status

# Проверка здоровья модели
curl http://localhost:8002/api/monitoring/health

# Проверка метрик производительности
curl "http://localhost:8002/api/monitoring/performance/summary?days=30"
```

### 3. Проверьте Admin Panel
1. Откройте http://localhost:8002/
2. В сайдбаре должен появиться раздел "МОНИТОРИНГ МОДЕЛЕЙ"
3. Проверьте 4 подстраницы:
   - 📊 Статус модели
   - 📈 Метрики производительности
   - 📋 История обучения
   - 🔄 Ручное переобучение

## Новые возможности

### Автоматическое переобучение
- **Расписание**: Каждое воскресенье в 3:00 AM
- **Логика**: Модель переобучается только при наличии достаточных данных
- **Развертывание**: Автоматическое только при улучшении метрик
- **Архивирование**: Старые модели сохраняются в папке archive/

### Мониторинг качества
- **Ежедневные метрики**: MAPE, MAE, RMSE автоматически рассчитываются
- **Health checks**: Комплексная проверка состояния модели
- **Алерты**: Автоматические уведомления при деградации
- **Trend analysis**: Отслеживание тенденций производительности

### Ручное управление
- **Внеплановое переобучение**: Через UI с настраиваемыми параметрами
- **Принудительное развертывание**: Опция для экстренных случаев
- **Детальные отчеты**: Полная информация о процессе и результатах

## Мониторинг системы

### Проверка расписания
```bash
# Статус scheduler jobs
curl http://localhost:8002/api/monitoring/retrain/status | jq '.scheduled_jobs'
```

### Анализ логов
```bash
# Docker logs
docker-compose -f docker-compose.prod.yml logs sales-forecast-app | grep -E "(retrain|monitor|scheduler)"

# Файловые логи
tail -f sales_forecast.log | grep -E "(ModelRetraining|ModelMonitoring)"
```

### База данных
```bash
# Проверка таблиц версионирования
docker exec sales-forecast-db psql -U sales_user -d sales_forecast -c "
SELECT COUNT(*) as model_versions_count FROM model_versions;
SELECT COUNT(*) as retrain_logs_count FROM model_retraining_log;
SELECT COUNT(*) as performance_metrics_count FROM model_performance_metrics;
"
```

## Устранение неполадок

### 1. Scheduler не запускается
- Проверьте логи на ошибки import
- Убедитесь, что APScheduler установлен: `pip install APScheduler==3.10.4`

### 2. API endpoints недоступны
- Проверьте, что monitoring router импортирован в main.py
- Перезапустите сервер после изменений

### 3. Ошибки базы данных
- Проверьте выполнение миграции 002_add_model_versioning.sql
- Убедитесь в правах доступа пользователя sales_user

### 4. UI не отображается
- Очистите кэш браузера (Ctrl+F5)
- Проверьте консоль браузера на JavaScript ошибки

## Команды для тестирования

### Ручное переобучение
```bash
curl -X POST "http://localhost:8002/api/monitoring/retrain/manual" \
  -H "Content-Type: application/json" \
  -d '{
    "reason": "Тестовое переобучение",
    "performance_threshold": 10.0,
    "force_deploy": false
  }'
```

### Расчет ежедневных метрик
```bash
curl -X POST "http://localhost:8002/api/monitoring/performance/calculate-daily"
```

### Получение уведомлений
```bash
curl "http://localhost:8002/api/monitoring/alerts/recent?days=7"
```

## Безопасность

- Все API endpoints доступны без аутентификации (соответствует текущей архитектуре)
- Автоматическое переобучение защищено от одновременного запуска
- Старые модели архивируются, но не удаляются
- Логи содержат полную трассировку для аудита

## Производительность

- Мониторинг не влияет на основную работу системы
- Переобучение выполняется в отдельных потоках
- Метрики рассчитываются асинхронно
- Chart.js используется для быстрой визуализации

## Следующие шаги

После успешного развертывания:
1. Настройте расписание переобучения под ваши потребности
2. Определите пороги алертов для вашего бизнеса
3. Настройте интеграцию с системами уведомлений
4. Проведите нагрузочное тестирование

## Контакты и поддержка

При возникновении проблем проверьте:
1. CLAUDE.md - основная документация проекта
2. IMPROVEMENT_PLAN.md - детальное описание этапов
3. Логи приложения и scheduler
4. Статус базы данных и миграций