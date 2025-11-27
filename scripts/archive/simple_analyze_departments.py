#!/usr/bin/env python3
"""
Упрощенный скрипт для анализа подразделений без продаж
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

# Параметры подключения к БД
DB_CONFIG = {
    'host': 'localhost',
    'port': 5435,
    'database': 'sales_forecast',
    'user': 'sales_user',
    'password': 'sales_password'
}


def analyze_departments():
    """Анализирует подразделения без продаж"""
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("=" * 80)
        print("АНАЛИЗ ПОДРАЗДЕЛЕНИЙ БЕЗ ПРОДАЖ")
        print("=" * 80)
        print()
        
        # Получить все подразделения типа DEPARTMENT
        cur.execute("""
            SELECT id, name, code, type, synced_at
            FROM departments
            WHERE type = 'DEPARTMENT'
            ORDER BY name
        """)
        all_departments = cur.fetchall()
        
        print(f"Всего подразделений типа DEPARTMENT: {len(all_departments)}")
        print()
        
        # Получить подразделения с продажами
        cur.execute("""
            SELECT DISTINCT department_id
            FROM sales_summary
        """)
        dept_ids_with_sales = {row['department_id'] for row in cur.fetchall()}
        
        print(f"Подразделений с продажами: {len(dept_ids_with_sales)}")
        print()
        
        # Найти подразделения без продаж
        departments_without_sales = []
        departments_with_sales = []
        
        for dept in all_departments:
            dept_id = str(dept['id'])
            has_sales = dept_id in dept_ids_with_sales
            
            if has_sales:
                # Получить информацию о последней продаже
                cur.execute("""
                    SELECT date, total_sales
                    FROM sales_summary
                    WHERE department_id = %s
                    ORDER BY date DESC
                    LIMIT 1
                """, (dept['id'],))
                last_sale = cur.fetchone()
                
                dept_info = {
                    'id': dept_id,
                    'name': dept['name'],
                    'code': dept['code'],
                    'has_sales': True,
                    'last_sale_date': last_sale['date'] if last_sale else None,
                    'last_sale_amount': last_sale['total_sales'] if last_sale else None
                }
                departments_with_sales.append(dept_info)
            else:
                dept_info = {
                    'id': dept_id,
                    'name': dept['name'],
                    'code': dept['code'],
                    'has_sales': False
                }
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
                code = dept['code'] or 'N/A'
                print(f"{i:<4} {dept['id']:<40} {name:<50} {code:<15}")
            
            print()
            print(f"\nПервые 5 ID для проверки:")
            for i, dept in enumerate(departments_without_sales[:5], 1):
                print(f"{i}. {dept['id']} - {dept['name']}")
        else:
            print("Все подразделения имеют продажи!")
        
        print()
        print("=" * 80)
        print(f"ПОДРАЗДЕЛЕНИЯ С ПРОДАЖАМИ: {len(departments_with_sales)}")
        print("=" * 80)
        
        # Статистика по подразделениям с продажами
        if departments_with_sales:
            recent_date = date.today() - timedelta(days=30)
            recent_sales = [
                d for d in departments_with_sales 
                if d['last_sale_date'] and d['last_sale_date'] >= recent_date
            ]
            
            print(f"\nПодразделений с продажами за последние 30 дней: {len(recent_sales)}")
            print(f"Подразделений без продаж за последние 30 дней: {len(departments_with_sales) - len(recent_sales)}")
            
            # Показать подразделения без продаж за последние 30 дней
            inactive = [
                d for d in departments_with_sales
                if d['last_sale_date'] is None or d['last_sale_date'] < recent_date
            ]
            
            if inactive:
                print(f"\nПодразделения с продажами, но неактивные (>30 дней):")
                for dept in inactive[:10]:
                    last_date = dept['last_sale_date'].strftime('%Y-%m-%d') if dept['last_sale_date'] else 'Никогда'
                    print(f"  - {dept['name']} (последняя продажа: {last_date})")
        
        print()
        print("=" * 80)
        print("АНАЛИЗ ПРИЧИН")
        print("=" * 80)
        print()
        
        # Проверить, когда была последняя синхронизация продаж
        cur.execute("""
            SELECT MAX(date) as max_date, MIN(date) as min_date, COUNT(*) as total_records
            FROM sales_summary
        """)
        sales_stats = cur.fetchone()
        
        if sales_stats and sales_stats['max_date']:
            print(f"Диапазон дат продаж в БД:")
            print(f"  С: {sales_stats['min_date']}")
            print(f"  По: {sales_stats['max_date']}")
            print(f"  Всего записей: {sales_stats['total_records']}")
            print()
            
            days_since_last = (date.today() - sales_stats['max_date']).days
            print(f"Дней с последней продажи: {days_since_last}")
            print()
        
        print("Возможные причины отсутствия продаж:")
        print("  1. Подразделение закрыто или неактивно")
        print("  2. Подразделение не синхронизируется из iiko (нет в ответе API)")
        print("  3. Подразделение не создает продажи в iiko")
        print("  4. Проблемы с синхронизацией данных")
        print("  5. Подразделение относится к другому типу (не DEPARTMENT)")
        print()
        
        return departments_without_sales
        
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    analyze_departments()


