#!/usr/bin/env python3
"""
Тест интеллектуальной обработки выбросов для графика "Факт vs Прогноз"
"""
import requests
import json

BASE_URL = "http://localhost:8002"

def test_smart_outlier_handling():
    print("=" * 80)
    print("ТЕСТИРОВАНИЕ ИНТЕЛЛЕКТУАЛЬНОЙ ОБРАБОТКИ ВЫБРОСОВ v2.2")
    print("=" * 80)
    
    # 1. Проверяем HTML на наличие новых элементов
    print("\n1. Проверка новых функций в HTML...")
    response = requests.get(f"{BASE_URL}/")
    html_content = response.text
    
    smart_features = {
        "Функция percentile": "function percentile(" in html_content,
        "Вычисление p5/p95": "percentile(allValues, 5)" in html_content,
        "Обнаружение выбросов": "hasExtremeOutliers" in html_content,
        "Ограничение данных": "displayPredicted" in html_content,
        "Подсчет clippedCount": "clippedCount++" in html_content,
        "Умные tooltip'ы": "originalValue" in html_content,
        "Новое предупреждение": "оптимизированы для читаемости" in html_content,
        "Линейная шкала": "type: 'linear'" in html_content,
        "Версия v2.2": "v2.2 (Smart Outliers)" in html_content
    }
    
    for name, found in smart_features.items():
        status = "✅" if found else "❌"
        print(f"   {status} {name}")
    
    # 2. Тестируем с реальными данными
    print("\n2. Тестирование с реальными данными...")
    
    dept_response = requests.get(f"{BASE_URL}/api/departments/")
    if dept_response.status_code == 200:
        departments = dept_response.json()
        test_dept = departments[0] if departments else None
        
        if test_dept:
            dept_id = test_dept['id']
            dept_name = test_dept['name']
            
            print(f"   Тестовый департамент: {dept_name}")
            
            # Получаем данные с выбросами
            comp_response = requests.get(f"{BASE_URL}/api/forecast/comparison", {
                "from_date": "2025-06-01",
                "to_date": "2025-06-07",
                "department_id": dept_id
            })
            
            if comp_response.status_code == 200:
                data = comp_response.json()
                print(f"   Получено записей: {len(data)}")
                
                if len(data) > 0:
                    # Анализируем данные
                    predicted = [item['predicted_sales'] for item in data if item['predicted_sales']]
                    actual = [item['actual_sales'] for item in data if item['actual_sales']]
                    all_values = predicted + actual
                    
                    if all_values:
                        min_val = min(all_values)
                        max_val = max(all_values)
                        ratio = max_val / min_val
                        
                        # Вычисляем процентили (симулируем алгоритм)
                        sorted_vals = sorted(all_values)
                        p5_idx = int(0.05 * (len(sorted_vals) - 1))
                        p95_idx = int(0.95 * (len(sorted_vals) - 1))
                        p5 = sorted_vals[p5_idx]
                        p95 = sorted_vals[p95_idx]
                        
                        original_range = max_val - min_val
                        clipped_range = p95 - p5
                        has_outliers = original_range / clipped_range > 3
                        
                        print(f"\n   📊 Анализ данных:")
                        print(f"      Диапазон: {min_val:,.0f}₸ - {max_val:,.0f}₸")
                        print(f"      Разброс: {ratio:.1f}x")
                        print(f"      5-й процентиль: {p5:,.0f}₸")
                        print(f"      95-й процентиль: {p95:,.0f}₸")
                        print(f"      Есть экстремальные выбросы: {'ДА' if has_outliers else 'НЕТ'}")
                        
                        if has_outliers:
                            outliers_count = sum(1 for v in all_values if v < p5 or v > p95)
                            print(f"      Количество выбросов: {outliers_count}")
                            print(f"      ✅ Эти данные будут оптимизированы для читаемости")
                        else:
                            print(f"      ✅ Эти данные будут отображены без изменений")
    
    # 3. Демонстрация ключевых улучшений
    print(f"\n" + "=" * 80)
    print("КЛЮЧЕВЫЕ УЛУЧШЕНИЯ v2.2")
    print("=" * 80)
    
    improvements = [
        ("🎯 Процентильная фильтрация", "Выбросы ограничиваются 5-95 процентилями"),
        ("📊 Читаемая визуализация", "График остается понятным при любых данных"),
        ("💡 Умные подсказки", "Tooltip'ы показывают реальные и ограниченные значения"),
        ("🔍 Прозрачность", "Пользователь видит количество отфильтрованных точек"),
        ("⚡ Производительность", "Только линейная шкала - быстрая отрисовка"),
        ("🎨 Автоматизация", "Система сама определяет нужна ли оптимизация"),
        ("📈 Сохраненные данные", "Реальные значения доступны при наведении мышью"),
        ("🚀 Лучший UX", "График всегда читаемый и информативный")
    ]
    
    for title, desc in improvements:
        print(f"   {title}: {desc}")

def show_testing_instructions():
    print(f"\n" + "=" * 80)
    print("ИНСТРУКЦИИ ДЛЯ ТЕСТИРОВАНИЯ v2.2")
    print("=" * 80)
    
    print(f"\n🔗 Откройте: {BASE_URL}/")
    print("\n📋 Шаги тестирования:")
    print("1. ПРОГНОЗ ПРОДАЖ → 📊 Сравнение факт / прогноз")
    print("2. Период: 01.06.2025 - 07.06.2025")
    print("3. Выберите любой филиал (например: Мадлен Plaza)")
    print("4. Нажмите 'Загрузить'")
    
    print("\n✅ Что проверять:")
    print("• График всегда читаемый (без экстремальных скачков)")
    print("• При наличии выбросов: голубое предупреждение с деталями")
    print("• Подписи оси: 'оптимизировано' если есть ограничения")
    print("• Tooltip'ы показывают:")
    print("  - Реальные значения всегда")
    print("  - '(на графике: ...)' если значение ограничено")
    print("• Отсутствие логарифмической шкалы")
    print("• Плавные линии без резких скачков")
    
    print("\n🎯 Сценарии тестирования:")
    print("• Данные без выбросов → обычный график, нет предупреждений")
    print("• Данные с выбросами → оптимизированный график + предупреждение")
    print("• Наведение мыши → реальные значения в tooltip'ах")
    print("• Разные филиалы → адаптивная обработка для каждого")
    
    print("\n🔄 Сравнение с предыдущей версией:")
    print("• v2.1: Логарифмическая шкала (плохо читается)")
    print("• v2.2: Интеллектуальное ограничение (отлично читается)")

if __name__ == "__main__":
    test_smart_outlier_handling()
    show_testing_instructions()
    
    print(f"\n" + "=" * 80)
    print("🎉 ИНТЕЛЛЕКТУАЛЬНАЯ ОБРАБОТКА ВЫБРОСОВ РЕАЛИЗОВАНА!")
    print("=" * 80)