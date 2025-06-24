#!/usr/bin/env python3
"""
Тест логарифмической шкалы графика "Факт vs Прогноз"
"""
import requests
import json

BASE_URL = "http://localhost:8002"

def test_log_scale_chart():
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ЛОГАРИФМИЧЕСКОЙ ШКАЛЫ ГРАФИКА 'ФАКТ vs ПРОГНОЗ'")
    print("=" * 80)
    
    # 1. Проверяем HTML на наличие новых элементов
    print("\n1. Проверка HTML логарифмических оптимизаций...")
    response = requests.get(f"{BASE_URL}/")
    html_content = response.text
    
    log_scale_features = {
        "Предупреждение о выбросах": "chart-outliers-warning" in html_content,
        "Логарифмическая шкала": "logarithmic" in html_content,
        "Анализ выбросов": "valueRatio" in html_content,
        "Автоматический выбор шкалы": "useLogScale" in html_content,
        "Форматирование меток": "toFixed(1)" in html_content and "'М'" in html_content,
        "Ограничение осей": "maxTicksLimit: 8" in html_content
    }
    
    for name, found in log_scale_features.items():
        status = "✅" if found else "❌"
        print(f"   {status} {name}")
    
    # 2. Анализ данных для тестирования шкал
    print("\n2. Анализ данных для тестирования шкал...")
    
    # Получаем список департаментов
    dept_response = requests.get(f"{BASE_URL}/api/departments/")
    if dept_response.status_code != 200:
        print("   ❌ Не удалось получить список департаментов")
        return
    
    departments = dept_response.json()
    print(f"   ✅ Найдено {len(departments)} департаментов")
    
    # Тестируем несколько департаментов на предмет разброса данных
    test_scenarios = []
    
    for i, dept in enumerate(departments[:5]):  # Первые 5 департаментов
        dept_id = dept['id']
        dept_name = dept['name']
        
        # Получаем данные сравнения за месяц
        comp_response = requests.get(f"{BASE_URL}/api/forecast/comparison", {
            "from_date": "2025-06-01",
            "to_date": "2025-06-30",
            "department_id": dept_id
        })
        
        if comp_response.status_code == 200:
            data = comp_response.json()
            if len(data) > 0:
                # Анализируем разброс значений
                predicted_values = [item['predicted_sales'] for item in data if item['predicted_sales']]
                actual_values = [item['actual_sales'] for item in data if item['actual_sales']]
                all_values = predicted_values + actual_values
                
                if len(all_values) > 0:
                    min_val = min(all_values)
                    max_val = max(all_values)
                    ratio = max_val / min_val if min_val > 0 else 0
                    
                    scenario = {
                        "dept_name": dept_name[:25],
                        "dept_id": dept_id,
                        "data_points": len(data),
                        "min_value": min_val,
                        "max_value": max_val,
                        "ratio": ratio,
                        "needs_log_scale": ratio > 5
                    }
                    test_scenarios.append(scenario)
    
    # Выводим результаты анализа
    print(f"\n   📊 Анализ разброса данных:")
    print(f"   {'Департамент':<25} {'Точек':<6} {'Мин. ₸':<12} {'Макс. ₸':<12} {'Разброс':<8} {'Лог.шкала'}")
    print("   " + "─" * 80)
    
    for scenario in test_scenarios:
        log_needed = "ДА" if scenario['needs_log_scale'] else "НЕТ"
        print(f"   {scenario['dept_name']:<25} "
              f"{scenario['data_points']:<6} "
              f"{scenario['min_value']:>11,.0f} "
              f"{scenario['max_value']:>11,.0f} "
              f"{scenario['ratio']:>7.1f}x "
              f"{log_needed}")
    
    # 3. Тестирование API с разными масштабами данных
    print("\n3. Поиск данных с большими разрывами...")
    
    high_ratio_scenarios = [s for s in test_scenarios if s['ratio'] > 5]
    low_ratio_scenarios = [s for s in test_scenarios if s['ratio'] <= 5 and s['ratio'] > 1]
    
    if high_ratio_scenarios:
        best_high = max(high_ratio_scenarios, key=lambda x: x['ratio'])
        print(f"   🔥 Лучший кандидат для лог. шкалы: {best_high['dept_name']}")
        print(f"      Разброс: {best_high['ratio']:.1f}x ({best_high['min_value']:,.0f}₸ - {best_high['max_value']:,.0f}₸)")
        print(f"      ID: {best_high['dept_id']}")
    else:
        print("   ⚠️ Не найдены данные с разбросом >5x для тестирования лог. шкалы")
    
    if low_ratio_scenarios:
        best_low = min(low_ratio_scenarios, key=lambda x: x['ratio'])
        print(f"   📈 Кандидат для линейной шкалы: {best_low['dept_name']}")
        print(f"      Разброс: {best_low['ratio']:.1f}x ({best_low['min_value']:,.0f}₸ - {best_low['max_value']:,.0f}₸)")
        print(f"      ID: {best_low['dept_id']}")
    
    # 4. Инструкции для ручного тестирования
    print("\n" + "=" * 80)
    print("ИНСТРУКЦИИ ДЛЯ РУЧНОГО ТЕСТИРОВАНИЯ ЛОГАРИФМИЧЕСКОЙ ШКАЛЫ")
    print("=" * 80)
    
    print(f"\n🔗 Откройте: {BASE_URL}/")
    print("\n📋 Тест логарифмической шкалы:")
    print("1. Навигация: ПРОГНОЗ ПРОДАЖ → 📊 Сравнение факт / прогноз")
    print("2. Период: 01.06.2025 - 30.06.2025")
    
    if high_ratio_scenarios:
        print(f"3. Филиал с большим разбросом: {best_high['dept_name']}")
        print("4. Нажмите 'Загрузить'")
        print("\n✅ Ожидаемый результат для большого разброса:")
        print("• Появится ЖЕЛТОЕ предупреждение: '📈 Внимание: График использует логарифмическую шкалу...'")
        print("• Ось Y подписана как: 'Сумма продаж (₸) - лог. шкала'")
        print("• Подписи оси Y в формате: ₸ 1.5М, ₸ 500К и т.д.")
        print("• График выглядит более 'сжатым' и читаемым")
        print("• Линии не 'прилипают' к краям графика")
    
    if low_ratio_scenarios:
        print(f"\n5. Затем протестируйте филиал: {best_low['dept_name']}")
        print("\n✅ Ожидаемый результат для небольшого разброса:")
        print("• НЕТ желтого предупреждения")
        print("• Ось Y подписана как: 'Сумма продаж (₸)' (без 'лог. шкала')")
        print("• Используется обычная линейная шкала")
    
    print("\n🧪 Дополнительные тесты:")
    print("• Проверьте tooltip'ы - должны показывать полные числа")
    print("• Подписи дат должны быть в формате ДД.ММ")
    print("• Максимум 8 меток по оси Y для читаемости")
    print("• График должен автоматически выбирать подходящую шкалу")
    
    print("\n🎯 Критерии успеха:")
    print("• Автоматическое переключение между линейной и логарифмической шкалой")
    print("• Предупреждение появляется только при разбросе >5x")
    print("• График остается читаемым при любых данных")
    print("• Подписи осей понятные и информативные")

if __name__ == "__main__":
    test_log_scale_chart()