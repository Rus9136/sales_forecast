#!/usr/bin/env python3
"""
Продвинутый скрипт для загрузки исторических данных с дополнительными функциями:
- Автоматическая повторная попытка при ошибках
- Возможность продолжить с места остановки
- Детальная статистика по департаментам
- Сохранение прогресса
"""

import asyncio
import aiohttp
from datetime import datetime, timedelta
import time
import logging
import json
import os
from typing import Dict, Any, Tuple, List, Optional

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
API_BASE_URL = "http://localhost:8002"
SALES_SYNC_ENDPOINT = f"{API_BASE_URL}/api/sales/sync"
STATS_ENDPOINT = f"{API_BASE_URL}/api/sales/stats"
PROGRESS_FILE = "load_progress.json"

# Date configuration
START_DATE = datetime(2024, 6, 1)
END_DATE = datetime(2024, 12, 31)
CHUNK_SIZE_DAYS = 15
DELAY_BETWEEN_REQUESTS = 5
MAX_RETRIES = 3
RETRY_DELAY = 10


class ProgressTracker:
    """Track loading progress"""
    
    def __init__(self, filename: str = PROGRESS_FILE):
        self.filename = filename
        self.progress = self.load_progress()
    
    def load_progress(self) -> Dict[str, Any]:
        """Load progress from file"""
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {
            'completed_chunks': [],
            'failed_chunks': [],
            'statistics': {
                'total_summary': 0,
                'total_hourly': 0,
                'start_time': None,
                'last_update': None
            }
        }
    
    def save_progress(self):
        """Save progress to file"""
        self.progress['statistics']['last_update'] = datetime.now().isoformat()
        with open(self.filename, 'w') as f:
            json.dump(self.progress, f, indent=2)
    
    def mark_completed(self, from_date: str, to_date: str, records: Dict[str, int]):
        """Mark chunk as completed"""
        chunk_id = f"{from_date}_{to_date}"
        if chunk_id not in self.progress['completed_chunks']:
            self.progress['completed_chunks'].append(chunk_id)
        
        # Remove from failed if it was there
        if chunk_id in self.progress['failed_chunks']:
            self.progress['failed_chunks'].remove(chunk_id)
        
        # Update statistics
        self.progress['statistics']['total_summary'] += records.get('summary', 0)
        self.progress['statistics']['total_hourly'] += records.get('hourly', 0)
        
        self.save_progress()
    
    def mark_failed(self, from_date: str, to_date: str):
        """Mark chunk as failed"""
        chunk_id = f"{from_date}_{to_date}"
        if chunk_id not in self.progress['failed_chunks']:
            self.progress['failed_chunks'].append(chunk_id)
        self.save_progress()
    
    def is_completed(self, from_date: str, to_date: str) -> bool:
        """Check if chunk is already completed"""
        chunk_id = f"{from_date}_{to_date}"
        return chunk_id in self.progress['completed_chunks']


async def sync_sales_with_retry(
    session: aiohttp.ClientSession, 
    from_date: datetime, 
    to_date: datetime,
    max_retries: int = MAX_RETRIES
) -> Dict[str, Any]:
    """Sync sales data with automatic retry on failure"""
    
    from_str = from_date.strftime('%Y-%m-%d')
    to_str = to_date.strftime('%Y-%m-%d')
    
    for attempt in range(max_retries):
        try:
            params = {'from_date': from_str, 'to_date': to_str}
            
            logger.info(f"🔄 Попытка {attempt + 1}/{max_retries}: Загрузка {from_str} - {to_str}")
            
            async with session.post(SALES_SYNC_ENDPOINT, params=params, timeout=300) as response:
                result = await response.json()
                
                if result.get('status') == 'success':
                    logger.info(
                        f"✅ Успешно: {result.get('summary_records', 0)} дневных, "
                        f"{result.get('hourly_records', 0)} почасовых записей"
                    )
                    return result
                else:
                    error_msg = result.get('message', 'Unknown error')
                    logger.warning(f"⚠️ Ошибка API: {error_msg}")
                    
                    # If it's a data issue, no point retrying
                    if 'No data found' in error_msg:
                        return result
                    
                    # Otherwise, retry
                    if attempt < max_retries - 1:
                        logger.info(f"⏳ Повторная попытка через {RETRY_DELAY} секунд...")
                        await asyncio.sleep(RETRY_DELAY)
                        
        except asyncio.TimeoutError:
            logger.error(f"❌ Таймаут при загрузке {from_str} - {to_str}")
        except Exception as e:
            logger.error(f"❌ Ошибка: {str(e)}")
        
        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY)
    
    # All retries failed
    return {
        'status': 'error',
        'message': f'Failed after {max_retries} attempts',
        'summary_records': 0,
        'hourly_records': 0
    }


async def get_current_stats(session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Get current database statistics"""
    try:
        async with session.get(STATS_ENDPOINT) as response:
            if response.status == 200:
                return await response.json()
    except:
        pass
    return {}


async def load_historical_data_advanced():
    """Advanced historical data loading with progress tracking"""
    
    logger.info(f"🚀 Загрузка исторических данных с {START_DATE.date()} по {END_DATE.date()}")
    
    # Initialize progress tracker
    tracker = ProgressTracker()
    
    # Generate date chunks
    date_chunks = []
    current_start = START_DATE
    while current_start <= END_DATE:
        current_end = min(current_start + timedelta(days=CHUNK_SIZE_DAYS - 1), END_DATE)
        date_chunks.append((current_start, current_end))
        current_start = current_end + timedelta(days=1)
    
    logger.info(f"📅 Всего частей: {len(date_chunks)}")
    
    # Check progress
    if tracker.progress['completed_chunks']:
        logger.info(f"📈 Уже загружено: {len(tracker.progress['completed_chunks'])} частей")
        logger.info(f"📊 Текущая статистика: {tracker.progress['statistics']['total_summary']} дневных записей")
    
    # Start loading
    start_time = time.time()
    if not tracker.progress['statistics']['start_time']:
        tracker.progress['statistics']['start_time'] = datetime.now().isoformat()
    
    async with aiohttp.ClientSession() as session:
        # Get initial stats
        initial_stats = await get_current_stats(session)
        logger.info(f"📊 Начальное состояние БД: {initial_stats.get('summary_records', 0)} записей")
        
        # Process chunks
        for i, (from_date, to_date) in enumerate(date_chunks, 1):
            from_str = from_date.strftime('%Y-%m-%d')
            to_str = to_date.strftime('%Y-%m-%d')
            
            # Skip if already completed
            if tracker.is_completed(from_str, to_str):
                logger.info(f"⏭️ Пропуск {from_str} - {to_str} (уже загружено)")
                continue
            
            logger.info(f"\n{'='*60}")
            logger.info(f"📦 Часть {i}/{len(date_chunks)}")
            
            # Sync with retry
            result = await sync_sales_with_retry(session, from_date, to_date)
            
            # Update progress
            if result.get('status') == 'success':
                tracker.mark_completed(from_str, to_str, {
                    'summary': result.get('summary_records', 0),
                    'hourly': result.get('hourly_records', 0)
                })
            else:
                tracker.mark_failed(from_str, to_str)
            
            # Show progress
            completed = len(tracker.progress['completed_chunks'])
            failed = len(tracker.progress['failed_chunks'])
            remaining = len(date_chunks) - completed - failed
            
            progress_pct = (completed / len(date_chunks)) * 100
            logger.info(
                f"📊 Прогресс: {progress_pct:.1f}% "
                f"(✅ {completed} | ❌ {failed} | ⏳ {remaining})"
            )
            
            # Delay between requests
            if i < len(date_chunks) and remaining > 0:
                await asyncio.sleep(DELAY_BETWEEN_REQUESTS)
        
        # Get final stats
        final_stats = await get_current_stats(session)
        new_records = final_stats.get('summary_records', 0) - initial_stats.get('summary_records', 0)
    
    # Final report
    elapsed_time = time.time() - start_time
    
    logger.info(f"\n{'='*60}")
    logger.info("📊 ИТОГОВЫЙ ОТЧЕТ:")
    logger.info(f"⏱️  Время выполнения: {elapsed_time/60:.1f} минут")
    logger.info(f"✅ Успешно загружено: {len(tracker.progress['completed_chunks'])} частей")
    logger.info(f"❌ С ошибками: {len(tracker.progress['failed_chunks'])} частей")
    logger.info(f"📈 Всего дневных записей: {tracker.progress['statistics']['total_summary']}")
    logger.info(f"📊 Всего почасовых записей: {tracker.progress['statistics']['total_hourly']}")
    logger.info(f"🆕 Новых записей в БД: {new_records}")
    
    if tracker.progress['failed_chunks']:
        logger.warning("\n⚠️ Не удалось загрузить следующие периоды:")
        for chunk in tracker.progress['failed_chunks']:
            logger.warning(f"  - {chunk.replace('_', ' по ')}")
        logger.info("\n💡 Совет: Запустите скрипт повторно для загрузки пропущенных периодов")
    else:
        logger.info("\n🎉 Все данные успешно загружены!")
        
        # Offer to clean up progress file
        if os.path.exists(PROGRESS_FILE):
            cleanup = input("\n❓ Удалить файл прогресса? (y/n): ").strip().lower()
            if cleanup == 'y':
                os.remove(PROGRESS_FILE)
                logger.info("🗑️  Файл прогресса удален")


async def main():
    """Main entry point"""
    logger.info("🔧 Sales Forecast Historical Data Loader (Advanced)")
    logger.info(f"📍 API URL: {API_BASE_URL}")
    
    # Test connection
    try:
        async with aiohttp.ClientSession() as session:
            stats = await get_current_stats(session)
            if stats:
                logger.info("✅ Соединение с API установлено")
                logger.info(f"📊 Текущая БД: {stats.get('summary_records', 0)} дневных записей")
            else:
                raise Exception("API не отвечает")
    except Exception as e:
        logger.error(f"❌ Ошибка подключения: {str(e)}")
        logger.error("Убедитесь, что приложение запущено на порту 8002")
        return
    
    # Check for existing progress
    if os.path.exists(PROGRESS_FILE):
        logger.info(f"\n📂 Найден файл прогресса от предыдущего запуска")
        resume = input("❓ Продолжить с места остановки? (y/n): ").strip().lower()
        if resume != 'y':
            os.remove(PROGRESS_FILE)
            logger.info("🗑️  Прогресс сброшен, начинаем заново")
    
    # Confirmation
    print(f"\n⚠️  Будут загружены данные с {START_DATE.date()} по {END_DATE.date()}")
    print(f"   Размер части: {CHUNK_SIZE_DAYS} дней")
    print(f"   Задержка между запросами: {DELAY_BETWEEN_REQUESTS} сек")
    
    confirmation = input("\n❓ Начать загрузку? (y/n): ").strip().lower()
    if confirmation != 'y':
        logger.info("❌ Операция отменена")
        return
    
    # Start loading
    await load_historical_data_advanced()


if __name__ == "__main__":
    asyncio.run(main())