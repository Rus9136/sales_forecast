#!/usr/bin/env python3
"""
Проверка правильного домена для Tary Shymkent
"""
import asyncio
import httpx
import xml.etree.ElementTree as ET
from datetime import date, timedelta

LOGIN = "Tanat"
PASSWORD = "7c4a8d09ca3762af61e59520943dc26494f8941b"

# Возможные домены (проверим варианты)
POSSIBLE_DOMAINS = [
    "https://sandy-co-co.iiko.it",
    "https://sandy-co.iiko.it", 
    "https://sandyk.iiko.it",
    "https://sandyk-co.iiko.it",
    "https://madlen-group-so.iiko.it",
    "https://madlen-group.iiko.it",
]

async def get_token(base_url: str) -> str:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{base_url}/resto/api/auth",
                params={"login": LOGIN, "pass": PASSWORD},
                timeout=10.0
            )
            response.raise_for_status()
            return response.text.strip()
    except Exception as e:
        return None

async def check_domain(domain: str):
    """Проверить домен и найти Tary Shymkent"""
    print(f"\n{'='*80}")
    print(f"Проверка домена: {domain}")
    print(f"{'='*80}")
    
    # Проверить авторизацию
    token = await get_token(domain)
    if not token:
        print("  ❌ Не удалось получить токен (домен недоступен или неправильный)")
        return False
    
    print(f"  ✓ Токен получен: {token[:20]}...")
    
    # Получить подразделения
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{domain}/resto/api/corporation/departments",
                params={"key": token, "revisionFrom": -1}
            )
            response.raise_for_status()
            
            root = ET.fromstring(response.text)
            
            departments = []
            tary_shymkent_found = False
            
            for item in root.findall('corporateItemDto'):
                name = item.find('name')
                dept_id = item.find('id')
                dept_type = item.find('type')
                
                if name is not None and dept_id is not None:
                    name_text = name.text or ''
                    type_text = dept_type.text if dept_type is not None else ''
                    
                    if 'tary' in name_text.lower() and 'shymkent' in name_text.lower():
                        tary_shymkent_found = True
                        print(f"  ✓✓✓ НАЙДЕНО: {name_text}")
                        print(f"     ID: {dept_id.text}")
                        print(f"     Type: {type_text}")
                        
                        # Проверить продажи за последнюю неделю
                        from_date = date.today() - timedelta(days=7)
                        to_date = date.today()
                        
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
                                    "values": [dept_id.text]
                                },
                                "OrderDeleted": {
                                    "filterType": "IncludeValues",
                                    "values": ["NOT_DELETED"]
                                }
                            }
                        }
                        
                        try:
                            sales_response = await client.post(
                                f"{domain}/resto/api/v2/reports/olap",
                                params={"key": token},
                                json=request_body,
                                timeout=60.0
                            )
                            sales_response.raise_for_status()
                            sales_data = sales_response.json().get('data', [])
                            
                            if sales_data:
                                total = sum(float(r.get('DishSumInt', 0)) for r in sales_data)
                                print(f"     ✓ Продажи за неделю: {len(sales_data)} записей, {total:,.2f}")
                            else:
                                print(f"     ⚠ Продажи за неделю: не найдены")
                        except Exception as e:
                            print(f"     ⚠ Ошибка проверки продаж: {e}")
                    
                    if type_text == 'DEPARTMENT':
                        departments.append(name_text)
            
            print(f"\n  Всего подразделений типа DEPARTMENT: {len(departments)}")
            if not tary_shymkent_found:
                print(f"  ✗ Tary Shymkent не найден в этом домене")
            
            return tary_shymkent_found
            
    except httpx.HTTPError as e:
        print(f"  ❌ HTTP ошибка: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"     Статус: {e.response.status_code}")
            print(f"     Ответ: {e.response.text[:200]}")
        return False
    except Exception as e:
        print(f"  ❌ Ошибка: {e}")
        return False

async def main():
    print("=" * 80)
    print("ПОИСК ПРАВИЛЬНОГО ДОМЕНА ДЛЯ TARY SHYMKENT")
    print("=" * 80)
    
    found_domains = []
    
    for domain in POSSIBLE_DOMAINS:
        found = await check_domain(domain)
        if found:
            found_domains.append(domain)
    
    print(f"\n{'='*80}")
    print("ИТОГ")
    print(f"{'='*80}")
    
    if found_domains:
        print(f"\n✓ Tary Shymkent найден в доменах:")
        for domain in found_domains:
            print(f"  - {domain}")
    else:
        print(f"\n✗ Tary Shymkent не найден ни в одном из проверенных доменов")
        print(f"\nПроверенные домены:")
        for domain in POSSIBLE_DOMAINS:
            print(f"  - {domain}")
    
    print()

if __name__ == "__main__":
    asyncio.run(main())


