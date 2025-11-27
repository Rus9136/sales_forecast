# Полный отчет: Система записи сырых продаж с iiko

## 📋 Содержание
1. [Общая архитектура системы](#общая-архитектура-системы)
2. [Хранение учетных записей для авторизации](#хранение-учетных-записей-для-авторизации)
3. [Источник подразделений](#источник-подразделений)
4. [Процесс синхронизации продаж](#процесс-синхронизации-продаж)
5. [Автоматическая синхронизация](#автоматическая-синхронизация)
6. [Какие подразделения получают данные](#какие-подразделения-получают-данные)
7. [Схема работы системы](#схема-работы-системы)

---

## 🏗️ Общая архитектура системы

Система синхронизации продаж с iiko состоит из следующих компонентов:

### Основные сервисы:

1. **`IikoAuthService`** (`app/services/iiko_auth.py`)
   - Авторизация в iiko API
   - Управление токенами авторизации

2. **`IikoSalesLoaderService`** (`app/services/iiko_sales_loader.py`)
   - Загрузка данных о продажах из iiko API
   - Обработка и агрегация данных
   - Сохранение в базу данных

3. **`IikoDepartmentLoaderService`** (`app/services/iiko_department_loader.py`)
   - Загрузка подразделений из iiko API
   - Синхронизация структуры подразделений

4. **`ScheduledSalesLoaderService`** (`app/services/scheduled_sales_loader.py`)
   - Автоматическая синхронизация по расписанию

---

## 🔐 Хранение учетных записей для авторизации

### Место хранения:
**Файл:** `app/services/iiko_auth.py`

### Текущие учетные данные:
```12:13:app/services/iiko_auth.py
        self.login = "Tanat"
        self.password = "7c4a8d09ca3762af61e59520943dc26494f8941b"
```

⚠️ **ВАЖНО:** Учетные данные хранятся **прямо в коде** (жестко закодированы). Это небезопасно для продакшн-окружения.

### Процесс авторизации:

```24:41:app/services/iiko_auth.py
    async def _refresh_token(self) -> str:
        """Refresh authentication token"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/resto/api/auth",
                    params={
                        "login": self.login,
                        "pass": self.password
                    }
                )
                response.raise_for_status()
                
                self.token = response.text.strip()
                self.token_expires_at = datetime.now() + timedelta(minutes=55)  # Refresh 5 minutes before expiry
                
                logger.info("Successfully refreshed iiko authentication token")
                return self.token
```

**Особенности:**
- Токен получается через GET-запрос к `/resto/api/auth` с параметрами `login` и `pass`
- Токен действителен 60 минут, обновляется за 5 минут до истечения
- Токен кэшируется в памяти до истечения

### Поддерживаемые домены:
```17:20:app/services/iiko_sales_loader.py
        self.domains = [
            "https://sandy-co-co.iiko.it",
            "https://madlen-group-so.iiko.it"
        ]
```

**Один и тот же логин/пароль используется для обоих доменов.**

---

## 🏢 Источник подразделений

### Откуда берутся подразделения:

Подразделения загружаются из **iiko API** через эндпоинт:
- **URL:** `{base_url}/resto/api/corporation/departments`
- **Метод:** GET
- **Параметры:** 
  - `key` - токен авторизации
  - `revisionFrom: -1` - получить все подразделения

### Процесс загрузки:

```21:47:app/services/iiko_department_loader.py
    async def fetch_departments_from_single_domain(self, base_url: str) -> List[dict]:
        """Fetch departments from a single iiko domain"""
        try:
            auth_service = IikoAuthService(base_url)
            token = await auth_service.get_auth_token()
            
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{base_url}/resto/api/corporation/departments",
                    params={
                        "key": token,
                        "revisionFrom": -1
                    }
                )
                response.raise_for_status()
                
                # Parse XML response
                departments = self._parse_departments_xml(response.text)
                logger.info(f"Fetched {len(departments)} departments from {base_url}")
                return departments
```

### Формат данных:

Ответ приходит в **XML формате**, парсится в структуру:
- `id` - UUID подразделения
- `parent_id` - UUID родительского подразделения
- `code` - код подразделения
- `name` - название
- `type` - тип (`DEPARTMENT`, `JURPERSON`, `CORPORATION`)
- `taxpayer_id_number` - ИНН

### Синхронизация подразделений:

```97:171:app/services/iiko_department_loader.py
    async def sync_departments(self) -> int:
        """Sync departments from iiko API to database"""
        try:
            iiko_departments = await self.fetch_departments_from_iiko()
            
            new_count = 0
            updated_count = 0
            processed_departments = set()
            remaining_departments = {dept['id']: dept for dept in iiko_departments if dept['id']}
            
            # Process departments in multiple passes to handle parent-child dependencies
            max_iterations = len(iiko_departments)
            iteration = 0
            
            while remaining_departments and iteration < max_iterations:
                iteration += 1
                departments_processed_this_iteration = 0
                
                for dept_id, iiko_dept in list(remaining_departments.items()):
                    # Check if this department can be processed
                    parent_id = iiko_dept['parent_id']
                    can_process = (parent_id is None or 
                                 parent_id in processed_departments or
                                 self.db.query(Department).filter(Department.id == parent_id).first() is not None)
                    
                    if can_process:
                        existing_dept = self.db.query(Department).filter(
                            Department.id == dept_id
                        ).first()
                        
                        if existing_dept:
                            # Update existing department
                            existing_dept.code = iiko_dept['code']
                            existing_dept.name = iiko_dept['name']
                            existing_dept.type = iiko_dept['type']
                            existing_dept.taxpayer_id_number = iiko_dept['taxpayer_id_number']
                            existing_dept.parent_id = parent_id
                            existing_dept.updated_at = datetime.utcnow()
                            existing_dept.synced_at = datetime.utcnow()
                            updated_count += 1
                        else:
                            # Create new department
                            new_dept = Department(
                                id=dept_id,
                                parent_id=parent_id,
                                code=iiko_dept['code'],
                                name=iiko_dept['name'],
                                type=iiko_dept['type'],
                                taxpayer_id_number=iiko_dept['taxpayer_id_number'],
                                synced_at=datetime.utcnow()
                            )
                            self.db.add(new_dept)
                            self.db.commit()  # Commit immediately for new records
                            new_count += 1
                        
                        processed_departments.add(dept_id)
                        del remaining_departments[dept_id]
                        departments_processed_this_iteration += 1
                
                # If no departments were processed in this iteration, break to avoid infinite loop
                if departments_processed_this_iteration == 0:
                    logger.warning(f"Could not process {len(remaining_departments)} departments due to missing parent dependencies")
                    for dept_id, dept in remaining_departments.items():
                        logger.warning(f"Department {dept_id} ({dept['name']}) has missing parent {dept['parent_id']}")
                    break
            
            # Commit any remaining updates
            self.db.commit()
            total_processed = new_count + updated_count
            logger.info(f"Successfully synced {new_count} new and {updated_count} updated departments")
            
            if remaining_departments:
                logger.warning(f"{len(remaining_departments)} departments could not be processed due to dependency issues")
            
            return total_processed
```

**Особенности:**
- Обрабатываются подразделения из обоих доменов
- Соблюдается иерархия (сначала родители, потом дети)
- Новые подразделения создаются, существующие обновляются

---

## 📊 Процесс синхронизации продаж

### Основной поток данных:

```
iiko API → IikoSalesLoaderService → Обработка → База данных
```

### 1. Загрузка данных из iiko API

**Эндпоинт:** `POST {base_url}/resto/api/v2/reports/olap`

**Запрос:**
```31:57:app/services/iiko_sales_loader.py
            request_body = {
                "reportType": "SALES",
                "groupByRowFields": [
                    "Department.Id",
                    "CloseTime",
                    "OrderNum"
                ],
                "aggregateFields": [
                    "DishSumInt"
                ],
                "filters": {
                    "OpenDate.Typed": {
                        "filterType": "DateRange",
                        "periodType": "CUSTOM",
                        "from": from_date.strftime("%Y-%m-%d"),
                        "to": to_date.strftime("%Y-%m-%d")
                    },
                    "OrderDeleted": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"]
                    },
                    "DeletedWithWriteoff": {
                        "filterType": "IncludeValues",
                        "values": ["NOT_DELETED"]
                    }
                }
            }
```

**Фильтры:**
- Учитываются только НЕ удаленные заказы (`NOT_DELETED`)
- Учитываются заказы без списаний (`NOT_DELETED`)
- Диапазон дат: `from_date` - `to_date`

### 2. Обработка данных

```109:155:app/services/iiko_sales_loader.py
    def process_sales_data(self, sales_data: List[dict]) -> tuple[List[dict], List[dict]]:
        """Process sales data to create summary and hourly records"""
        if not sales_data:
            return [], []
        
        # Convert to DataFrame for easier processing
        df = pd.DataFrame(sales_data)
        
        # Debug: log the first few records to understand structure
        logger.info(f"Sales data sample: {sales_data[:2] if len(sales_data) > 0 else 'empty'}")
        logger.info(f"DataFrame columns: {df.columns.tolist()}")
        
        # Parse datetime and extract components - handle mixed formats
        df['CloseTime'] = pd.to_datetime(df['CloseTime'], format='mixed')
        df['date'] = df['CloseTime'].dt.date
        df['hour'] = df['CloseTime'].dt.hour
        
        # Group by department and date for daily summary
        sales_summary = df.groupby(['Department.Id', 'date']).agg(
            total_sales=('DishSumInt', 'sum')
        ).reset_index()
        
        # Group by department, date, and hour for hourly summary
        sales_by_hour = df.groupby(['Department.Id', 'date', 'hour']).agg(
            sales_amount=('DishSumInt', 'sum')
        ).reset_index()
        
        # Convert to dictionaries
        summary_records = []
        for _, row in sales_summary.iterrows():
            summary_records.append({
                'department_id': row['Department.Id'],
                'date': row['date'],
                'total_sales': float(row['total_sales'])
            })
        
        hourly_records = []
        for _, row in sales_by_hour.iterrows():
            hourly_records.append({
                'department_id': row['Department.Id'],
                'date': row['date'],
                'hour': int(row['hour']),
                'sales_amount': float(row['sales_amount'])
            })
        
        logger.info(f"Processed {len(summary_records)} daily summary records and {len(hourly_records)} hourly records")
        return summary_records, hourly_records
```

**Результат обработки:**
- **Ежедневные сводки** (`SalesSummary`): сумма продаж по подразделению за день
- **Почасовые сводки** (`SalesByHour`): сумма продаж по подразделению за час

### 3. Сохранение в базу данных

#### Ежедневные сводки:

```157:194:app/services/iiko_sales_loader.py
    def sync_sales_summary(self, summary_records: List[dict]) -> int:
        """Sync sales summary records to database"""
        new_count = 0
        updated_count = 0
        
        for record in summary_records:
            # Check if department exists
            dept = self.db.query(Department).filter(Department.id == record['department_id']).first()
            if not dept:
                logger.warning(f"Department {record['department_id']} not found, skipping sales record")
                continue
            
            # Check if record already exists
            existing_record = self.db.query(SalesSummary).filter(
                SalesSummary.department_id == record['department_id'],
                SalesSummary.date == record['date']
            ).first()
            
            if existing_record:
                # Update existing record
                existing_record.total_sales = record['total_sales']
                existing_record.updated_at = datetime.utcnow()
                existing_record.synced_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new record
                new_record = SalesSummary(
                    department_id=record['department_id'],
                    date=record['date'],
                    total_sales=record['total_sales'],
                    synced_at=datetime.utcnow()
                )
                self.db.add(new_record)
                new_count += 1
        
        self.db.commit()
        logger.info(f"Synced {new_count} new and {updated_count} updated sales summary records")
        return new_count + updated_count
```

#### Почасовые сводки:

```196:235:app/services/iiko_sales_loader.py
    def sync_sales_by_hour(self, hourly_records: List[dict]) -> int:
        """Sync sales by hour records to database"""
        new_count = 0
        updated_count = 0
        
        for record in hourly_records:
            # Check if department exists
            dept = self.db.query(Department).filter(Department.id == record['department_id']).first()
            if not dept:
                logger.warning(f"Department {record['department_id']} not found, skipping hourly sales record")
                continue
            
            # Check if record already exists
            existing_record = self.db.query(SalesByHour).filter(
                SalesByHour.department_id == record['department_id'],
                SalesByHour.date == record['date'],
                SalesByHour.hour == record['hour']
            ).first()
            
            if existing_record:
                # Update existing record
                existing_record.sales_amount = record['sales_amount']
                existing_record.updated_at = datetime.utcnow()
                existing_record.synced_at = datetime.utcnow()
                updated_count += 1
            else:
                # Create new record
                new_record = SalesByHour(
                    department_id=record['department_id'],
                    date=record['date'],
                    hour=record['hour'],
                    sales_amount=record['sales_amount'],
                    synced_at=datetime.utcnow()
                )
                self.db.add(new_record)
                new_count += 1
        
        self.db.commit()
        logger.info(f"Synced {new_count} new and {updated_count} updated hourly sales records")
        return new_count + updated_count
```

**Логика сохранения:**
- Если подразделение не существует в БД → запись пропускается
- Если запись существует → обновляется
- Если запись новая → создается

---

## ⏰ Автоматическая синхронизация

### Планировщик задач:

Система использует **APScheduler** для автоматической синхронизации.

```26:67:app/main.py
# Initialize scheduler for automatic sales loading
scheduler = BackgroundScheduler()

@app.on_event("startup")
async def startup_event():
    """Initialize background scheduler on application startup"""
    try:
        # Schedule daily automatic sales loading at 2:00 AM
        scheduler.add_job(
            func=run_auto_sync,
            trigger="cron", 
            hour=2,
            minute=0,
            id='daily_sales_sync',
            name='Daily Sales Auto-Sync',
            replace_existing=True
        )
```

**Расписание:**
- **Время:** 02:00 каждый день
- **Задача:** Автоматическая синхронизация продаж за предыдущий день

### Процесс автоматической синхронизации:

```18:70:app/services/scheduled_sales_loader.py
    async def auto_load_sales(self) -> dict:
        """
        Automatically load sales data for the previous day
        This method is called by the scheduler
        """
        db: Session = next(get_db())
        
        try:
            # Calculate date range (previous day) 
            # iiko API requires different from_date and to_date (409 error if same)
            yesterday = date.today() - timedelta(days=1)
            from_date = yesterday
            # Use today as to_date to avoid 409 error
            to_date = date.today()
            
            self.logger.info(f"Starting automatic sales sync for {from_date}")
            
            # Create sales loader service
            sales_loader = IikoSalesLoaderService(db)
            
            # Perform sync
            result = await sales_loader.sync_sales(from_date, to_date)
            
            # Log the auto-sync attempt
            self._log_auto_sync(db, from_date, to_date, result)
            
            if result.get("status") == "success":
                self.logger.info(f"Automatic sales sync completed successfully: {result.get('message')}")
                self.logger.info(f"Records synced - Summary: {result.get('summary_records', 0)}, Hourly: {result.get('hourly_records', 0)}")
            else:
                self.logger.error(f"Automatic sales sync failed: {result.get('message')}")
                
            return result
```

**Особенности:**
- Синхронизируется **вчерашний день** (предыдущий день)
- `from_date = вчера`, `to_date = сегодня` (избегает ошибку 409 API)
- Результаты логируются в таблицу `AutoSyncLog`

### Логирование автоматической синхронизации:

```72:94:app/services/scheduled_sales_loader.py
    def _log_auto_sync(self, db: Session, from_date: date, to_date: date, result: dict):
        """Log automatic sync attempt to database"""
        try:
            log_entry = AutoSyncLog(
                sync_date=from_date,
                sync_type="daily_auto",
                status=result.get("status", "unknown"),
                message=result.get("message", "No message"),
                summary_records=result.get("summary_records", 0),
                hourly_records=result.get("hourly_records", 0),
                total_raw_records=result.get("total_raw_records", 0),
                error_details=result.get("details") if result.get("status") == "error" else None,
                executed_at=datetime.utcnow()
            )
            
            db.add(log_entry)
            db.commit()
            
            self.logger.info(f"Auto-sync log entry created for {from_date}")
            
        except Exception as e:
            self.logger.error(f"Failed to log auto-sync attempt: {e}")
            db.rollback()
```

---

## 🎯 Какие подразделения получают данные

### Принцип работы:

**Все подразделения, которые возвращает iiko API, автоматически получают записи по продажам.**

### Процесс:

1. **Загрузка данных из iiko API**
   - Запрос к OLAP API не фильтрует подразделения
   - Возвращаются все продажи для всех подразделений в указанном диапазоне дат

2. **Обработка данных**
   - Данные агрегируются по `Department.Id`
   - Группировка происходит по всем подразделениям из ответа API

3. **Сохранение в БД**
   - **Проверка существования подразделения:**

```164:167:app/services/iiko_sales_loader.py
            dept = self.db.query(Department).filter(Department.id == record['department_id']).first()
            if not dept:
                logger.warning(f"Department {record['department_id']} not found, skipping sales record")
                continue
```

   - Если подразделение **существует в БД** → данные сохраняются
   - Если подразделение **НЕ существует в БД** → данные **пропускаются** (с предупреждением в лог)

### Важные моменты:

1. **Нет явной фильтрации по типу подразделения**
   - Система получает данные для всех подразделений из iiko API
   - Типы подразделений: `DEPARTMENT`, `JURPERSON`, `CORPORATION`

2. **Фильтрация происходит на этапе сохранения**
   - Только подразделения, которые уже есть в таблице `departments`, получают данные
   - Если подразделение не синхронизировано из iiko → данные не сохраняются

3. **Рекомендация:**
   - Перед синхронизацией продаж нужно синхронизировать подразделения
   - Использовать эндпоинт `/departments/sync` для обновления списка подразделений

### Типы подразделений:

- **`DEPARTMENT`** - Торговые точки (реальные места продаж) ✅ **Основной тип для продаж**
- **`JURPERSON`** - Юридические лица (организационные единицы)
- **`CORPORATION`** - Корпорации (верхний уровень иерархии)

**Примечание:** Данные по продажам могут приходить для всех типов, но обычно реальные продажи идут только через тип `DEPARTMENT`.

---

## 🔄 Схема работы системы

```
┌─────────────────────────────────────────────────────────────────┐
│                    СИСТЕМА СИНХРОНИЗАЦИИ С iiko                  │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────┐
│ 1. АВТОРИЗАЦИЯ (IikoAuthService)                                 │
├──────────────────────────────────────────────────────────────────┤
│  Хранение: app/services/iiko_auth.py                              │
│  Логин: "Tanat"                                                   │
│  Пароль: "7c4a8d09ca3762af61e59520943dc26494f8941b"              │
│                                                                   │
│  Домены:                                                          │
│  • https://sandy-co-co.iiko.it                                    │
│  • https://madlen-group-so.iiko.it                                │
│                                                                   │
│  Процесс:                                                         │
│  GET /resto/api/auth?login=Tanat&pass=***                        │
│  → Получение токена (действителен 60 минут)                      │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 2. СИНХРОНИЗАЦИЯ ПОДРАЗДЕЛЕНИЙ (IikoDepartmentLoaderService)     │
├──────────────────────────────────────────────────────────────────┤
│  Эндпоинт: GET /resto/api/corporation/departments                │
│  Формат ответа: XML                                              │
│                                                                   │
│  Данные:                                                          │
│  • id (UUID)                                                      │
│  • parent_id (UUID)                                               │
│  • code, name, type, taxpayer_id_number                          │
│                                                                   │
│  Сохранение:                                                      │
│  → Таблица: departments                                           │
│  → Обработка иерархии (родители → дети)                          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 3. ЗАГРУЗКА ПРОДАЖ (IikoSalesLoaderService)                      │
├──────────────────────────────────────────────────────────────────┤
│  Эндпоинт: POST /resto/api/v2/reports/olap                        │
│                                                                   │
│  Запрос:                                                          │
│  {                                                                │
│    "reportType": "SALES",                                         │
│    "groupByRowFields": ["Department.Id", "CloseTime", "OrderNum"],│
│    "aggregateFields": ["DishSumInt"],                             │
│    "filters": {                                                   │
│      "OpenDate.Typed": {DateRange},                               │
│      "OrderDeleted": "NOT_DELETED",                              │
│      "DeletedWithWriteoff": "NOT_DELETED"                         │
│    }                                                              │
│  }                                                                │
│                                                                   │
│  Получение:                                                       │
│  → Сырые данные продаж по всем подразделениям                    │
│  → Агрегация по Department.Id                                    │
│                                                                   │
│  Обработка:                                                       │
│  → Ежедневные сводки (SalesSummary)                              │
│  → Почасовые сводки (SalesByHour)                                 │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 4. СОХРАНЕНИЕ В БД                                                │
├──────────────────────────────────────────────────────────────────┤
│  Проверка:                                                        │
│  • Подразделение существует в departments?                       │
│    ├─ ДА → Сохранить данные                                       │
│    └─ НЕТ → Пропустить (с предупреждением в лог)                  │
│                                                                   │
│  Таблицы:                                                         │
│  • sales_summary (ежедневные сводки)                             │
│  • sales_by_hour (почасовые сводки)                              │
│                                                                   │
│  Логика:                                                          │
│  • Если запись существует → Обновить                              │
│  • Если запись новая → Создать                                    │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ 5. АВТОМАТИЧЕСКАЯ СИНХРОНИЗАЦИЯ (ScheduledSalesLoaderService)    │
├──────────────────────────────────────────────────────────────────┤
│  Планировщик: APScheduler                                         │
│  Расписание: Ежедневно в 02:00                                    │
│                                                                   │
│  Процесс:                                                         │
│  1. Вычисление диапазона:                                         │
│     from_date = вчера                                             │
│     to_date = сегодня                                             │
│                                                                   │
│  2. Вызов IikoSalesLoaderService.sync_sales()                    │
│                                                                   │
│  3. Логирование результата:                                      │
│     → Таблица: auto_sync_log                                      │
│     → Поля: status, records, error_details                       │
└──────────────────────────────────────────────────────────────────┘
```

### Поток данных для одного подразделения:

```
iiko API
  │
  ├─> Получение токена (IikoAuthService)
  │
  ├─> Запрос подразделений (IikoDepartmentLoaderService)
  │   └─> departments: [id, name, type, ...]
  │
  ├─> Запрос продаж (IikoSalesLoaderService)
  │   └─> sales_data: [{Department.Id, CloseTime, DishSumInt}, ...]
  │
  ├─> Обработка данных
  │   ├─> Группировка по Department.Id + date
  │   │   └─> sales_summary: [{department_id, date, total_sales}]
  │   │
  │   └─> Группировка по Department.Id + date + hour
  │       └─> sales_by_hour: [{department_id, date, hour, sales_amount}]
  │
  ├─> Проверка существования подразделения
  │   └─> Если существует → Сохранить
  │       └─> Если нет → Пропустить
  │
  └─> Сохранение в БД
      ├─> sales_summary (ежедневные сводки)
      └─> sales_by_hour (почасовые сводки)
```

---

## 📝 Резюме

### Ключевые моменты:

1. **Учетные данные:**
   - Хранятся в коде (`app/services/iiko_auth.py`)
   - Один логин/пароль для обоих доменов
   - ⚠️ Требуется вынести в переменные окружения

2. **Подразделения:**
   - Загружаются из iiko API (`/resto/api/corporation/departments`)
   - Синхронизируются из обоих доменов
   - Сохраняются в таблицу `departments`
   - Обрабатываются с учетом иерархии

3. **Продажи:**
   - Загружаются для **всех подразделений** из ответа iiko API
   - Сохраняются только для подразделений, существующих в БД
   - Агрегируются в ежедневные и почасовые сводки

4. **Автоматическая синхронизация:**
   - Запускается ежедневно в 02:00
   - Синхронизирует данные за предыдущий день
   - Результаты логируются в `auto_sync_log`

5. **Фильтрация:**
   - Нет явной фильтрации по типу подразделения на этапе загрузки
   - Фильтрация происходит на этапе сохранения (проверка существования в БД)
   - Рекомендуется синхронизировать подразделения перед загрузкой продаж

---

## 🔧 Рекомендации по улучшению

1. **Безопасность:**
   - Вынести учетные данные в переменные окружения (.env)
   - Использовать секреты для хранения паролей

2. **Мониторинг:**
   - Добавить алерты при пропуске записей из-за отсутствующих подразделений
   - Автоматическая синхронизация подразделений перед синхронизацией продаж

3. **Производительность:**
   - Добавить батчинг для больших объемов данных
   - Оптимизировать запросы к БД

---

**Дата создания отчета:** 2024-12-19  
**Версия системы:** 0.1.0

