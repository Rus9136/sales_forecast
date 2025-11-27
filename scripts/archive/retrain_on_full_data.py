#!/usr/bin/env python3
"""
Переобучение модели на всех доступных данных (3+ года)
"""

import asyncio
import aiohttp
import json
import time
from datetime import datetime, timedelta

API_BASE_URL = "http://localhost:8002"
RETRAIN_ENDPOINT = f"{API_BASE_URL}/api/forecast/retrain"
MODEL_INFO_ENDPOINT = f"{API_BASE_URL}/api/forecast/model/info"
STATS_ENDPOINT = f"{API_BASE_URL}/api/sales/stats"

async def check_api_connection():
    """Проверка соединения с API"""
    print("🔧 Проверка соединения с API...")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(STATS_ENDPOINT) as response:
                if response.status == 200:
                    stats = await response.json()
                    print(f"✅ API доступен")
                    print(f"📊 Данных в БД: {stats.get('summary_records', 0)} записей")
                    return True
                else:
                    print(f"❌ API вернул статус: {response.status}")
                    return False
    except Exception as e:
        print(f"❌ Ошибка подключения: {str(e)}")
        return False

async def get_current_model_info():
    """Получение информации о текущей модели"""
    print("\n📋 Информация о текущей модели:")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(MODEL_INFO_ENDPOINT) as response:
                if response.status == 200:
                    info = await response.json()
                    print(f"  Статус: {info.get('status', 'unknown')}")
                    if 'training_metrics' in info:
                        metrics = info['training_metrics']
                        print(f"  Текущий MAPE: {metrics.get('test_mape', 'N/A'):.2f}%")
                        print(f"  Данных для обучения: {metrics.get('train_samples', 0) + metrics.get('val_samples', 0) + metrics.get('test_samples', 0)}")
                        print(f"  R²: {metrics.get('test_r2', 'N/A'):.4f}")
                    return info
                else:
                    print(f"  ❌ Ошибка получения информации: {response.status}")
                    return None
    except Exception as e:
        print(f"  ❌ Ошибка: {str(e)}")
        return None

async def retrain_model():
    """Переобучение модели на всех данных"""
    print("\n🚀 Начинаем переобучение модели на всех доступных данных...")
    print("⏳ Это может занять 2-5 минут...")
    
    start_time = time.time()
    
    try:
        timeout = aiohttp.ClientTimeout(total=600)  # 10 минут таймаут
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(RETRAIN_ENDPOINT) as response:
                if response.status == 200:
                    result = await response.json()
                    elapsed_time = time.time() - start_time
                    
                    print(f"\n✅ Переобучение завершено за {elapsed_time/60:.1f} минут!")
                    print("\n📊 РЕЗУЛЬТАТЫ ОБУЧЕНИЯ:")
                    
                    # Training metrics
                    if 'training_data_info' in result:
                        data_info = result['training_data_info']
                        print(f"📈 Объем данных:")
                        print(f"  - Train: {data_info.get('train_samples', 0):,} записей")
                        print(f"  - Validation: {data_info.get('val_samples', 0):,} записей")
                        print(f"  - Test: {data_info.get('test_samples', 0):,} записей")
                        print(f"  - ВСЕГО: {data_info.get('total_samples', 0):,} записей")
                    
                    # Model metrics
                    if 'metrics' in result:
                        metrics = result['metrics']
                        print(f"\n🎯 Качество модели:")
                        print(f"  - Test MAPE: {metrics.get('test_mape', 0):.2f}%")
                        print(f"  - Validation MAPE: {metrics.get('val_mape', 0):.2f}%")
                        print(f"  - Test R²: {metrics.get('test_r2', 0):.4f}")
                        print(f"  - Test RMSE: {metrics.get('test_rmse', 0):,.0f}")
                        
                        # Сравнение с предыдущей моделью
                        if metrics.get('test_mape', 0) < 7.67:
                            improvement = 7.67 - metrics.get('test_mape', 0)
                            print(f"\n🏆 УЛУЧШЕНИЕ: MAPE снизился на {improvement:.2f}% (с 7.67% до {metrics.get('test_mape', 0):.2f}%)")
                        else:
                            print(f"\n📊 MAPE: {metrics.get('test_mape', 0):.2f}% (предыдущий: 7.67%)")
                    
                    # Feature importance
                    if 'feature_importance' in result:
                        print(f"\n🔍 Топ-5 важных признаков:")
                        for feature in result['feature_importance'][:5]:
                            print(f"  - {feature['feature']}: {feature['importance']:.4f}")
                    
                    return result
                    
                else:
                    error_text = await response.text()
                    print(f"❌ Ошибка переобучения: {response.status}")
                    print(f"   Детали: {error_text}")
                    return None
                    
    except asyncio.TimeoutError:
        print("❌ Таймаут при переобучении модели (10 минут)")
        return None
    except Exception as e:
        print(f"❌ Критическая ошибка: {str(e)}")
        return None

async def compare_before_after():
    """Сравнение до и после переобучения"""
    print("\n" + "="*60)
    print("СРАВНЕНИЕ РЕЗУЛЬТАТОВ")
    print("="*60)
    
    print("\n📊 ТЕКУЩАЯ МОДЕЛЬ (180 дней):")
    print("  - Данных для обучения: ~5,008 записей")
    print("  - Test MAPE: 7.67%")
    print("  - R²: 0.9952")
    
    print("\n📈 НОВАЯ МОДЕЛЬ (3+ года данных):")
    await get_current_model_info()

async def main():
    """Основная функция"""
    print("🤖 Sales Forecast Model Retraining (Full Dataset)")
    print("="*50)
    
    # Проверка соединения
    if not await check_api_connection():
        print("❌ Не удалось подключиться к API")
        return
    
    # Информация о текущей модели
    await get_current_model_info()
    
    # Подтверждение
    print(f"\n⚠️  ВНИМАНИЕ:")
    print(f"   - Модель будет переобучена на ВСЕХ доступных данных (3+ года)")
    print(f"   - Ожидается значительное улучшение качества прогнозов")
    print(f"   - Процесс займет 2-5 минут")
    
    confirmation = input("\n❓ Начать переобучение? (y/n): ").strip().lower()
    if confirmation != 'y':
        print("❌ Операция отменена")
        return
    
    # Переобучение
    result = await retrain_model()
    
    if result:
        # Сравнение результатов
        await compare_before_after()
        
        print("\n🎉 Переобучение успешно завершено!")
        print("💡 Теперь модель учитывает:")
        print("   - Полные годовые циклы и сезонность")
        print("   - Долгосрочные тренды развития бизнеса")
        print("   - Больший объем праздничных и особых дней")
        print("   - Исторические паттерны поведения клиентов")
    else:
        print("\n❌ Переобучение не удалось. Проверьте логи приложения.")

if __name__ == "__main__":
    asyncio.run(main())