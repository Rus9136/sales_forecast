#!/usr/bin/env python3
"""
Анализ потенциала обучения модели на годовых данных
"""

import pandas as pd
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import numpy as np

DATABASE_URL = "postgresql://sales_user:sales_password@localhost:5435/sales_forecast"
engine = create_engine(DATABASE_URL)

def analyze_yearly_data():
    print("=== АНАЛИЗ ОБУЧЕНИЯ МОДЕЛИ НА ГОДОВЫХ ДАННЫХ ===\n")
    
    # 1. Текущая модель (180 дней)
    print("📊 ТЕКУЩАЯ МОДЕЛЬ (180 дней):")
    print("  - Данных для обучения: ~5,008 записей")
    print("  - Test MAPE: 7.67%")
    print("  - R²: 0.9952")
    
    # 2. Анализ годовых данных
    end_date = datetime.now().date()
    start_date_180 = end_date - timedelta(days=180)
    start_date_365 = end_date - timedelta(days=365)
    
    print(f"\n📊 ПОТЕНЦИАЛЬНАЯ МОДЕЛЬ (365 дней):")
    
    # Количество данных
    query_365 = f"""
    SELECT 
        COUNT(*) as total_records,
        COUNT(DISTINCT department_id) as departments,
        COUNT(DISTINCT date) as unique_dates
    FROM sales_summary 
    WHERE total_sales > 0 
    AND date >= '{start_date_365}'
    AND date <= '{end_date}'
    """
    
    with engine.connect() as conn:
        result = conn.execute(text(query_365))
        data_365 = result.fetchone()
    
    # Оценка после dropna (теряем ~7 записей на департамент из-за lag features)
    estimated_after_dropna = data_365[0] - (data_365[1] * 7)
    
    print(f"  - Записей в БД: {data_365[0]:,}")
    print(f"  - Уникальных департаментов: {data_365[1]}")
    print(f"  - Уникальных дат: {data_365[2]}")
    print(f"  - Ожидается после dropna: ~{estimated_after_dropna:,} записей")
    print(f"  - Увеличение объема данных: {estimated_after_dropna/5008:.1f}x")
    
    # 3. Анализ сезонности
    print("\n📈 АНАЛИЗ СЕЗОННОСТИ:")
    
    query_monthly = f"""
    SELECT 
        EXTRACT(MONTH FROM date) as month,
        COUNT(*) as records,
        ROUND(AVG(total_sales)::numeric, 0) as avg_sales,
        ROUND(STDDEV(total_sales)::numeric, 0) as std_sales
    FROM sales_summary 
    WHERE total_sales > 0 
    AND date >= '{start_date_365}'
    AND date <= '{end_date}'
    GROUP BY month
    ORDER BY month
    """
    
    with engine.connect() as conn:
        monthly_df = pd.read_sql(query_monthly, conn)
    
    # Коэффициент вариации по месяцам
    cv_monthly = monthly_df['avg_sales'].std() / monthly_df['avg_sales'].mean() * 100
    
    print(f"  - Коэффициент вариации продаж по месяцам: {cv_monthly:.1f}%")
    if cv_monthly > 20:
        print("  - ✅ ВЫСОКАЯ СЕЗОННОСТЬ - годовые данные будут полезны!")
    else:
        print("  - ⚠️ Низкая сезонность - годовые данные могут быть избыточны")
    
    # Показываем топ месяцы
    print("\n  Средние продажи по месяцам:")
    months = ['Янв', 'Фев', 'Мар', 'Апр', 'Май', 'Июн', 'Июл', 'Авг', 'Сен', 'Окт', 'Ноя', 'Дек']
    for _, row in monthly_df.iterrows():
        month_idx = int(row['month']) - 1
        print(f"    {months[month_idx]}: {row['avg_sales']:,.0f} тг")
    
    # 4. Анализ праздников и событий
    print("\n🎉 АНАЛИЗ ОСОБЫХ ДНЕЙ:")
    
    query_holidays = f"""
    SELECT 
        date,
        SUM(total_sales) as daily_total,
        COUNT(DISTINCT department_id) as departments
    FROM sales_summary 
    WHERE total_sales > 0 
    AND date >= '{start_date_365}'
    AND date <= '{end_date}'
    GROUP BY date
    ORDER BY daily_total DESC
    LIMIT 10
    """
    
    with engine.connect() as conn:
        top_days = pd.read_sql(query_holidays, conn)
    
    print("  Топ-10 дней по продажам:")
    for _, row in top_days.iterrows():
        date_str = row['date'].strftime('%Y-%m-%d (%A)')
        print(f"    {date_str}: {row['daily_total']:,.0f} тг")
    
    # 5. Преимущества и недостатки
    print("\n✅ ПРЕИМУЩЕСТВА ОБУЧЕНИЯ НА ГОДОВЫХ ДАННЫХ:")
    print("  1. Больше данных → потенциально лучшая генерализация")
    print("  2. Захват полного годового цикла и сезонности")
    print("  3. Учет праздников и особых событий")
    print("  4. Лучшее понимание долгосрочных трендов")
    
    print("\n⚠️ ПОТЕНЦИАЛЬНЫЕ НЕДОСТАТКИ:")
    print("  1. Старые данные могут быть менее релевантными")
    print("  2. Изменения в бизнесе за год (новые филиалы, закрытия)")
    print("  3. Больше времени на обучение")
    print("  4. Риск переобучения на исторических паттернах")
    
    # 6. Рекомендация
    print("\n🎯 РЕКОМЕНДАЦИЯ:")
    if cv_monthly > 20:
        print("  ✅ РЕКОМЕНДУЮ обучить модель на годовых данных!")
        print("  Высокая сезонность оправдывает использование полного года.")
        print(f"  Ожидаемое улучшение MAPE: с 7.67% до ~6.5-7.0%")
    else:
        print("  ⚠️ Обучение на годовых данных может дать небольшое улучшение.")
        print("  Рекомендую сначала протестировать на валидационной выборке.")
    
    # 7. Оптимальный период
    print("\n🔧 АЛЬТЕРНАТИВНЫЕ ВАРИАНТЫ:")
    for days in [270, 300, 330]:
        query = f"""
        SELECT COUNT(*) as cnt
        FROM sales_summary 
        WHERE total_sales > 0 
        AND date >= CURRENT_DATE - INTERVAL '{days} days'
        """
        with engine.connect() as conn:
            result = conn.execute(text(query))
            count = result.scalar()
        est = count - 40*7  # примерная оценка
        print(f"  - {days} дней: ~{est:,} записей для обучения")

if __name__ == "__main__":
    analyze_yearly_data()