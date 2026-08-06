"""Unit tests for iiko price orders (menuChange push).

Покрывает то, что решает судьбу цены в боевой кассе: форму payload,
предохранители сборки, разбор ответа iiko и опознание документа-сироты.
Без БД — сервисы создаются с db=None там, где используются чистые методы.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.services.iiko_menu_change_writer import (
    IikoMenuChangeWriter,
    IikoOrderError,
    base_url_for_host,
    marker_for,
)
from app.services.price_order_service import (
    APPROVED_TTL_DAYS,
    PriceOrderError,
    PriceOrderService,
)

pytestmark = pytest.mark.unit


DOMAINS = ["https://sandy-co-co.iiko.it", "https://madlen-group-so.iiko.it"]
DEPT_ID = "6e3aa45a-a8bc-4373-82fd-00e6ceb60357"
IIKO_PID = "8c6d1c3d-3b47-4b00-8c4d-18d2f614789d"


@pytest.fixture()
def service() -> PriceOrderService:
    return PriceOrderService(db=None)


def _item(**over) -> dict:
    base = {
        "recommendation_id": 1,
        "product_id": 10,
        "iiko_product_id": IIKO_PID,
        "new_price": 1500.0,
        "catalog_document_id": "f921a290-256f-409a-bcbd-3ce23ed5e87a",
    }
    base.update(over)
    return base


def _dept(domain: str = "madlen-group-so.iiko.it"):
    return SimpleNamespace(id=DEPT_ID, name="Мадлен 18 мкр", iiko_source_domain=domain)


def _rec(**over):
    base = {
        "id": 1,
        "product_id": 10,
        "current_price": 1400,
        "recommended_price": 1450,  # +3.6% — в пределах max_step 5%
        "cogs": 400,
        "menu_role": "workhorse",
        "reviewed_at": datetime.now(),
        "iiko_product_id": IIKO_PID,
        "iiko_source_domain": "madlen-group-so.iiko.it",
        "product_name": "Торт Наполеон",
        "product_code": "0001",
        "delta_pct": 7.14,
        "delta_gp": 12000,
        "rec_type": "optimizer",
    }
    base.update(over)
    return SimpleNamespace(**base)


def _catalog(**over) -> dict:
    base = {"price": 1400.0, "date_from": date.today() - timedelta(days=60),
            "document_id": "f921a290-256f-409a-bcbd-3ce23ed5e87a",
            "product_size_id": None, "price_type": "BASE",
            "has_sizes": False, "has_non_base": False}
    base.update(over)
    return base


class _FakeRules:
    """Правила «как в проде по умолчанию»: max_step 5%, min_margin 60%."""

    def __init__(self, violations=None):
        self.violations = violations or []

    def get_effective_rules(self, *_args, **_kwargs):
        return {}

    def check_recommendation(self, current_price, candidate_price, cogs, menu_role,
                             last_change_date, rules):
        if self.violations:
            return False, self.violations
        step = abs(candidate_price - current_price) / current_price
        if step > 0.05:
            return False, [f"max_step: {step:.2%} > 5%"]
        return True, []


class TestPayload:
    """Форма документа — то, что реально уедет в iiko."""

    def test_delete_previous_menu_is_always_false(self, service):
        payload = service._build_payload(DEPT_ID, date(2026, 8, 7), [_item()], {},
                                         "SF#1", "NEW")
        # true исключил бы из меню точки всё, чего нет в документе
        assert payload["deletePreviousMenu"] is False

    def test_document_shape(self, service):
        payload = service._build_payload(DEPT_ID, date(2026, 8, 7), [_item()], {},
                                         "SF#1 комментарий", "PROCESSED")
        assert payload["dateIncoming"] == "2026-08-07"
        assert payload["status"] == "PROCESSED"
        assert payload["dateTo"] == "2500-01-01"
        assert payload["comment"] == "SF#1 комментарий"
        assert len(payload["items"]) == 1

    def test_item_shape(self, service):
        item = service._build_payload(DEPT_ID, date(2026, 8, 7), [_item()], {},
                                      "c", "NEW")["items"][0]
        assert item["departmentId"] == DEPT_ID
        assert item["productId"] == IIKO_PID
        assert item["productSizeId"] is None
        assert item["including"] is True
        assert item["price"] == 1500.0

    def test_carried_attributes_win_over_defaults(self, service):
        carried = {IIKO_PID: {
            "dishOfDay": True, "flyerProgram": True,
            "pricesForCategories": [{"categoryId": "c1", "price": 100}],
            "includeForCategories": [{"categoryId": "c1", "include": True}],
        }}
        item = service._build_payload(DEPT_ID, date(2026, 8, 7), [_item()], carried,
                                      "c", "NEW")["items"][0]
        # приказ задаёт позицию целиком: не перенести атрибуты = обнулить их
        assert item["dishOfDay"] is True
        assert item["flyerProgram"] is True
        assert item["pricesForCategories"] == [{"categoryId": "c1", "price": 100}]

    def test_missing_carried_falls_back_to_empty(self, service):
        item = service._build_payload(DEPT_ID, date(2026, 8, 7), [_item()], {},
                                      "c", "NEW")["items"][0]
        assert item["dishOfDay"] is False
        assert item["flyerProgram"] is False
        assert item["pricesForCategories"] == []
        assert item["includeForCategories"] == []


class TestRejectReason:
    """Предохранители сборки: что НЕ должно уехать в кассу."""

    def _svc(self, rules=None) -> PriceOrderService:
        svc = PriceOrderService(db=None)
        svc._rules = rules or _FakeRules()
        return svc

    def test_valid_position_passes(self):
        assert self._svc()._reject_reason(_rec(), _dept(), _catalog()) is None

    def test_foreign_domain_rejected(self):
        reason = self._svc()._reject_reason(
            _rec(iiko_source_domain="sandy-co-co.iiko.it"), _dept(), _catalog())
        assert "другой базе iiko" in reason

    def test_missing_iiko_product_id_rejected(self):
        reason = self._svc()._reject_reason(_rec(iiko_product_id=None), _dept(), _catalog())
        assert "iiko_product_id" in reason

    def test_catalog_price_drifted_rejected(self):
        # цену поправили руками в iiko после approve — базис решения устарел
        reason = self._svc()._reject_reason(_rec(), _dept(), _catalog(price=1390.0))
        assert "отличается от базиса" in reason

    def test_no_catalog_price_rejected(self):
        reason = self._svc()._reject_reason(_rec(), _dept(), None)
        assert "нет действующей цены" in reason

    def test_sized_position_rejected(self):
        reason = self._svc()._reject_reason(_rec(), _dept(), _catalog(has_sizes=True))
        assert "размерам" in reason

    def test_scheduled_price_rejected(self):
        reason = self._svc()._reject_reason(_rec(), _dept(), _catalog(has_non_base=True))
        assert "расписанию" in reason

    def test_stale_approval_rejected(self):
        old = datetime.now() - timedelta(days=APPROVED_TTL_DAYS + 1)
        reason = self._svc()._reject_reason(_rec(reviewed_at=old), _dept(), _catalog())
        assert "устарел" in reason

    def test_zero_price_rejected(self):
        assert "некорректная" in self._svc()._reject_reason(
            _rec(recommended_price=0), _dept(), _catalog())

    def test_no_op_price_rejected(self):
        reason = self._svc()._reject_reason(_rec(recommended_price=1400), _dept(), _catalog())
        assert "совпадает с текущей" in reason

    def test_rule_violation_rejected(self):
        svc = self._svc(_FakeRules(violations=["min_margin: 12% < 60%"]))
        reason = svc._reject_reason(_rec(), _dept(), _catalog())
        assert "нарушены правила" in reason and "min_margin" in reason

    def test_step_over_max_rejected(self):
        # +20% при потолке шага 5%
        reason = self._svc()._reject_reason(_rec(recommended_price=1680), _dept(), _catalog())
        assert "max_step" in reason


class TestEffectiveDate:
    def test_past_rejected(self, service):
        with pytest.raises(PriceOrderError) as e:
            service._check_effective_date(date.today() - timedelta(days=1))
        assert e.value.code == "date_in_past"

    def test_too_far_rejected(self, service):
        with pytest.raises(PriceOrderError) as e:
            service._check_effective_date(date.today() + timedelta(days=365))
        assert e.value.code == "date_too_far"

    def test_tomorrow_ok(self, service):
        service._check_effective_date(date.today() + timedelta(days=1))


class TestKillSwitch:
    def test_disabled_blocks(self, service, monkeypatch):
        monkeypatch.setattr("app.services.price_order_service.settings.IIKO_PRICE_PUSH_ENABLED",
                            False, raising=False)
        with pytest.raises(PriceOrderError) as e:
            service._check_enabled(DEPT_ID)
        assert e.value.code == "push_disabled"
        assert e.value.http_status == 503

    def test_whitelist_blocks_other_departments(self, service, monkeypatch):
        monkeypatch.setattr("app.services.price_order_service.settings.IIKO_PRICE_PUSH_ENABLED",
                            True, raising=False)
        monkeypatch.setattr(
            "app.services.price_order_service.settings.IIKO_PRICE_PUSH_DEPARTMENTS",
            "11111111-1111-1111-1111-111111111111", raising=False)
        with pytest.raises(PriceOrderError) as e:
            service._check_enabled(DEPT_ID)
        assert e.value.code == "department_not_allowed"

    def test_empty_whitelist_allows_all(self, service, monkeypatch):
        monkeypatch.setattr("app.services.price_order_service.settings.IIKO_PRICE_PUSH_ENABLED",
                            True, raising=False)
        monkeypatch.setattr(
            "app.services.price_order_service.settings.IIKO_PRICE_PUSH_DEPARTMENTS",
            "", raising=False)
        service._check_enabled(DEPT_ID)


class TestDomainResolution:
    def test_host_resolves_to_base_url(self):
        assert base_url_for_host("madlen-group-so.iiko.it", DOMAINS) == \
            "https://madlen-group-so.iiko.it"

    def test_unknown_host_raises(self):
        with pytest.raises(IikoOrderError):
            base_url_for_host("unknown.iiko.it", DOMAINS)

    def test_marker_is_stable_and_unique(self):
        assert marker_for(42) == "SF#42"
        assert marker_for(42) != marker_for(43)


class TestResponseParsing:
    def _resp(self, payload, status=200) -> httpx.Response:
        return httpx.Response(status, json=payload,
                              request=httpx.Request("POST", "https://x/resto"))

    def test_success_envelope_unwrapped(self):
        doc = {"id": "abc", "documentNumber": "1424"}
        assert IikoMenuChangeWriter._unwrap(self._resp(
            {"result": "SUCCESS", "errors": [], "response": doc})) == doc

    def test_error_envelope_raises_with_errors(self):
        with pytest.raises(IikoOrderError) as e:
            IikoMenuChangeWriter._unwrap(self._resp(
                {"result": "ERROR", "errors": ["Нет прав"], "response": None}))
        assert "Нет прав" in str(e.value)
        assert e.value.errors == ["Нет прав"]

    def test_bare_document_supported(self):
        # GET byId на части сборок отдаёт документ без конверта
        doc = {"id": "abc", "status": "NEW"}
        assert IikoMenuChangeWriter._unwrap(self._resp(doc)) == doc

    def test_http_error_raises(self):
        with pytest.raises(IikoOrderError) as e:
            IikoMenuChangeWriter._unwrap(httpx.Response(
                500, text="boom", request=httpx.Request("POST", "https://x/resto")))
        assert e.value.status_code == 500

    def test_non_json_raises(self):
        with pytest.raises(IikoOrderError):
            IikoMenuChangeWriter._unwrap(httpx.Response(
                200, text="<html>gateway</html>",
                request=httpx.Request("POST", "https://x/resto")))


class TestOrphanRecovery:
    """После обрыва POST документ опознаётся по маркеру в комментарии."""

    @pytest.mark.asyncio
    async def test_finds_document_by_marker(self, monkeypatch):
        writer = IikoMenuChangeWriter("https://madlen-group-so.iiko.it")
        docs = [
            {"id": "1", "comment": "ручной приказ"},
            {"id": "2", "comment": "SF#77 Sales Forecast: 3 поз."},
        ]

        async def fake_list(*_a, **_kw):
            return docs

        monkeypatch.setattr(writer, "list_orders", fake_list)
        found = await writer.find_by_marker(marker_for(77), "2026-08-07", "2026-08-07")
        assert found["id"] == "2"

    @pytest.mark.asyncio
    async def test_returns_none_when_absent(self, monkeypatch):
        writer = IikoMenuChangeWriter("https://madlen-group-so.iiko.it")

        async def fake_list(*_a, **_kw):
            return [{"id": "1", "comment": "SF#78 другой приказ"}]

        monkeypatch.setattr(writer, "list_orders", fake_list)
        assert await writer.find_by_marker(marker_for(77), "2026-08-07", "2026-08-07") is None
