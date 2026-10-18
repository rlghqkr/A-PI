"""AnthropicAdapter 네트워크 없는 테스트.

- normalize_anthropic_usage: total 계산식, 캐시/thinking 분해
- error_from_exception: 529/429(spend limit)/400(usage limits, credit balance)/타임아웃/네트워크/TypeError/ValueError 매핑
- NO_KEY 경로: 모든 메서드가 예외 없이 [] / error / NotSupported 를 돌려준다
- generate(): fake 클라이언트로 text/finish_reason/usage/헤더 화이트리스트/temperature 제거/refusal/예외→CallResult 변환
- usage_report()/cost_report(): requests.get 을 가짜로 바꿔 파싱·페이지네이션 확인

실행: uv run pytest tests/test_anthropic_adapter.py -q
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from apicompare.errors import ErrorCategory
from apicompare.models import CallResult, HealthResult, ModelInfo, NotSupported, UsageReport
from apicompare.providers import get_adapter
from apicompare.providers import anthropic_adapter as mod
from apicompare.providers.anthropic_adapter import (
    AnthropicAdapter,
    error_from_exception,
    normalize_anthropic_usage,
    parse_cost_report,
    parse_usage_report,
)

DUMMY_KEY = "INVALID-KEY-FOR-TEST"


# ---------------------------------------------------------------------------
# 헬퍼: SDK 예외 / fake 객체
# ---------------------------------------------------------------------------
def make_status_error(status: int, error_type: str, message: str, *, details: dict | None = None, headers: dict | None = None):
    """실제 anthropic 예외 객체를 httpx2.Response 로 만든다(네트워크 없음)."""
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    body = {"type": "error", "error": {"type": error_type, "message": message}, "request_id": "req_test_123"}
    if details:
        body["error"]["details"] = details
    hdrs = {"request-id": "req_test_123", **(headers or {})}
    resp = httpx2.Response(status, headers=hdrs, json=body, request=req)
    cls = {
        400: anthropic.BadRequestError,
        401: anthropic.AuthenticationError,
        404: anthropic.NotFoundError,
        429: anthropic.RateLimitError,
        500: anthropic.InternalServerError,
        529: anthropic.OverloadedError,
    }.get(status, anthropic.APIStatusError)
    return cls(message, response=resp, body=body)


def fake_usage(**over):
    base = dict(
        input_tokens=100,
        output_tokens=50,
        cache_creation_input_tokens=20,
        cache_read_input_tokens=30,
        cache_creation=SimpleNamespace(ephemeral_5m_input_tokens=20, ephemeral_1h_input_tokens=0),
        output_tokens_details=SimpleNamespace(thinking_tokens=10),
        server_tool_use=None,
        service_tier="standard",
        speed="standard",
        inference_geo=None,
    )
    base.update(over)
    return SimpleNamespace(**base)


class FakeMessage:
    def __init__(self, *, text="서울입니다.", stop_reason="end_turn", usage=None, thinking=False):
        self.id = "msg_test"
        self.model = "claude-haiku-5-5"
        self.role = "assistant"
        self.content = []
        if thinking:
            self.content.append(SimpleNamespace(type="thinking", thinking="...", signature="sig"))
        self.content.append(SimpleNamespace(type="text", text=text))
        self.stop_reason = stop_reason
        self.stop_sequence = None
        self.stop_details = None
        self.usage = usage or fake_usage()
        self._request_id = "req_from_model"


class FakeRaw:
    def __init__(self, message, headers=None, status_code=200):
        self._message = message
        self.headers = httpx2.Headers(
            headers
            or {
                "request-id": "req_header_1",
                "anthropic-ratelimit-requests-remaining": "999",
                "anthropic-ratelimit-tokens-limit": "400000",
                "x-api-key": "should-not-leak",
                "anthropic-organization-id": "org-should-not-leak",
                "content-type": "application/json",
            }
        )
        self.status_code = status_code

    def parse(self):
        return self._message


class FakeMessages:
    def __init__(self, response=None, exc=None):
        self.calls: list[dict] = []
        self._response = response
        self._exc = exc
        self.with_raw_response = SimpleNamespace(create=self._create)

    def _create(self, **params):
        self.calls.append(params)
        if self._exc is not None:
            raise self._exc
        return self._response

    def count_tokens(self, **params):
        self.calls.append(params)
        return SimpleNamespace(input_tokens=17)


def live_adapter(messages: FakeMessages) -> AnthropicAdapter:
    a = AnthropicAdapter(api_key=DUMMY_KEY, admin_key="", timeout_s=5, max_retries=0)
    a._client = SimpleNamespace(messages=messages)
    return a


# ---------------------------------------------------------------------------
# normalize_anthropic_usage
# ---------------------------------------------------------------------------
def test_normalize_usage_total_is_computed():
    u = normalize_anthropic_usage(fake_usage())
    assert u.input_tokens == 100 + 20 + 30
    assert u.cached_input_tokens == 30
    assert u.cache_write_tokens == 20
    assert u.output_tokens == 50
    assert u.reasoning_tokens == 10
    assert u.total_tokens == 150 + 50
    assert u.total_is_computed is True
    assert u.raw["service_tier"] == "standard"
    assert u.raw["speed"] == "standard"
    assert u.raw["input_tokens"] == 100  # 원본(비캐시) 값 보존
    assert "total_tokens" not in u.raw  # Anthropic 응답에는 total 이 없다


def test_normalize_usage_handles_none_fields_and_dict_input():
    u = normalize_anthropic_usage(
        {"input_tokens": 7, "output_tokens": 3, "cache_creation_input_tokens": None, "cache_read_input_tokens": None}
    )
    assert (u.input_tokens, u.output_tokens, u.total_tokens) == (7, 3, 10)
    assert u.reasoning_tokens == 0 and u.cached_input_tokens == 0 and u.cache_write_tokens == 0
    assert u.raw["output_tokens_details"] is None


# ---------------------------------------------------------------------------
# error_from_exception
# ---------------------------------------------------------------------------
def test_error_529_overloaded_not_internal_server_error():
    exc = make_status_error(529, "overloaded_error", "Overloaded")
    assert not isinstance(exc, anthropic.InternalServerError)  # InternalServerError 만 잡으면 누락됨
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.OVERLOADED.value
    assert e.status_code == 529
    assert e.provider_type == "overloaded_error"
    assert e.request_id == "req_test_123"
    assert e.exception_class == "OverloadedError"


def test_error_429_spend_limit_vs_rate_limit():
    spend = error_from_exception(
        make_status_error(429, "rate_limit_error", "Monthly spend limit reached", details={"error_code": "enforced_spend_limit_reached"})
    )
    assert spend.category == ErrorCategory.SPEND_LIMIT.value
    assert spend.provider_code == "enforced_spend_limit_reached"
    assert spend.retry_after is None

    rate = error_from_exception(make_status_error(429, "rate_limit_error", "Too many requests", headers={"retry-after": "7"}))
    assert rate.category == ErrorCategory.RATE_LIMIT.value
    assert rate.retry_after == "7"


def test_error_400_usage_limits_and_credit_balance():
    spend = error_from_exception(make_status_error(400, "invalid_request_error", "You have reached your specified API usage limits."))
    assert spend.category == ErrorCategory.SPEND_LIMIT.value
    credit = error_from_exception(
        make_status_error(400, "invalid_request_error", "Your credit balance is too low to access the Anthropic API.")
    )
    assert credit.category == ErrorCategory.QUOTA_EXHAUSTED.value
    plain = error_from_exception(make_status_error(400, "invalid_request_error", "max_tokens: must be positive"))
    assert plain.category == ErrorCategory.BAD_REQUEST.value


def test_error_auth_not_found_server():
    assert error_from_exception(make_status_error(401, "authentication_error", "invalid x-api-key")).category == "AUTH"
    assert error_from_exception(make_status_error(404, "not_found_error", "model: nope")).category == "NOT_FOUND"
    assert error_from_exception(make_status_error(500, "api_error", "boom")).category == "SERVER"


def test_error_timeout_and_network():
    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    t = error_from_exception(anthropic.APITimeoutError(req))
    assert t.category == ErrorCategory.TIMEOUT.value and t.status_code is None
    n = error_from_exception(anthropic.APIConnectionError(request=req))
    assert n.category == ErrorCategory.NETWORK.value and n.exception_class == "APIConnectionError"


def test_error_typeerror_unsupported_param_and_valueerror_streaming():
    te = error_from_exception(TypeError("Messages.create() got an unexpected keyword argument 'temperature'"))
    assert te.category == ErrorCategory.BAD_REQUEST.value
    assert "temperature" in te.message and "TypeError" in te.message
    ve = error_from_exception(ValueError("Streaming is required for operations that may take longer than 10 minutes."))
    assert ve.category == ErrorCategory.BAD_REQUEST.value
    assert "21,333" in ve.message
    unk = error_from_exception(RuntimeError("weird"))
    assert unk.category == ErrorCategory.UNKNOWN.value


def test_error_message_is_redacted():
    e = error_from_exception(make_status_error(401, "authentication_error", "bad key " + "sk-" + "ant-" + "api03-ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
    assert "ABCDEFGHIJKLMNOP" not in e.message and "REDACTED" in e.message


# ---------------------------------------------------------------------------
# NO_KEY 경로
# ---------------------------------------------------------------------------
@pytest.fixture
def nokey() -> AnthropicAdapter:
    return AnthropicAdapter(api_key="", admin_key="", timeout_s=5)


def test_registry_and_class_attrs(nokey):
    assert isinstance(get_adapter("anthropic", api_key="", admin_key=""), AnthropicAdapter)
    assert (nokey.name, nokey.key_env, nokey.admin_key_env, nokey.default_model) == (
        "anthropic",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_ADMIN_KEY",
        "claude-haiku-5-5",
    )
    assert nokey.mode == "NO_KEY"
    assert nokey.label == "Anthropic Claude"


def test_nokey_paths_never_raise(nokey):
    assert nokey.list_models() == []
    r = nokey.generate("ping")
    assert isinstance(r, CallResult) and r.status == "error" and r.error.category == "AUTH" and r.api == "messages"
    assert "ANTHROPIC_API_KEY" in r.error.message
    h = nokey.health()
    assert isinstance(h, HealthResult) and h.ok is False and h.error.category == "AUTH" and h.checked_via == "GET /v1/models"
    ct = nokey.count_tokens("ping")
    assert isinstance(ct, NotSupported)
    now = datetime.now(timezone.utc)
    ur = nokey.usage_report(now, now)
    assert isinstance(ur, NotSupported) and ur.item == "usage_report"
    assert "ANTHROPIC_ADMIN_KEY" in ur.reason and "Admin" in ur.reason and "raw HTTP" in ur.reason
    assert "usagelog.aggregate" in ur.alternative
    cr = nokey.cost_report(now, now)
    assert isinstance(cr, NotSupported) and cr.item == "cost_report"
    assert isinstance(nokey.verify_admin_key(), NotSupported)
    assert nokey._client is None  # 키 없이는 SDK 클라이언트를 만들지 않는다


def test_live_without_admin_key_still_not_supported_for_admin_api():
    a = AnthropicAdapter(api_key=DUMMY_KEY, admin_key="")
    assert a.mode == "LIVE"
    now = datetime.now(timezone.utc)
    assert isinstance(a.usage_report(now, now), NotSupported)
    assert isinstance(a.cost_report(now, now), NotSupported)


# ---------------------------------------------------------------------------
# generate() with fake client
# ---------------------------------------------------------------------------
def test_generate_ok_maps_fields_and_filters_headers():
    fm = FakeMessages(response=FakeRaw(FakeMessage(thinking=True)))
    a = live_adapter(fm)
    r = a.generate("대한민국의 수도?", system="짧게", max_output_tokens=32)
    assert r.status == "ok" and r.error is None
    assert r.text == "서울입니다."  # thinking 블록은 text 에 섞이지 않는다
    assert r.finish_reason == "end_turn"
    assert r.model == "claude-haiku-5-5" and r.api == "messages"
    assert r.usage.total_tokens == 200 and r.usage.total_is_computed
    assert r.service_tier == "standard"
    assert r.request_id == "req_header_1"
    assert r.latency_ms >= 0
    assert "anthropic-ratelimit-requests-remaining" in r.response_headers
    assert "x-api-key" not in r.response_headers and "anthropic-organization-id" not in r.response_headers
    assert r.raw["content_block_types"] == ["thinking", "text"]
    call = fm.calls[0]
    assert call["max_tokens"] == 32 and call["system"] == "짧게"
    assert call["messages"] == [{"role": "user", "content": "대한민국의 수도?"}]


def test_generate_drops_sampling_params_and_passes_json_schema():
    fm = FakeMessages(response=FakeRaw(FakeMessage(text='{"city": "Seoul"}')))
    a = live_adapter(fm)
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    r = a.generate("JSON", json_schema=schema, temperature=0.5, top_p=0.9, top_k=5, output_config={"effort": "low"})
    assert r.status == "ok"
    call = fm.calls[0]
    for p in ("temperature", "top_p", "top_k"):
        assert p not in call
    assert call["output_config"] == {"effort": "low", "format": {"type": "json_schema", "schema": schema}}
    assert set(r.raw["dropped_params"]["params"]) == {"temperature", "top_p", "top_k"}


def test_generate_refusal_is_ok_with_finish_reason():
    fm = FakeMessages(response=FakeRaw(FakeMessage(text="", stop_reason="refusal")))
    r = live_adapter(fm).generate("x")
    assert r.status == "ok" and r.finish_reason == "refusal" and r.text == ""


def test_generate_converts_exceptions_to_error_result():
    r = live_adapter(FakeMessages(exc=make_status_error(529, "overloaded_error", "Overloaded", headers={"retry-after": "2"}))).generate("x")
    assert r.status == "error" and r.error.category == "OVERLOADED" and r.error.status_code == 529
    assert r.error.retry_after == "2" and r.request_id == "req_test_123"
    assert "retry-after" in r.response_headers

    r2 = live_adapter(FakeMessages(exc=TypeError("Messages.create() got an unexpected keyword argument 'temperature'"))).generate("x")
    assert r2.status == "error" and r2.error.category == "BAD_REQUEST"

    r3 = live_adapter(FakeMessages(exc=RuntimeError("boom"))).generate("x")
    assert r3.status == "error" and r3.error.category == "UNKNOWN"


def test_count_tokens_uses_sdk():
    fm = FakeMessages()
    a = live_adapter(fm)
    assert a.count_tokens("안녕") == 17
    assert fm.calls[0]["model"] == "claude-haiku-5-5"


def test_health_ok_and_error():
    raw = FakeRaw(None, headers={"request-id": "req_h", "anthropic-ratelimit-requests-limit": "1000", "x-api-key": "nope"})
    a = AnthropicAdapter(api_key=DUMMY_KEY, admin_key="")
    a._client = SimpleNamespace(models=SimpleNamespace(with_raw_response=SimpleNamespace(list=lambda **kw: raw)))
    h = a.health()
    assert h.ok and h.status_code == 200 and h.request_id == "req_h"
    assert h.ratelimit == {"request-id": "req_h", "anthropic-ratelimit-requests-limit": "1000"}

    def boom(**kw):
        raise make_status_error(401, "authentication_error", "invalid x-api-key")

    a._client = SimpleNamespace(models=SimpleNamespace(with_raw_response=SimpleNamespace(list=boom)))
    h2 = a.health()
    assert h2.ok is False and h2.status_code == 401 and h2.error.category == "AUTH"


def test_list_models_maps_model_info():
    m = SimpleNamespace(
        id="claude-haiku-5-5",
        display_name="Claude Haiku 5.5",
        max_input_tokens=1_000_000,
        max_tokens=128_000,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        retires_at=None,
        lifecycle="active",
        to_dict=lambda mode="json": {"id": "claude-haiku-5-5", "capabilities": {"structured_outputs": {"supported": True}}},
    )
    a = AnthropicAdapter(api_key=DUMMY_KEY, admin_key="")
    a._client = SimpleNamespace(models=SimpleNamespace(list=lambda **kw: iter([m])))
    out = a.list_models()
    assert len(out) == 1 and isinstance(out[0], ModelInfo)
    mi = out[0]
    assert (mi.context_window, mi.max_output_tokens, mi.lifecycle, mi.shutdown_date) == (1_000_000, 128_000, "active", None)
    assert mi.created_at.startswith("2026-01-01")
    assert mi.capabilities["structured_outputs"]["supported"] is True


# ---------------------------------------------------------------------------
# Admin API 파싱 + raw HTTP (requests.get 을 가짜로)
# ---------------------------------------------------------------------------
USAGE_PAGE_1 = {
    "data": [
        {
            "starting_at": "2026-10-12T00:00:00Z",
            "ending_at": "2026-10-13T00:00:00Z",
            "results": [
                {
                    "uncached_input_tokens": 10,
                    "cache_creation": {"ephemeral_5m_input_tokens": 2, "ephemeral_1h_input_tokens": 3},
                    "cache_read_input_tokens": 5,
                    "output_tokens": 7,
                    "model": "claude-haiku-5-5",
                }
            ],
        }
    ],
    "has_more": True,
    "next_page": "page_2",
}
USAGE_PAGE_2 = {
    "data": [{"starting_at": "2026-10-13T00:00:00Z", "ending_at": "2026-10-14T00:00:00Z", "results": [{"uncached_input_tokens": 1, "output_tokens": 1, "model": "claude-haiku-5-5"}]}],
    "has_more": False,
    "next_page": None,
}
COST_PAGE = {
    "data": [
        {
            "starting_at": "2026-10-12T00:00:00Z",
            "ending_at": "2026-10-13T00:00:00Z",
            "results": [
                {"amount": "123.45", "currency": "USD", "cost_type": "tokens", "token_type": "output_tokens", "model": "claude-haiku-5-5", "description": "Claude Haiku 5.5 Output Tokens"},
                {"amount": "0.5", "currency": "USD", "cost_type": "tokens", "token_type": "uncached_input_tokens", "model": "claude-haiku-5-5", "description": "Claude Haiku 5.5 Input Tokens"},
            ],
        }
    ],
    "has_more": False,
}


def test_parse_usage_report_sums_all_input_kinds():
    b = parse_usage_report(USAGE_PAGE_1, ("model",))
    assert len(b) == 1
    assert b[0].input_tokens == 10 + 2 + 3 + 5 and b[0].output_tokens == 7
    assert b[0].group == {"model": "claude-haiku-5-5"} and b[0].requests is None


def test_parse_cost_report_cents_decimal_to_usd():
    b = parse_cost_report(COST_PAGE)
    assert [x.cost_usd for x in b] == [1.2345, 0.005]
    assert b[0].group["token_type"] == "output_tokens"


class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


def test_usage_report_raw_http_pagination(monkeypatch):
    seen: list[tuple[str, list]] = []

    def fake_get(url, params=None, headers=None, timeout=None):
        seen.append((url, list(params)))
        assert headers["x-api-key"] == "INVALID-ADMIN-KEY-FOR-TEST"
        assert headers["anthropic-version"] == "2023-06-01"
        assert timeout == 5
        return FakeResp(200, USAGE_PAGE_2 if ("page", "page_2") in params else USAGE_PAGE_1)

    monkeypatch.setattr(mod.requests, "get", fake_get)
    a = AnthropicAdapter(api_key="", admin_key="INVALID-ADMIN-KEY-FOR-TEST", timeout_s=5)
    rep = a.usage_report(datetime(2026, 10, 12, tzinfo=timezone.utc), datetime(2026, 10, 19, tzinfo=timezone.utc), group_by=("model",))
    assert isinstance(rep, UsageReport) and rep.source == "admin_api"
    assert len(rep.buckets) == 2 and sum(b.input_tokens for b in rep.buckets) == 21
    assert len(seen) == 2 and seen[0][0] == mod.USAGE_REPORT_URL
    p = dict(seen[0][1])
    assert p["starting_at"] == "2026-10-12T00:00:00Z" and p["ending_at"] == "2026-10-19T00:00:00Z"
    assert p["bucket_width"] == "1d" and ("group_by[]", "model") in seen[0][1]


def test_cost_report_raw_http_and_http_error(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda url, params=None, headers=None, timeout=None: FakeResp(200, COST_PAGE))
    a = AnthropicAdapter(api_key="", admin_key="INVALID-ADMIN-KEY-FOR-TEST", timeout_s=5)
    rep = a.cost_report(datetime(2026, 10, 12, tzinfo=timezone.utc), datetime(2026, 10, 19, tzinfo=timezone.utc))
    assert isinstance(rep, UsageReport) and round(sum(b.cost_usd for b in rep.buckets), 6) == 1.2395
    assert "total_usd=1.2395" in rep.note

    err_body = {"type": "error", "error": {"type": "permission_error", "message": "Admin API key required"}}
    monkeypatch.setattr(mod.requests, "get", lambda url, params=None, headers=None, timeout=None: FakeResp(403, err_body))
    ns = a.cost_report(datetime(2026, 10, 12, tzinfo=timezone.utc), datetime(2026, 10, 19, tzinfo=timezone.utc))
    assert isinstance(ns, NotSupported) and "403" in ns.reason and "permission_error" in ns.reason
    v = a.verify_admin_key()
    assert v["ok"] is False and v["status_code"] == 403


def test_verify_admin_key_hides_org_id(monkeypatch):
    monkeypatch.setattr(mod.requests, "get", lambda url, params=None, headers=None, timeout=None: FakeResp(200, {"id": "org-secret", "name": "Team"}))
    a = AnthropicAdapter(api_key="", admin_key="INVALID-ADMIN-KEY-FOR-TEST")
    v = a.verify_admin_key()
    assert v == {"ok": True, "status_code": 200, "organization_name": "Team", "has_id": True}
    assert "org-secret" not in str(v)
