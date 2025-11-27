#!/usr/bin/env python3
"""
Проверка всех продаж за последнюю неделю без фильтра
для поиска подразделения Tary Shymkent
"""
import asyncio
import httpx
from datetime import date, timedelta
from collections import defaultdict

LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"
DOMAINS = [
    "https://sandy-co-co.iiko.it",
    "https://madlen-group-so.iiko.it"
]

async def get_token(base_url: str) -> str:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{base_url}/resto/api/auth",
            params={"login": LOGIN, "pass": PASSWORD}
        )
        response.raise_for_status()
        return response.text.strip()

async def fetch_all_sales(from_date: date, to_date: date, base_url: str):
    """Получить все продажи без фильтра"""
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
        return []

async def get_departments_from_api(base_url: str):
    """Получить список подразделений из API"""
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
            
            import xml.etree.ElementTree as ET
            root = ET.fromstring(response.text)
            
            departments = {}
            for item in root.findall('corporateItemDto'):
                dept_id = item.find('id')
                name = item.find('name')
                dept_type = item.find('type')
                
                if dept_id is not None and name is not None and (dept_type is None or dept_type.text == 'DEPARTMENT'):
                    departments[dept_id.text] = name.text
            
            return departments
    except Exception as e:
        print(f"Ошибка получения подразделений: {e}")
        return {}

async def main():
    print("=" * 80)
    print("ПОИСК ПРОДАЖ TARY SHYMKENT В ОБЩЕМ СПИСКЕ ПРОДАЖ")
    print("=" * 80)
    print()
    
    # Период: последняя неделя
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    
    print(f"Период: {from_date} - {to_date}")
    print()
    
    # ID Tary Shymkent из БД
    tary_shymkent_id = "a6761046-fc28-44a6-9357-f34772fa38a7"
    
    for domain in DOMAINS:
        domain_name = domain.replace('https://', '').replace('.iiko.it', '')
        print(f"{'='*80}")
        print(f"Домен: {domain_name}")
        print(f"{'='*80}")
        print()
        
        # Получить все продажи
        print("Загрузка всех продаж...")
        all_sales = await fetch_all_sales(from_date, to_date, domain)
        print(f"Получено записей: {len(all_sales)}")
        print()
        
        if not all_sales:
            print("Продажи не найдены")
            print()
            continue
        
        # Получить список подразделений из API
        print("Загрузка списка подразделений...")
        departments = await get_departments_from_api(domain)
        print(f"Получено подразделений: {len(departments)}")
        print()
        
        # Группировать по подразделениям
        dept_sales = defaultdict(lambda: {'count': 0, 'amount': 0.0})
        
        for record in all_sales:
            dept_id = record.get('Department.Id')
            amount = float(record.get('DishSumInt', 0))
            
            if dept_id:
                dept_sales[dept_id]['count'] += 1
                dept_sales[dept_id]['amount'] += amount
        
        print(f"Найдено уникальных подразделений с продажами: {len(dept_sales)}")
        print()
        
        # Искать Tary Shymkent
        print("Поиск Tary Shymkent...")
        print(f"ID в БД: {tary_shymkent_id}")
        print()
        
        found_by_id = tary_shymkent_id in dept_sales
        
        if found_by_id:
            sales_info = dept_sales[tary_shymkent_id]
            dept_name = departments.get(tary_shymkent_id, 'Неизвестно')
            print(f"✓ НАЙДЕНО ПО ID!")
            print(f"  Название: {dept_name}")
            print(f"  Записей: {sales_info['count']}")
            print(f"  Сумма: {sales_info['amount']:,.2f}")
        else:
            print(f"✗ Не найдено по ID")
            print()
            
            # Попробовать найти по названию
            print("Поиск по названию 'Tary Shymkent' или 'Shymkent'...")
            found_by_name = False
            
            for dept_id, dept_name in departments.items():
                if 'shymkent' in dept_name.lower() or 'tary' in dept_name.lower():
                    if dept_id in dept_sales:
                        sales_info = dept_sales[dept_id]
                        print(f"✓ Найдено похожее подразделение:")
                        print(f"  Название: {dept_name}")
                        print(f"  ID: {dept_id}")
                        print(f"  Записей: {sales_info['count']}")
                        print(f"  Сумма: {sales_info['amount']:,.2f}")
                        print()
                        print(f"⚠ ID в API отличается от ID в БД!")
                        print(f"   БД ID: {tary_shymkent_id}")
                        print(f"   API ID: {dept_id}")
                        found_by_name = True
            
            if not found_by_name:
                print("✗ Не найдено по названию")
        
        print()
        print("Все подразделения с продажами за неделю:")
        print(f"{'ID':<40} {'Название':<50} {'Записей':<10} {'Сумма':<15}")
        print("-" * 115)
        
        # Сортировать по сумме
        sorted_depts = sorted(dept_sales.items(), key=lambda x: x[1]['amount'], reverse=True)
        
        for dept_id, sales_info in sorted_depts[:20]:  # Показать первые 20
            dept_name = departments.get(dept_id, 'Неизвестно')
            name_display = (dept_name[:47] + '...') if len(dept_name) > 50 else dept_name
            print(f"{dept_id:<40} {name_display:<50} {sales_info['count']:<10} {sales_info['amount']:>15,.2f}")
        
        if len(sorted_depts) > 20:
            print(f"... и еще {len(sorted_depts) - 20} подразделений")
        
        print()
        print("-" * 80)
        print()

if __name__ == "__main__":
    asyncio.run(main())


