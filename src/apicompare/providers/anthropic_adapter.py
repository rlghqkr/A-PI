"""Anthropic Claude 어댑터 (anthropic SDK 1.x, Messages API).

조사 항목과의 대응
    ① list_models()   GET /v1/models (자동 페이지네이션, 무료 — 키만 있으면 크레딧 없이도 LIVE)
    ② generate()      POST /v1/messages (with_raw_response 로 헤더까지 확보)
    ③ usage           normalize_anthropic_usage() + count_tokens() (POST /v1/messages/count_tokens, 무료)
    ④ usage_report()  GET /v1/organizations/usage_report/messages  — Admin 키 + 조직 계정 필수, SDK 미지원 → requests 로 raw HTTP
    ⑤ cost_report()   GET /v1/organizations/cost_report            — 동일. amount 는 '센트 단위 decimal 문자열'
    ⑥ health()        GET /v1/models?limit=1 (토큰 과금 0) + error_from_exception()

Anthropic 고유 주의점 (검증된 조사 매트릭스 기준)
- usage 에 total_tokens 가 없다 → total = (input + cache_creation + cache_read) + output 을 로컬에서 계산(total_is_computed=True).
- usage.input_tokens 는 '마지막 캐시 브레이크포인트 이후' 비캐시 토큰만 뜻한다. 과금 관점 총입력은 cache_creation/cache_read 를 더해야 한다.
- thinking 토큰은 output_tokens 에 이미 포함(output 단가) — output_tokens_details.thinking_tokens 는 분해값이므로 더하지 않는다.
- 현행 모델(Opus 5.5 / Sonnet 5.5 / Haiku 5.5 / Fable 5.1)은 temperature/top_p/top_k 를 받지 않는다(서버 400).
  SDK 1.x 는 messages.create() 시그니처에서 이 파라미터 자체를 제거했으므로 그냥 넘기면 네트워크 이전에 TypeError 가 난다.
  (서버 400 을 재현하려면 extra_body={"temperature": 0.5} 로 보내야 한다.) 이 어댑터는 세 파라미터를 절대 전달하지 않고 raw["dropped_params"] 에 기록한다.
- 과부하는 503 이 아니라 529 overloaded_error. SDK 의 OverloadedError 는 InternalServerError 의 하위 클래스가 아니므로
  InternalServerError 만 잡으면 529 가 빠진다 → APIStatusError 로 받아 status_code 로 분기한다.
- 429 는 (a) 순간 rate limit(retry-after 있음) 과 (b) 티어 월 지출 한도(error.details.error_code=enforced_spend_limit_reached, retry-after 없음)를 공유.
  사용자 설정 지출 한도는 400 invalid_request_error('...usage limits'), 크레딧 소진은 400 'credit balance is too low'.
- 비스트리밍 요청은 max_tokens > 21,333 이면 SDK 가 요청 전에 ValueError("Streaming is required ...") 를 던진다.
- client.beta.organization.analytics.usage_report / cost_report 는 /v1/organizations/analytics/* (Claude Enterprise 전용, Analytics 키 필요)이며
  Console 조직의 usage_report/messages · cost_report 와 다른 API 다. 후자는 SDK 메서드가 없어 raw HTTP 만 가능하다.

SDK 소스 확인 위치 (.venv/lib/python3.12/site-packages/anthropic/)
    resources/messages/messages.py  create()/count_tokens() 시그니처(temperature 없음, output_config, extra_body), with_raw_response
    resources/models.py             list(limit, after_id, before_id, lifecycle, workspace_id), with_raw_response
    _exceptions.py                  APIStatusError(.status_code/.type/.request_id/.body/.response), OverloadedError(529), APITimeoutError ⊂ APIConnectionError
    _base_client.py                 _calculate_nonstreaming_timeout(): 3600*max_tokens/128000 > 600s → ValueError (= max_tokens > 21,333)
    types/usage.py, types/output_tokens_details.py, types/cache_creation.py, types/model_info.py, types/output_config_param.py, types/json_output_format_param.py
    _response.py                    APIResponse.headers / .status_code / .request_id / .parse()
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import anthropic
import requests

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

ANTHROPIC_VERSION = "2023-06-01"
API_BASE = "https://api.anthropic.com"
USAGE_REPORT_URL = f"{API_BASE}/v1/organizations/usage_report/messages"
COST_REPORT_URL = f"{API_BASE}/v1/organizations/cost_report"
ORG_ME_URL = f"{API_BASE}/v1/organizations/me"

# SDK 1.x 가 시그니처에서 제거한 샘플링 파라미터. 넘기면 클라이언트 TypeError, extra_body 로 보내면 현행 모델 서버 400.
UNSUPPORTED_SAMPLING_PARAMS: tuple[str, ...] = ("temperature", "top_p", "top_k")
# 비스트리밍 요청 상한: _calculate_nonstreaming_timeout() 의 3600 * max_tokens / 128_000 > 600 조건.
NONSTREAMING_MAX_TOKENS = 21_333

ADMIN_REASON = "ANTHROPIC_ADMIN_KEY 없음 — Usage & Cost Admin API 는 조직(Organization) 계정 + Admin 키 필수, SDK 미지원(raw HTTP)"
ADMIN_ALTERNATIVE = "platform.claude.com/usage 대시보드 또는 usagelog.aggregate()"


# ---------------------------------------------------------------------------
# 순수 함수 (네트워크 없이 테스트 가능)
# ---------------------------------------------------------------------------
def _get(obj: Any, name: str, default: Any = None) -> Any:
    """SDK pydantic 객체와 dict 양쪽에서 필드를 읽는다."""
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


def normalize_anthropic_usage(usage: Any) -> UsageNormalized:
    """Messages 응답의 usage → 과금 관점 UsageNormalized.

    input_tokens  = input_tokens(비캐시) + cache_creation_input_tokens + cache_read_input_tokens
    output_tokens = output_tokens (thinking 포함, 과금 총합)
    total_tokens  = input + output  (응답에 total 필드가 없어 계산 → total_is_computed=True)
    reasoning     = output_tokens_details.thinking_tokens (output 에 이미 포함, 더하지 않음)
    """
    base = _int(_get(usage, "input_tokens"))
    cw = _int(_get(usage, "cache_creation_input_tokens"))
    cr = _int(_get(usage, "cache_read_input_tokens"))
    out = _int(_get(usage, "output_tokens"))
    details = _get(usage, "output_tokens_details")
    thinking = _int(_get(details, "thinking_tokens"))
    cache_creation = _get(usage, "cache_creation")
    server_tool_use = _get(usage, "server_tool_use")

    raw: dict[str, Any] = {
        "input_tokens": base,
        "cache_creation_input_tokens": _get(usage, "cache_creation_input_tokens"),
        "cache_read_input_tokens": _get(usage, "cache_read_input_tokens"),
        "cache_creation": {
            "ephemeral_5m_input_tokens": _get(cache_creation, "ephemeral_5m_input_tokens"),
            "ephemeral_1h_input_tokens": _get(cache_creation, "ephemeral_1h_input_tokens"),
        }
        if cache_creation is not None
        else None,
        "output_tokens": out,
        "output_tokens_details": {"thinking_tokens": _get(details, "thinking_tokens")} if details is not None else None,
        "server_tool_use": {
            "web_search_requests": _get(server_tool_use, "web_search_requests"),
            "web_fetch_requests": _get(server_tool_use, "web_fetch_requests"),
        }
        if server_tool_use is not None
        else None,
        "service_tier": _get(usage, "service_tier"),
        "speed": _get(usage, "speed"),
        "inference_geo": _get(usage, "inference_geo"),
        "total_formula": "(input_tokens + cache_creation_input_tokens + cache_read_input_tokens) + output_tokens",
    }
    total_input = base + cw + cr
    return UsageNormalized(
        input_tokens=total_input,
        output_tokens=out,
        total_tokens=total_input + out,
        cached_input_tokens=cr,
        cache_write_tokens=cw,
        reasoning_tokens=thinking,
        total_is_computed=True,
        raw=raw,
    )


def _error_body(exc: anthropic.APIStatusError) -> dict[str, Any]:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        err = body.get("error")
        return err if isinstance(err, dict) else {}
    return {}


def error_from_exception(exc: BaseException) -> ErrorInfo:
    """SDK 예외 → ErrorInfo. 어떤 예외가 와도 예외를 다시 던지지 않는다.

    분기 순서가 중요하다: APITimeoutError ⊂ APIConnectionError 이고, APIConnectionError 는 APIStatusError 의 형제 클래스다.
    HTTP 오류는 하위 클래스(InternalServerError 등)가 아니라 APIStatusError 로 받아 status_code 로 분류한다(529 누락 방지).
    """
    if isinstance(exc, anthropic.APITimeoutError):
        return make_error(exc, category=ErrorCategory.TIMEOUT, message=f"요청 타임아웃: {exc.message}")
    if isinstance(exc, anthropic.APIConnectionError):
        cause = getattr(exc, "__cause__", None)
        detail = f" ({type(cause).__name__}: {cause})" if cause else ""
        return make_error(exc, category=ErrorCategory.NETWORK, message=f"네트워크 오류: {exc.message}{detail}")
    if isinstance(exc, anthropic.APIStatusError):
        err = _error_body(exc)
        details = err.get("details") if isinstance(err.get("details"), dict) else {}
        headers = getattr(getattr(exc, "response", None), "headers", None)
        retry_after = headers.get("retry-after") if headers is not None else None
        request_id = getattr(exc, "request_id", None) or (headers.get("request-id") if headers is not None else None)
        return make_error(
            exc,
            status_code=exc.status_code,
            provider_type=getattr(exc, "type", None) or err.get("type"),
            provider_code=details.get("error_code"),
            message=err.get("message") or exc.message,
            retry_after=str(retry_after) if retry_after is not None else None,
            request_id=request_id,
        )
    if isinstance(exc, TypeError):
        text = str(exc)
        hit = [p for p in UNSUPPORTED_SAMPLING_PARAMS if p in text]
        if hit:
            msg = (
                f"SDK 1.x 가 제거한 파라미터 {hit} 를 messages.create() 에 넘김 → 네트워크 이전 클라이언트 TypeError. "
                f"현행 모델은 서버에서도 400 으로 거부하므로 파라미터를 삭제할 것. 원문: {text}"
            )
        else:
            msg = f"SDK 호출 인자 오류(TypeError): {text}"
        return make_error(exc, category=ErrorCategory.BAD_REQUEST, message=msg)
    if isinstance(exc, ValueError):
        text = str(exc)
        if "Streaming is required" in text or "10 minutes" in text:
            msg = (
                f"비스트리밍 요청의 max_tokens 가 SDK 상한({NONSTREAMING_MAX_TOKENS:,})을 넘어 SDK 가 요청 전에 거부(ValueError). "
                f"stream=True 또는 messages.stream() 을 쓸 것. 원문: {text}"
            )
        else:
            msg = f"SDK 인자 검증 실패(ValueError): {text}"
        return make_error(exc, category=ErrorCategory.BAD_REQUEST, message=msg)
    return make_error(exc, category=ErrorCategory.UNKNOWN, message=f"{type(exc).__name__}: {exc}")


def _rfc3339(dt: datetime) -> str:
    """Admin API 의 starting_at/ending_at 형식(UTC 'Z'). naive datetime 은 UTC 로 간주."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_usage_report(payload: dict[str, Any], group_by: tuple[str, ...] = ("model",)) -> list[UsageBucket]:
    """GET /v1/organizations/usage_report/messages 응답(한 페이지) → UsageBucket 목록.

    입력 토큰 = uncached_input_tokens + cache_creation.ephemeral_5m_input_tokens + cache_creation.ephemeral_1h_input_tokens + cache_read_input_tokens
    (Messages 응답과 달리 필드명이 uncached_input_tokens 임에 주의.)
    """
    buckets: list[UsageBucket] = []
    for b in payload.get("data", []) or []:
        for r in b.get("results", []) or []:
            cc = r.get("cache_creation") or {}
            input_tokens = (
                _int(r.get("uncached_input_tokens"))
                + _int(cc.get("ephemeral_5m_input_tokens"))
                + _int(cc.get("ephemeral_1h_input_tokens"))
                + _int(r.get("cache_read_input_tokens"))
            )
            group = {g: str(r.get(g)) for g in group_by if r.get(g) is not None}
            buckets.append(
                UsageBucket(
                    start=str(b.get("starting_at", "")),
                    end=str(b.get("ending_at", "")),
                    group=group,
                    input_tokens=input_tokens,
                    output_tokens=_int(r.get("output_tokens")),
                    requests=None,  # 이 엔드포인트는 요청 수를 돌려주지 않는다
                    cost_usd=None,
                    raw=r,
                )
            )
    return buckets


def parse_cost_report(payload: dict[str, Any]) -> list[UsageBucket]:
    """GET /v1/organizations/cost_report 응답(한 페이지) → UsageBucket(cost_usd 채움).

    amount 는 '최소 통화 단위(센트)' 의 decimal 문자열 — "123.45" = $1.2345 → Decimal 파싱 후 /100.
    model/token_type/cost_type 등은 group_by[]=description 을 지정했을 때만 채워진다.
    """
    buckets: list[UsageBucket] = []
    for b in payload.get("data", []) or []:
        for r in b.get("results", []) or []:
            amount = r.get("amount")
            try:
                cost_usd = float(Decimal(str(amount)) / Decimal(100)) if amount is not None else None
            except (InvalidOperation, ValueError):
                cost_usd = None
            group = {
                k: str(r[k])
                for k in ("description", "model", "token_type", "cost_type", "service_tier", "workspace_id", "context_window")
                if r.get(k) is not None
            }
            buckets.append(
                UsageBucket(
                    start=str(b.get("starting_at", "")),
                    end=str(b.get("ending_at", "")),
                    group=group,
                    input_tokens=0,  # cost_report 에는 토큰 수가 없다(usage_report 와 합쳐서 볼 것)
                    output_tokens=0,
                    requests=None,
                    cost_usd=cost_usd,
                    raw={**r, "currency": r.get("currency", "USD"), "amount_unit": "cents (decimal string)"},
                )
            )
    return buckets


# ---------------------------------------------------------------------------
# 어댑터
# ---------------------------------------------------------------------------
class AnthropicAdapter(ProviderAdapter):
    name = "anthropic"
    key_env = "ANTHROPIC_API_KEY"
    admin_key_env = "ANTHROPIC_ADMIN_KEY"
    default_model = "claude-haiku-5-5"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: anthropic.Anthropic | None = None

    # ---------------- 클라이언트 ----------------
    @property
    def client(self) -> anthropic.Anthropic:
        """lazy 생성. 재시도는 self.max_retries(기본 0), timeout 은 self.timeout_s 로 고정한다(SDK 기본 2회/600초와 다름)."""
        if self._client is None:
            self._client = anthropic.Anthropic(
                api_key=self.api_key,
                timeout=self.timeout_s,
                max_retries=self.max_retries,
            )
        return self._client

    def _admin_headers(self) -> dict[str, str]:
        return {"x-api-key": self.admin_key or "", "anthropic-version": ANTHROPIC_VERSION}

    # ---------------- ① 모델 목록 ----------------
    def list_models(self) -> list[ModelInfo]:
        if self.mode == "NO_KEY":
            return []
        out: list[ModelInfo] = []
        try:
            for m in self.client.models.list(limit=100):  # SyncPage 를 순회하면 after_id 커서로 자동 페이지네이션
                try:
                    raw = m.to_dict(mode="json")
                except Exception:  # pragma: no cover - 방어적
                    raw = {"id": m.id}
                caps = raw.get("capabilities")
                out.append(
                    ModelInfo(
                        provider=self.name,
                        id=m.id,
                        display_name=m.display_name,
                        context_window=m.max_input_tokens,
                        max_output_tokens=m.max_tokens,
                        created_at=_iso(m.created_at),
                        shutdown_date=_iso(m.retires_at),
                        lifecycle=m.lifecycle,
                        capabilities=caps if isinstance(caps, dict) else {},
                        raw=raw,
                    )
                )
        except Exception:
            # 목록 조회 실패(401 등)는 빈 목록으로 돌려준다. 원인은 health() 로 확인.
            return out
        return out

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
        result = CallResult(provider=self.name, model=model, api="messages", status="error")
        if self.mode == "NO_KEY":
            result.error = self.no_key_error()
            return result

        # temperature/top_p/top_k 는 절대 넘기지 않는다(현행 모델 400, SDK 1.x 는 TypeError).
        dropped = {k: kwargs.pop(k) for k in UNSUPPORTED_SAMPLING_PARAMS if k in kwargs}
        params: dict[str, Any] = {
            "model": model,
            "max_tokens": max_output_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            params["system"] = system
        if json_schema:
            # structured outputs: output_config.format = {"type": "json_schema", "schema": {...}}
            output_config = dict(kwargs.pop("output_config", None) or {})
            output_config["format"] = {"type": "json_schema", "schema": json_schema}
            params["output_config"] = output_config
        params.update(kwargs)
        if dropped:
            result.raw["dropped_params"] = {
                "params": dropped,
                "reason": "현행 Claude 모델은 temperature/top_p/top_k 를 받지 않음(400). SDK 1.x 는 파라미터 자체가 없어 TypeError → 어댑터가 제거",
            }

        t0 = self.now()
        try:
            raw = self.client.messages.with_raw_response.create(**params)
            result.latency_ms = self.elapsed_ms(t0)
            msg = raw.parse()
            headers = raw.headers
            content = list(getattr(msg, "content", []) or [])
            result.status = "ok"
            result.text = "".join(getattr(b, "text", "") for b in content if getattr(b, "type", None) == "text")
            result.finish_reason = getattr(msg, "stop_reason", None)  # refusal 도 그대로 기록(status 는 ok)
            result.usage = normalize_anthropic_usage(getattr(msg, "usage", None))
            result.service_tier = _get(getattr(msg, "usage", None), "service_tier")
            result.request_id = headers.get("request-id") or getattr(msg, "_request_id", None)
            result.response_headers = self.filter_headers(headers)
            stop_details = getattr(msg, "stop_details", None)
            result.raw.update(
                {
                    "id": getattr(msg, "id", None),
                    "model": getattr(msg, "model", None),
                    "stop_reason": result.finish_reason,
                    "stop_sequence": getattr(msg, "stop_sequence", None),
                    "stop_details": _to_plain(stop_details),
                    "content_block_types": [getattr(b, "type", None) for b in content],
                    "http_status": getattr(raw, "status_code", None),
                }
            )
        except Exception as exc:  # 어떤 경우에도 예외를 밖으로 던지지 않는다
            if not result.latency_ms:
                result.latency_ms = self.elapsed_ms(t0)
            result.status = "error"
            result.error = error_from_exception(exc)
            headers = getattr(getattr(exc, "response", None), "headers", None)
            if headers is not None:
                result.response_headers = self.filter_headers(headers)
                result.request_id = result.error.request_id
        return result

    # ---------------- ③ 토큰 카운트 ----------------
    def count_tokens(self, prompt: str, *, model: str | None = None) -> int | NotSupported:
        model = model or self.default_model
        if self.mode == "NO_KEY":
            return self.not_supported("count_tokens", f"{self.key_env} 없음 — POST /v1/messages/count_tokens 는 일반 키 필요(무료)", "키 설정 후 재실행")
        try:
            resp = self.client.messages.count_tokens(model=model, messages=[{"role": "user", "content": prompt}])
            return int(resp.input_tokens)
        except Exception as exc:
            err = error_from_exception(exc)
            return self.not_supported("count_tokens", f"count_tokens 실패: {err.category} {err.message}", "응답 usage.input_tokens 로 대체")

    # ---------------- ⑥ 상태 확인 ----------------
    def health(self) -> HealthResult:
        """가장 저렴한 확인: GET /v1/models?limit=1 (토큰 과금 0). 200=연결+인증 OK, 401=키 문제, 403=권한."""
        checked_via = "GET /v1/models"
        if self.mode == "NO_KEY":
            return HealthResult(self.name, ok=False, status_code=None, latency_ms=0.0, checked_via=checked_via, error=self.no_key_error())
        t0 = self.now()
        try:
            raw = self.client.models.with_raw_response.list(limit=1)
            ms = self.elapsed_ms(t0)
            return HealthResult(
                self.name,
                ok=True,
                status_code=raw.status_code,
                latency_ms=ms,
                checked_via=checked_via,
                ratelimit=self.filter_headers(raw.headers),
                request_id=raw.headers.get("request-id"),
            )
        except Exception as exc:
            ms = self.elapsed_ms(t0)
            err = error_from_exception(exc)
            headers = getattr(getattr(exc, "response", None), "headers", None)
            return HealthResult(
                self.name,
                ok=False,
                status_code=err.status_code,
                latency_ms=ms,
                checked_via=checked_via,
                error=err,
                ratelimit=self.filter_headers(headers) if headers is not None else {},
                request_id=err.request_id,
            )

    # ---------------- ④⑤ Admin API (raw HTTP) ----------------
    def _admin_get(self, url: str, params: list[tuple[str, str]]) -> tuple[int, dict[str, Any] | None, str]:
        """(status_code, json_or_None, redacted_error_message)."""
        resp = requests.get(url, params=params, headers=self._admin_headers(), timeout=self.timeout_s)
        try:
            data = resp.json()
        except ValueError:
            data = None
        if resp.status_code >= 400:
            err = (data or {}).get("error", {}) if isinstance(data, dict) else {}
            msg = err.get("message") if isinstance(err, dict) else None
            return resp.status_code, None, redact(f"HTTP {resp.status_code} {err.get('type', '') if isinstance(err, dict) else ''}: {msg or resp.text[:200]}")
        return resp.status_code, data if isinstance(data, dict) else {}, ""

    def _admin_paginate(self, url: str, params: list[tuple[str, str]], max_pages: int = 20) -> tuple[list[dict[str, Any]], str]:
        pages: list[dict[str, Any]] = []
        page_cursor: str | None = None
        for _ in range(max_pages):
            q = list(params) + ([("page", page_cursor)] if page_cursor else [])
            status, data, msg = self._admin_get(url, q)
            if data is None:
                return pages, msg
            pages.append(data)
            if not data.get("has_more") or not data.get("next_page"):
                break
            page_cursor = data["next_page"]
        return pages, ""

    def usage_report(
        self,
        start: datetime,
        end: datetime,
        *,
        bucket: str = "1d",
        group_by: tuple[str, ...] = ("model",),
    ) -> UsageReport | NotSupported:
        """GET /v1/organizations/usage_report/messages — Admin 키 필수(SDK 미지원 → requests).

        NOTE: client.beta.organization.analytics.* 는 /v1/organizations/analytics/* (Claude Enterprise 전용) 이라 이 엔드포인트와 다르다.
        """
        if not self.admin_key:
            return self.not_supported("usage_report", ADMIN_REASON, ADMIN_ALTERNATIVE)
        params: list[tuple[str, str]] = [
            ("starting_at", _rfc3339(start)),
            ("ending_at", _rfc3339(end)),
            ("bucket_width", bucket),
            ("limit", "31" if bucket == "1d" else ("168" if bucket == "1h" else "1440")),
        ] + [("group_by[]", g) for g in group_by]
        try:
            pages, msg = self._admin_paginate(USAGE_REPORT_URL, params)
        except requests.RequestException as exc:
            return self.not_supported("usage_report", redact(f"요청 실패: {type(exc).__name__}: {exc}"), ADMIN_ALTERNATIVE)
        if msg and not pages:
            return self.not_supported("usage_report", f"Admin API 오류 — {msg} (Admin 키/조직 권한 확인)", ADMIN_ALTERNATIVE)
        buckets = [b for p in pages for b in parse_usage_report(p, group_by)]
        return UsageReport(
            provider=self.name,
            source="admin_api",
            buckets=buckets,
            note=f"GET /v1/organizations/usage_report/messages bucket_width={bucket} group_by={list(group_by)} pages={len(pages)}"
            + (f" (partial: {msg})" if msg else "")
            + "; 데이터 지연 약 5분, 입력 토큰 = uncached + cache_creation(5m+1h) + cache_read",
        )

    def cost_report(self, start: datetime, end: datetime) -> UsageReport | NotSupported:
        """GET /v1/organizations/cost_report?group_by[]=description — 일(1d) 단위만, amount 는 센트 decimal 문자열."""
        if not self.admin_key:
            return self.not_supported("cost_report", ADMIN_REASON, ADMIN_ALTERNATIVE + " / cost() 로컬 계산")
        params: list[tuple[str, str]] = [
            ("starting_at", _rfc3339(start)),
            ("ending_at", _rfc3339(end)),
            ("bucket_width", "1d"),
            ("limit", "31"),
            ("group_by[]", "description"),
        ]
        try:
            pages, msg = self._admin_paginate(COST_REPORT_URL, params)
        except requests.RequestException as exc:
            return self.not_supported("cost_report", redact(f"요청 실패: {type(exc).__name__}: {exc}"), "cost() 로컬 계산")
        if msg and not pages:
            return self.not_supported("cost_report", f"Admin API 오류 — {msg} (Admin 키/조직 권한 확인)", "cost() 로컬 계산")
        buckets = [b for p in pages for b in parse_cost_report(p)]
        total = round(sum(b.cost_usd or 0.0 for b in buckets), 6)
        return UsageReport(
            provider=self.name,
            source="admin_api",
            buckets=buckets,
            note=f"GET /v1/organizations/cost_report group_by[]=description pages={len(pages)} total_usd={total}"
            + (f" (partial: {msg})" if msg else "")
            + "; amount 는 센트 단위 decimal 문자열 → /100, 1d 버킷만, Priority Tier 비용 미포함",
        )

    def verify_admin_key(self) -> dict[str, Any] | NotSupported:
        """GET /v1/organizations/me 로 Admin 키 유효성 확인. 조직 ID 는 민감정보라 돌려주지 않는다(존재 여부만)."""
        if not self.admin_key:
            return self.not_supported("verify_admin_key", ADMIN_REASON, "Console > Admin keys 에서 조직 admin 역할로 발급")
        try:
            status, data, msg = self._admin_get(ORG_ME_URL, [])
        except requests.RequestException as exc:
            return {"ok": False, "status_code": None, "error": redact(f"{type(exc).__name__}: {exc}")}
        if data is None:
            return {"ok": False, "status_code": status, "error": msg}
        return {"ok": True, "status_code": status, "organization_name": data.get("name"), "has_id": bool(data.get("id"))}


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------
def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _to_plain(obj: Any) -> Any:
    if obj is None:
        return None
    to_dict = getattr(obj, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict(mode="json")
        except Exception:
            pass
    if isinstance(obj, dict):
        return obj
    return str(obj)
