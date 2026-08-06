"""Транспорт к iiko API приказов (menuChange) — создание, чтение, отмена.

Только HTTP и разбор ответа, без бизнес-логики: решение «что и когда
отправлять» принимает price_order_service.

Endpoint-ы (iiko 7.8, docs/prikazy.pdf):
    POST /resto/api/v2/documents/menuChange           — создание (без id) /
                                                        редактирование (с id)
    GET  /resto/api/v2/documents/menuChange/byId?id=
    GET  /resto/api/v2/documents/menuChange?dateFrom&dateTo[&status]

Проверено на боевом контуре 2026-08-06 (этап 0): создание возвращает документ
целиком, documentNumber присваивает iiko сама, отмена — POST с тем же id и
status='DELETED'.

ГЛАВНОЕ ПРАВИЛО ЭТОГО МОДУЛЯ: POST не ретраится никогда. Повтор после
таймаута создал бы второй приказ на те же позиции — цена уехала бы дважды.
При обрыве вызывающий помечает приказ 'sending' и ищет документ-сироту по
маркеру SF#{order_id} в комментарии (find_by_marker).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional
from urllib.parse import urlparse

import httpx

from .iiko_auth import IikoAuthService

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 120.0
MENU_CHANGE_PATH = "/resto/api/v2/documents/menuChange"


class IikoOrderError(Exception):
    """iiko отказал в операции (result != SUCCESS или HTTP-ошибка)."""

    def __init__(self, message: str, errors: Optional[list] = None,
                 status_code: Optional[int] = None):
        super().__init__(message)
        self.errors = errors or []
        self.status_code = status_code


def marker_for(order_id: int) -> str:
    """Маркер приказа в комментарии — единственный способ опознать документ,
    если ответ на POST не дошёл. Должен быть уникален и стабилен."""
    return f"SF#{order_id}"


def domain_host(url: str) -> str:
    return urlparse(url).hostname or url


def base_url_for_host(host: str, domains: list[str]) -> str:
    """host из departments.iiko_source_domain → базовый URL из IIKO_DOMAINS."""
    for url in domains:
        if domain_host(url) == host:
            return url
    raise IikoOrderError(f"Домен iiko '{host}' не настроен в IIKO_DOMAINS")


class IikoMenuChangeWriter:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self._auth = IikoAuthService(self.base_url)

    async def _token(self) -> str:
        return await self._auth.get_auth_token()

    @staticmethod
    def _unwrap(resp: httpx.Response) -> Any:
        """Разобрать конверт {result, errors, response}. GET byId на части
        сборок отдаёт документ без конверта — поддерживаем оба вида."""
        if resp.status_code != 200:
            raise IikoOrderError(
                f"iiko вернул HTTP {resp.status_code}: {resp.text[:500]}",
                status_code=resp.status_code,
            )
        try:
            body = resp.json()
        except ValueError:
            raise IikoOrderError(f"iiko вернул не-JSON: {resp.text[:500]}")

        if isinstance(body, dict) and "result" in body:
            if body.get("result") != "SUCCESS":
                errors = body.get("errors") or []
                raise IikoOrderError(
                    f"iiko отклонил запрос: {'; '.join(str(e) for e in errors) or 'без описания'}",
                    errors=errors,
                )
            return body.get("response")
        return body

    async def create_order(self, payload: dict) -> dict:
        """Создать приказ (payload без 'id'). Возвращает созданный документ.

        НЕ РЕТРАИТСЯ. Любая сетевая ошибка/таймаут пробрасывается наверх —
        документ мог создаться, и решение принимает вызывающий.
        """
        token = await self._token()
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}{MENU_CHANGE_PATH}",
                params={"key": token},
                headers={"Content-Type": "application/json"},
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
        doc = self._unwrap(resp)
        if not isinstance(doc, dict) or not doc.get("id"):
            raise IikoOrderError(f"iiko не вернул id созданного приказа: {str(doc)[:300]}")
        logger.info("iiko menuChange created: id=%s number=%s status=%s",
                    doc.get("id"), doc.get("documentNumber"), doc.get("status"))
        return doc

    async def update_order(self, payload: dict) -> dict:
        """Редактировать существующий приказ (payload с 'id').

        Ограничения iiko: редактировать можно приказ в статусе NEW либо
        PROCESSED с датой проведения сегодня или позже. У проведённого
        задним числом меняется только dateTo.
        """
        if not payload.get("id"):
            raise IikoOrderError("update_order требует 'id' в payload")
        token = await self._token()
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{self.base_url}{MENU_CHANGE_PATH}",
                params={"key": token},
                headers={"Content-Type": "application/json"},
                content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            )
        return self._unwrap(resp)

    async def get_order(self, document_id: str) -> Optional[dict]:
        token = await self._token()
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{self.base_url}{MENU_CHANGE_PATH}/byId",
                params={"key": token, "id": document_id},
            )
        try:
            doc = self._unwrap(resp)
        except IikoOrderError as e:
            if e.status_code == 404:
                return None
            raise
        return doc if isinstance(doc, dict) else None

    async def list_orders(self, date_from: str, date_to: str,
                          status: Optional[str] = None) -> list[dict]:
        token = await self._token()
        params: dict = {"key": token, "dateFrom": date_from, "dateTo": date_to}
        if status:
            params["status"] = status
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(f"{self.base_url}{MENU_CHANGE_PATH}", params=params)
        docs = self._unwrap(resp)
        return docs if isinstance(docs, list) else []

    async def find_by_marker(self, marker: str, date_from: str, date_to: str) -> Optional[dict]:
        """Найти документ-сироту по маркеру в комментарии — восстановление
        после обрыва POST (см. модульный docstring)."""
        for doc in await self.list_orders(date_from, date_to):
            if marker in (doc.get("comment") or ""):
                return doc
        return None
