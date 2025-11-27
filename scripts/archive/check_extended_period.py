#!/usr/bin/env python3
"""
Проверка продаж за расширенный период (месяц) для неактивных подразделений
"""
import asyncio
import httpx
from datetime import date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict

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

async def fetch_sales_for_department(department_id: str, from_date: date, to_date: date, base_url: str):
    """Получить продажи для конкретного подразделения"""
    try:
        token = await get_token(base_url)
        
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
                "Department.Id": {
                    "filterType": "IncludeValues",
                    "values": [department_id]
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
        print(f"    ❌ Ошибка: {e}")
        return []

async def main():
    print("=" * 80)
    print("ПРОВЕРКА ПРОДАЖ ЗА РАСШИРЕННЫЙ ПЕРИОД (30 дней)")
    print("=" * 80)
    print()
    
    # Получить неактивные подразделения
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT d.id, d.name, d.code, MAX(s.date) as last_sale_date
        FROM departments d
        JOIN sales_summary s ON d.id = s.department_id
        WHERE d.type = 'DEPARTMENT'
        GROUP BY d.id, d.name, d.code
        HAVING MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'
        ORDER BY d.name
    """)
    
    inactive_depts = cur.fetchall()
    cur.close()
    conn.close()
    
    print(f"Проверяем {len(inactive_depts)} неактивных подразделений")
    print()
    
    # Периоды для проверки
    periods = [
        ("Последние 7 дней", 7),
        ("Последние 14 дней", 14),
        ("Последние 30 дней", 30),
        ("Последние 60 дней", 60),
    ]
    
    results = {}
    
    for dept in inactive_depts:
        dept_id = str(dept['id'])
        dept_name = dept['name']
        last_sale = dept['last_sale_date'].strftime('%Y-%m-%d') if dept['last_sale_date'] else 'Никогда'
        
        print(f"\n{'='*80}")
        print(f"Подразделение: {dept_name}")
        print(f"ID: {dept_id}")
        print(f"Последняя продажа в БД: {last_sale}")
        print(f"{'='*80}")
        
        dept_results = {}
        
        for period_name, days in periods:
            from_date = date.today() - timedelta(days=days)
            to_date = date.today()
            
            print(f"\n  {period_name} ({from_date} - {to_date}):")
            
            found_any = False
            total_sales = 0
            total_records = 0
            
            for domain in DOMAINS:
                domain_name = domain.split('.')[1]  # Извлечь имя домена
                sales = await fetch_sales_for_department(dept_id, from_date, to_date, domain)
                
                if sales:
                    found_any = True
                    total = sum(float(r.get('DishSumInt', 0)) for r in sales)
                    total_sales += total
                    total_records += len(sales)
                    print(f"    {domain_name}: {len(sales)} записей, {total:,.2f}")
            
            dept_results[period_name] = {
                'found': found_any,
                'records': total_records,
                'amount': total_sales
            }
            
            if not found_any:
                print(f"    ⚠ Продажи не найдены")
            
            # Если нашли продажи, не проверяем большие периоды
            if found_any:
                break
        
        results[dept_id] = {
            'name': dept_name,
            'results': dept_results
        }
    
    # Итоговая сводка
    print("\n" + "=" * 80)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 80)
    print()
    
    found_in_any_period = []
    not_found_at_all = []
    
    for dept_id, dept_data in results.items():
        found = any(r['found'] for r in dept_data['results'].values())
        if found:
            found_in_any_period.append(dept_data)
        else:
            not_found_at_all.append(dept_data)
    
    print(f"Подразделений с продажами (в любом периоде): {len(found_in_any_period)}")
    print(f"Подразделений БЕЗ продаж (во всех периодах): {len(not_found_at_all)}")
    print()
    
    if found_in_any_period:
        print("ПОДРАЗДЕЛЕНИЯ С ПРОДАЖАМИ:")
        print(f"{'Название':<50} {'Период':<20} {'Записей':<10} {'Сумма':<15}")
        print("-" * 95)
        for dept in found_in_any_period:
            for period_name, period_result in dept['results'].items():
                if period_result['found']:
                    print(f"{dept['name']:<50} {period_name:<20} {period_result['records']:<10} {period_result['amount']:>15,.2f}")
                    break
        print()
    
    if not_found_at_all:
        print("ПОДРАЗДЕЛЕНИЯ БЕЗ ПРОДАЖ (во всех проверенных периодах):")
        for dept in not_found_at_all:
            print(f"  - {dept['name']}")
        print()
        print("⚠ Эти подразделения действительно не имеют продаж в iiko API")
        print("   за последние 60 дней. Возможные причины:")
        print("   • Подразделения закрыты или временно не работают")
        print("   • Подразделения не используют iiko для продаж")
        print("   • Проблемы с подключением подразделений к iiko")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


