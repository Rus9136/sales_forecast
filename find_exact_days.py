#!/usr/bin/env python3
"""
Скрипт для поиска точного количества дней для получения 6008 записей
"""

from datetime import datetime, timedelta
from sqlalchemy import create_engine, text

DATABASE_URL = "postgresql://sales_user:sales_password@localhost:5435/sales_forecast"
engine = create_engine(DATABASE_URL)

end_date = datetime.now().date()

# Бинарный поиск нужного количества дней
low, high = 180, 365
target = 6008

while low <= high:
    mid = (low + high) // 2
    start_date = end_date - timedelta(days=mid)
    
    query = f"""
    SELECT COUNT(*) as cnt
    FROM sales_summary ss
    WHERE ss.date >= '{start_date}' 
    AND ss.date <= '{end_date}'
    AND ss.total_sales > 0
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        count = result.scalar()
    
    # Учитываем dropna после rolling features (~273 записи на 39 департаментов)
    # При 39 департаментах и lag_7d мы теряем примерно 7 * 39 = 273 записи
    estimated_after_dropna = count - 273
    
    print(f"Дней: {mid}, Записей в БД: {count}, После dropna (оценка): {estimated_after_dropna}")
    
    if abs(estimated_after_dropna - target) < 50:  # Близко к цели
        # Проверяем точнее в окрестности
        for d in range(mid-5, mid+6):
            if d < 0: continue
            test_start = end_date - timedelta(days=d)
            query_test = f"""
            SELECT COUNT(*) as cnt
            FROM sales_summary ss
            WHERE ss.date >= '{test_start}' 
            AND ss.date <= '{end_date}'
            AND ss.total_sales > 0
            """
            with engine.connect() as conn:
                result = conn.execute(text(query_test))
                test_count = result.scalar()
            test_estimated = test_count - 273
            print(f"  -> {d} дней: {test_count} записей, после dropna: {test_estimated}")
            if abs(test_estimated - target) < 10:
                print(f"\n✅ НАЙДЕНО: При {d} днях получаем примерно {test_estimated} записей после dropna!")
        break
    
    if estimated_after_dropna < target:
        low = mid + 1
    else:
        high = mid - 1

# Дополнительная проверка - возможно модель была обучена на старых данных
print("\n\n=== ПРОВЕРКА ГИПОТЕЗЫ О СТАРЫХ ДАННЫХ ===")
print("Возможно, модель была обучена когда было больше данных в БД.")
print("Проверяем количество записей на разные даты окончания периода:")

for days_ago in [0, 7, 14, 30, 60]:
    check_end_date = end_date - timedelta(days=days_ago)
    check_start_date = check_end_date - timedelta(days=180)
    
    query = f"""
    SELECT COUNT(*) as cnt
    FROM sales_summary ss
    WHERE ss.date >= '{check_start_date}' 
    AND ss.date <= '{check_end_date}'
    AND ss.total_sales > 0
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query))
        count = result.scalar()
    
    estimated = count - 273
    print(f"\n{days_ago} дней назад (период: {check_start_date} - {check_end_date}):")
    print(f"  Записей: {count}, после dropna: {estimated}")
    
    if abs(estimated - 6008) < 50:
        print(f"  ⚠️ БЛИЗКО К ЦЕЛЕВОМУ ЗНАЧЕНИЮ!")