#!/usr/bin/env python3
"""
Детальная проверка продаж Tary Shymkent с полным логированием
"""
import asyncio
import httpx
from datetime import date, timedelta
import json

LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"
DOMAIN = "https://sandy-co-co.iiko.it"
DEPT_ID = "a6761046-fc28-44a6-9357-f34772fa38a7"

async def get_token():
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{DOMAIN}/resto/api/auth",
            params={"login": LOGIN, "pass": PASSWORD}
        )
        response.raise_for_status()
        return response.text.strip()

async def check_sales(from_date: date, to_date: date):
    token = await get_token()
    print(f"Токен получен: {token[:30]}...")
    print()
    
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
                "values": [DEPT_ID]
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
    
    print("Запрос:")
    print(json.dumps(request_body, indent=2, ensure_ascii=False))
    print()
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        url = f"{DOMAIN}/resto/api/v2/reports/olap"
        params = {"key": token}
        
        print(f"URL: {url}")
        print(f"Параметры: {params}")
        print()
        
        try:
            response = await client.post(url, params=params, json=request_body)
            
            print(f"Статус ответа: {response.status_code}")
            print(f"Заголовки: {dict(response.headers)}")
            print()
            
            if response.status_code != 200:
                print(f"Ошибка! Тело ответа:")
                print(response.text[:1000])
                return None
            
            data = response.json()
            
            print("Структура ответа:")
            print(f"  Ключи: {list(data.keys())}")
            print()
            
            sales_data = data.get('data', [])
            print(f"Найдено записей: {len(sales_data)}")
            
            if sales_data:
                print("\nПервая запись:")
                print(json.dumps(sales_data[0], indent=2, ensure_ascii=False))
                
                total = sum(float(r.get('DishSumInt', 0)) for r in sales_data)
                print(f"\nОбщая сумма: {total:,.2f}")
            else:
                print("\nДанные пусты или отсутствуют")
                print("Полный ответ:")
                print(json.dumps(data, indent=2, ensure_ascii=False)[:2000])
            
            return sales_data
            
        except httpx.HTTPStatusError as e:
            print(f"HTTP ошибка: {e}")
            print(f"Статус: {e.response.status_code}")
            print(f"Ответ: {e.response.text[:1000]}")
            return None
        except Exception as e:
            print(f"Ошибка: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

async def main():
    print("=" * 80)
    print("ДЕТАЛЬНАЯ ПРОВЕРКА ПРОДАЖ TARY SHYMKENT")
    print("=" * 80)
    print()
    print(f"Домен: {DOMAIN}")
    print(f"ID подразделения: {DEPT_ID}")
    print()
    
    # Проверить за последнюю неделю
    to_date = date.today()
    from_date = to_date - timedelta(days=7)
    
    print(f"Период: {from_date} - {to_date}")
    print()
    print("=" * 80)
    print()
    
    sales = await check_sales(from_date, to_date)
    
    print()
    print("=" * 80)
    
    # Также попробуем без фильтра по подразделению - получить все продажи
    print("\nПопытка получить ВСЕ продажи за неделю (без фильтра)...")
    print()
    
    token = await get_token()
    request_body_all = {
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
            "OrderDeleted": {
                "filterType": "IncludeValues",
                "values": ["NOT_DELETED"]
            }
        }
    }
    
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(
            f"{DOMAIN}/resto/api/v2/reports/olap",
            params={"key": token},
            json=request_body_all
        )
        response.raise_for_status()
        all_data = response.json().get('data', [])
        
        print(f"Всего записей в ответе: {len(all_data)}")
        
        # Найти наш ID
        found_records = [r for r in all_data if r.get('Department.Id') == DEPT_ID]
        
        if found_records:
            print(f"✓ НАЙДЕНО записей для Tary Shymkent: {len(found_records)}")
            total = sum(float(r.get('DishSumInt', 0)) for r in found_records)
            print(f"  Сумма: {total:,.2f}")
        else:
            print(f"✗ Записей для Tary Shymkent не найдено в общем ответе")
            
            # Показать какие ID есть
            unique_ids = set(r.get('Department.Id') for r in all_data if r.get('Department.Id'))
            print(f"\nНайдено {len(unique_ids)} уникальных подразделений в ответе")
            print("Первые 10 ID:")
            for i, dept_id in enumerate(list(unique_ids)[:10], 1):
                print(f"  {i}. {dept_id}")

if __name__ == "__main__":
    asyncio.run(main())


