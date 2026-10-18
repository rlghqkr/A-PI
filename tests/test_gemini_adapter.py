"""GeminiAdapter 네트워크 없는 테스트: usage 정규화 / 오류 매핑 / NotSupported / NO_KEY 경로 / fake 클라이언트.

    uv run pytest tests/test_gemini_adapter.py -q
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from google.genai import errors as genai_errors
from google.genai import types

from apicompare.errors import ErrorCategory
from apicompare.models import CallResult, HealthResult, NotSupported, UsageNormalized
from apicompare.providers import get_adapter
from apicompare.providers.gemini_adapter import (
    GeminiAdapter,
    error_from_exception,
    extract_provider_code,
    normalize_generate_content_usage,
    normalize_interactions_usage,
    strip_model_prefix,
)

DUMMY_KEY = "INVALID-KEY-FOR-TEST"


# ---------------------------------------------------------------------------
# 헬퍼: 실제 SDK 예외 객체를 네트워크 없이 만든다 (errors.APIError.raise_for_response 는 200 외 전부 raise)
# ---------------------------------------------------------------------------
def make_api_error(status: int, body: dict) -> genai_errors.APIError:
    resp = httpx.Response(status, json=body, request=httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/x"))
    with pytest.raises(genai_errors.APIError) as ei:
        genai_errors.APIError.raise_for_response(resp)
    return ei.value


@pytest.fixture
def no_key_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # .env 가 로드돼도 어댑터는 config.get_key 를 쓰므로 환경변수가 없으면 NO_KEY 다. load_env 가 override=False 라 다시 채우지는 않지만
    # .env 에 GEMINI_API_KEY 가 생겼을 때도 테스트가 결정적이도록 api_key="" 는 쓰지 않고 명시적으로 None 을 넘긴다.
    yield


# ---------------------------------------------------------------------------
# usage 정규화
# ---------------------------------------------------------------------------
def test_normalize_generate_content_usage_with_thoughts_and_cache():
    um = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=100,
        cached_content_token_count=40,
        tool_use_prompt_token_count=5,
        candidates_token_count=20,
        thoughts_token_count=30,
        total_token_count=155,
    )
    u = normalize_generate_content_usage(um)
    assert isinstance(u, UsageNormalized)
    assert u.input_tokens == 105  # prompt(캐시 포함) + tool_use
    assert u.cached_input_tokens == 40
    assert u.output_tokens == 50  # candidates + thoughts
    assert u.reasoning_tokens == 30
    assert u.total_tokens == 155 and u.total_is_computed is False
    assert u.raw["prompt_token_count"] == 100 and u.raw["thoughts_token_count"] == 30
    assert u.cache_write_tokens == 0


def test_normalize_generate_content_usage_total_missing_is_computed():
    um = types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=5)
    u = normalize_generate_content_usage(um)
    assert u.total_tokens == 15 and u.total_is_computed is True
    assert u.reasoning_tokens == 0 and u.cached_input_tokens == 0
    assert u.raw["total_token_count"] is None


def test_normalize_generate_content_usage_accepts_dict():
    u = normalize_generate_content_usage({"prompt_token_count": 3, "candidates_token_count": 4, "total_token_count": 7})
    assert (u.input_tokens, u.output_tokens, u.total_tokens) == (3, 4, 7)


def test_normalize_interactions_usage_thinking_doc_example():
    # thinking 문서 예시: 62 + 171 + 297 = 530 → total_output_tokens 는 thought 제외
    from google.genai._gaos.types.interactions.usage import Usage

    u = normalize_interactions_usage(Usage(total_input_tokens=62, total_output_tokens=171, total_thought_tokens=297, total_tokens=530))
    assert u.input_tokens == 62
    assert u.output_tokens == 171 + 297
    assert u.reasoning_tokens == 297
    assert u.total_tokens == 530 and u.total_is_computed is False
    assert u.raw["total_thought_tokens"] == 297


def test_normalize_interactions_usage_total_missing():
    u = normalize_interactions_usage({"total_input_tokens": 10, "total_output_tokens": 2, "total_cached_tokens": 4})
    assert u.total_tokens == 12 and u.total_is_computed is True and u.cached_input_tokens == 4


def test_strip_model_prefix():
    assert strip_model_prefix("models/gemini-3.8-flash") == "gemini-3.8-flash"
    assert strip_model_prefix("gemini-3.8-flash") == "gemini-3.8-flash"
    assert strip_model_prefix(None) == ""


# ---------------------------------------------------------------------------
# 오류 매핑
# ---------------------------------------------------------------------------
def test_error_429_rate_limit_exceeded_snake_case_code():
    exc = make_api_error(429, {"error": {"code": "rate_limit_exceeded", "message": "Quota exceeded for metric", "status": "RESOURCE_EXHAUSTED"}})
    assert isinstance(exc, genai_errors.ClientError)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.RATE_LIMIT.value
    assert e.status_code == 429
    assert e.provider_type == "RESOURCE_EXHAUSTED"
    assert e.provider_code == "rate_limit_exceeded"
    assert e.exception_class == "ClientError"


def test_error_429_quota_exceeded_rpd_is_rate_limit_with_retry_delay():
    exc = make_api_error(
        429,
        {"error": {"code": 429, "message": "You exceeded your current quota", "status": "RESOURCE_EXHAUSTED",
                   "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "17s"}]}},
    )
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.RATE_LIMIT.value
    assert e.retry_after == "17s"
    assert e.provider_code == "resource_exhausted"  # 정수 code → 텍스트에서 알려진 코드 추출


def test_error_402_payment_required_is_quota_exhausted():
    exc = make_api_error(402, {"error": {"code": "payment_required", "message": "Prepaid balance exhausted"}})
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.QUOTA_EXHAUSTED.value
    assert e.status_code == 402 and e.provider_code == "payment_required"


def test_error_503_unavailable_is_overloaded():
    exc = make_api_error(503, {"error": {"code": 503, "message": "The model is overloaded. Please try again later.", "status": "UNAVAILABLE"}})
    assert isinstance(exc, genai_errors.ServerError)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.OVERLOADED.value
    assert e.status_code == 503 and e.provider_type == "UNAVAILABLE"


def test_error_503_service_unavailable_code_is_overloaded():
    exc = make_api_error(503, {"error": {"code": "service_unavailable", "message": "Service temporarily unavailable"}})
    assert error_from_exception(exc).category == ErrorCategory.OVERLOADED.value


def test_error_401_auth_and_400_api_key_invalid_reason():
    e401 = error_from_exception(make_api_error(401, {"error": {"code": "authentication", "message": "API key not valid.", "status": "UNAUTHENTICATED"}}))
    assert e401.category == ErrorCategory.AUTH.value and e401.provider_code == "authentication"

    exc = make_api_error(
        400,
        {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT",
                   "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo", "reason": "API_KEY_INVALID", "domain": "googleapis.com"}]}},
    )
    e400 = error_from_exception(exc)
    assert e400.category == ErrorCategory.BAD_REQUEST.value
    assert e400.provider_code == "api_key_invalid"
    assert e400.provider_type == "INVALID_ARGUMENT"


def test_error_404_model_not_found():
    exc = make_api_error(404, {"error": {"code": "model_not_found", "message": "models/model-does-not-exist-123 is not found", "status": "NOT_FOUND"}})
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.NOT_FOUND.value and e.provider_code == "model_not_found"


def test_error_500_server_and_504_timeout():
    assert error_from_exception(make_api_error(500, {"error": {"code": "api_error", "message": "internal"}})).category == ErrorCategory.SERVER.value
    assert error_from_exception(make_api_error(504, {"error": {"code": "deadline_exceeded", "message": "deadline"}})).category == ErrorCategory.TIMEOUT.value


def test_error_httpx_timeout_and_connect():
    req = httpx.Request("POST", "https://generativelanguage.googleapis.com")
    assert error_from_exception(httpx.ReadTimeout("timed out", request=req)).category == ErrorCategory.TIMEOUT.value
    assert error_from_exception(httpx.ConnectTimeout("connect timed out", request=req)).category == ErrorCategory.TIMEOUT.value
    e = error_from_exception(httpx.ConnectError("connection refused", request=req))
    assert e.category == ErrorCategory.NETWORK.value and e.status_code is None


def test_error_interactions_compat_hierarchy():
    """Interactions 경로는 compat_errors.APIStatusError(status_code, body) 를 던진다 — 같은 ErrorInfo 로 매핑돼야 한다."""
    from google.genai._gaos.lib import compat_errors as ce

    resp = httpx.Response(429, json={"error": {"code": "rate_limit_exceeded", "message": "slow down"}}, request=httpx.Request("POST", "https://x"))
    exc = ce.APIError.generate(status_code=429, body=resp.json(), message="429 rate_limit_exceeded: slow down", response=resp)
    assert isinstance(exc, ce.RateLimitError)
    e = error_from_exception(exc)
    assert e.category == ErrorCategory.RATE_LIMIT.value
    assert e.status_code == 429 and e.provider_code == "rate_limit_exceeded"

    t = error_from_exception(ce.APITimeoutError(request=httpx.Request("POST", "https://x")))
    assert t.category == ErrorCategory.TIMEOUT.value
    c = error_from_exception(ce.APIConnectionError(request=httpx.Request("POST", "https://x")))
    assert c.category == ErrorCategory.NETWORK.value


def test_error_unknown_and_redaction():
    e = error_from_exception(ValueError("boom"))
    assert e.category == ErrorCategory.UNKNOWN.value and e.exception_class == "ValueError"
    leaked = make_api_error(400, {"error": {"code": "invalid_request", "message": "bad key " + "AIza" + "SyA1234567890abcdefghijklmnopqrstuv"}})
    assert "AIza" not in error_from_exception(leaked).message
    assert "***REDACTED***" in error_from_exception(leaked).message


def test_error_from_not_supported():
    e = error_from_exception(NotSupported("gemini", "interactions", "no sdk", "upgrade"))
    assert e.category == ErrorCategory.UNKNOWN.value and "NotSupported" in e.message


def test_extract_provider_code_fallbacks():
    assert extract_provider_code({"error": {"code": "QUOTA_EXCEEDED"}}) == "quota_exceeded"
    assert extract_provider_code({"error": {"code": 429, "details": [{"reason": "RATE_LIMIT_EXCEEDED"}]}}) == "rate_limit_exceeded"
    assert extract_provider_code(None, "model_not_found: nope") == "model_not_found"
    assert extract_provider_code({"error": {"code": 418}}, "I am a teapot") is None


# ---------------------------------------------------------------------------
# NO_KEY 경로 (현재 .env 에 GEMINI_API_KEY 없음 — 이 경로가 반드시 동작해야 한다)
# ---------------------------------------------------------------------------
def test_no_key_paths(no_key_env):
    a = GeminiAdapter(api_key=None)
    if a.mode != "NO_KEY":  # .env 에 키가 생긴 환경이면 명시적으로 비운다
        a.api_key = None
    assert a.mode == "NO_KEY"
    assert a.name == "gemini" and a.key_env == "GEMINI_API_KEY" and a.default_model == "gemini-3.8-flash"
    assert a.admin_key_env is None and a.admin_key is None

    assert a.list_models() == []

    r = a.generate("ping")
    assert isinstance(r, CallResult) and r.status == "error"
    assert r.error.category == ErrorCategory.AUTH.value and "GEMINI_API_KEY" in r.error.message
    assert r.api == "generate_content" and r.model == "gemini-3.8-flash"
    r2 = a.generate("ping", api="interactions")
    assert r2.status == "error" and r2.api == "interactions" and r2.error.category == ErrorCategory.AUTH.value

    h = a.health()
    assert isinstance(h, HealthResult) and h.ok is False and h.status_code is None
    assert h.error.category == ErrorCategory.AUTH.value and h.checked_via == "GET /v1beta/models/{model}"

    ct = a.count_tokens("ping")
    assert isinstance(ct, NotSupported) and ct.item == "count_tokens"

    now = datetime.now(timezone.utc)
    ur = a.usage_report(now - timedelta(days=7), now)
    assert isinstance(ur, NotSupported) and ur.item == "usage_report" and "AI Studio" in ur.reason and "usagelog" in ur.alternative
    cr = a.cost_report(now - timedelta(days=7), now)
    assert isinstance(cr, NotSupported) and cr.item == "cost_report" and "Cloud Billing" in cr.reason


def test_get_adapter_registry_name():
    a = get_adapter("gemini", api_key=DUMMY_KEY)
    assert isinstance(a, GeminiAdapter) and a.mode == "LIVE"
    assert a.label == "Google Gemini"


def test_unknown_api_value_returns_error_not_exception():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    r = a.generate("ping", api="chat_completions")
    assert r.status == "error" and r.error.category == ErrorCategory.BAD_REQUEST.value


# ---------------------------------------------------------------------------
# 클라이언트 설정: 재시도 0회 고정 + timeout 밀리초 (네트워크 없이 Client 생성만)
# ---------------------------------------------------------------------------
def test_client_retry_and_timeout_are_pinned():
    a = GeminiAdapter(api_key=DUMMY_KEY, timeout_s=12.5, max_retries=0)
    ho = a.client._api_client._http_options
    assert ho.timeout == 12500
    assert ho.retry_options is not None and ho.retry_options.attempts == 1  # attempts 는 초기 호출 포함 → 재시도 없음
    b = GeminiAdapter(api_key=DUMMY_KEY, max_retries=2)
    assert b.client._api_client._http_options.retry_options.attempts == 3
    # SDK 기본값 확인: retry_options=None 이면 stop_after_attempt(1) (문서의 '4회' 와 다름)
    from google.genai import _api_client

    args = _api_client.retry_args(None)
    assert "retry" not in args and args["stop"] is not None


# ---------------------------------------------------------------------------
# fake 클라이언트로 generate()/list_models()/count_tokens()/health() 성공·실패 경로
# ---------------------------------------------------------------------------
class _FakeModels:
    def __init__(self, *, response=None, raise_exc=None, models=None, count=12):
        self._response = response
        self._raise = raise_exc
        self._models = models or []
        self._count = count
        self.last_call: dict = {}

    def generate_content(self, *, model, contents, config=None):
        self.last_call = {"model": model, "contents": contents, "config": config}
        if self._raise:
            raise self._raise
        return self._response

    def list(self, config=None):
        if self._raise:
            raise self._raise
        return iter(self._models)

    def count_tokens(self, *, model, contents, config=None):
        if self._raise:
            raise self._raise
        return types.CountTokensResponse(total_tokens=self._count)

    def get(self, *, model, config=None):
        if self._raise:
            raise self._raise
        return types.Model(name=f"models/{model}", display_name="Gemini 3.8 Flash")


class _FakeInteractions:
    def __init__(self, result=None, raise_exc=None):
        self._result = result
        self._raise = raise_exc
        self.last_body: dict = {}

    def create(self, **body):
        self.last_body = body
        if self._raise:
            raise self._raise
        return self._result


class _FakeClient:
    def __init__(self, models, interactions=None):
        self.models = models
        if interactions is not None:
            self.interactions = interactions


def _ok_response() -> types.GenerateContentResponse:
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(parts=[types.Part(text="서울입니다.")], role="model"), finish_reason="STOP")],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=9, candidates_token_count=4, thoughts_token_count=6, total_token_count=19),
        model_version="gemini-3.8-flash-001",
        response_id="resp-abc123",
        sdk_http_response=types.HttpResponse(
            headers={"content-type": "application/json", "date": "Mon, 19 Oct 2026 05:00:00 GMT", "x-goog-api-key": "must-not-leak",
                     "Server-Timing": "gfet4t7; dur=812", "x-gemini-deprecation-warning": "temperature is ignored for this model"}
        ),
    )


def test_generate_content_success_with_fake_client():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    fake = _FakeModels(response=_ok_response())
    a._client = _FakeClient(fake)
    r = a.generate("대한민국의 수도?", system="한 문장으로", max_output_tokens=32, temperature=0.0)
    assert r.status == "ok" and r.text == "서울입니다."
    assert r.api == "generate_content" and r.finish_reason == "STOP" and r.request_id == "resp-abc123"
    assert r.usage.input_tokens == 9 and r.usage.output_tokens == 10 and r.usage.reasoning_tokens == 6 and r.usage.total_tokens == 19
    assert r.raw["model_version"] == "gemini-3.8-flash-001"
    assert r.raw["warning_headers"] == {"x-gemini-deprecation-warning": "temperature is ignored for this model"}
    # 헤더 화이트리스트: 민감 헤더 제외, 소문자 키
    assert "x-goog-api-key" not in r.response_headers
    assert r.response_headers["content-type"] == "application/json" and "server-timing" in r.response_headers and "date" in r.response_headers
    # config 전달 확인
    cfg = fake.last_call["config"]
    assert isinstance(cfg, types.GenerateContentConfig)
    assert cfg.max_output_tokens == 32 and cfg.temperature == 0.0 and cfg.system_instruction == "한 문장으로"
    assert r.latency_ms >= 0


def test_generate_content_json_schema_sets_mime_and_schema():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    fake = _FakeModels(response=_ok_response())
    a._client = _FakeClient(fake)
    schema = {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    a.generate("JSON 으로", json_schema=schema)
    cfg = fake.last_call["config"]
    assert cfg.response_mime_type == "application/json" and cfg.response_json_schema == schema


def test_generate_content_sdk_error_becomes_call_result():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    exc = make_api_error(404, {"error": {"code": "model_not_found", "message": "models/nope is not found", "status": "NOT_FOUND"}})
    a._client = _FakeClient(_FakeModels(raise_exc=exc))
    r = a.generate("ping", model="nope")
    assert r.status == "error" and r.error.category == ErrorCategory.NOT_FOUND.value and r.error.status_code == 404
    assert r.text is None and r.usage is None and r.model == "nope"


def test_generate_content_blocked_prompt_is_content_blocked():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    resp = types.GenerateContentResponse(
        candidates=[],
        prompt_feedback=types.GenerateContentResponsePromptFeedback(block_reason="SAFETY"),
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=5, total_token_count=5),
    )
    a._client = _FakeClient(_FakeModels(response=resp))
    r = a.generate("…")
    assert r.status == "error" and r.error.category == ErrorCategory.CONTENT_BLOCKED.value and r.raw["block_reason"] == "SAFETY"


def test_generate_interactions_success_and_body():
    from google.genai._gaos.types.interactions.usage import Usage

    class _It:
        id = "interaction-123"
        status = "completed"
        model = "gemini-3.8-flash"
        output_text = "Seoul."
        usage = Usage(total_input_tokens=62, total_output_tokens=171, total_thought_tokens=297, total_tokens=530)
        errors = None
        service_tier = None

    a = GeminiAdapter(api_key=DUMMY_KEY, timeout_s=7)
    fi = _FakeInteractions(result=_It())
    a._client = _FakeClient(_FakeModels(), interactions=fi)
    r = a.generate("Capital of Korea?", api="interactions", system="short", max_output_tokens=16, thinking_level="low", labels={"run": "t"})
    assert r.status == "ok" and r.api == "interactions" and r.text == "Seoul." and r.request_id == "interaction-123"
    assert r.usage.output_tokens == 468 and r.usage.reasoning_tokens == 297 and r.usage.total_tokens == 530
    assert r.finish_reason == "completed" and r.response_headers == {}
    b = fi.last_body
    assert b["model"] == "gemini-3.8-flash" and b["input"] == "Capital of Korea?" and b["store"] is False
    assert b["system_instruction"] == "short" and b["timeout"] == 7
    assert b["generation_config"] == {"max_output_tokens": 16, "thinking_level": "low"} and b["labels"] == {"run": "t"}


def test_generate_interactions_missing_in_sdk_becomes_error():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    a._client = _FakeClient(_FakeModels())  # interactions 속성 없음
    r = a.generate("ping", api="interactions")
    assert r.status == "error" and "NotSupported" in r.error.message and r.api == "interactions"


def test_generate_interactions_error_mapped():
    from google.genai._gaos.lib import compat_errors as ce

    resp = httpx.Response(402, json={"error": {"code": "payment_required", "message": "balance exhausted"}}, request=httpx.Request("POST", "https://x"))
    exc = ce.APIError.generate(status_code=402, body=resp.json(), message="402 payment_required", response=resp)
    a = GeminiAdapter(api_key=DUMMY_KEY)
    a._client = _FakeClient(_FakeModels(), interactions=_FakeInteractions(raise_exc=exc))
    r = a.generate("ping", api="interactions")
    assert r.status == "error" and r.error.category == ErrorCategory.QUOTA_EXHAUSTED.value and r.error.status_code == 402


def test_list_models_maps_fields_and_strips_prefix():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    m = types.Model(
        name="models/gemini-3.8-flash", display_name="Gemini 3.8 Flash", version="001",
        input_token_limit=1_048_576, output_token_limit=65_536, supported_actions=["generateContent", "countTokens"], thinking=True, temperature=1.0,
    )
    m2 = types.Model(name="models/embedding-001", display_name="Embedding", input_token_limit=2048, output_token_limit=1)
    a._client = _FakeClient(_FakeModels(models=[m, m2]))
    out = a.list_models()
    assert [x.id for x in out] == ["gemini-3.8-flash", "embedding-001"]
    first = out[0]
    assert first.provider == "gemini" and first.display_name == "Gemini 3.8 Flash"
    assert first.context_window == 1_048_576 and first.max_output_tokens == 65_536
    assert first.capabilities["supported_actions"] == ["generateContent", "countTokens"] and first.capabilities["thinking"] is True
    assert first.capabilities["temperature"] == 1.0
    assert "thinking" not in out[1].capabilities  # 존재하는 필드만
    assert first.raw["name"] == "models/gemini-3.8-flash" and first.shutdown_date is None and first.created_at is None


def test_list_models_error_returns_empty_and_records_last_error():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    a._client = _FakeClient(_FakeModels(raise_exc=make_api_error(403, {"error": {"code": "permission_denied", "message": "nope"}})))
    assert a.list_models() == []
    assert a.last_error is not None and a.last_error.category == ErrorCategory.PERMISSION.value


def test_count_tokens_and_health_with_fake_client():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    a._client = _FakeClient(_FakeModels(count=12))
    assert a.count_tokens("hello") == 12
    h = a.health()
    assert h.ok is True and h.status_code == 200 and h.ratelimit == {} and h.checked_via == "GET /v1beta/models/{model}"

    bad = GeminiAdapter(api_key=DUMMY_KEY)
    bad._client = _FakeClient(_FakeModels(raise_exc=make_api_error(400, {"error": {"code": 400, "message": "API key not valid", "status": "INVALID_ARGUMENT",
                                                                                     "details": [{"reason": "API_KEY_INVALID"}]}})))
    h2 = bad.health()
    assert h2.ok is False and h2.status_code == 400 and h2.error.provider_code == "api_key_invalid"
    ct = bad.count_tokens("x")
    assert isinstance(ct, NotSupported) and "countTokens 실패" in ct.reason


def test_cost_uses_local_price_table():
    a = GeminiAdapter(api_key=DUMMY_KEY)
    usage = UsageNormalized(input_tokens=1_000_000, output_tokens=1_000_000, total_tokens=2_000_000, reasoning_tokens=200_000)
    c = a.cost("gemini-3.8-flash", usage)
    assert not isinstance(c, NotSupported)
    assert c.usd == pytest.approx(0.75 + 3.75)
    assert c.effective_from == "2027-01-01" and "thoughts" in c.note
