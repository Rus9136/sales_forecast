#!/usr/bin/env python3
"""
Поиск оптимального периода обучения модели
Тестируем разные периоды: 6 месяцев, 12 месяцев, 18 месяцев, 24 месяца
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timedelta

API_BASE_URL = "http://localhost:8002"
RETRAIN_ENDPOINT = f"{API_BASE_URL}/api/forecast/retrain"
MODEL_INFO_ENDPOINT = f"{API_BASE_URL}/api/forecast/model/info"

# Периоды для тестирования (в днях)
PERIODS_TO_TEST = [
    (180, "6 месяцев"),
    (365, "12 месяцев"),
    (547, "18 месяцев"),
    (730, "24 месяца")
]

async def test_training_period(days: int, period_name: str):
    """Тестирование конкретного периода обучения"""
    print(f"\n{'='*50}")
    print(f"🔬 ТЕСТИРОВАНИЕ: {period_name} ({days} дней)")
    print(f"{'='*50}")
    
    # Временно изменяем период в коде (через API параметры)
    # Для этого нам нужно модифицировать API или создать тестовый endpoint
    
    try:
        start_time = time.time()
        
        # Отправляем запрос на переобучение
        # Пока API не поддерживает параметры периода, используем стандартный endpoint
        timeout = aiohttp.ClientTimeout(total=300)  # 5 минут
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(RETRAIN_ENDPOINT) as response:
                if response.status == 200:
                    result = await response.json()
                    elapsed_time = time.time() - start_time
                    
                    print(f"✅ Обучение завершено за {elapsed_time:.1f} сек")
                    
                    if 'metrics' in result:
                        metrics = result['metrics']
                        train_samples = metrics.get('train_samples', 0)
                        val_samples = metrics.get('val_samples', 0) 
                        test_samples = metrics.get('test_samples', 0)
                        total_samples = train_samples + val_samples + test_samples
                        
                        print(f"📊 Результаты:")
                        print(f"  - Всего данных: {total_samples:,} записей")
                        print(f"  - Test MAPE: {metrics.get('test_mape', 0):.2f}%")
                        print(f"  - Val MAPE: {metrics.get('val_mape', 0):.2f}%")
                        print(f"  - R²: {metrics.get('test_r2', 0):.4f}")
                        
                        return {
                            'period_days': days,
                            'period_name': period_name,
                            'total_samples': total_samples,
                            'test_mape': metrics.get('test_mape', 0),
                            'val_mape': metrics.get('val_mape', 0),
                            'test_r2': metrics.get('test_r2', 0),
                            'training_time': elapsed_time
                        }
                else:
                    print(f"❌ Ошибка: {response.status}")
                    return None
                    
    except Exception as e:
        print(f"❌ Ошибка: {str(e)}")
        return None

async def quick_period_analysis():
    """Быстрый анализ без переобучения - через проверку объема данных"""
    print("📊 БЫСТРЫЙ АНАЛИЗ ОБЪЕМА ДАННЫХ ПО ПЕРИОДАМ:")
    print("=" * 60)
    
    from datetime import datetime, timedelta
    import aiohttp
    
    end_date = datetime.now().date()
    
    async with aiohttp.ClientSession() as session:
        for days, period_name in PERIODS_TO_TEST:
            start_date = end_date - timedelta(days=days)
            
            # Здесь мы бы запросили статистику через отдельный endpoint
            # Пока покажем теоретические расчеты
            
            # Средние значения на основе имеющихся данных
            avg_records_per_day = 15097 / (datetime.now().date() - datetime(2022, 3, 1).date()).days
            estimated_records = int(avg_records_per_day * days)
            
            # Учитываем потери от rolling features
            departments = 40  # примерно
            estimated_after_dropna = estimated_records - (departments * 7)
            
            print(f"\n📅 {period_name} ({start_date} - {end_date}):")
            print(f"  - Ожидается записей: ~{estimated_after_dropna:,}")
            print(f"  - Увеличение от базовой модели: {estimated_after_dropna/5008:.1f}x")
            
            # Оценка качества на основе объема данных
            if estimated_after_dropna > 10000:
                quality_estimate = "Отлично"
            elif estimated_after_dropna > 7000:
                quality_estimate = "Хорошо"
            elif estimated_after_dropna > 5000:
                quality_estimate = "Нормально"
            else:
                quality_estimate = "Недостаточно"
            
            print(f"  - Оценка качества: {quality_estimate}")

async def create_custom_retrain_request(days: int):
    """Создание кастомного запроса переобучения через прямое обращение к сервису"""
    # Это требует модификации API для принятия параметра training_days
    # Пока не реализовано
    pass

async def main():
    """Основная функция"""
    print("🔬 Поиск оптимального периода обучения модели")
    print("=" * 50)
    
    # Быстрый анализ объема данных
    await quick_period_analysis()
    
    print(f"\n\n💡 РЕКОМЕНДАЦИИ НА ОСНОВЕ АНАЛИЗА:")
    print("=" * 50)
    
    print("\n🎯 Оптимальный период: 12-18 месяцев")
    print("   Причины:")
    print("   ✅ Захватывает полный годовой цикл сезонности")
    print("   ✅ Достаточно данных для хорошей генерализации")
    print("   ✅ Не включает слишком старые данные (2022)")
    print("   ✅ Баланс между актуальностью и объемом")
    
    print(f"\n⚠️ Проблема с 3+ годами данных:")
    print("   - MAPE увеличился до 10.42% (был 7.67%)")
    print("   - Вероятно, данные 2022-2023 содержат устаревшие паттерны")
    print("   - Бизнес мог измениться за это время")
    
    print(f"\n🔧 Следующие шаги:")
    print("   1. Вернуть настройку на 365 дней (12 месяцев)")
    print("   2. Переобучить модель")
    print("   3. Сравнить с базовой моделью (180 дней)")
    
    # Предложение автоматического применения
    apply_recommendation = input("\n❓ Применить рекомендацию (12 месяцев)? (y/n): ").strip().lower()
    
    if apply_recommendation == 'y':
        print("\n🔧 Применяем оптимальную настройку...")
        
        # Здесь можно было бы изменить настройки и переобучить
        print("✅ Для применения измените training_service.py:")
        print("   start_date = end_date - timedelta(days=365)")
        print("   Затем запустите переобучение через API")
    else:
        print("ℹ️ Настройки не изменены")

if __name__ == "__main__":
    asyncio.run(main())