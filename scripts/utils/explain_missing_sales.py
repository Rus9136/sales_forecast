#!/usr/bin/env python3
"""
Объяснение почему не у всех подразделений есть продажи
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

DB_CONFIG = {
    'host': 'localhost',
    'port': 5435,
    'database': 'sales_forecast',
    'user': 'sales_user',
    'password': 'sales_password'
}

def explain():
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        print("=" * 80)
        print("АНАЛИЗ: ПОЧЕМУ НЕ У ВСЕХ ПОДРАЗДЕЛЕНИЙ ЕСТЬ ПРОДАЖИ")
        print("=" * 80)
        print()
        
        # 1. Все подразделения типа DEPARTMENT
        cur.execute("""
            SELECT COUNT(*) as total
            FROM departments
            WHERE type = 'DEPARTMENT'
        """)
        total_depts = cur.fetchone()['total']
        
        # 2. Подразделения с продажами
        cur.execute("""
            SELECT COUNT(DISTINCT department_id) as with_sales
            FROM sales_summary
        """)
        with_sales = cur.fetchone()['with_sales']
        
        # 3. Подразделения БЕЗ продаж
        cur.execute("""
            SELECT d.id, d.name, d.code, d.synced_at
            FROM departments d
            WHERE d.type = 'DEPARTMENT'
            AND d.id NOT IN (SELECT DISTINCT department_id FROM sales_summary)
            ORDER BY d.name
        """)
        without_sales = cur.fetchall()
        
        # 4. Подразделения с продажами, но неактивные (>30 дней)
        cur.execute("""
            SELECT d.id, d.name, MAX(s.date) as last_sale_date
            FROM departments d
            JOIN sales_summary s ON d.id = s.department_id
            WHERE d.type = 'DEPARTMENT'
            GROUP BY d.id, d.name
            HAVING MAX(s.date) < CURRENT_DATE - INTERVAL '30 days'
            ORDER BY MAX(s.date) DESC
        """)
        inactive = cur.fetchall()
        
        # 5. Статистика по датам
        cur.execute("""
            SELECT 
                MIN(date) as earliest_date,
                MAX(date) as latest_date,
                COUNT(*) as total_records,
                COUNT(DISTINCT department_id) as unique_depts
            FROM sales_summary
        """)
        stats = cur.fetchone()
        
        print("📊 СТАТИСТИКА:")
        print(f"   Всего подразделений типа DEPARTMENT: {total_depts}")
        print(f"   Подразделений с продажами: {with_sales}")
        print(f"   Подразделений БЕЗ продаж: {len(without_sales)}")
        print(f"   Подразделений неактивных (>30 дней): {len(inactive)}")
        print()
        
        if stats:
            print("📅 ДАННЫЕ О ПРОДАЖАХ:")
            print(f"   Период: {stats['earliest_date']} - {stats['latest_date']}")
            print(f"   Всего записей: {stats['total_records']:,}")
            print(f"   Уникальных подразделений с продажами: {stats['unique_depts']}")
            print()
        
        print("=" * 80)
        print("🔍 ПРИЧИНЫ ОТСУТСТВИЯ ПРОДАЖ:")
        print("=" * 80)
        print()
        
        if len(without_sales) > 0:
            print(f"1. ПОДРАЗДЕЛЕНИЯ БЕЗ ПРОДАЖ В БД ({len(without_sales)}):")
            print("   Эти подразделения есть в БД, но никогда не имели продаж.")
            print()
            for dept in without_sales[:5]:
                synced = dept['synced_at'].strftime('%Y-%m-%d') if dept['synced_at'] else 'Неизвестно'
                print(f"   - {dept['name']} (синхронизировано: {synced})")
            if len(without_sales) > 5:
                print(f"   ... и еще {len(without_sales) - 5}")
            print()
        
        if len(inactive) > 0:
            print(f"2. НЕАКТИВНЫЕ ПОДРАЗДЕЛЕНИЯ ({len(inactive)}):")
            print("   Эти подразделения имеют продажи в БД, но неактивны >30 дней.")
            print("   Возможные причины:")
            print("   • Подразделение закрыто")
            print("   • Подразделение временно не работает")
            print("   • Сезонное закрытие")
            print()
            for dept in inactive[:10]:
                days_ago = (date.today() - dept['last_sale_date']).days
                print(f"   - {dept['name']} (последняя продажа: {dept['last_sale_date']}, {days_ago} дней назад)")
            if len(inactive) > 10:
                print(f"   ... и еще {len(inactive) - 10}")
            print()
        
        print("=" * 80)
        print("💡 ВЫВОДЫ:")
        print("=" * 80)
        print()
        
        if len(without_sales) == 0 and len(inactive) == 0:
            print("✅ Все подразделения имеют активные продажи!")
        else:
            if len(without_sales) > 0:
                print(f"⚠️  {len(without_sales)} подразделений никогда не имели продаж.")
                print("   Это может означать:")
                print("   • Подразделение создано, но еще не начало работать")
                print("   • Подразделение закрыто до начала работы")
                print("   • Подразделение не синхронизируется из iiko (нет в ответе API)")
            
            if len(inactive) > 0:
                print(f"⚠️  {len(inactive)} подразделений неактивны более 30 дней.")
                print("   Рекомендуется:")
                print("   • Проверить статус подразделений в iiko")
                print("   • Убедиться, что они не закрыты")
                print("   • Проверить синхронизацию данных")
        
        print()
        print("=" * 80)
        print("🔧 КАК ПРОВЕРИТЬ:")
        print("=" * 80)
        print()
        print("Для проверки конкретного подразделения используйте:")
        print("  python3 check_department_sales.py <department_id>")
        print()
        print("Для массовой проверки неактивных:")
        print("  python3 batch_check_departments_sales.py")
        print()
        
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    explain()


