#!/usr/bin/env python3
"""
Проверка продаж за последнюю неделю для всех неактивных подразделений
"""
import asyncio
import httpx
from datetime import date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor
from collections import defaultdict

# Учетные данные
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
    """Получить токен авторизации"""
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
        
        # Подготовить запрос БЕЗ фильтра по Department.Id (для проверки всех)
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
        print(f"  ❌ Ошибка: {e}")
        return []

async def check_department_with_filter(department_id: str, from_date: date, to_date: date, base_url: str):
    """Проверить продажи с фильтром по подразделению"""
    try:
        token = await get_token(base_url)
        
        # Попробуем с фильтром по Department.Id
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
        return None

async def main():
    print("=" * 80)
    print("ПРОВЕРКА ПРОДАЖ ЗА ПОСЛЕДНЮЮ НЕДЕЛЮ ДЛЯ НЕАКТИВНЫХ ПОДРАЗДЕЛЕНИЙ")
    print("=" * 80)
    print()
    
    # Получить неактивные подразделения из БД
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT d.id, d.name, d.code, MAX(s.date) as last_sale_date
        FROM departments d
        JOIN sales_summary s ON d.id = s.department_id
        WHERE d.type = 'DEPARTMENT'
        GROUP BY d.id, d.name, d.code
        HAVING MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'
        ORDER BY MAX(s.date) DESC
    """)
    
    inactive_depts = cur.fetchall()
    cur.close()
    conn.close()
    
    print(f"Найдено неактивных подразделений: {len(inactive_depts)}")
    print()
    
    # Период: последняя неделя
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    
    print(f"Период проверки: {from_date} - {to_date}")
    print()
    
    results = []
    
    # Сначала получим все продажи за неделю из обоих доменов
    print("Загрузка всех продаж за последнюю неделю из iiko API...")
    print()
    
    all_sales_by_domain = {}
    for domain in DOMAINS:
        print(f"Загрузка из {domain}...")
        sales = await fetch_sales_for_department("", from_date, to_date, domain)
        all_sales_by_domain[domain] = sales
        print(f"  Получено {len(sales)} записей")
        
        # Посмотрим какие подразделения есть в ответе
        dept_ids_in_response = set()
        for record in sales:
            dept_id = record.get('Department.Id')
            if dept_id:
                dept_ids_in_response.add(dept_id)
        
        print(f"  Уникальных подразделений в ответе: {len(dept_ids_in_response)}")
    
    print()
    
    # Теперь проверим каждое неактивное подразделение
    print("=" * 80)
    print("ПРОВЕРКА КАЖДОГО ПОДРАЗДЕЛЕНИЯ")
    print("=" * 80)
    print()
    
    for dept in inactive_depts:
        dept_id = str(dept['id'])
        dept_name = dept['name']
        last_sale = dept['last_sale_date'].strftime('%Y-%m-%d') if dept['last_sale_date'] else 'Никогда'
        days_ago = (date.today() - dept['last_sale_date']).days if dept['last_sale_date'] else 'N/A'
        
        print(f"\n{'='*80}")
        print(f"Подразделение: {dept_name}")
        print(f"ID: {dept_id}")
        print(f"Последняя продажа в БД: {last_sale} ({days_ago} дней назад)")
        print(f"{'='*80}")
        
        found_in_any_domain = False
        total_sales = 0
        total_records = 0
        
        # Проверить в каждом домене
        for domain in DOMAINS:
            print(f"\n  Проверка домена: {domain}")
            
            # Проверить есть ли это подразделение в общем ответе
            sales_for_dept = [
                s for s in all_sales_by_domain[domain]
                if s.get('Department.Id') == dept_id
            ]
            
            if sales_for_dept:
                found_in_any_domain = True
                total = sum(float(r.get('DishSumInt', 0)) for r in sales_for_dept)
                total_sales += total
                total_records += len(sales_for_dept)
                
                print(f"    ✓ Найдено продаж: {len(sales_for_dept)}")
                print(f"    ✓ Сумма: {total:,.2f}")
                
                # Показать по дням
                daily = defaultdict(float)
                for record in sales_for_dept:
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
                
                if daily:
                    print(f"    По дням:")
                    for day in sorted(daily.keys()):
                        print(f"      {day}: {daily[day]:,.2f}")
            else:
                # Попробуем прямой запрос с фильтром
                print(f"    Не найдено в общем ответе, пробуем прямой запрос...")
                direct_sales = await check_department_with_filter(dept_id, from_date, to_date, domain)
                
                if direct_sales is not None:
                    if direct_sales:
                        found_in_any_domain = True
                        total = sum(float(r.get('DishSumInt', 0)) for r in direct_sales)
                        total_sales += total
                        total_records += len(direct_sales)
                        print(f"    ✓ Найдено продаж (прямой запрос): {len(direct_sales)}")
                        print(f"    ✓ Сумма: {total:,.2f}")
                    else:
                        print(f"    ⚠ Продажи не найдены")
                else:
                    print(f"    ⚠ Ошибка при запросе")
        
        result = {
            'id': dept_id,
            'name': dept_name,
            'found_in_api': found_in_any_domain,
            'total_records': total_records,
            'total_amount': total_sales,
            'last_sale_in_db': last_sale
        }
        results.append(result)
        
        if not found_in_any_domain:
            print(f"\n  ⚠⚠⚠ ПРОДАЖИ НЕ НАЙДЕНЫ В iiko API ⚠⚠⚠")
        
        print()
    
    # Итоговая сводка
    print("=" * 80)
    print("ИТОГОВАЯ СВОДКА")
    print("=" * 80)
    print()
    
    found_count = sum(1 for r in results if r['found_in_api'])
    not_found_count = len(results) - found_count
    
    print(f"Подразделений с продажами в iiko API: {found_count}")
    print(f"Подразделений БЕЗ продаж в iiko API: {not_found_count}")
    print()
    
    if found_count > 0:
        print("Подразделения С ПРОДАЖАМИ:")
        print(f"{'Название':<50} {'Записей':<10} {'Сумма':<15}")
        print("-" * 75)
        for r in results:
            if r['found_in_api']:
                print(f"{r['name']:<50} {r['total_records']:<10} {r['total_amount']:>15,.2f}")
        print()
    
    if not_found_count > 0:
        print("Подразделения БЕЗ ПРОДАЖ:")
        for r in results:
            if not r['found_in_api']:
                print(f"  - {r['name']} (ID: {r['id']})")
        print()
        print("⚠ ВОЗМОЖНЫЕ ПРИЧИНЫ:")
        print("  1. ID подразделения в БД не совпадает с ID в iiko")
        print("  2. Подразделение находится в другом домене")
        print("  3. Подразделение действительно не имеет продаж")
        print("  4. Проблема с форматом ID (UUID vs строка)")
    
    print()
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


