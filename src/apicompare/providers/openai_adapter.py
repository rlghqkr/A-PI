"""OpenAI 어댑터 (openai SDK 3.x, Responses API 기본).

조사 항목 ↔ 메서드
    ① list_models()          GET /v1/models — id/created/owned_by/shutdown_date 만 제공(컨텍스트·단가 없음)
    ② generate()             POST /v1/responses (기본) | POST /v1/chat/completions (api="chat_completions")
    ③ generate().usage       응답 usage 정규화(normalize_responses_usage / normalize_chat_usage) + count_tokens() (POST /v1/responses/input_tokens)
    ④ usage_report()         GET /v1/organization/usage/completions — Admin 키 필수, 없으면 NotSupported
       probe_usage_api_with_standard_key()  표준 키로 같은 엔드포인트를 1회 때려 실제 오류(상태코드·code)를 실측
    ⑤ cost() / cost_report() 로컬 단가 계산 / GET /v1/organization/costs (Admin 키 필수)
    ⑥ health() / status_page() / error_from_exception()

SDK 소스로 확인한 사실 (.venv/lib/python3.12/site-packages/openai/)
- _client.py: OpenAI(api_key=, admin_api_key=, timeout=, max_retries=). admin_api_key 는 OPENAI_ADMIN_KEY 환경변수를 자동으로 읽는다.
  Admin 엔드포인트(resources/admin/organization/usage.py)는 security={"admin_api_key_auth": True} 로만 인증하므로
  admin_api_key 가 없는 클라이언트로 호출하면 서버에 가기 전에 TypeError("Could not resolve authentication method") 가 난다.
  → 표준 키로 "실제 서버 응답" 을 보려면 admin_api_key=<표준 키> 로 별도 클라이언트를 만들어야 한다(probe_usage_api_with_standard_key).
- resources/responses/responses.py: create(model, input, instructions, max_output_tokens, store, text=ResponseTextConfigParam, ...).
  Structured Outputs 는 text={"format": {"type": "json_schema", "name", "schema", "strict"}}.
- resources/responses/input_tokens.py: client.responses.input_tokens.count(model=, input=) → .input_tokens
- resources/chat/completions/completions.py: create(model, messages, max_completion_tokens, reasoning_effort, tools, response_format, ...)
- _exceptions.py: APITimeoutError ⊂ APIConnectionError ⊂ APIError ; APIStatusError(.status_code, .response, .body, .code, .type, .request_id).
  _client._make_status_error 가 body["error"] 를 꺼내 넘기므로 e.body 는 {"message","type","code","param"} 형태.
- _legacy_response.py: with_raw_response.*  → LegacyAPIResponse(.headers, .status_code, .request_id, .parse())
- types/model.py: Model.shutdown_date: Optional[str]  (REST 뿐 아니라 SDK 타입에도 존재)
- types/responses/response_usage.py: input_tokens_details.{cached_tokens, cache_write_tokens}(int 필수), output_tokens_details.reasoning_tokens
- types/completion_usage.py: prompt_tokens_details.{cached_tokens, cache_write_tokens}, completion_tokens_details.reasoning_tokens — 전부 Optional → None 방어 필요
- types/admin/organization/usage_completions_response.py: data[].{start_time,end_time,results[]} ; results[].{input_tokens, output_tokens, num_model_requests, model, project_id, ...}
- types/admin/organization/usage_costs_response.py: results[].{amount.{value,currency}, line_item, project_id, ...}
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

import openai
import requests
from openai import OpenAI

from ..errors import ErrorCategory, make_error, redact
from ..models import (
    CallResult,
    ErrorInfo,
    HealthResult,
    ModelInfo,
    NotSupported,
    UsageBucket,
    UsageNormalized,
    UsageReport,
)
from .base import ProviderAdapter

STATUS_URL = "https://status.openai.com/api/v2/status.json"
COMPONENTS_URL = "https://status.openai.com/api/v2/components.json"
USAGE_ENDPOINT = "GET /v1/organization/usage/completions"
COSTS_ENDPOINT = "GET /v1/organization/costs"

# 텍스트 생성 모델 판별: gpt-* / o1·o3·o4… 접두 + 비텍스트 계열 제외
_TEXT_PREFIX = re.compile(r"^(gpt-|o\d)")
_NON_TEXT_MARKERS = ("tts", "embedding", "dall-e", "whisper", "image", "realtime", "transcribe", "audio", "moderation")


# ---------------------------------------------------------------------------
# 순수 함수 (네트워크 없이 테스트 가능)
# ---------------------------------------------------------------------------
def _get(obj: Any, name: str, default: Any = None) -> Any:
    """pydantic 객체 / dict / SimpleNamespace 모두에서 필드를 읽는다."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _dump(obj: Any) -> dict[str, Any]:
    """SDK 객체 → dict. 실패하면 빈 dict."""
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json", exclude_none=False)
        except Exception:  # noqa: BLE001 - 덤프 실패는 정보 손실일 뿐 치명적이지 않다
            try:
                return dump()
            except Exception:  # noqa: BLE001
                return {}
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return {}


def unix_to_iso(ts: Any) -> str | None:
    """Unix 초 → ISO 8601(UTC) 문자열. None/비정상 값은 None."""
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def is_text_model(model_id: str) -> bool:
    """GET /v1/models 결과에서 텍스트 생성 모델만 고른다 (tts/embedding/dall-e/whisper/image/realtime/transcribe 제외)."""
    mid = (model_id or "").lower()
    if not _TEXT_PREFIX.match(mid):
        return False
    return not any(marker in mid for marker in _NON_TEXT_MARKERS)


def normalize_responses_usage(u: Any) -> UsageNormalized:
    """Responses API usage → UsageNormalized.

    input_tokens(캐시 포함) / output_tokens(reasoning 포함) / total_tokens(응답 제공) /
    input_tokens_details.{cached_tokens, cache_write_tokens} / output_tokens_details.reasoning_tokens
    """
    input_tokens = _int(_get(u, "input_tokens"))
    output_tokens = _int(_get(u, "output_tokens"))
    total = _get(u, "total_tokens")
    itd = _get(u, "input_tokens_details")
    otd = _get(u, "output_tokens_details")
    return UsageNormalized(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=_int(total) if total is not None else input_tokens + output_tokens,
        cached_input_tokens=_int(_get(itd, "cached_tokens")),
        cache_write_tokens=_int(_get(itd, "cache_write_tokens")),
        reasoning_tokens=_int(_get(otd, "reasoning_tokens")),
        total_is_computed=total is None,
        raw=_dump(u),
    )


def normalize_chat_usage(u: Any) -> UsageNormalized:
    """Chat Completions usage → UsageNormalized.

    prompt_tokens / completion_tokens / total_tokens /
    prompt_tokens_details.{cached_tokens, cache_write_tokens} / completion_tokens_details.reasoning_tokens
    (details 하위 필드는 SDK 타입에서 전부 Optional → None 방어)
    """
    input_tokens = _int(_get(u, "prompt_tokens"))
    output_tokens = _int(_get(u, "completion_tokens"))
    total = _get(u, "total_tokens")
    ptd = _get(u, "prompt_tokens_details")
    ctd = _get(u, "completion_tokens_details")
    return UsageNormalized(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=_int(total) if total is not None else input_tokens + output_tokens,
        cached_input_tokens=_int(_get(ptd, "cached_tokens")),
        cache_write_tokens=_int(_get(ptd, "cache_write_tokens")),
        reasoning_tokens=_int(_get(ctd, "reasoning_tokens")),
        total_is_computed=total is None,
        raw=_dump(u),
    )


def _error_body(exc: Any) -> dict[str, Any]:
    """APIStatusError 에서 {message,type,code,param} 를 꺼낸다. e.body 가 없으면 e.response.json() 시도."""
    def _unwrap(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        inner = data.get("error")
        if isinstance(inner, dict):
            return inner
        if isinstance(inner, str):  # Admin 엔드포인트 403 은 {"error": "<문장>"} 형태(실측 2026-10-19)
            return {"message": inner}
        return data

    body = _unwrap(getattr(exc, "body", None))
    if body is not None:
        return body
    response = getattr(exc, "response", None)
    if response is not None:
        try:
            body = _unwrap(response.json())
            if body is not None:
                return body
        except Exception:  # noqa: BLE001 - 바디가 JSON 이 아닐 수 있다
            pass
    return {}


def error_from_exception(exc: BaseException) -> ErrorInfo:
    """openai SDK 예외 → ErrorInfo. (순서 중요: APITimeoutError 는 APIConnectionError 의 하위 클래스)"""
    if isinstance(exc, openai.APITimeoutError):
        return make_error(exc, category=ErrorCategory.TIMEOUT, message=str(exc))
    if isinstance(exc, openai.APIConnectionError):
        return make_error(exc, category=ErrorCategory.NETWORK, message=str(exc))
    if isinstance(exc, openai.APIStatusError):
        body = _error_body(exc)
        headers = getattr(getattr(exc, "response", None), "headers", None)
        retry_after = None
        if headers is not None:
            try:
                retry_after = headers.get("retry-after")
            except Exception:  # noqa: BLE001
                retry_after = None
        provider_type = body.get("type") or getattr(exc, "type", None)
        provider_code = body.get("code") or getattr(exc, "code", None)
        message = body.get("message") or getattr(exc, "message", None) or str(exc)
        return make_error(
            exc,
            status_code=getattr(exc, "status_code", None),
            provider_type=str(provider_type) if provider_type is not None else None,
            provider_code=str(provider_code) if provider_code is not None else None,
            message=str(message),
            retry_after=str(retry_after) if retry_after is not None else None,
            request_id=getattr(exc, "request_id", None),
        )
    return make_error(exc, category=ErrorCategory.UNKNOWN, message=redact(str(exc)))


def _json_schema_format(json_schema: dict) -> dict[str, Any]:
    """json_schema 인자를 {name, schema, strict} 로 정규화. 순수 JSON Schema 를 넘겨도 된다."""
    if isinstance(json_schema.get("schema"), dict):
        name = json_schema.get("name") or "result"
        schema = json_schema["schema"]
        strict = json_schema.get("strict", True)
    else:
        name, schema, strict = "result", json_schema, True
    return {"name": str(name), "schema": schema, "strict": bool(strict)}


# ---------------------------------------------------------------------------
# 어댑터
# ---------------------------------------------------------------------------
class OpenAIAdapter(ProviderAdapter):
    name = "openai"
    key_env = "OPENAI_API_KEY"
    admin_key_env = "OPENAI_ADMIN_KEY"
    default_model = "gpt-5.4-mini"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: OpenAI | None = None
        self._admin_client: OpenAI | None = None
        self.last_error: ErrorInfo | None = None  # list_models() 처럼 반환형이 list 인 메서드의 실패 사유

    # ---------------- 클라이언트 (lazy) ----------------
    @property
    def client(self) -> OpenAI:
        """표준 키 클라이언트. 재시도는 self.max_retries(기본 0), timeout 은 self.timeout_s 로 고정."""
        if self._client is None:
            self._client = OpenAI(api_key=self.api_key, timeout=self.timeout_s, max_retries=self.max_retries)
        return self._client

    @property
    def admin_client(self) -> OpenAI | None:
        """Admin 키가 있을 때만 별도 생성(SDK 생성자 admin_api_key 파라미터 — _client.py 에서 확인)."""
        if not self.admin_key:
            return None
        if self._admin_client is None:
            self._admin_client = OpenAI(
                api_key=self.api_key,
                admin_api_key=self.admin_key,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
        return self._admin_client

    # ---------------- ① 모델 목록 ----------------
    @staticmethod
    def is_text_model(model_id: str) -> bool:
        return is_text_model(model_id)

    def list_models(self) -> list[ModelInfo]:
        self.last_error = None
        if self.mode == "NO_KEY":
            self.last_error = self.no_key_error()
            return []
        try:
            page = self.client.models.list()
            out: list[ModelInfo] = []
            for m in page:
                out.append(
                    ModelInfo(
                        provider=self.name,
                        id=m.id,
                        display_name=None,
                        context_window=None,  # API 미제공 — 모델 문서에서 수동 확인
                        max_output_tokens=None,
                        created_at=unix_to_iso(getattr(m, "created", None)),
                        shutdown_date=getattr(m, "shutdown_date", None),
                        capabilities={"text_model": is_text_model(m.id), "owned_by": getattr(m, "owned_by", None)},
                        raw=_dump(m),
                    )
                )
            return sorted(out, key=lambda x: x.id)
        except Exception as exc:  # noqa: BLE001 - 어댑터는 예외를 밖으로 던지지 않는다
            self.last_error = error_from_exception(exc)
            return []

    # ---------------- ② 모델 호출 ----------------
    def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        system: str | None = None,
        max_output_tokens: int = 64,
        api: str | None = None,
        json_schema: dict | None = None,
        **kwargs: Any,
    ) -> CallResult:
        model = model or self.default_model
        api = api or "responses"
        base = dict(provider=self.name, model=model, api=api)

        if self.mode == "NO_KEY":
            return CallResult(**base, status="error", error=self.no_key_error())
        if api not in ("responses", "chat_completions"):
            return CallResult(
                **base,
                status="error",
                error=make_error(category=ErrorCategory.BAD_REQUEST, message=f"api 는 'responses' | 'chat_completions' 중 하나: {api}"),
            )

        t0 = self.now()
        latency = 0.0
        try:
            if api == "responses":
                params: dict[str, Any] = dict(model=model, input=prompt, max_output_tokens=max_output_tokens, store=False)
                if system is not None:
                    params["instructions"] = system
                if json_schema is not None:
                    params["text"] = {"format": {"type": "json_schema", **_json_schema_format(json_schema)}}
                params.update(kwargs)
                raw = self.client.responses.with_raw_response.create(**params)
                latency = self.elapsed_ms(t0)
                parsed = raw.parse()
                text = getattr(parsed, "output_text", None)
                finish = getattr(parsed, "status", None)
                inc = getattr(parsed, "incomplete_details", None)
                inc_reason = getattr(inc, "reason", None) if inc is not None else None
                if inc_reason:
                    finish = f"incomplete:{inc_reason}"
                usage_obj = getattr(parsed, "usage", None)
                usage = normalize_responses_usage(usage_obj) if usage_obj is not None else None
            else:
                messages: list[dict[str, str]] = []
                if system is not None:
                    messages.append({"role": "system", "content": system})
                messages.append({"role": "user", "content": prompt})
                params = dict(model=model, messages=messages, max_completion_tokens=max_output_tokens)
                if json_schema is not None:
                    params["response_format"] = {"type": "json_schema", "json_schema": _json_schema_format(json_schema)}
                params.update(kwargs)
                raw = self.client.chat.completions.with_raw_response.create(**params)
                latency = self.elapsed_ms(t0)
                parsed = raw.parse()
                choices = getattr(parsed, "choices", None) or []
                choice = choices[0] if choices else None
                text = getattr(getattr(choice, "message", None), "content", None) if choice is not None else None
                finish = getattr(choice, "finish_reason", None) if choice is not None else None
                usage_obj = getattr(parsed, "usage", None)
                usage = normalize_chat_usage(usage_obj) if usage_obj is not None else None

            headers = getattr(raw, "headers", None)
            request_id = None
            if headers is not None:
                try:
                    request_id = headers.get("x-request-id")
                except Exception:  # noqa: BLE001
                    request_id = None
            request_id = request_id or getattr(parsed, "_request_id", None)
            return CallResult(
                **base,
                status="ok",
                text=text,
                usage=usage,
                latency_ms=latency,
                request_id=request_id,
                finish_reason=finish,
                service_tier=getattr(parsed, "service_tier", None),
                response_headers=self.filter_headers(headers),
                raw=_dump(parsed),
            )
        except Exception as exc:  # noqa: BLE001 - 어떤 경우에도 예외를 밖으로 던지지 않는다
            latency = latency or self.elapsed_ms(t0)
            err = error_from_exception(exc)
            resp_headers = getattr(getattr(exc, "response", None), "headers", None)
            return CallResult(
                **base,
                status="error",
                latency_ms=latency,
                request_id=err.request_id,
                response_headers=self.filter_headers(resp_headers),
                error=err,
            )

    # ---------------- ③ 사전 토큰 카운트 ----------------
    def count_tokens(self, prompt: str, *, model: str | None = None) -> int | NotSupported:
        model = model or self.default_model
        if self.mode == "NO_KEY":
            return self.not_supported("count_tokens", self.no_key_error().message, "키 설정 후 POST /v1/responses/input_tokens")
        input_tokens_res = getattr(getattr(self.client, "responses", None), "input_tokens", None)
        count = getattr(input_tokens_res, "count", None)
        if not callable(count):
            return self.not_supported(
                "count_tokens",
                "설치된 openai SDK 에 client.responses.input_tokens.count 가 없음",
                "tiktoken(o200k_base) 로컬 추정 또는 SDK 업그레이드",
            )
        try:
            res = count(model=model, input=prompt)
            return int(_get(res, "input_tokens"))
        except Exception as exc:  # noqa: BLE001
            err = error_from_exception(exc)
            return self.not_supported(
                "count_tokens",
                f"POST /v1/responses/input_tokens 실패: {err.category} status={err.status_code} code={err.provider_code} {err.message}",
                "응답 usage.input_tokens 로 사후 확인",
            )

    # ---------------- ⑥ 상태 ----------------
    def health(self) -> HealthResult:
        checked_via = "GET /v1/models"
        if self.mode == "NO_KEY":
            return HealthResult(self.name, ok=False, status_code=None, latency_ms=0.0, checked_via=checked_via, error=self.no_key_error())
        t0 = self.now()
        try:
            raw = self.client.models.with_raw_response.list()
            latency = self.elapsed_ms(t0)
            headers = getattr(raw, "headers", None)
            rid = None
            if headers is not None:
                try:
                    rid = headers.get("x-request-id")
                except Exception:  # noqa: BLE001
                    rid = None
            return HealthResult(
                self.name,
                ok=True,
                status_code=getattr(raw, "status_code", None),
                latency_ms=latency,
                checked_via=checked_via,
                ratelimit=self.filter_headers(headers),
                request_id=rid,
            )
        except Exception as exc:  # noqa: BLE001
            latency = self.elapsed_ms(t0)
            err = error_from_exception(exc)
            resp_headers = getattr(getattr(exc, "response", None), "headers", None)
            return HealthResult(
                self.name,
                ok=False,
                status_code=err.status_code,
                latency_ms=latency,
                checked_via=checked_via,
                error=err,
                ratelimit=self.filter_headers(resp_headers),
                request_id=err.request_id,
            )

    def status_page(self) -> dict[str, Any]:
        """status.openai.com Statuspage API (인증 불필요). 실패 시 {"error": ...}."""
        try:
            s = requests.get(STATUS_URL, timeout=self.timeout_s)
            s.raise_for_status()
            status = s.json().get("status", {}) or {}
            c = requests.get(COMPONENTS_URL, timeout=self.timeout_s)
            c.raise_for_status()
            components = [
                {"name": comp.get("name"), "status": comp.get("status")}
                for comp in (c.json().get("components", []) or [])
                if isinstance(comp, dict)
            ]
            return {
                "indicator": status.get("indicator"),
                "description": status.get("description"),
                "components": components,
                "source": STATUS_URL,
            }
        except Exception as exc:  # noqa: BLE001
            return {"error": redact(str(exc))[:300], "source": STATUS_URL}

    # ---------------- ④ Usage 조회 ----------------
    def _usage_not_supported(self, item: str, endpoint: str) -> NotSupported:
        return self.not_supported(
            item,
            f"OPENAI_ADMIN_KEY 없음 — {endpoint} 는 Admin API 키(조직 Owner 발급) 필수. 표준/프로젝트 키로는 불가",
            "platform.openai.com/usage 대시보드 또는 apicompare.usagelog.aggregate()",
        )

    def usage_report(
        self,
        start: datetime,
        end: datetime,
        *,
        bucket: str = "1d",
        group_by: tuple[str, ...] = ("model",),
    ) -> UsageReport | NotSupported:
        admin = self.admin_client
        if admin is None:
            return self._usage_not_supported("usage_report", USAGE_ENDPOINT)
        try:
            page = admin.admin.organization.usage.completions(
                start_time=int(start.timestamp()),
                end_time=int(end.timestamp()),
                bucket_width=bucket,
                group_by=list(group_by),
            )
            buckets: list[UsageBucket] = []
            for b in getattr(page, "data", None) or []:
                b_start = unix_to_iso(_get(b, "start_time")) or ""
                b_end = unix_to_iso(_get(b, "end_time")) or ""
                for r in _get(b, "results", None) or []:
                    group = {k: str(_get(r, k)) for k in group_by if _get(r, k) is not None}
                    buckets.append(
                        UsageBucket(
                            start=b_start,
                            end=b_end,
                            group=group,
                            input_tokens=_int(_get(r, "input_tokens")),
                            output_tokens=_int(_get(r, "output_tokens")),
                            requests=_int(_get(r, "num_model_requests")),
                            raw=_dump(r),
                        )
                    )
            return UsageReport(
                provider=self.name,
                source="admin_api",
                buckets=buckets,
                note=f"{USAGE_ENDPOINT} bucket_width={bucket} group_by={list(group_by)} 첫 페이지만 (has_more={_get(page, 'has_more')})",
            )
        except Exception as exc:  # noqa: BLE001
            err = error_from_exception(exc)
            return self.not_supported(
                "usage_report",
                f"{USAGE_ENDPOINT} 호출 실패: {err.category} status={err.status_code} type={err.provider_type} code={err.provider_code} {err.message}",
                "Admin 키 권한 확인 또는 apicompare.usagelog.aggregate()",
            )

    def probe_usage_api_with_standard_key(self) -> ErrorInfo:
        """표준 키로 Usage API 를 1회 호출해 실제 응답(상태코드·code)을 실측한다. 토큰 과금 없음.

        SDK 가 admin 엔드포인트에 admin_api_key 만 쓰므로 표준 키를 admin_api_key 자리에 넣어 서버까지 보낸다.
        """
        if self.mode == "NO_KEY":
            return self.no_key_error()
        try:
            probe = OpenAI(api_key=self.api_key, admin_api_key=self.api_key, timeout=self.timeout_s, max_retries=self.max_retries)
            now = int(datetime.now(timezone.utc).timestamp())
            page = probe.admin.organization.usage.completions(start_time=now - 86400, end_time=now, bucket_width="1d", limit=1)
            return make_error(
                category=ErrorCategory.UNKNOWN,
                status_code=200,
                message=f"예상 외: 표준 키로 {USAGE_ENDPOINT} 호출이 성공함 (buckets={len(_get(page, 'data', None) or [])}). 이 키가 Admin 권한을 가진 것으로 추정",
            )
        except Exception as exc:  # noqa: BLE001
            return error_from_exception(exc)

    # ---------------- ⑤ 비용 ----------------
    def cost_report(self, start: datetime, end: datetime) -> UsageReport | NotSupported:
        admin = self.admin_client
        if admin is None:
            return self._usage_not_supported("cost_report", COSTS_ENDPOINT)
        try:
            page = admin.admin.organization.usage.costs(
                start_time=int(start.timestamp()),
                end_time=int(end.timestamp()),
                bucket_width="1d",
                group_by=["line_item"],
            )
            buckets: list[UsageBucket] = []
            for b in getattr(page, "data", None) or []:
                b_start = unix_to_iso(_get(b, "start_time")) or ""
                b_end = unix_to_iso(_get(b, "end_time")) or ""
                for r in _get(b, "results", None) or []:
                    amount = _get(r, "amount")
                    value = _get(amount, "value")
                    group = {"line_item": str(_get(r, "line_item") or "")}
                    if _get(r, "project_id") is not None:
                        group["project_id"] = str(_get(r, "project_id"))
                    buckets.append(
                        UsageBucket(
                            start=b_start,
                            end=b_end,
                            group=group,
                            cost_usd=float(value) if value is not None else None,
                            raw=_dump(r),
                        )
                    )
            return UsageReport(
                provider=self.name,
                source="admin_api",
                buckets=buckets,
                note=f"{COSTS_ENDPOINT} bucket_width=1d group_by=[line_item] amount.value 는 USD(달러) 첫 페이지만 (has_more={_get(page, 'has_more')})",
            )
        except Exception as exc:  # noqa: BLE001
            err = error_from_exception(exc)
            return self.not_supported(
                "cost_report",
                f"{COSTS_ENDPOINT} 호출 실패: {err.category} status={err.status_code} type={err.provider_type} code={err.provider_code} {err.message}",
                "cost() 로컬 계산 또는 platform.openai.com/usage Costs 탭",
            )


__all__ = [
    "OpenAIAdapter",
    "error_from_exception",
    "is_text_model",
    "normalize_chat_usage",
    "normalize_responses_usage",
    "unix_to_iso",
]
