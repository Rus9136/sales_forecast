#!/usr/bin/env python3
"""
Скрипт для ручной проверки продаж конкретного подразделения в iiko API
Использование: python check_department_sales.py <department_id> [--from-date YYYY-MM-DD] [--to-date YYYY-MM-DD]
"""
import sys
import asyncio
import argparse
from datetime import date, timedelta
from typing import List, Dict, Any
import httpx

# Add app directory to path
import os
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

from app.services.iiko_auth import IikoAuthService
from app.services.iiko_sales_loader import IikoSalesLoaderService
from app.db import get_db
from app.models.branch import Department


async def fetch_sales_for_department(
    department_id: str,
    from_date: date,
    to_date: date,
    base_url: str
) -> List[Dict[str, Any]]:
    """Получить продажи для конкретного подразделения из iiko API"""
    try:
        # Получить токен авторизации
        auth_service = IikoAuthService(base_url)
        token = await auth_service._refresh_token()
        print(f"✓ Получен токен авторизации для {base_url}")
        
        # Подготовить запрос с фильтром по подразделению
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
        
        print(f"📤 Отправка запроса к iiko API...")
        print(f"   Подразделение: {department_id}")
        print(f"   Период: {from_date} - {to_date}")
        print(f"   Домен: {base_url}")
        
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{base_url}/resto/api/v2/reports/olap",
                params={"key": token},
                json=request_body
            )
            response.raise_for_status()
            
            # Проверить формат ответа
            try:
                response_data = response.json()
            except Exception as json_error:
                print(f"❌ Ошибка парсинга JSON: {json_error}")
                print(f"   Ответ: {response.text[:500]}")
                return []
            
            # Извлечь данные
            sales_data = response_data.get('data', [])
            print(f"✓ Получено {len(sales_data)} записей продаж")
            
            return sales_data
            
    except httpx.HTTPError as e:
        print(f"❌ HTTP ошибка: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"   Статус: {e.response.status_code}")
            print(f"   Ответ: {e.response.text[:500]}")
        return []
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        return []


async def check_department_in_all_domains(
    department_id: str,
    from_date: date,
    to_date: date
) -> Dict[str, List[Dict[str, Any]]]:
    """Проверить продажи подразделения во всех доменах"""
    domains = [
        "https://sandy-co-co.iiko.it",
        "https://madlen-group-so.iiko.it"
    ]
    
    results = {}
    
    for domain in domains:
        print(f"\n{'='*80}")
        print(f"Проверка домена: {domain}")
        print(f"{'='*80}")
        
        sales = await fetch_sales_for_department(department_id, from_date, to_date, domain)
        results[domain] = sales
        
        if sales:
            total_amount = sum(float(record.get('DishSumInt', 0)) for record in sales)
            print(f"✓ Найдено продаж на сумму: {total_amount:,.2f}")
        else:
            print("⚠ Продажи не найдены")
    
    return results


def print_sales_summary(sales_data: List[Dict[str, Any]], domain: str):
    """Вывести сводку по продажам"""
    if not sales_data:
        print(f"\n⚠ Нет данных о продажах для домена {domain}")
        return
    
    print(f"\n{'='*80}")
    print(f"СВОДКА ПО ПРОДАЖАМ - {domain}")
    print(f"{'='*80}")
    
    # Группировать по датам
    from collections import defaultdict
    daily_sales = defaultdict(float)
    
    for record in sales_data:
        close_time = record.get('CloseTime', '')
        amount = float(record.get('DishSumInt', 0))
        
        # Извлечь дату из CloseTime
        if close_time:
            try:
                # CloseTime может быть в формате "2024-12-19T10:30:00" или другом
                if 'T' in str(close_time):
                    date_str = str(close_time).split('T')[0]
                else:
                    date_str = str(close_time)[:10]
                daily_sales[date_str] += amount
            except:
                pass
    
    print(f"\nВсего записей: {len(sales_data)}")
    print(f"Дней с продажами: {len(daily_sales)}")
    print(f"Общая сумма: {sum(daily_sales.values()):,.2f}")
    
    print(f"\nДетализация по дням:")
    print(f"{'Дата':<12} {'Сумма':<15}")
    print("-" * 30)
    for date_str in sorted(daily_sales.keys()):
        print(f"{date_str:<12} {daily_sales[date_str]:>15,.2f}")


async def main():
    parser = argparse.ArgumentParser(
        description='Проверка продаж конкретного подразделения в iiko API'
    )
    parser.add_argument(
        'department_id',
        help='ID подразделения (UUID)'
    )
    parser.add_argument(
        '--from-date',
        type=str,
        default=None,
        help='Начальная дата (YYYY-MM-DD), по умолчанию: 30 дней назад'
    )
    parser.add_argument(
        '--to-date',
        type=str,
        default=None,
        help='Конечная дата (YYYY-MM-DD), по умолчанию: сегодня'
    )
    
    args = parser.parse_args()
    
    # Определить даты
    if args.from_date:
        from_date = date.fromisoformat(args.from_date)
    else:
        from_date = date.today() - timedelta(days=30)
    
    if args.to_date:
        to_date = date.fromisoformat(args.to_date)
    else:
        to_date = date.today()
    
    print("=" * 80)
    print("ПРОВЕРКА ПРОДАЖ ПОДРАЗДЕЛЕНИЯ В iiko API")
    print("=" * 80)
    print(f"\nПодразделение ID: {args.department_id}")
    print(f"Период: {from_date} - {to_date}")
    print()
    
    # Проверить, существует ли подразделение в БД
    db = next(get_db())
    try:
        department = db.query(Department).filter(Department.id == args.department_id).first()
        if department:
            print(f"✓ Подразделение найдено в БД:")
            print(f"   Название: {department.name}")
            print(f"   Код: {department.code}")
            print(f"   Тип: {department.type}")
        else:
            print(f"⚠ Подразделение НЕ найдено в БД (будет проверено только в iiko API)")
    finally:
        db.close()
    
    print()
    
    # Проверить продажи во всех доменах
    results = await check_department_in_all_domains(
        args.department_id,
        from_date,
        to_date
    )
    
    # Вывести сводку
    print(f"\n{'='*80}")
    print("ИТОГОВАЯ СВОДКА")
    print(f"{'='*80}")
    
    total_records = 0
    total_amount = 0
    
    for domain, sales_data in results.items():
        if sales_data:
            total_records += len(sales_data)
            domain_total = sum(float(record.get('DishSumInt', 0)) for record in sales_data)
            total_amount += domain_total
            print_sales_summary(sales_data, domain)
    
    print(f"\n{'='*80}")
    print(f"ВСЕГО:")
    print(f"  Записей: {total_records}")
    print(f"  Сумма: {total_amount:,.2f}")
    print(f"{'='*80}")
    
    if total_records == 0:
        print(f"\n⚠ ПРОДАЖИ НЕ НАЙДЕНЫ")
        print(f"\nВозможные причины:")
        print(f"  1. Подразделение не существует в iiko")
        print(f"  2. В указанном периоде не было продаж")
        print(f"  3. ID подразделения указан неверно")
        print(f"  4. Подразделение находится в другом домене")
        print(f"\nРекомендации:")
        print(f"  - Проверьте правильность ID подразделения")
        print(f"  - Попробуйте расширить период поиска")
        print(f"  - Убедитесь, что подразделение синхронизировано из iiko")


if __name__ == "__main__":
    asyncio.run(main())

