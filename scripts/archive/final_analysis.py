#!/usr/bin/env python3
"""
Финальный анализ: проверка продаж с даты последней продажи в БД
"""
import asyncio
import httpx
from datetime import date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"
DOMAINS = [
    "https://sandy-co-co.iiko.it",
    "https://madlen-group-so.iiko.it"
]

DB_CONFIG = {
    'host': 'localhost',
    'port': 5435,
    'database': 'sales_forecast',
    'user': 'sales_user',
    'password': 'sales_password'
}

async def get_token(base_url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/resto/api/auth",
            params={"login": LOGIN, "pass": PASSWORD}
        )
        response.raise_for_status()
        return response.text.strip()

async def fetch_sales(department_id: str, from_date: date, to_date: date, base_url: str):
    try:
        token = await get_token(base_url)
        
        request_body = {
            "reportType": "SALES",
            "groupByRowFields": ["Department.Id", "CloseTime"],
            "aggregateFields": ["DishSumInt"],
            "filters": {
                "OpenDate.Typed": {
                    "filterType": "DateRange",
                    "periodType": "CUSTOM",
                    "from": from_date.strftime("%Y-%m-%d"),
                    "to": to_date.strftime("%Y-%m-%d")
                },
                "Department.Id": {
                    "filterType": "IncludeValues",
                    "values": [department_id]
                },
                "OrderDeleted": {
                    "filterType": "IncludeValues",
                    "values": ["NOT_DELETED"]
                }
            }
        }
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/resto/api/v2/reports/olap",
                params={"key": token},
                json=request_body
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
    except Exception as e:
        return None

async def main():
    print("=" * 80)
    print("ФИНАЛЬНЫЙ АНАЛИЗ: ПРОВЕРКА ПРОДАЖ С ДАТЫ ПОСЛЕДНЕЙ ПРОДАЖИ В БД")
    print("=" * 80)
    print()
    
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT d.id, d.name, MAX(s.date) as last_sale_date
        FROM departments d
        JOIN sales_summary s ON d.id = s.department_id
        WHERE d.type = 'DEPARTMENT'
        GROUP BY d.id, d.name
        HAVING MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'
        ORDER BY d.name
    """)
    
    inactive_depts = cur.fetchall()
    cur.close()
    conn.close()
    
    print(f"Проверяем {len(inactive_depts)} подразделений")
    print()
    
    results = []
    
    for dept in inactive_depts:
        dept_id = str(dept['id'])
        dept_name = dept['name']
        last_sale_date = dept['last_sale_date']
        
        # Проверить продажи с даты последней продажи в БД до сегодня
        from_date = last_sale_date + timedelta(days=1)
        to_date = date.today()
        
        days_since = (to_date - last_sale_date).days
        
        print(f"\n{'='*80}")
        print(f"{dept_name}")
        print(f"Последняя продажа в БД: {last_sale_date}")
        print(f"Проверяем период: {from_date} - {to_date} ({days_since} дней)")
        print(f"{'='*80}")
        
        found_sales = False
        total_amount = 0
        total_records = 0
        
        for domain in DOMAINS:
            domain_name = domain.split('.')[1]
            sales = await fetch_sales(dept_id, from_date, to_date, domain)
            
            if sales is None:
                print(f"  {domain_name}: Ошибка запроса")
                continue
            
            if sales:
                found_sales = True
                total = sum(float(r.get('DishSumInt', 0)) for r in sales)
                total_amount += total
                total_records += len(sales)
                print(f"  {domain_name}: ✓ {len(sales)} записей, {total:,.2f}")
            else:
                print(f"  {domain_name}: ✗ Продажи не найдены")
        
        if found_sales:
            print(f"\n  ⚠⚠⚠ НАЙДЕНЫ ПРОДАЖИ, КОТОРЫЕ НЕ СИНХРОНИЗИРОВАНЫ В БД! ⚠⚠⚠")
            print(f"     Записей: {total_records}")
            print(f"     Сумма: {total_amount:,.2f}")
        
        results.append({
            'name': dept_name,
            'id': dept_id,
            'last_sale_in_db': last_sale_date,
            'found_sales': found_sales,
            'records': total_records,
            'amount': total_amount
        })
    
    # Итоговая сводка
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 80)
    print()
    
    with_missing_sales = [r for r in results if r['found_sales']]
    without_sales = [r for r in results if not r['found_sales']]
    
    print(f"Подразделений с НЕСИНХРОНИЗИРОВАННЫМИ продажами: {len(with_missing_sales)}")
    print(f"Подразделений БЕЗ продаж в iiko: {len(without_sales)}")
    print()
    
    if with_missing_sales:
        print("⚠ ПРОБЛЕМА: ЕСТЬ ПРОДАЖИ В iiko API, КОТОРЫЕ НЕ СИНХРОНИЗИРОВАНЫ В БД!")
        print()
        print(f"{'Название':<50} {'Дней назад':<12} {'Записей':<10} {'Сумма':<15}")
        print("-" * 87)
        for r in with_missing_sales:
            days = (date.today() - r['last_sale_in_db']).days
            print(f"{r['name']:<50} {days:<12} {r['records']:<10} {r['amount']:>15,.2f}")
        print()
        print("ПРИЧИНА:")
        print("  Автоматическая синхронизация работает только для ВЧЕРАШНЕГО дня.")
        print("  Продажи за другие дни не синхронизируются автоматически.")
        print()
        print("РЕШЕНИЕ:")
        print("  1. Запустить ручную синхронизацию для этих периодов")
        print("  2. Или изменить автоматическую синхронизацию на больший период")
    
    if without_sales:
        print("\nПодразделения БЕЗ продаж в iiko API:")
        for r in without_sales:
            days = (date.today() - r['last_sale_in_db']).days
            print(f"  - {r['name']} (последняя продажа в БД: {r['last_sale_in_db']}, {days} дней назад)")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


