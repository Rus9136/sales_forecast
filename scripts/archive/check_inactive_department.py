#!/usr/bin/env python3
"""
Проверка неактивных подразделений через iiko API
"""
import asyncio
import httpx
from datetime import date, timedelta

# Учетные данные
LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"
DOMAINS = [
    "https://sandy-co-co.iiko.it",
    "https://madlen-group-so.iiko.it"
]

async def get_token(base_url: str) -> str:
    """Получить токен авторизации"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/resto/api/auth",
            params={"login": LOGIN, "pass": PASSWORD}
        )
        response.raise_for_status()
        return response.text.strip()

async def check_department_sales(department_id: str, from_date: date, to_date: date, base_url: str):
    """Проверить продажи для подразделения"""
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
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/resto/api/v2/reports/olap",
                params={"key": token},
                json=request_body
            )
            response.raise_for_status()
            data = response.json()
            return data.get('data', [])
    except Exception as e:
        print(f"  Ошибка для {base_url}: {e}")
        return []

async def main():
    # Неактивные подразделения из анализа
    inactive_depts = [
        ("Anor Korday", "неизвестен"),
        ("Salam Bro Ayusai", "неизвестен"),
        ("Salam Bro Charyn", "неизвестен"),
    ]
    
    print("Проверка неактивных подразделений через iiko API...")
    print("=" * 80)
    
    # Получить ID из БД
    import psycopg2
    from psycopg2.extras import RealDictCursor
    
    conn = psycopg2.connect(
        host='localhost',
        port=5435,
        database='sales_forecast',
        user='sales_user',
        password='sales_password'
    )
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT id, name 
        FROM departments 
        WHERE type = 'DEPARTMENT'
        AND name IN ('Anor Korday', 'Salam Bro Ayusai', 'Salam Bro Charyn', 
                     'Sandyq Шымкент', 'Shopan Bateel')
        ORDER BY name
    """)
    
    depts_to_check = cur.fetchall()
    cur.close()
    conn.close()
    
    print(f"Найдено подразделений для проверки: {len(depts_to_check)}\n")
    
    from_date = date.today() - timedelta(days=60)
    to_date = date.today()
    
    for dept in depts_to_check[:3]:  # Проверим первые 3
        dept_id = str(dept['id'])
        print(f"\n{'='*80}")
        print(f"Подразделение: {dept['name']}")
        print(f"ID: {dept_id}")
        print(f"Период: {from_date} - {to_date}")
        print(f"{'='*80}")
        
        for domain in DOMAINS:
            print(f"\nПроверка домена: {domain}")
            sales = await check_department_sales(dept_id, from_date, to_date, domain)
            
            if sales:
                total = sum(float(r.get('DishSumInt', 0)) for r in sales)
                print(f"  ✓ Найдено {len(sales)} записей, сумма: {total:,.2f}")
            else:
                print(f"  ⚠ Продажи не найдены")

if __name__ == "__main__":
    asyncio.run(main())


