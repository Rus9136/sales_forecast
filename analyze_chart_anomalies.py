#!/usr/bin/env python3
"""
Анализ данных для выявления проблем читаемости графика при аномалиях
"""
import json

# Реальные данные из API
data = [
    {"date":"2025-06-01","predicted_sales":597896.54,"actual_sales":1063939.25},
    {"date":"2025-06-02","predicted_sales":1403580.67,"actual_sales":362424.0},
    {"date":"2025-06-03","predicted_sales":222441.66,"actual_sales":364130.0},
    {"date":"2025-06-04","predicted_sales":371386.4,"actual_sales":354109.0},
    {"date":"2025-06-05","predicted_sales":339182.52,"actual_sales":290542.0},
    {"date":"2025-06-06","predicted_sales":264949.48,"actual_sales":387173.0},
    {"date":"2025-06-07","predicted_sales":562517.88,"actual_sales":415558.0}
]

def analyze_data_issues():
    print("=" * 80)
    print("АНАЛИЗ ПРОБЛЕМ ЧИТАЕМОСТИ ГРАФИКА ПРИ АНОМАЛИЯХ")
    print("=" * 80)
    
    # Извлекаем все значения
    predicted = [item['predicted_sales'] for item in data]
    actual = [item['actual_sales'] for item in data]
    all_values = predicted + actual
    
    # Базовая статистика
    min_val = min(all_values)
    max_val = max(all_values)
    avg_val = sum(all_values) / len(all_values)
    
    print(f"\n📊 СТАТИСТИКА ДАННЫХ:")
    print(f"   Минимум: {min_val:>12,.0f}₸")
    print(f"   Максимум: {max_val:>11,.0f}₸")
    print(f"   Среднее: {avg_val:>12,.0f}₸")
    print(f"   Разброс: {max_val/min_val:>13.1f}x")
    
    # Анализ отклонений от среднего
    print(f"\n🔍 АНАЛИЗ ОТКЛОНЕНИЙ:")
    extreme_values = []
    
    for i, val in enumerate(all_values):
        deviation = abs(val - avg_val) / avg_val * 100
        is_extreme = deviation > 50  # Отклонение больше 50%
        
        data_type = "Прогноз" if i < len(predicted) else "Факт"
        date_idx = i if i < len(predicted) else i - len(predicted)
        date = data[date_idx]['date']
        
        if is_extreme:
            extreme_values.append({
                'date': date,
                'type': data_type,
                'value': val,
                'deviation': deviation
            })
    
    print(f"   Экстремальных значений (>50% от среднего): {len(extreme_values)}")
    for ext in extreme_values:
        print(f"   📈 {ext['date']} {ext['type']:7}: {ext['value']:>10,.0f}₸ ({ext['deviation']:>5.1f}%)")
    
    # Проблемы текущего подхода
    print(f"\n❌ ПРОБЛЕМЫ ТЕКУЩЕГО ЛОГАРИФМИЧЕСКОГО ПОДХОДА:")
    print(f"   1. Логарифмическая шкала не решает визуальное восприятие")
    print(f"   2. Экстремальные значения все равно 'сжимают' обычные данные")
    print(f"   3. Пользователь не может различить тренды в основной массе данных")
    print(f"   4. График становится нечитаемым для анализа")

def suggest_solutions():
    print(f"\n✅ ПРЕДЛАГАЕМЫЕ РЕШЕНИЯ:")
    
    solutions = [
        ("IQR Outlier Detection", "Удаление выбросов методом межквартильного размаха"),
        ("Winsorization", "Ограничение экстремальных значений percentile'ами"),
        ("Dual Y-Axis", "Две оси: основная для нормальных данных, вторая для выбросов"),
        ("Data Smoothing", "Сглаживание резких скачков скользящим средним"),
        ("Zoom Controls", "Элементы управления масштабом для детального просмотра"),
        ("Outlier Indicators", "Специальные маркеры для выбросов с подписями")
    ]
    
    for i, (name, desc) in enumerate(solutions, 1):
        print(f"   {i}. {name}: {desc}")

def recommend_implementation():
    print(f"\n🎯 РЕКОМЕНДУЕМАЯ РЕАЛИЗАЦИЯ:")
    print(f"   ┌─ Используем Winsorization (ограничение 5-95 процентилей)")
    print(f"   ├─ + IQR фильтрация экстремальных выбросов")  
    print(f"   ├─ + Индикаторы отфильтрованных данных")
    print(f"   ├─ + Tooltip'ы с реальными значениями")
    print(f"   └─ + Опция 'Показать все данные' для детального анализа")
    
    print(f"\n📝 АЛГОРИТМ:")
    print(f"   1. Вычисляем 5-й и 95-й процентили")
    print(f"   2. Ограничиваем данные этими границами для визуализации")
    print(f"   3. Показываем количество отфильтрованных точек")
    print(f"   4. В tooltip'ах отображаем реальные (неограниченные) значения")
    print(f"   5. Добавляем переключатель для показа полных данных")

if __name__ == "__main__":
    analyze_data_issues()
    suggest_solutions()
    recommend_implementation()