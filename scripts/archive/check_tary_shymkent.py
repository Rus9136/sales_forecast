#!/usr/bin/env python3
"""
Проверка продаж для Tary Shymkent за последнюю неделю
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
        print(f"  ❌ Ошибка: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"     Статус: {e.response.status_code}")
            print(f"     Ответ: {e.response.text[:500]}")
        return []

async def main():
    print("=" * 80)
    print("ПРОВЕРКА ПРОДАЖ: Tary Shymkent")
    print("=" * 80)
    print()
    
    # Получить ID подразделения из БД
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT id, name, code, type
        FROM departments
        WHERE name = 'Tary Shymkent'
        AND type = 'DEPARTMENT'
    """)
    
    dept = cur.fetchone()
    
    if not dept:
        print("❌ Подразделение 'Tary Shymkent' не найдено в БД")
        cur.close()
        conn.close()
        return
    
    dept_id = str(dept['id'])
    
    # Получить последнюю продажу в БД
    cur.execute("""
        SELECT MAX(date) as last_sale_date, MAX(total_sales) as last_sale_amount
        FROM sales_summary
        WHERE department_id = %s
    """, (dept['id'],))
    
    last_sale = cur.fetchone()
    cur.close()
    conn.close()
    
    print(f"Подразделение: {dept['name']}")
    print(f"ID: {dept_id}")
    print(f"Код: {dept['code'] or 'N/A'}")
    if last_sale and last_sale['last_sale_date']:
        days_ago = (date.today() - last_sale['last_sale_date']).days
        print(f"Последняя продажа в БД: {last_sale['last_sale_date']} ({days_ago} дней назад)")
        print(f"Сумма последней продажи: {last_sale['last_sale_amount']:,.2f}")
    else:
        print("Последняя продажа в БД: Нет данных")
    print()
    
    # Период: последняя неделя
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    
    print(f"Период проверки: {from_date} - {to_date}")
    print()
    print("=" * 80)
    print()
    
    all_sales = []
    
    # Проверить в каждом домене
    for domain in DOMAINS:
        domain_name = domain.replace('https://', '').replace('.iiko.it', '')
        print(f"Запрос к домену: {domain_name}")
        print(f"URL: {domain}")
        print()
        
        sales = await fetch_sales_for_department(dept_id, from_date, to_date, domain)
        
        if sales:
            print(f"✓ Найдено записей: {len(sales)}")
            
            # Анализ по дням
            daily_sales = defaultdict(lambda: {'count': 0, 'amount': 0.0})
            
            for record in sales:
                close_time = record.get('CloseTime', '')
                amount = float(record.get('DishSumInt', 0))
                
                # Извлечь дату
                if close_time:
                    try:
                        if 'T' in str(close_time):
                            date_str = str(close_time).split('T')[0]
                        else:
                            date_str = str(close_time)[:10]
                        daily_sales[date_str]['count'] += 1
                        daily_sales[date_str]['amount'] += amount
                    except Exception as e:
                        pass
            
            # Вывести детализацию по дням
            print(f"\nДетализация по дням:")
            print(f"{'Дата':<12} {'Заказов':<10} {'Сумма':<15}")
            print("-" * 40)
            
            total_amount = 0
            total_count = 0
            
            for day in sorted(daily_sales.keys()):
                day_info = daily_sales[day]
                total_amount += day_info['amount']
                total_count += day_info['count']
                print(f"{day:<12} {day_info['count']:<10} {day_info['amount']:>15,.2f}")
            
            print("-" * 40)
            print(f"{'ИТОГО':<12} {total_count:<10} {total_amount:>15,.2f}")
            
            # Показать первые несколько записей
            print(f"\nПервые 5 записей:")
            print(f"{'Дата/Время':<20} {'Номер заказа':<15} {'Сумма':<15}")
            print("-" * 50)
            for i, record in enumerate(sales[:5], 1):
                close_time = record.get('CloseTime', 'N/A')
                order_num = record.get('OrderNum', 'N/A')
                amount = float(record.get('DishSumInt', 0))
                
                # Форматировать время
                if 'T' in str(close_time):
                    time_str = str(close_time).replace('T', ' ')[:19]
                else:
                    time_str = str(close_time)[:19]
                
                print(f"{time_str:<20} {str(order_num):<15} {amount:>15,.2f}")
            
            all_sales.extend(sales)
            
        else:
            print("✗ Продажи не найдены")
        
        print()
        print("-" * 80)
        print()
    
    # Итоговая сводка
    print("=" * 80)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 80)
    print()
    
    if all_sales:
        total_amount = sum(float(r.get('DishSumInt', 0)) for r in all_sales)
        print(f"✓ ПРОДАЖИ НАЙДЕНЫ")
        print(f"  Всего записей: {len(all_sales)}")
        print(f"  Общая сумма: {total_amount:,.2f}")
        print()
        
        # Проверить, есть ли эти данные в БД
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        cur.execute("""
            SELECT COUNT(*) as count, SUM(total_sales) as total
            FROM sales_summary
            WHERE department_id = %s
            AND date >= %s
            AND date <= %s
        """, (dept['id'], from_date, to_date))
        
        db_stats = cur.fetchone()
        cur.close()
        conn.close()
        
        if db_stats and db_stats['count'] > 0:
            print(f"В БД за этот период:")
            print(f"  Записей: {db_stats['count']}")
            print(f"  Сумма: {float(db_stats['total'] or 0):,.2f}")
            print()
            print(f"⚠ РАЗНИЦА:")
            print(f"  Записей в API: {len(all_sales)}, в БД: {db_stats['count']}")
            print(f"  Сумма в API: {total_amount:,.2f}, в БД: {float(db_stats['total'] or 0):,.2f}")
        else:
            print(f"⚠ В БД НЕТ ДАННЫХ за этот период!")
            print(f"   Это означает, что синхронизация не работала для этого подразделения.")
            print(f"   Нужно запустить синхронизацию для периода {from_date} - {to_date}")
    else:
        print("✗ ПРОДАЖИ НЕ НАЙДЕНЫ в iiko API за последнюю неделю")
        print()
        print("Возможные причины:")
        print("  1. Подразделение действительно не имело продаж")
        print("  2. ID подразделения неверный")
        print("  3. Подразделение находится в другом домене")
        print("  4. Проблемы с доступом к данным")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


