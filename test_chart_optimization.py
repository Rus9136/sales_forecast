#!/usr/bin/env python3
"""
Тест оптимизации графика "Факт vs Прогноз"
"""
import requests
import json

BASE_URL = "http://localhost:8002"

def test_chart_optimization():
    print("=" * 70)
    print("ТЕСТИРОВАНИЕ ОПТИМИЗАЦИИ ГРАФИКА 'ФАКТ vs ПРОГНОЗ'")
    print("=" * 70)
    
    # 1. Проверяем HTML на наличие оптимизированных элементов
    print("\n1. Проверка HTML оптимизаций...")
    response = requests.get(f"{BASE_URL}/")
    html_content = response.text
    
    optimizations = {
        "Chart Warning": "chart-warning" in html_content,
        "No Data Message": "chart-no-data" in html_content, 
        "Chart.js Library": "chart.js" in html_content,
        "updateForecastChart Function": "updateForecastChart" in html_content,
        "Max Points Limit": "MAX_POINTS = 30" in html_content,
        "Animation Optimization": "animation" in html_content and "duration:" in html_content,
        "Decimation Plugin": "decimation" in html_content,
        "Tick Optimization": "maxTicksLimit" in html_content
    }
    
    for name, found in optimizations.items():
        status = "✅" if found else "❌"
        print(f"   {status} {name}")
    
    # 2. Тестируем API с разными объемами данных
    print("\n2. Тестирование API с разными датами...")
    
    test_scenarios = [
        {"name": "Малый объем (7 дней)", "from": "2025-06-01", "to": "2025-06-07"},
        {"name": "Средний объем (30 дней)", "from": "2025-06-01", "to": "2025-06-30"},
        {"name": "Большой объем (90 дней)", "from": "2025-03-01", "to": "2025-06-30"}
    ]
    
    department_id = "0d30c200-87b5-45a5-89f0-eb76e2892b4a"  # Мадлен Plaza
    
    for scenario in test_scenarios:
        url = f"{BASE_URL}/api/forecast/comparison"
        params = {
            "from_date": scenario["from"],
            "to_date": scenario["to"],
            "department_id": department_id
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                count = len(data)
                
                if count > 30:
                    print(f"   📊 {scenario['name']}: {count} записей (>30, потребуется оптимизация)")
                elif count > 0:
                    print(f"   ✅ {scenario['name']}: {count} записей (оптимальный объем)")
                else:
                    print(f"   ⚠️ {scenario['name']}: Нет данных")
            else:
                print(f"   ❌ {scenario['name']}: Ошибка API {response.status_code}")
        except Exception as e:
            print(f"   ❌ {scenario['name']}: Ошибка запроса - {e}")
    
    # 3. Проверяем все филиалы
    print("\n3. Проверка данных по филиалам...")
    
    departments_response = requests.get(f"{BASE_URL}/api/departments/")
    if departments_response.status_code == 200:
        departments = departments_response.json()
        branches_with_data = 0
        total_branches = len(departments)
        
        for dept in departments[:5]:  # Проверяем первые 5 филиалов
            dept_id = dept['id']
            dept_name = dept['name']
            
            comp_response = requests.get(f"{BASE_URL}/api/forecast/comparison", {
                "from_date": "2025-06-01",
                "to_date": "2025-06-07",
                "department_id": dept_id
            })
            
            if comp_response.status_code == 200:
                data_count = len(comp_response.json())
                if data_count > 0:
                    branches_with_data += 1
                    print(f"   ✅ {dept_name[:30]:30} : {data_count:2d} записей")
                else:
                    print(f"   ⚠️ {dept_name[:30]:30} : Нет данных")
        
        print(f"\n   Филиалов с данными: {branches_with_data}/5 протестированных")
    
    # 4. Инструкции для ручного тестирования
    print("\n" + "=" * 70)
    print("ИНСТРУКЦИИ ДЛЯ РУЧНОГО ТЕСТИРОВАНИЯ ОПТИМИЗАЦИЙ")
    print("=" * 70)
    
    print(f"\n🔗 Откройте: http://localhost:8002/")
    print("\n📋 Тест оптимизаций:")
    print("1. Навигация: ПРОГНОЗ ПРОДАЖ → 📊 Сравнение факт / прогноз")
    print("2. Фильтры: 01.06.2025 - 30.06.2025, филиал 'Мадлен Plaza'")
    print("3. Нажмите 'Загрузить'")
    
    print("\n✅ Ожидаемые оптимизации:")
    print("• График показывается только для одного филиала")
    print("• Если данных >30 дат → предупреждение: '⚠️ Для удобства...'")
    print("• График не зависает при большом количестве точек")
    print("• Подписи оси X читаемые (максимум 10 меток)")
    print("• Без анимации при >15 точках данных")
    print("• Точки меньше при >15 данных (radius: 2 вместо 4)")
    print("• При отсутствии данных: 'Нет данных для отображения'")
    
    print("\n🧪 Тест производительности:")
    print("• Попробуйте период 01.03.2025 - 30.06.2025 (большой объем)")
    print("• График должен отображаться быстро без зависаний")
    print("• Должно показываться предупреждение об ограничении 30 точек")
    
    print("\n🔄 Тест условий отображения:")
    print("• График скрывается при выборе 'Все подразделения'")
    print("• График появляется при выборе конкретного филиала")
    print("• График обновляется при сортировке таблицы")

if __name__ == "__main__":
    test_chart_optimization()