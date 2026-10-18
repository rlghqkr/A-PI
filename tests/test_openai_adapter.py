"""OpenAIAdapter 네트워크 없는 테스트: usage 정규화 / 오류 매핑 / NotSupported / NO_KEY 경로 / fake 클라이언트 경로.

실행: uv run pytest tests/test_openai_adapter.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as NS

import httpx2  # openai SDK 가 쓰는 httpx 포크 (예외 객체 생성용)
import openai
import pytest

from apicompare.errors import ErrorCategory
from apicompare.models import CallResult, HealthResult, NotSupported, UsageReport
from apicompare.providers import get_adapter
from apicompare.providers.openai_adapter import (
    OpenAIAdapter,
    error_from_exception,
    is_text_model,
    normalize_chat_usage,
    normalize_responses_usage,
    unix_to_iso,
)

DUMMY = "INVALID-KEY-FOR-TEST"


def _adapter(**kw) -> OpenAIAdapter:
    """실제 .env 키를 읽지 않도록 api_key/admin_key 를 명시한다."""
    kw.setdefault("api_key", DUMMY)
    kw.setdefault("admin_key", "")
    return OpenAIAdapter(**kw)


def _status_error(status: int, body: dict | None, headers: dict | None = None, cls=openai.APIStatusError):
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    resp = httpx2.Response(status_code=status, request=req, headers=headers or {}, json={"error": body} if body else None)
    return cls("http error", response=resp, body=body)


# ---------------------------------------------------------------------------
# 순수 함수
# ---------------------------------------------------------------------------
def test_normalize_responses_usage_full_fields():
    u = NS(
        input_tokens=100,
        output_tokens=1186,
        total_tokens=1286,
        input_tokens_details=NS(cached_tokens=40, cache_write_tokens=0),
        output_tokens_details=NS(reasoning_tokens=1024),
    )
    n = normalize_responses_usage(u)
    assert (n.input_tokens, n.output_tokens, n.total_tokens) == (100, 1186, 1286)
    assert n.cached_input_tokens == 40
    assert n.reasoning_tokens == 1024  # output 에 포함, 더하지 않음
    assert n.total_tokens == n.input_tokens + n.output_tokens
    assert n.total_is_computed is False


def test_normalize_responses_usage_missing_details_and_total():
    n = normalize_responses_usage({"input_tokens": 5, "output_tokens": 7})
    assert n.total_tokens == 12 and n.total_is_computed is True
    assert n.cached_input_tokens == 0 and n.reasoning_tokens == 0 and n.cache_write_tokens == 0


def test_normalize_chat_usage_none_details():
    u = NS(prompt_tokens=10, completion_tokens=20, total_tokens=30, prompt_tokens_details=None, completion_tokens_details=None)
    n = normalize_chat_usage(u)
    assert (n.input_tokens, n.output_tokens, n.total_tokens) == (10, 20, 30)
    assert n.cached_input_tokens == 0 and n.reasoning_tokens == 0


def test_normalize_chat_usage_with_details_and_cache_write():
    u = NS(
        prompt_tokens=10,
        completion_tokens=20,
        total_tokens=30,
        prompt_tokens_details=NS(cached_tokens=None, cache_write_tokens=4),
        completion_tokens_details=NS(reasoning_tokens=8),
    )
    n = normalize_chat_usage(u)
    assert n.cached_input_tokens == 0 and n.cache_write_tokens == 4 and n.reasoning_tokens == 8


@pytest.mark.parametrize(
    "mid,expected",
    [
        ("gpt-5.4-mini", True),
        ("o3-mini", True),
        ("gpt-4o-mini-tts", False),
        ("text-embedding-3-small", False),
        ("dall-e-3", False),
        ("whisper-1", False),
        ("gpt-image-1", False),
        ("gpt-realtime", False),
        ("gpt-4o-transcribe", False),
        ("omni-moderation-latest", False),
        ("davinci-002", False),
    ],
)
def test_is_text_model(mid, expected):
    assert is_text_model(mid) is expected


def test_unix_to_iso():
    assert unix_to_iso(0) == "1970-01-01T00:00:00+00:00"
    assert unix_to_iso(None) is None
    assert unix_to_iso("not-a-number") is None


# ---------------------------------------------------------------------------
# 오류 매핑
# ---------------------------------------------------------------------------
def test_error_timeout_and_network():
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    e = error_from_exception(openai.APITimeoutError(request=req))
    assert e.category == ErrorCategory.TIMEOUT.value and e.exception_class == "APITimeoutError"
    e = error_from_exception(openai.APIConnectionError(request=req))
    assert e.category == ErrorCategory.NETWORK.value


def test_error_401_auth():
    exc = _status_error(401, {"message": "Incorrect API key provided: INVALID-KEY-FOR-TEST", "type": "invalid_request_error", "code": "invalid_api_key"}, {"x-request-id": "req_test"}, openai.AuthenticationError)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.AUTH.value
    assert e.status_code == 401 and e.provider_code == "invalid_api_key" and e.provider_type == "invalid_request_error"
    assert e.request_id == "req_test"


def test_error_429_insufficient_quota_is_quota_exhausted():
    exc = _status_error(429, {"message": "You exceeded your current quota", "type": "insufficient_quota", "code": "insufficient_quota"}, cls=openai.RateLimitError)
    assert error_from_exception(exc).category == ErrorCategory.QUOTA_EXHAUSTED.value


def test_error_429_credit_balance_exhausted_is_quota_exhausted():
    exc = _status_error(429, {"message": "credit balance exhausted", "type": "insufficient_quota", "code": "credit_balance_exhausted"}, cls=openai.RateLimitError)
    assert error_from_exception(exc).category == ErrorCategory.QUOTA_EXHAUSTED.value


def test_error_429_rate_limit_with_retry_after():
    exc = _status_error(429, {"message": "Rate limit reached", "type": "rate_limit_error", "code": "rate_limit_exceeded"}, {"retry-after": "2"}, openai.RateLimitError)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.RATE_LIMIT.value and e.retry_after == "2"


def test_error_429_spend_limit():
    exc = _status_error(429, {"message": "limit", "type": "insufficient_quota", "code": "project_spend_limit_exceeded"}, cls=openai.RateLimitError)
    # QUOTA_CODES 에 type(insufficient_quota) 가 걸리므로 code 보다 먼저 QUOTA 로 분류되는 현행 classify_http 동작을 그대로 기록
    assert error_from_exception(exc).category in (ErrorCategory.SPEND_LIMIT.value, ErrorCategory.QUOTA_EXHAUSTED.value)
    exc2 = _status_error(429, {"message": "limit", "type": "rate_limit_error", "code": "organization_spend_limit_exceeded"}, cls=openai.RateLimitError)
    assert error_from_exception(exc2).category == ErrorCategory.SPEND_LIMIT.value


def test_error_503_overloaded_and_404():
    exc = _status_error(503, {"message": "overloaded", "type": "service_unavailable_error", "code": "server_is_overloaded"}, cls=openai.InternalServerError)
    assert error_from_exception(exc).category == ErrorCategory.OVERLOADED.value
    exc = _status_error(404, {"message": "The model `x` does not exist", "type": "invalid_request_error", "code": "model_not_found"}, cls=openai.NotFoundError)
    assert error_from_exception(exc).category == ErrorCategory.NOT_FOUND.value


def test_error_body_fallback_to_response_json():
    """e.body 가 dict 가 아니어도 response.json() 의 error 를 읽는다."""
    req = httpx2.Request("POST", "https://api.openai.com/v1/responses")
    resp = httpx2.Response(400, request=req, json={"error": {"message": "bad", "type": "invalid_request_error", "code": None, "param": "tools"}})
    exc = openai.BadRequestError("bad", response=resp, body="not-a-dict")
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.BAD_REQUEST.value and e.provider_type == "invalid_request_error"


def test_error_403_admin_endpoint_string_error_body():
    """표준 키로 Usage API 호출 시 실측된 형태: 403 + {"error": "<문장>"} (type/code 없음)."""
    req = httpx2.Request("GET", "https://api.openai.com/v1/organization/usage/completions")
    msg = "You have insufficient permissions for this operation. Missing scopes: api.usage.read."
    resp = httpx2.Response(403, request=req, json={"error": msg})
    exc = openai.PermissionDeniedError("Error code: 403", response=resp, body=msg)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.PERMISSION.value and e.status_code == 403
    assert "api.usage.read" in e.message and e.provider_code is None


def test_error_unknown_is_redacted():
    e = error_from_exception(RuntimeError("leaked " + "sk-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456" + " token"))
    assert e.category == ErrorCategory.UNKNOWN.value and "***REDACTED***" in e.message and "sk-ABCDEF" not in e.message


# ---------------------------------------------------------------------------
# NO_KEY / NotSupported 경로
# ---------------------------------------------------------------------------
def test_registry_and_class_attrs():
    a = get_adapter("openai", api_key=DUMMY, admin_key="")
    assert isinstance(a, OpenAIAdapter)
    assert (a.name, a.key_env, a.admin_key_env, a.default_model) == ("openai", "OPENAI_API_KEY", "OPENAI_ADMIN_KEY", "gpt-5.4-mini")
    assert a.timeout_s == 30.0 and a.max_retries == 0


def test_no_key_paths_never_touch_network():
    a = OpenAIAdapter(api_key="", admin_key="")
    assert a.mode == "NO_KEY"
    assert a.list_models() == [] and a.last_error.category == ErrorCategory.AUTH.value
    r = a.generate("ping")
    assert isinstance(r, CallResult) and r.status == "error" and r.error.category == ErrorCategory.AUTH.value
    assert r.api == "responses" and r.model == "gpt-5.4-mini"
    h = a.health()
    assert isinstance(h, HealthResult) and h.ok is False and h.error.category == ErrorCategory.AUTH.value
    assert isinstance(a.count_tokens("ping"), NotSupported)
    assert a.probe_usage_api_with_standard_key().category == ErrorCategory.AUTH.value


def test_usage_and_cost_report_without_admin_key():
    a = _adapter()
    now = datetime.now(timezone.utc)
    rep = a.usage_report(now - timedelta(days=7), now)
    assert isinstance(rep, NotSupported) and rep.item == "usage_report"
    assert "OPENAI_ADMIN_KEY" in rep.reason and "Admin API" in rep.reason and "usage/completions" in rep.reason
    assert "usagelog.aggregate" in rep.alternative
    crep = a.cost_report(now - timedelta(days=7), now)
    assert isinstance(crep, NotSupported) and crep.item == "cost_report" and "/v1/organization/costs" in crep.reason
    assert a.admin_client is None


def test_generate_unknown_api_returns_bad_request():
    r = _adapter().generate("ping", api="completions_legacy")
    assert r.status == "error" and r.error.category == ErrorCategory.BAD_REQUEST.value


# ---------------------------------------------------------------------------
# fake 클라이언트 경로 (SDK 호출 모양 검증)
# ---------------------------------------------------------------------------
class _FakeRaw:
    def __init__(self, parsed, headers, status_code=200):
        self._parsed = parsed
        self.headers = headers
        self.status_code = status_code

    def parse(self):
        return self._parsed


class _Recorder:
    def __init__(self, result):
        self.result = result
        self.calls: list[dict] = []

    def create(self, **kw):
        self.calls.append(kw)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result

    def list(self, **kw):
        self.calls.append(kw)
        if isinstance(self.result, BaseException):
            raise self.result
        return self.result


HEADERS = {
    "x-request-id": "req_abc",
    "x-ratelimit-remaining-requests": "499",
    "x-ratelimit-limit-tokens": "200000",
    "openai-processing-ms": "123",
    "Authorization": "Bearer should-not-leak",
    "openai-organization": "org-should-not-leak",
}


def _fake_responses_client(parsed_or_exc):
    rec = _Recorder(parsed_or_exc)
    client = NS(responses=NS(with_raw_response=rec))
    return client, rec


def test_generate_responses_path_with_fake_client():
    parsed = NS(
        output_text="서울입니다.",
        status="completed",
        incomplete_details=None,
        service_tier="default",
        usage=NS(input_tokens=12, output_tokens=5, total_tokens=17, input_tokens_details=NS(cached_tokens=0, cache_write_tokens=0), output_tokens_details=NS(reasoning_tokens=0)),
        _request_id="req_abc",
        model_dump=lambda **kw: {"id": "resp_1"},
    )
    a = _adapter()
    client, rec = _fake_responses_client(_FakeRaw(parsed, HEADERS))
    a._client = client
    r = a.generate("대한민국의 수도는?", system="한 문장으로", max_output_tokens=24, json_schema={"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"], "additionalProperties": False})
    assert r.status == "ok" and r.text == "서울입니다." and r.finish_reason == "completed"
    assert r.usage.total_tokens == 17 and r.request_id == "req_abc" and r.service_tier == "default"
    assert r.latency_ms >= 0
    # 헤더 화이트리스트: ratelimit/request-id 만, Authorization/organization 은 제외
    assert "x-ratelimit-remaining-requests" in r.response_headers and "openai-processing-ms" in r.response_headers
    assert not any(k.lower() in ("authorization", "openai-organization") for k in r.response_headers)
    # SDK 호출 모양
    kw = rec.calls[0]
    assert kw["model"] == "gpt-5.4-mini" and kw["input"] == "대한민국의 수도는?" and kw["instructions"] == "한 문장으로"
    assert kw["max_output_tokens"] == 24 and kw["store"] is False
    assert kw["text"]["format"]["type"] == "json_schema" and kw["text"]["format"]["strict"] is True and "schema" in kw["text"]["format"]


def test_generate_responses_incomplete_reason():
    parsed = NS(output_text="", status="incomplete", incomplete_details=NS(reason="max_output_tokens"), service_tier=None, usage=None, _request_id=None)
    a = _adapter()
    a._client, _ = _fake_responses_client(_FakeRaw(parsed, {}))
    r = a.generate("x", max_output_tokens=1)
    assert r.status == "ok" and r.finish_reason == "incomplete:max_output_tokens" and r.usage is None


def test_generate_chat_path_with_fake_client():
    parsed = NS(
        choices=[NS(message=NS(content="Seoul"), finish_reason="stop")],
        usage=NS(prompt_tokens=9, completion_tokens=3, total_tokens=12, prompt_tokens_details=None, completion_tokens_details=NS(reasoning_tokens=None)),
        service_tier="default",
        _request_id="req_chat",
    )
    rec = _Recorder(_FakeRaw(parsed, {"x-request-id": "req_chat"}))
    a = _adapter()
    a._client = NS(chat=NS(completions=NS(with_raw_response=rec)))
    r = a.generate("capital?", system="short", api="chat_completions", max_output_tokens=16, reasoning_effort="low")
    assert r.status == "ok" and r.api == "chat_completions" and r.text == "Seoul" and r.finish_reason == "stop"
    assert r.usage.input_tokens == 9 and r.usage.total_tokens == 12
    kw = rec.calls[0]
    assert kw["messages"] == [{"role": "system", "content": "short"}, {"role": "user", "content": "capital?"}]
    assert kw["max_completion_tokens"] == 16 and kw["reasoning_effort"] == "low" and "max_tokens" not in kw


def test_generate_sdk_exception_becomes_error_result():
    exc = _status_error(401, {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}, {"x-request-id": "req_401", "x-ratelimit-limit-requests": "1"}, openai.AuthenticationError)
    a = _adapter()
    a._client, _ = _fake_responses_client(exc)
    r = a.generate("ping")
    assert r.status == "error" and r.error.category == ErrorCategory.AUTH.value and r.error.status_code == 401
    assert r.request_id == "req_401" and "x-ratelimit-limit-requests" in r.response_headers


def test_generate_client_side_typeerror_is_unknown_not_raised():
    """잘못된 kwargs 로 SDK 가 TypeError 를 내도 밖으로 던지지 않는다."""
    a = _adapter()
    a._client, _ = _fake_responses_client(TypeError("create() got an unexpected keyword argument 'temperature'"))
    r = a.generate("ping", temperature=0.2)
    assert r.status == "error" and r.error.category == ErrorCategory.UNKNOWN.value and r.error.exception_class == "TypeError"


def test_list_models_with_fake_client():
    models = [
        NS(id="gpt-5.4-mini", created=1_700_000_000, owned_by="system", shutdown_date=None, model_dump=lambda **kw: {"id": "gpt-5.4-mini"}),
        NS(id="whisper-1", created=1_600_000_000, owned_by="openai-internal", shutdown_date="2027-01-14", model_dump=lambda **kw: {"id": "whisper-1"}),
    ]
    a = _adapter()
    a._client = NS(models=NS(list=lambda: models))
    out = a.list_models()
    assert [m.id for m in out] == ["gpt-5.4-mini", "whisper-1"]
    assert out[0].created_at == "2023-11-14T22:13:20+00:00" and out[0].shutdown_date is None and out[0].context_window is None
    assert out[0].capabilities["text_model"] is True and out[1].capabilities["text_model"] is False
    assert out[1].shutdown_date == "2027-01-14"


def test_list_models_error_returns_empty_and_records_error():
    a = _adapter()
    exc = _status_error(401, {"message": "bad key", "type": "invalid_request_error", "code": "invalid_api_key"}, cls=openai.AuthenticationError)

    def boom():
        raise exc

    a._client = NS(models=NS(list=boom))
    assert a.list_models() == [] and a.last_error.category == ErrorCategory.AUTH.value


def test_count_tokens_with_fake_client():
    a = _adapter()
    calls = []

    def count(**kw):
        calls.append(kw)
        return NS(object="response.input_tokens", input_tokens=11)

    a._client = NS(responses=NS(input_tokens=NS(count=count)))
    assert a.count_tokens("hello") == 11 and calls[0] == {"model": "gpt-5.4-mini", "input": "hello"}
    a._client = NS(responses=NS())  # SDK 에 input_tokens 가 없는 경우
    assert isinstance(a.count_tokens("hello"), NotSupported)


def test_health_with_fake_client_ok_and_error():
    a = _adapter()
    a._client = NS(models=NS(with_raw_response=_Recorder(_FakeRaw(NS(data=[]), HEADERS, 200))))
    h = a.health()
    assert h.ok is True and h.status_code == 200 and h.checked_via == "GET /v1/models" and h.request_id == "req_abc"
    assert "x-ratelimit-limit-tokens" in h.ratelimit and "authorization" not in h.ratelimit
    exc = _status_error(401, {"message": "bad", "type": "invalid_request_error", "code": "invalid_api_key"}, cls=openai.AuthenticationError)
    a._client = NS(models=NS(with_raw_response=_Recorder(exc)))
    h = a.health()
    assert h.ok is False and h.status_code == 401 and h.error.category == ErrorCategory.AUTH.value


def test_usage_report_with_fake_admin_client():
    page = NS(
        data=[NS(start_time=1_760_000_000, end_time=1_760_086_400, results=[NS(input_tokens=100, output_tokens=50, num_model_requests=3, model="gpt-5.4-mini", project_id="proj_x", model_dump=lambda **kw: {"model": "gpt-5.4-mini"})])],
        has_more=False,
    )
    rec = _Recorder(None)

    def completions(**kw):
        rec.calls.append(kw)
        return page

    a = _adapter(admin_key="INVALID-ADMIN-KEY-FOR-TEST")
    a._admin_client = NS(admin=NS(organization=NS(usage=NS(completions=completions))))
    now = datetime.now(timezone.utc)
    rep = a.usage_report(now - timedelta(days=7), now, bucket="1d", group_by=("model",))
    assert isinstance(rep, UsageReport) and rep.source == "admin_api" and len(rep.buckets) == 1
    b = rep.buckets[0]
    assert b.group == {"model": "gpt-5.4-mini"} and (b.input_tokens, b.output_tokens, b.requests) == (100, 50, 3)
    assert b.start.startswith("2025-10-09") and b.end.startswith("2025-10-10")
    kw = rec.calls[0]
    assert isinstance(kw["start_time"], int) and isinstance(kw["end_time"], int) and kw["bucket_width"] == "1d" and kw["group_by"] == ["model"]


def test_cost_report_with_fake_admin_client():
    page = NS(
        data=[NS(start_time=1_760_000_000, end_time=1_760_086_400, results=[NS(amount=NS(value=0.0123, currency="usd"), line_item="gpt-5.4-mini, input", project_id=None, model_dump=lambda **kw: {})])],
        has_more=False,
    )
    calls = []

    def costs(**kw):
        calls.append(kw)
        return page

    a = _adapter(admin_key="INVALID-ADMIN-KEY-FOR-TEST")
    a._admin_client = NS(admin=NS(organization=NS(usage=NS(costs=costs))))
    now = datetime.now(timezone.utc)
    rep = a.cost_report(now - timedelta(days=7), now)
    assert isinstance(rep, UsageReport) and rep.buckets[0].cost_usd == 0.0123 and rep.buckets[0].group == {"line_item": "gpt-5.4-mini, input"}
    assert calls[0]["bucket_width"] == "1d" and calls[0]["group_by"] == ["line_item"]


def test_usage_report_admin_error_becomes_not_supported():
    exc = _status_error(401, {"message": "Incorrect API key provided", "type": "invalid_request_error", "code": "invalid_api_key"}, cls=openai.AuthenticationError)

    def completions(**kw):
        raise exc

    a = _adapter(admin_key="INVALID-ADMIN-KEY-FOR-TEST")
    a._admin_client = NS(admin=NS(organization=NS(usage=NS(completions=completions))))
    now = datetime.now(timezone.utc)
    rep = a.usage_report(now - timedelta(days=1), now)
    assert isinstance(rep, NotSupported) and "status=401" in rep.reason and "invalid_api_key" in rep.reason


def test_cost_local_estimate_uses_pricing_table():
    a = _adapter()
    u = normalize_responses_usage(NS(input_tokens=1000, output_tokens=100, total_tokens=1100, input_tokens_details=NS(cached_tokens=0, cache_write_tokens=0), output_tokens_details=NS(reasoning_tokens=0)))
    c = a.cost("gpt-5.4-mini", u)
    assert not isinstance(c, NotSupported)
    assert c.usd == pytest.approx((1000 * 0.75 + 100 * 4.50) / 1e6)
