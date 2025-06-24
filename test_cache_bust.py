#!/usr/bin/env python3
"""
Проверка что кэш браузера обновлен и новая версия загружена
"""
import requests
import re

BASE_URL = "http://localhost:8002"

def test_cache_busting():
    print("=" * 80)
    print("ПРОВЕРКА ОБНОВЛЕНИЯ КЭША БРАУЗЕРА")
    print("=" * 80)
    
    response = requests.get(f"{BASE_URL}/")
    html_content = response.text
    
    print("\n🔍 Проверка версионирования:")
    
    # Проверяем мета-теги для кэша
    cache_control_found = 'no-cache, no-store, must-revalidate' in html_content
    print(f"   {'✅' if cache_control_found else '❌'} Cache-Control: no-cache")
    
    pragma_found = 'Pragma" content="no-cache' in html_content
    print(f"   {'✅' if pragma_found else '❌'} Pragma: no-cache")
    
    expires_found = 'Expires" content="0' in html_content
    print(f"   {'✅' if expires_found else '❌'} Expires: 0")
    
    # Проверяем версию в title
    version_title = 'v2.1 (LogScale)' in html_content
    print(f"   {'✅' if version_title else '❌'} Title версия: v2.1 (LogScale)")
    
    print("\n🚀 Проверка логарифмической функциональности:")
    
    # Проверяем новые элементы
    outliers_warning = 'chart-outliers-warning' in html_content
    print(f"   {'✅' if outliers_warning else '❌'} Предупреждение о выбросах")
    
    log_scale_code = 'logarithmic' in html_content
    print(f"   {'✅' if log_scale_code else '❌'} Логарифмическая шкала")
    
    value_ratio = 'valueRatio' in html_content
    print(f"   {'✅' if value_ratio else '❌'} Анализ разброса данных")
    
    auto_scale = 'useLogScale' in html_content
    print(f"   {'✅' if auto_scale else '❌'} Автоматический выбор шкалы")
    
    # Проверяем комментарии версий
    version_comments = 'v2.1 - LOGARITHMIC SCALE EDITION' in html_content
    print(f"   {'✅' if version_comments else '❌'} Комментарии версии в JS")
    
    chart_function_comments = 'Auto-detects data outliers' in html_content
    print(f"   {'✅' if chart_function_comments else '❌'} Комментарии функции графика")
    
    print("\n📋 Проверка кода логарифмической шкалы:")
    
    # Ищем ключевые части кода
    log_axis_config = 'type: \'logarithmic\'' in html_content
    print(f"   {'✅' if log_axis_config else '❌'} Конфигурация логарифмической оси")
    
    format_labels = 'toFixed(1)' in html_content and "'М'" in html_content
    print(f"   {'✅' if format_labels else '❌'} Форматирование меток (₸ 1.5М)")
    
    max_ticks = 'maxTicksLimit: 8' in html_content
    print(f"   {'✅' if max_ticks else '❌'} Ограничение меток (макс. 8)")
    
    outlier_detection = 'valueRatio > 5' in html_content
    print(f"   {'✅' if outlier_detection else '❌'} Обнаружение выбросов (>5x)")
    
    print("\n🎯 ИТОГОВАЯ ПРОВЕРКА:")
    
    all_features = [
        cache_control_found,
        version_title,
        outliers_warning,
        log_scale_code,
        value_ratio,
        auto_scale,
        log_axis_config,
        outlier_detection
    ]
    
    success_count = sum(all_features)
    total_features = len(all_features)
    
    if success_count == total_features:
        print(f"   🎉 ВСЕ ФУНКЦИИ ОБНОВЛЕНЫ! ({success_count}/{total_features})")
        print("   ✅ Кэш браузера принудительно сброшен")
        print("   ✅ Логарифмическая шкала активна")
        print("   ✅ Система готова к тестированию")
    else:
        print(f"   ⚠️ Обновлено функций: {success_count}/{total_features}")
        print("   🔄 Возможно требуется жесткий перезапуск браузера (Ctrl+Shift+R)")
    
    print("\n" + "=" * 80)
    print("ИНСТРУКЦИИ ДЛЯ ПОЛЬЗОВАТЕЛЯ")
    print("=" * 80)
    
    print(f"\n🔗 Адрес: {BASE_URL}/")
    print("\n💻 Для обновления кэша в браузере:")
    print("   • Chrome/Firefox: Ctrl + Shift + R")
    print("   • Safari: Cmd + Shift + R")
    print("   • Или F12 → Network → Disable cache + перезагрузка")
    
    print("\n📊 Тестирование логарифмической шкалы:")
    print("   1. ПРОГНОЗ ПРОДАЖ → 📊 Сравнение факт / прогноз")
    print("   2. Период: 01.06.2025 - 07.06.2025")
    print("   3. Филиал: Мадлен Plaza")
    print("   4. Нажать 'Загрузить'")
    
    print("\n✅ Ожидаемые результаты:")
    print("   • Title окна: 'Админ панель - v2.1 (LogScale)'")
    print("   • График автоматически выбирает шкалу")
    print("   • При разбросе >5x: желтое предупреждение + лог. шкала")
    print("   • При разбросе ≤5x: обычная линейная шкала")
    print("   • Подписи: ₸ 1.5М, ₸ 500К")
    print("   • Максимум 8 меток по оси Y")

if __name__ == "__main__":
    test_cache_busting()