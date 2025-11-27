#!/usr/bin/env python3
"""
Проверка продаж Tary Shymkent за расширенные периоды
"""
import asyncio
import httpx
from datetime import date, timedelta
from collections import defaultdict

LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"
DOMAINS = ["https://sandy-co-co.iiko.it"]

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
            "groupByRowFields": ["Department.Id", "CloseTime", "OrderNum"],
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
    print("ПРОВЕРКА ПРОДАЖ TARY SHYMKENT ЗА РАСШИРЕННЫЕ ПЕРИОДЫ")
    print("=" * 80)
    print()
    
    dept_id = "a6761046-fc28-44a6-9357-f34772fa38a7"
    domain = "https://sandy-co-co.iiko.it"
    
    periods = [
        ("Сегодня", 0),
        ("Последние 3 дня", 3),
        ("Последние 7 дней", 7),
        ("Последние 14 дней", 14),
        ("Последние 30 дней", 30),
        ("Последние 60 дней", 60),
        ("Последние 90 дней", 90),
    ]
    
    print(f"Подразделение: Tary Shymkent")
    print(f"ID: {dept_id}")
    print(f"Домен: {domain}")
    print()
    print("=" * 80)
    print()
    
    for period_name, days in periods:
        if days == 0:
            from_date = date.today()
            to_date = date.today()
        else:
            from_date = date.today() - timedelta(days=days)
            to_date = date.today()
        
        print(f"{period_name} ({from_date} - {to_date}):")
        
        sales = await fetch_sales(dept_id, from_date, to_date, domain)
        
        if sales is None:
            print("  ❌ Ошибка запроса")
        elif sales:
            total_amount = sum(float(r.get('DishSumInt', 0)) for r in sales)
            
            # Группировка по дням
            daily = defaultdict(float)
            for record in sales:
                close_time = record.get('CloseTime', '')
                if close_time:
                    try:
                        if 'T' in str(close_time):
                            date_str = str(close_time).split('T')[0]
                        else:
                            date_str = str(close_time)[:10]
                        daily[date_str] += float(record.get('DishSumInt', 0))
                    except:
                        pass
            
            print(f"  ✓ Найдено записей: {len(sales)}")
            print(f"  ✓ Общая сумма: {total_amount:,.2f}")
            
            if daily:
                print(f"  Детализация по дням:")
                for day in sorted(daily.keys()):
                    print(f"    {day}: {daily[day]:,.2f}")
        else:
            print(f"  ✗ Продажи не найдены")
        
        print()
    
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


