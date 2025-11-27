#!/usr/bin/env python3

import sys
import os
sys.path.append('/root/projects/SalesForecast/sales_forecast')

from datetime import date
import pandas as pd

def debug_day_features():
    """Проверим генерацию features для разных дней недели"""
    
    # Тестовые даты
    saturday = date(2025, 7, 5)  # Суббота
    monday = date(2025, 7, 7)    # Понедельник
    
    print("=== ДИАГНОСТИКА FEATURES ДЛЯ ДНЕЙ НЕДЕЛИ ===\n")
    
    for test_date in [saturday, monday]:
        forecast_datetime = pd.to_datetime(test_date)
        day_name = test_date.strftime('%A')
        
        print(f"📅 {test_date} ({day_name})")
        print(f"   Python dayofweek: {forecast_datetime.dayofweek}")
        
        # Наша конвертация
        python_dow = forecast_datetime.dayofweek  # 0=Monday, ..., 6=Sunday
        postgres_dow = (python_dow + 1) % 7  # Convert: 0=Sunday, 1=Monday, ..., 6=Saturday
        
        print(f"   PostgreSQL dow: {postgres_dow}")
        print(f"   is_weekend: {1 if postgres_dow == 0 or postgres_dow == 6 else 0}")
        print(f"   is_friday: {1 if postgres_dow == 5 else 0}")
        print(f"   is_monday: {1 if postgres_dow == 1 else 0}")
        print()

def analyze_weekend_data():
    """Анализ данных по выходным из БД"""
    print("=== АНАЛИЗ ВЫХОДНЫХ ИЗ БД ===")
    # Эта функция требует подключения к БД
    pass

if __name__ == "__main__":
    debug_day_features()
    
    # Проверим правильность нумерации
    print("=== ПРОВЕРКА НУМЕРАЦИИ ===")
    days = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    print("PostgreSQL нумерация (правильная):")
    for i, day in enumerate(days):
        print(f"   {i}: {day}")
    
    print("\nPython нумерация (неправильная для нашей модели):")
    python_days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    for i, day in enumerate(python_days):
        print(f"   {i}: {day}")