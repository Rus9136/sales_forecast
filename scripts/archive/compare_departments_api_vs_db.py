#!/usr/bin/env python3
"""
Сравнение подразделений из API с подразделениями в БД
Проверка по названиям для выявления несоответствия ID
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
    """Получить токен авторизации"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/resto/api/auth",
            params={"login": LOGIN, "pass": PASSWORD}
        )
        response.raise_for_status()
        return response.text.strip()

async def fetch_departments_from_api(base_url: str):
    """Получить список подразделений из iiko API"""
    try:
        token = await get_token(base_url)
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/resto/api/corporation/departments",
                params={
                    "key": token,
                    "revisionFrom": -1
                }
            )
            response.raise_for_status()
            
            # Парсим XML
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            
            departments = []
            for item in root.findall('corporateItemDto'):
                dept_id = item.find('id')
                name = item.find('name')
                code = item.find('code')
                dept_type = item.find('type')
                
                if dept_id is not None and name is not None:
                    departments.append({
                        'id': dept_id.text if dept_id is not None else None,
                        'name': name.text if name is not None else '',
                        'code': code.text if code is not None else None,
                        'type': dept_type.text if dept_type is not None else 'DEPARTMENT'
                    })
            
            return departments
    except Exception as e:
        print(f"Ошибка получения подразделений из {base_url}: {e}")
        return []

async def fetch_sales_departments(base_url: str, from_date: date, to_date: date):
    """Получить список подразделений из ответа продаж"""
    try:
        token = await get_token(base_url)
        
        request_body = {
            "reportType": "SALES",
            "groupByRowFields": ["Department.Id"],
            "aggregateFields": ["DishSumInt"],
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
            
            # Извлечь уникальные ID подразделений
            dept_ids = set()
            for record in data.get('data', []):
                dept_id = record.get('Department.Id')
                if dept_id:
                    dept_ids.add(dept_id)
            
            return dept_ids
    except Exception as e:
        print(f"Ошибка получения продаж из {base_url}: {e}")
        return set()

async def main():
    print("=" * 80)
    print("СРАВНЕНИЕ ПОДРАЗДЕЛЕНИЙ: API vs БД")
    print("=" * 80)
    print()
    
    # Получить подразделения из БД
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    cur.execute("""
        SELECT id, name, code, type
        FROM departments
        WHERE type = 'DEPARTMENT'
        ORDER BY name
    """)
    db_departments = {str(row['id']): row for row in cur.fetchall()}
    
    # Получить неактивные подразделения
    cur.execute("""
        SELECT d.id, d.name, d.code, MAX(s.date) as last_sale_date
        FROM departments d
        JOIN sales_summary s ON d.id = s.department_id
        WHERE d.type = 'DEPARTMENT'
        GROUP BY d.id, d.name, d.code
        HAVING MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'
        ORDER BY d.name
    """)
    inactive_depts = {str(row['id']): row for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    
    print(f"Подразделений в БД: {len(db_departments)}")
    print(f"Неактивных подразделений: {len(inactive_depts)}")
    print()
    
    # Период для проверки продаж
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    
    all_api_departments = {}
    all_sales_dept_ids = set()
    
    # Проверить каждый домен
    for domain in DOMAINS:
        print(f"{'='*80}")
        print(f"Домен: {domain}")
        print(f"{'='*80}")
        print()
        
        # Получить подразделения из API
        print("Загрузка подразделений из API...")
        api_depts = await fetch_departments_from_api(domain)
        print(f"  Получено подразделений: {len(api_depts)}")
        
        # Получить подразделения из ответа продаж
        print("Загрузка подразделений из ответа продаж...")
        sales_dept_ids = await fetch_sales_departments(domain, from_date, to_date)
        print(f"  Подразделений с продажами: {len(sales_dept_ids)}")
        
        # Сохранить для сравнения
        for dept in api_depts:
            if dept['type'] == 'DEPARTMENT':
                dept_id = dept['id']
                all_api_departments[dept_id] = dept
                if dept_id in sales_dept_ids:
                    all_api_departments[dept_id]['has_sales'] = True
                else:
                    all_api_departments[dept_id]['has_sales'] = False
        
        all_sales_dept_ids.update(sales_dept_ids)
        
        print()
    
    print("=" * 80)
    print("АНАЛИЗ НЕСООТВЕТСТВИЙ")
    print("=" * 80)
    print()
    
    # Сравнить по названиям
    print("Поиск подразделений по названиям...")
    print()
    
    matches_by_name = {}
    not_found_in_api = []
    
    for dept_id, dept_info in inactive_depts.items():
        dept_name = dept_info['name']
        found = False
        
        # Искать по названию в API
        for api_id, api_dept in all_api_departments.items():
            if api_dept['name'].strip() == dept_name.strip():
                found = True
                matches_by_name[dept_id] = {
                    'db_id': dept_id,
                    'db_name': dept_name,
                    'api_id': api_id,
                    'api_name': api_dept['name'],
                    'has_sales_in_api': api_dept.get('has_sales', False)
                }
                break
        
        if not found:
            not_found_in_api.append({
                'id': dept_id,
                'name': dept_name,
                'code': dept_info.get('code')
            })
    
    print(f"Найдено совпадений по названию: {len(matches_by_name)}")
    print(f"Не найдено в API: {len(not_found_in_api)}")
    print()
    
    if matches_by_name:
        print("=" * 80)
        print("НАЙДЕННЫЕ НЕСООТВЕТСТВИЯ ID:")
        print("=" * 80)
        print()
        print(f"{'Название':<50} {'ID в БД':<40} {'ID в API':<40} {'Продажи в API':<15}")
        print("-" * 145)
        
        for db_id, match in matches_by_name.items():
            sales_status = "✓ Есть" if match['has_sales_in_api'] else "✗ Нет"
            print(f"{match['db_name']:<50} {match['db_id']:<40} {match['api_id']:<40} {sales_status:<15}")
        
        print()
        print("⚠ ПРОБЛЕМА: ID подразделений в БД не совпадают с ID в iiko API!")
        print("   Это означает, что подразделения были переименованы или их ID изменились.")
        print("   Нужно обновить ID в БД или синхронизировать подразделения заново.")
        print()
    
    if not_found_in_api:
        print("=" * 80)
        print("ПОДРАЗДЕЛЕНИЯ, НЕ НАЙДЕННЫЕ В API:")
        print("=" * 80)
        print()
        for dept in not_found_in_api:
            print(f"  - {dept['name']} (ID: {dept['id']}, код: {dept.get('code', 'N/A')})")
        print()
        print("Эти подразделения могут быть:")
        print("  • Закрыты в iiko")
        print("  • Удалены из iiko")
        print("  • Перемещены в другой домен")
        print()
    
    # Показать подразделения из API, которых нет в БД
    api_names = {dept['name']: dept for dept in all_api_departments.values()}
    db_names = {row['name']: row for row in db_departments.values()}
    
    new_in_api = []
    for name, api_dept in api_names.items():
        if name not in db_names:
            new_in_api.append(api_dept)
    
    if new_in_api:
        print("=" * 80)
        print("НОВЫЕ ПОДРАЗДЕЛЕНИЯ В API (нет в БД):")
        print("=" * 80)
        print()
        for dept in new_in_api[:10]:
            sales = "✓ Есть продажи" if dept.get('has_sales') else "✗ Нет продаж"
            print(f"  - {dept['name']} (ID: {dept['id']}) {sales}")
        if len(new_in_api) > 10:
            print(f"  ... и еще {len(new_in_api) - 10}")
        print()
    
    print("=" * 80)

if __name__ == "__main__":
    asyncio.run(main())


