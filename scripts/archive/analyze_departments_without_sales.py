#!/usr/bin/env python3
"""
Скрипт для анализа подразделений без продаж
Находит все подразделения типа DEPARTMENT и проверяет, есть ли у них продажи
"""
import sys
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

# Add app directory to path
import os
base_path = os.path.dirname(os.path.abspath(__file__))
if base_path not in sys.path:
    sys.path.insert(0, base_path)

from app.db import get_db
from app.models.branch import Department, SalesSummary


def analyze_departments_without_sales():
    """Анализирует подразделения без продаж"""
    db: Session = next(get_db())
    
    try:
        print("=" * 80)
        print("АНАЛИЗ ПОДРАЗДЕЛЕНИЙ БЕЗ ПРОДАЖ")
        print("=" * 80)
        print()
        
        # Получить все подразделения типа DEPARTMENT
        all_departments = db.query(Department).filter(
            Department.type == "DEPARTMENT"
        ).all()
        
        print(f"Всего подразделений типа DEPARTMENT: {len(all_departments)}")
        print()
        
        # Получить подразделения с продажами
        departments_with_sales = db.query(
            func.distinct(SalesSummary.department_id)
        ).subquery()
        
        departments_with_sales_ids = db.query(departments_with_sales).all()
        departments_with_sales_ids = {str(row[0]) for row in departments_with_sales_ids}
        
        print(f"Подразделений с продажами: {len(departments_with_sales_ids)}")
        print()
        
        # Найти подразделения без продаж
        departments_without_sales = []
        departments_with_sales_list = []
        
        for dept in all_departments:
            dept_id_str = str(dept.id)
            has_sales = dept_id_str in departments_with_sales_ids
            
            dept_info = {
                'id': dept_id_str,
                'name': dept.name,
                'code': dept.code,
                'type': dept.type,
                'has_sales': has_sales,
                'last_synced': dept.synced_at
            }
            
            if has_sales:
                # Получить последнюю дату продаж
                last_sale = db.query(SalesSummary).filter(
                    SalesSummary.department_id == dept.id
                ).order_by(SalesSummary.date.desc()).first()
                
                if last_sale:
                    dept_info['last_sale_date'] = last_sale.date
                    dept_info['last_sale_amount'] = last_sale.total_sales
                
                departments_with_sales_list.append(dept_info)
            else:
                departments_without_sales.append(dept_info)
        
        print("=" * 80)
        print(f"ПОДРАЗДЕЛЕНИЯ БЕЗ ПРОДАЖ: {len(departments_without_sales)}")
        print("=" * 80)
        print()
        
        if departments_without_sales:
            print(f"{'№':<4} {'ID':<40} {'Название':<50} {'Код':<15}")
            print("-" * 110)
            for i, dept in enumerate(departments_without_sales, 1):
                name = (dept['name'][:47] + '...') if len(dept['name']) > 50 else dept['name']
                print(f"{i:<4} {dept['id']:<40} {name:<50} {dept['code'] or 'N/A':<15}")
            
            print()
            print(f"\nСписок ID для проверки (первые 10):")
            for i, dept in enumerate(departments_without_sales[:10], 1):
                print(f"{i}. {dept['id']} - {dept['name']}")
        else:
            print("Все подразделения имеют продажи!")
        
        print()
        print("=" * 80)
        print(f"ПОДРАЗДЕЛЕНИЯ С ПРОДАЖАМИ: {len(departments_with_sales_list)}")
        print("=" * 80)
        print()
        
        # Статистика по подразделениям с продажами
        if departments_with_sales_list:
            # Найти подразделения с недавними продажами (последние 30 дней)
            recent_date = date.today() - timedelta(days=30)
            recent_sales = [
                d for d in departments_with_sales_list 
                if 'last_sale_date' in d and d['last_sale_date'] >= recent_date
            ]
            
            print(f"Подразделений с продажами за последние 30 дней: {len(recent_sales)}")
            print(f"Подразделений без продаж за последние 30 дней: {len(departments_with_sales_list) - len(recent_sales)}")
        
        print()
        print("=" * 80)
        print("РЕКОМЕНДАЦИИ")
        print("=" * 80)
        print("1. Используйте скрипт check_department_sales.py для проверки конкретных подразделений")
        print("2. Проверьте, синхронизированы ли подразделения из iiko")
        print("3. Возможно, некоторые подразделения неактивны или закрыты")
        print()
        
        return departments_without_sales
        
    finally:
        db.close()


if __name__ == "__main__":
    analyze_departments_without_sales()

