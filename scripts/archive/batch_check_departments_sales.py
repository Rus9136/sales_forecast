#!/usr/bin/env python3
"""
Скрипт для массовой проверки продаж подразделений без продаж
Проверяет несколько подразделений подряд и выводит отчет
"""
import sys
import asyncio
from datetime import date, timedelta
from typing import List, Dict

# Add app directory to path
import os
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

from check_department_sales import fetch_sales_for_department
from app.db import get_db
from app.models.branch import Department, SalesSummary


async def batch_check_departments(department_ids: List[str], days_back: int = 30):
    """Проверить продажи для списка подразделений"""
    domains = [
        "https://sandy-co-co.iiko.it",
        "https://madlen-group-so.iiko.it"
    ]
    
    from_date = date.today() - timedelta(days=days_back)
    to_date = date.today()
    
    print("=" * 80)
    print("МАССОВАЯ ПРОВЕРКА ПРОДАЖ ПОДРАЗДЕЛЕНИЙ")
    print("=" * 80)
    print(f"Период: {from_date} - {to_date}")
    print(f"Количество подразделений: {len(department_ids)}")
    print()
    
    results = []
    
    for i, dept_id in enumerate(department_ids, 1):
        print(f"\n[{i}/{len(department_ids)}] Проверка подразделения: {dept_id}")
        print("-" * 80)
        
        # Получить информацию о подразделении из БД
        db = next(get_db())
        try:
            dept = db.query(Department).filter(Department.id == dept_id).first()
            dept_name = dept.name if dept else "Неизвестно"
            dept_code = dept.code if dept else "N/A"
        finally:
            db.close()
        
        print(f"Название: {dept_name}")
        print(f"Код: {dept_code}")
        
        # Проверить во всех доменах
        found_sales = False
        total_amount = 0
        total_records = 0
        
        for domain in domains:
            sales = await fetch_sales_for_department(dept_id, from_date, to_date, domain)
            
            if sales:
                found_sales = True
                domain_total = sum(float(record.get('DishSumInt', 0)) for record in sales)
                total_amount += domain_total
                total_records += len(sales)
                print(f"  ✓ {domain}: {len(sales)} записей, сумма: {domain_total:,.2f}")
        
        result = {
            'id': dept_id,
            'name': dept_name,
            'code': dept_code,
            'has_sales': found_sales,
            'total_records': total_records,
            'total_amount': total_amount
        }
        
        results.append(result)
        
        if not found_sales:
            print(f"  ⚠ Продажи не найдены")
    
    # Вывести итоговую сводку
    print(f"\n{'='*80}")
    print("ИТОГОВАЯ СВОДКА")
    print(f"{'='*80}")
    
    with_sales = [r for r in results if r['has_sales']]
    without_sales = [r for r in results if not r['has_sales']]
    
    print(f"\nПодразделений с продажами: {len(with_sales)}")
    print(f"Подразделений без продаж: {len(without_sales)}")
    
    if with_sales:
        print(f"\n{'='*80}")
        print("ПОДРАЗДЕЛЕНИЯ С ПРОДАЖАМИ:")
        print(f"{'='*80}")
        print(f"{'ID':<40} {'Название':<50} {'Записей':<10} {'Сумма':<15}")
        print("-" * 115)
        for r in with_sales:
            name = (r['name'][:47] + '...') if len(r['name']) > 50 else r['name']
            print(f"{r['id']:<40} {name:<50} {r['total_records']:<10} {r['total_amount']:>15,.2f}")
    
    if without_sales:
        print(f"\n{'='*80}")
        print("ПОДРАЗДЕЛЕНИЯ БЕЗ ПРОДАЖ:")
        print(f"{'='*80}")
        print(f"{'ID':<40} {'Название':<50} {'Код':<15}")
        print("-" * 105)
        for r in without_sales:
            name = (r['name'][:47] + '...') if len(r['name']) > 50 else r['name']
            print(f"{r['id']:<40} {name:<50} {r['code'] or 'N/A':<15}")
    
    print()
    return results


async def main():
    """Основная функция - проверяет подразделения без продаж из БД"""
    print("Загрузка списка подразделений без продаж из БД...")
    
    # Получить подразделения без продаж
    db = next(get_db())
    try:
        # Получить все DEPARTMENT подразделения
        all_departments = db.query(Department).filter(
            Department.type == "DEPARTMENT"
        ).all()
        
        # Получить ID подразделений с продажами
        dept_ids_with_sales = db.query(
            SalesSummary.department_id
        ).distinct().all()
        dept_ids_with_sales = {str(row[0]) for row in dept_ids_with_sales}
        
        # Найти подразделения без продаж
        departments_without_sales = [
            dept for dept in all_departments 
            if str(dept.id) not in dept_ids_with_sales
        ]
        
        print(f"Найдено {len(departments_without_sales)} подразделений без продаж")
        
        # Ограничить проверку первыми 10 подразделениями (для начала)
        dept_ids_to_check = [str(dept.id) for dept in departments_without_sales[:10]]
        
        if len(departments_without_sales) > 10:
            print(f"⚠ Проверка ограничена первыми 10 подразделениями")
            print(f"   Для проверки всех используйте: python batch_check_departments_sales.py --all")
        
    finally:
        db.close()
    
    if not dept_ids_to_check:
        print("Нет подразделений для проверки")
        return
    
    # Проверить подразделения
    await batch_check_departments(dept_ids_to_check, days_back=30)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Массовая проверка продаж подразделений без продаж'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='Проверить все подразделения без продаж (не только первые 10)'
    )
    parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Количество дней для проверки (по умолчанию: 30)'
    )
    
    args = parser.parse_args()
    
    # Если нужно проверить все, изменим логику
    if args.all:
        # Здесь можно добавить логику для проверки всех
        print("Режим проверки всех подразделений - это может занять время...")
    
    asyncio.run(main())

