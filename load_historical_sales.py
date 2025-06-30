#!/usr/bin/env python3
"""
Скрипт для загрузки исторических данных продаж из iiko API
Загружает данные с 01.06.2024 по 31.12.2024 частями по 15 дней
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
import time
import logging
from typing import Dict, Any, Tuple, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API configuration
API_BASE_URL = "http://localhost:8002"
SALES_SYNC_ENDPOINT = f"{API_BASE_URL}/api/sales/sync"

# Date configuration
START_DATE = datetime(2024, 6, 1)  # 01.06.2024
END_DATE = datetime(2024, 12, 31)  # 31.12.2024
CHUNK_SIZE_DAYS = 15  # Load 15 days at a time
DELAY_BETWEEN_REQUESTS = 5  # Seconds to wait between requests


def generate_date_chunks(start: datetime, end: datetime, chunk_days: int) -> List[Tuple[datetime, datetime]]:
    """Generate list of date ranges for chunked loading"""
    chunks = []
    current_start = start
    
    while current_start <= end:
        current_end = min(current_start + timedelta(days=chunk_days - 1), end)
        chunks.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    return chunks


async def sync_sales_chunk(session: aiohttp.ClientSession, from_date: datetime, to_date: datetime) -> Dict[str, Any]:
    """Sync sales data for a specific date range"""
    params = {
        'from_date': from_date.strftime('%Y-%m-%d'),
        'to_date': to_date.strftime('%Y-%m-%d')
    }
    
    logger.info(f"🔄 Загрузка данных: {params['from_date']} - {params['to_date']}")
    
    try:
        async with session.post(SALES_SYNC_ENDPOINT, params=params) as response:
            result = await response.json()
            
            if result.get('status') == 'success':
                logger.info(
                    f"✅ Успешно загружено: {result.get('summary_records', 0)} дневных, "
                    f"{result.get('hourly_records', 0)} почасовых записей"
                )
            else:
                logger.error(
                    f"❌ Ошибка: {result.get('message', 'Unknown error')}\n"
                    f"   Детали: {result.get('details', 'No details')}"
                )
            
            return result
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при загрузке {from_date} - {to_date}: {str(e)}")
        return {
            'status': 'error',
            'message': str(e),
            'summary_records': 0,
            'hourly_records': 0
        }


async def load_historical_data():
    """Main function to load all historical data"""
    logger.info(f"🚀 Начало загрузки исторических данных с {START_DATE.date()} по {END_DATE.date()}")
    
    # Generate date chunks
    date_chunks = generate_date_chunks(START_DATE, END_DATE, CHUNK_SIZE_DAYS)
    logger.info(f"📅 Разбито на {len(date_chunks)} частей по {CHUNK_SIZE_DAYS} дней")
    
    # Statistics
    total_summary = 0
    total_hourly = 0
    success_count = 0
    error_count = 0
    
    async with aiohttp.ClientSession() as session:
        for i, (from_date, to_date) in enumerate(date_chunks, 1):
            logger.info(f"\n{'='*60}")
            logger.info(f"📦 Часть {i}/{len(date_chunks)}")
            
            # Sync data
            result = await sync_sales_chunk(session, from_date, to_date)
            
            # Update statistics
            if result.get('status') == 'success':
                success_count += 1
                total_summary += result.get('summary_records', 0)
                total_hourly += result.get('hourly_records', 0)
            else:
                error_count += 1
            
            # Delay between requests (except for the last one)
            if i < len(date_chunks):
                logger.info(f"⏳ Пауза {DELAY_BETWEEN_REQUESTS} секунд перед следующим запросом...")
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
    
    # Final report
    logger.info(f"\n{'='*60}")
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ:")
    logger.info(f"✅ Успешно загружено: {success_count} частей")
    logger.info(f"❌ С ошибками: {error_count} частей")
    logger.info(f"📈 Всего дневных записей: {total_summary}")
    logger.info(f"📊 Всего почасовых записей: {total_hourly}")
    logger.info(f"{'='*60}\n")
    
    if error_count > 0:
        logger.warning("⚠️ Некоторые части не были загружены. Проверьте логи выше для деталей.")
    else:
        logger.info("🎉 Все данные успешно загружены!")


async def test_connection():
    """Test connection to the API"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{API_BASE_URL}/api/sales/stats") as response:
                if response.status == 200:
                    stats = await response.json()
                    logger.info("✅ Соединение с API установлено")
                    logger.info(f"📊 Текущая статистика: {stats.get('summary_records', 0)} записей в БД")
                    return True
                else:
                    logger.error(f"❌ API вернул статус: {response.status}")
                    return False
    except Exception as e:
        logger.error(f"❌ Не удалось подключиться к API: {str(e)}")
        return False


async def main():
    """Main entry point"""
    logger.info("🔧 Sales Forecast Historical Data Loader")
    logger.info(f"📍 API URL: {API_BASE_URL}")
    
    # Test connection first
    if not await test_connection():
        logger.error("❌ Не удалось подключиться к API. Проверьте, что приложение запущено на порту 8002")
        return
    
    # Ask for confirmation
    print(f"\n⚠️  ВНИМАНИЕ: Будут загружены данные с {START_DATE.date()} по {END_DATE.date()}")
    print(f"   Это может занять примерно {len(generate_date_chunks(START_DATE, END_DATE, CHUNK_SIZE_DAYS)) * (DELAY_BETWEEN_REQUESTS + 10) // 60} минут")
    
    confirmation = input("\n❓ Продолжить? (y/n): ").strip().lower()
    if confirmation != 'y':
        logger.info("❌ Операция отменена пользователем")
        return
    
    # Start loading
    start_time = time.time()
    await load_historical_data()
    
    elapsed_time = time.time() - start_time
    logger.info(f"⏱️  Общее время выполнения: {elapsed_time/60:.1f} минут")


if __name__ == "__main__":
    asyncio.run(main())