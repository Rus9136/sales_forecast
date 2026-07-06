"""Отправка алертов мониторинга наружу (ML_AUDIT_REPORT.md P0-6, Фаза 1.5).

До этого алерты формировались в model_monitoring_service и никуда не
отправлялись — были видны только по запросу GET /api/monitoring/alerts/recent.

Канал — Telegram Bot API. Конфигурация через env (.env.prod):
    TELEGRAM_BOT_TOKEN=123456:ABC-...   (создать через @BotFather)
    TELEGRAM_CHAT_ID=-1001234567890     (id чата/группы для алертов)

Отказоустойчивость: любая ошибка отправки логируется и НЕ пробрасывается —
алертинг не должен ронять мониторинг или retrain.
"""

import logging

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
_MAX_MESSAGE_LEN = 4000  # лимит Telegram 4096, оставляем запас


def telegram_configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_CHAT_ID)


def send_telegram_alert(text: str) -> bool:
    """Отправить сообщение в настроенный Telegram-чат.

    Возвращает True при успехе. Если токен/чат не настроены — warning в лог
    и False (сам алерт при этом уже есть в логах вызывающего кода).
    """
    if not telegram_configured():
        logger.warning(
            "Telegram alert skipped (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not set): %s",
            text[:200],
        )
        return False

    try:
        resp = httpx.post(
            _TELEGRAM_API.format(token=settings.TELEGRAM_BOT_TOKEN),
            json={
                "chat_id": settings.TELEGRAM_CHAT_ID,
                "text": text[:_MAX_MESSAGE_LEN],
            },
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.error(
                f"Telegram alert failed: HTTP {resp.status_code} — {resp.text[:200]}"
            )
            return False
        return True
    except Exception as e:
        logger.error(f"Telegram alert failed: {e}")
        return False
