#!/usr/bin/env python3
"""
Тест функциональности графика "Факт vs Прогноз"
"""
import requests
import json

BASE_URL = "http://localhost:8002"

def test_chart_functionality():
    print("=" * 60)
    print("ТЕСТИРОВАНИЕ ГРАФИКА 'ФАКТ vs ПРОГНОЗ'")
    print("=" * 60)
    
    # 1. Проверяем доступность главной страницы
    print("\n1. Проверка доступности главной страницы...")
    try:
        response = requests.get(f"{BASE_URL}/")
        if response.status_code == 200:
            print("   ✅ Главная страница доступна")
            # Проверяем наличие Chart.js
            if "chart.js" in response.text:
                print("   ✅ Chart.js библиотека подключена")
            else:
                print("   ❌ Chart.js библиотека НЕ найдена")
            
            # Проверяем наличие контейнера графика
            if "forecast-chart-wrapper" in response.text:
                print("   ✅ Контейнер графика найден")
            else:
                print("   ❌ Контейнер графика НЕ найден")
                
            # Проверяем наличие функций Chart.js
            if "updateForecastChart" in response.text:
                print("   ✅ Функция updateForecastChart найдена")
            else:
                print("   ❌ Функция updateForecastChart НЕ найдена")
        else:
            print(f"   ❌ Главная страница недоступна: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка доступа к главной странице: {e}")
        return False
    
    # 2. Проверяем API сравнения прогнозов
    print("\n2. Проверка API сравнения прогнозов...")
    try:
        url = f"{BASE_URL}/api/forecast/comparison?from_date=2025-06-01&to_date=2025-06-05"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ API сравнения работает, найдено {len(data)} записей")
            
            # Получаем уникальные филиалы
            departments = list(set(item['department_id'] for item in data))
            if departments:
                print(f"   ✅ Найдены данные для {len(departments)} филиалов")
                
                # Тестируем данные для одного филиала
                test_dept = departments[0]
                dept_data = [item for item in data if item['department_id'] == test_dept]
                dept_name = dept_data[0]['department_name']
                
                print(f"\n   Тестовый филиал: {dept_name}")
                print(f"   Количество дней: {len(dept_data)}")
                
                # Выводим пример данных
                print("   Пример данных для графика:")
                for item in dept_data[:3]:  # Первые 3 записи
                    date = item['date']
                    pred = item['predicted_sales']
                    actual = item['actual_sales']
                    error_pct = item['error_percentage']
                    print(f"     {date}: Прогноз={pred:,.0f}₸, Факт={actual:,.0f}₸, Ошибка={error_pct:.1f}%")
                
                return True
            else:
                print("   ❌ Не найдены данные филиалов")
                return False
        else:
            print(f"   ❌ API сравнения недоступно: {response.status_code}")
            return False
    except Exception as e:
        print(f"   ❌ Ошибка API сравнения: {e}")
        return False
    
    # 3. Инструкции для ручного тестирования
    print("\n" + "=" * 60)
    print("ИНСТРУКЦИИ ДЛЯ РУЧНОГО ТЕСТИРОВАНИЯ")
    print("=" * 60)
    
    print("\n🔗 Откройте в браузере: http://localhost:8002/")
    print("\n📋 Шаги тестирования:")
    print("1. В боковом меню нажмите 'ПРОГНОЗ ПРОДАЖ'")
    print("2. Выберите '📊 Сравнение факт / прогноз'")
    print("3. Установите период: с 2025-06-01 по 2025-06-05")
    print("4. В выпадающем списке выберите 'Мадлен Plaza' (или любой другой филиал)")
    print("5. Нажмите кнопку 'Загрузить'")
    
    print("\n✅ Ожидаемый результат:")
    print("• Появится таблица с данными факт/прогноз")
    print("• НАД таблицей появится график с двумя линиями:")
    print("  - Синяя линия: Прогноз")
    print("  - Зелёная линия: Факт")
    print("• Ось X: даты")
    print("• Ось Y: сумма продаж в тенге")
    print("• При наведении на точки - подсказки с значениями")
    
    print("\n⚠️ Проверьте условия:")
    print("• График НЕ показывается если выбрано 'Все подразделения'")
    print("• График скрывается при очистке данных")
    print("• График обновляется при сортировке таблицы")
    
    print("\n🎯 Тестовые данные доступны для:")
    print("• Мадлен Plaza (ID: 0d30c200-87b5-45a5-89f0-eb76e2892b4a)")
    print("• Мадлен Аэропорт (ID: 138ca7c6-1741-4ba9-8342-1a239a514308)")
    print("• Мадлен Колос (ID: 18d35be9-4ac6-4ad0-8351-373ed9a7bcac)")
    print("• И другие филиалы за период 01-05 июня 2025")

if __name__ == "__main__":
    test_chart_functionality()