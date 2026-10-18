"""Google Gemini(Gemini Developer API, AI Studio 키) 어댑터 — google-genai 2.x.

조사 매트릭스(Gemini 섹션)에서 확정된 사실
- 모델 호출 경로가 두 개 공존: generateContent(유지, 기본) 와 Interactions(권장). usage 필드명이 다르므로 여기서 정규화한다.
    generateContent : usage_metadata.{prompt_token_count, candidates_token_count, thoughts_token_count,
                      cached_content_token_count, tool_use_prompt_token_count, total_token_count}
    Interactions    : usage.{total_input_tokens, total_output_tokens, total_thought_tokens,
                      total_cached_tokens, total_tool_use_tokens, total_tokens}
- 과금 관점 정규화: input = prompt(캐시 포함) + tool_use_prompt, output = candidates + thoughts(output 단가),
  total = total_token_count (없으면 input+output 계산 → total_is_computed=True).
- 기간별 Usage/비용 API 가 없다(AI Studio 대시보드 전용). usage_report()/cost_report() 는 항상 NotSupported.
- 단가는 API 로 미제공 → cost() 는 base 의 pricing.PRICE_TABLE 로컬 계산.
- 오류: google.genai.errors.APIError(code:int, status:gRPC 이름, message, details) → ClientError(4xx)/ServerError(5xx).
  error.code 가 snake_case 문자열(rate_limit_exceeded, quota_exceeded, model_not_found, …)로 올 수도, 정수(HTTP) 로 올 수도 있다.
  Interactions 경로는 다른 예외 계층(google.genai._gaos.lib.compat_errors.APIStatusError: status_code, body, message)을 던지므로
  error_from_exception() 은 두 계층을 모두 처리한다. 레이트리밋 응답 헤더(Retry-After, x-ratelimit-*)는 문서화돼 있지 않다.

[SDK 재시도 함정 — 소스로 확인]
  google/genai/types.py: HttpOptions.retry_options 기본값 None.
  google/genai/_api_client.py retry_args(): options 가 None 이면 {'stop': tenacity.stop_after_attempt(1)} → 재시도 없음.
  retry_options=HttpRetryOptions() 를 넘긴 경우에만 _RETRY_ATTEMPTS=5(초기 호출 포함)·1s→60s 지수 백오프·(408,429,500,502,503,504) 가 기본.
  troubleshooting 문서의 "기본 4회 재시도" 와 다르다. 이 어댑터는 HttpRetryOptions(attempts=self.max_retries + 1) 로 명시해
  세 Provider 의 재시도 횟수를 같게 고정한다(attempts 는 초기 호출을 포함하므로 max_retries=0 → attempts=1).
  timeout 단위는 밀리초(HttpOptions.timeout: int) — _api_client 가 /1000 해서 httpx 에 넘긴다.

확인한 SDK 소스(.venv/lib/python3.12/site-packages/google/genai/):
  types.py (HttpOptions, HttpRetryOptions, GenerateContentConfig, GenerateContentResponse, GenerateContentResponseUsageMetadata,
  CountTokensResponse, Model, Candidate, FinishReason, HttpResponse) · models.py (list/get/count_tokens/generate_content, sdk_http_response 주입)
  · errors.py (APIError/ClientError/ServerError) · _api_client.py (retry_args, _HTTPX_TRANSIENT_EXC, timeout/1000)
  · client.py (Client.interactions 프로퍼티) · _gaos/google_genai.py (GeminiNextGenInteractions.create 시그니처)
  · _gaos/types/interactions/usage.py (Usage) · _gaos/types/interactions/interaction.py (Interaction.output_text/usage/status)
  · _gaos/lib/compat_errors.py (APIError/APIStatusError/APITimeoutError/APIConnectionError)
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from ..errors import ErrorCategory, make_error
from ..models import (
    CallResult,
    ErrorInfo,
    HealthResult,
    ModelInfo,
    NotSupported,
    UsageNormalized,
    UsageReport,
)
from .base import ProviderAdapter

GENERATE_CONTENT = "generate_content"
INTERACTIONS = "interactions"
MODEL_PREFIX = "models/"

# api-errors 문서의 snake_case 코드 + 자주 보이는 ErrorInfo.reason(소문자화). 목록에 없는 코드는 HTTP status 의 snake_case 로 폴백되므로
# 어댑터는 '화이트리스트 매칭' 이 아니라 '패턴 추출' 을 한다(아래 _CODE_PATTERN).
KNOWN_PROVIDER_CODES: tuple[str, ...] = (
    "rate_limit_exceeded",
    "quota_exceeded",
    "too_many_requests",
    "resource_exhausted",
    "payment_required",
    "model_not_found",
    "not_found",
    "api_key_invalid",
    "api_key_service_blocked",
    "authentication",
    "permission_denied",
    "invalid_request",
    "invalid_argument",
    "failed_precondition",
    "parameter_unknown",
    "service_unavailable",
    "unavailable",
    "deadline_exceeded",
    "api_error",
    "internal",
    "unimplemented",
    "already_exists",
    "aborted",
    "out_of_range",
    "cancelled",
    "prohibited_content",
    "content_blocked",
    "safety",
    "recitation",
    "blocklist",
    "spii",
    "malformed_function_call",
    "missing_thought_signature",
)
_CODE_PATTERN = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")


# ---------------------------------------------------------------------------
# 순수 함수 (네트워크 없이 테스트 가능)
# ---------------------------------------------------------------------------
def _get(obj: Any, name: str, default: Any = None) -> Any:
    """pydantic 모델/dict/None 어디서든 필드를 읽는다."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int(v: Any) -> int:
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def strip_model_prefix(name: str | None) -> str:
    """'models/gemini-3.8-flash' → 'gemini-3.8-flash'."""
    if not name:
        return ""
    return name[len(MODEL_PREFIX):] if name.startswith(MODEL_PREFIX) else name


def normalize_generate_content_usage(um: Any) -> UsageNormalized:
    """generateContent 응답의 usage_metadata → UsageNormalized(과금 관점).

    input  = prompt_token_count(캐시 포함) + tool_use_prompt_token_count
    cached = cached_content_token_count (input 에 포함)
    output = candidates_token_count + thoughts_token_count (둘 다 output 단가)
    total  = total_token_count; None 이면 input+output 로 계산(total_is_computed=True)
    """
    prompt = _int(_get(um, "prompt_token_count"))
    tool_use = _int(_get(um, "tool_use_prompt_token_count"))
    cached = _int(_get(um, "cached_content_token_count"))
    candidates = _int(_get(um, "candidates_token_count"))
    thoughts = _int(_get(um, "thoughts_token_count"))
    total_raw = _get(um, "total_token_count")

    input_tokens = prompt + tool_use
    output_tokens = candidates + thoughts
    computed = total_raw is None
    total = input_tokens + output_tokens if computed else _int(total_raw)

    raw = {
        "prompt_token_count": _get(um, "prompt_token_count"),
        "candidates_token_count": _get(um, "candidates_token_count"),
        "thoughts_token_count": _get(um, "thoughts_token_count"),
        "cached_content_token_count": _get(um, "cached_content_token_count"),
        "tool_use_prompt_token_count": _get(um, "tool_use_prompt_token_count"),
        "total_token_count": total_raw,
    }
    traffic = _get(um, "traffic_type")
    if traffic is not None:
        raw["traffic_type"] = str(getattr(traffic, "value", traffic))
    return UsageNormalized(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cached_input_tokens=cached,
        cache_write_tokens=0,  # Gemini 는 캐시 쓰기 토큰을 usage 에 분리하지 않는다(캐시 생성은 caches API 별도 과금)
        reasoning_tokens=thoughts,
        total_is_computed=computed,
        raw=raw,
    )


def normalize_interactions_usage(u: Any) -> UsageNormalized:
    """Interactions API 의 interaction.usage → UsageNormalized.

    thinking 문서 예시(62 + 171 + 297 = 530)대로 total_output_tokens 는 thought 를 제외한 값이다 → output = total_output + total_thought.
    input = total_input_tokens + total_tool_use_tokens, cached = total_cached_tokens(input 에 포함).
    """
    total_input = _int(_get(u, "total_input_tokens"))
    tool_use = _int(_get(u, "total_tool_use_tokens"))
    cached = _int(_get(u, "total_cached_tokens"))
    output = _int(_get(u, "total_output_tokens"))
    thought = _int(_get(u, "total_thought_tokens"))
    total_raw = _get(u, "total_tokens")

    input_tokens = total_input + tool_use
    output_tokens = output + thought
    computed = total_raw is None
    total = input_tokens + output_tokens if computed else _int(total_raw)
    raw = {
        "total_input_tokens": _get(u, "total_input_tokens"),
        "total_output_tokens": _get(u, "total_output_tokens"),
        "total_thought_tokens": _get(u, "total_thought_tokens"),
        "total_cached_tokens": _get(u, "total_cached_tokens"),
        "total_tool_use_tokens": _get(u, "total_tool_use_tokens"),
        "total_tokens": total_raw,
    }
    return UsageNormalized(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total,
        cached_input_tokens=cached,
        cache_write_tokens=0,
        reasoning_tokens=thought,
        total_is_computed=computed,
        raw=raw,
    )


def extract_provider_code(details: Any, message: str = "") -> str | None:
    """오류 바디/메시지에서 snake_case 코드를 뽑는다.

    우선순위: error.code 가 문자열이면 그대로 → details[].reason(API_KEY_INVALID 등, 소문자화) → 알려진 코드가 바디/메시지 텍스트에 있으면 그것
    → 그 외 None. (목록에 없는 코드는 HTTP status 의 snake_case 로 폴백된다는 api-errors 규칙 때문에 화이트리스트가 아닌 패턴 추출을 한다.)
    """
    err = details.get("error", details) if isinstance(details, dict) else {}
    if isinstance(err, dict):
        code = err.get("code")
        if isinstance(code, str) and code:
            return code.lower()
        for d in err.get("details") or []:
            reason = d.get("reason") if isinstance(d, dict) else None
            if isinstance(reason, str) and reason:
                return reason.lower()
    try:
        blob = json.dumps(details, ensure_ascii=False, default=str) if details is not None else ""
    except (TypeError, ValueError):
        blob = str(details)
    text = f"{blob} {message or ''}".lower()
    for known in KNOWN_PROVIDER_CODES:
        if re.search(rf"\b{known}\b", text):
            return known
    return None


def _retry_delay(details: Any) -> str | None:
    """429 바디의 RetryInfo.retryDelay(비공식, 사용자 보고) 가 있으면 문자열로 돌려준다. 공식 헤더는 없다."""
    err = details.get("error", details) if isinstance(details, dict) else {}
    if isinstance(err, dict):
        for d in err.get("details") or []:
            if isinstance(d, dict) and d.get("retryDelay"):
                return str(d["retryDelay"])
    return None


def _looks_like_api_error(exc: BaseException) -> bool:
    """google.genai.errors.APIError 또는 Interactions 경로의 compat APIStatusError(status_code:int, body) 인지."""
    try:
        from google.genai import errors as genai_errors

        if isinstance(exc, genai_errors.APIError):
            return True
    except ImportError:  # pragma: no cover
        pass
    return isinstance(getattr(exc, "status_code", None), int) and (hasattr(exc, "body") or hasattr(exc, "response"))


def error_from_exception(exc: BaseException | NotSupported) -> ErrorInfo:
    """SDK/네트워크 예외 → ErrorInfo. 어떤 예외가 와도 예외를 다시 던지지 않는다. (NotSupported dataclass 도 받아 ErrorInfo 로 바꾼다.)"""
    if isinstance(exc, NotSupported):  # generate(api="interactions") 에서 SDK 미지원일 때
        return make_error(
            category=ErrorCategory.UNKNOWN,
            message=f"NotSupported: {exc.reason} / 대안: {exc.alternative}",
        )

    name = type(exc).__name__
    if _looks_like_api_error(exc):
        code = getattr(exc, "code", None)
        status_code = code if isinstance(code, int) else getattr(exc, "status_code", None)
        details = getattr(exc, "details", None)
        if details is None:
            details = getattr(exc, "body", None)
        err = details.get("error", details) if isinstance(details, dict) else {}
        provider_type = getattr(exc, "status", None) or (err.get("status") if isinstance(err, dict) else None)
        message = getattr(exc, "message", None) or str(exc)
        if not isinstance(message, str):
            message = str(message)
        provider_code = extract_provider_code(details, message)
        request_id = None
        resp = getattr(exc, "response", None)
        headers = getattr(resp, "headers", None)
        if headers is not None:
            try:
                request_id = headers.get("x-request-id") or headers.get("x-goog-request-id")
            except Exception:  # noqa: BLE001 - 헤더 객체 종류가 다양함
                request_id = None
        return make_error(
            exc,
            status_code=status_code,
            provider_type=str(provider_type) if provider_type else None,
            provider_code=provider_code,
            message=message,
            retry_after=_retry_delay(details),
            request_id=request_id,
        )

    if "Timeout" in name or "timed out" in str(exc).lower():
        return make_error(exc, category=ErrorCategory.TIMEOUT, message=str(exc) or name)
    if "Connect" in name or "Network" in name:
        return make_error(exc, category=ErrorCategory.NETWORK, message=str(exc) or name)
    return make_error(exc, category=ErrorCategory.UNKNOWN, message=str(exc) or name)


def _finish_reason_str(candidate: Any) -> str | None:
    fr = _get(candidate, "finish_reason")
    if fr is None:
        return None
    return str(getattr(fr, "value", fr))


def _warning_headers(headers: Any) -> dict[str, str]:
    """deprecation/warning 류 헤더만 뽑는다(Gemini 3.6+/4 가 temperature 등을 무시할 때 'deprecation warning headers' 를 돌려준다는 문서 근거)."""
    out: dict[str, str] = {}
    try:
        items = headers.items()
    except AttributeError:
        return out
    for k, v in items:
        lk = str(k).lower()
        if "warning" in lk or "deprecat" in lk:
            out[lk] = str(v)
    return out


# ---------------------------------------------------------------------------
# 어댑터
# ---------------------------------------------------------------------------
class GeminiAdapter(ProviderAdapter):
    """Gemini Developer API(AI Studio 키) 어댑터.

    - 재시도: SDK 기본은 retry_options=None → 재시도 없음(문서의 '4회' 와 다름). 여기서는 HttpRetryOptions(attempts=max_retries+1) 로
      명시해 고정한다(attempts 는 초기 호출 포함). timeout 은 HttpOptions.timeout(밀리초) 로 명시.
    - Admin 키 개념이 없다(admin_key_env=None). usage_report()/cost_report() 는 항상 NotSupported.
    """

    name = "gemini"
    key_env = "GEMINI_API_KEY"
    admin_key_env = None
    default_model = "gemini-3.8-flash"

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._client: Any = None
        self.last_error: ErrorInfo | None = None  # list_models()/count_tokens() 가 [] / NotSupported 를 돌려줄 때의 원인

    # ---------------- 클라이언트 ----------------
    @property
    def client(self) -> Any:
        """lazy google.genai.Client. 키가 없으면 RuntimeError(호출측은 mode 로 먼저 분기한다)."""
        if self._client is None:
            if not self.api_key:
                raise RuntimeError("GEMINI_API_KEY 없음 — mode=NO_KEY")
            from google import genai
            from google.genai import types

            self._client = genai.Client(
                api_key=self.api_key,
                http_options=types.HttpOptions(
                    timeout=max(int(self.timeout_s * 1000), 1),  # 밀리초
                    retry_options=types.HttpRetryOptions(attempts=self.max_retries + 1),  # 1 → 재시도 없음
                ),
            )
        return self._client

    def _no_key_result(self, model: str, api: str) -> CallResult:
        return CallResult(provider=self.name, model=model, api=api, status="error", error=self.no_key_error())

    # ---------------- ① 모델 목록 ----------------
    def list_models(self) -> list[ModelInfo]:
        """GET /v1beta/models (client.models.list, Pager 가 페이지네이션 처리). 키 없으면 []. 실패 시 [] + last_error."""
        if self.mode == "NO_KEY":
            return []
        out: list[ModelInfo] = []
        try:
            for m in self.client.models.list():
                caps: dict[str, Any] = {}
                actions = _get(m, "supported_actions")
                if actions is not None:
                    caps["supported_actions"] = list(actions)
                thinking = _get(m, "thinking")
                if thinking is not None:
                    caps["thinking"] = bool(thinking)
                for extra in ("temperature", "max_temperature", "top_p", "top_k"):
                    v = _get(m, extra)
                    if v is not None:
                        caps[extra] = v
                raw = m.model_dump(exclude_none=True) if hasattr(m, "model_dump") else dict(m)
                out.append(
                    ModelInfo(
                        provider=self.name,
                        id=strip_model_prefix(_get(m, "name")),
                        display_name=_get(m, "display_name"),
                        context_window=_get(m, "input_token_limit"),
                        max_output_tokens=_get(m, "output_token_limit"),
                        created_at=None,  # Gemini Model 객체에 생성일 없음
                        shutdown_date=None,  # deprecations 페이지에만 있음
                        lifecycle=None,
                        capabilities=caps,
                        raw=raw,
                    )
                )
            self.last_error = None
        except Exception as exc:  # noqa: BLE001
            self.last_error = error_from_exception(exc)
            return []
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
        """api=None|'generate_content'(기본) | 'interactions'. 절대 예외를 던지지 않는다.

        kwargs 는 그대로 GenerateContentConfig(또는 Interactions generation_config) 로 넘어간다(예: temperature=0.0 — 3.6+/4 는 무시).
        """
        model = model or self.default_model
        api = api or GENERATE_CONTENT
        if api not in (GENERATE_CONTENT, INTERACTIONS):
            return CallResult(
                provider=self.name, model=model, api=api, status="error",
                error=make_error(category=ErrorCategory.BAD_REQUEST, message=f"알 수 없는 api: {api} (generate_content | interactions)"),
            )
        if self.mode == "NO_KEY":
            return self._no_key_result(model, api)
        try:
            if api == INTERACTIONS:
                return self._generate_interactions(prompt, model=model, system=system, max_output_tokens=max_output_tokens, json_schema=json_schema, **kwargs)
            return self._generate_content(prompt, model=model, system=system, max_output_tokens=max_output_tokens, json_schema=json_schema, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 어떤 경우에도 밖으로 던지지 않는다
            return CallResult(provider=self.name, model=model, api=api, status="error", error=error_from_exception(exc))

    def _generate_content(self, prompt: str, *, model: str, system: str | None, max_output_tokens: int, json_schema: dict | None, **kwargs: Any) -> CallResult:
        from google.genai import types

        cfg: dict[str, Any] = {"max_output_tokens": max_output_tokens}
        if system:
            cfg["system_instruction"] = system
        if json_schema:
            cfg["response_mime_type"] = "application/json"
            cfg["response_json_schema"] = json_schema
        cfg.update(kwargs)
        config = types.GenerateContentConfig(**cfg)

        t0 = self.now()
        try:
            resp = self.client.models.generate_content(model=model, contents=prompt, config=config)
        except Exception as exc:  # noqa: BLE001
            latency = self.elapsed_ms(t0)
            return CallResult(provider=self.name, model=model, api=GENERATE_CONTENT, status="error", latency_ms=latency, error=error_from_exception(exc))
        latency = self.elapsed_ms(t0)

        headers_obj = _get(_get(resp, "sdk_http_response"), "headers")
        headers = self.filter_headers(headers_obj)
        candidates = _get(resp, "candidates") or []
        first = candidates[0] if candidates else None
        finish = _finish_reason_str(first)
        try:
            text = resp.text  # 후보가 없거나 비텍스트 파트면 None
        except Exception:  # noqa: BLE001
            text = None
        um = _get(resp, "usage_metadata")
        usage = normalize_generate_content_usage(um) if um is not None else None
        raw: dict[str, Any] = {
            "model_version": _get(resp, "model_version"),
            "response_id": _get(resp, "response_id"),
            "finish_reason": finish,
            "candidate_count": len(candidates),
            "warning_headers": _warning_headers(headers_obj),
            "config_sent": {k: v for k, v in cfg.items() if k != "response_json_schema"},
        }
        pf = _get(resp, "prompt_feedback")
        block = _get(pf, "block_reason")
        if block is not None:
            raw["block_reason"] = str(getattr(block, "value", block))

        status = "ok"
        error: ErrorInfo | None = None
        if first is None and block is not None:
            status = "error"
            error = make_error(
                category=ErrorCategory.CONTENT_BLOCKED,
                status_code=200,
                provider_type="prompt_feedback.block_reason",
                provider_code=str(getattr(block, "value", block)).lower(),
                message=f"프롬프트가 차단됨: {raw['block_reason']}",
            )
        elif text is None and finish not in (None, "STOP", "MAX_TOKENS"):
            status = "error"
            error = make_error(
                category=ErrorCategory.CONTENT_BLOCKED if (finish or "").lower() in ("safety", "recitation", "blocklist", "prohibited_content", "spii") else ErrorCategory.UNKNOWN,
                status_code=200,
                provider_type="finish_reason",
                provider_code=(finish or "").lower() or None,
                message=f"텍스트 없이 종료: finish_reason={finish}",
            )

        return CallResult(
            provider=self.name,
            model=model,
            api=GENERATE_CONTENT,
            status=status,
            text=text,
            usage=usage,
            latency_ms=latency,
            request_id=_get(resp, "response_id"),
            finish_reason=finish,
            service_tier=str(kwargs["service_tier"]) if kwargs.get("service_tier") is not None else None,
            response_headers=headers,
            error=error,
            raw=raw,
        )

    def _generate_interactions(self, prompt: str, *, model: str, system: str | None, max_output_tokens: int, json_schema: dict | None, **kwargs: Any) -> CallResult:
        client = self.client
        interactions = getattr(client, "interactions", None)
        if interactions is None or not hasattr(interactions, "create"):
            ns = self.not_supported(
                "interactions",
                "설치된 google-genai 에 client.interactions 가 없음(>= 2.3.0 필요)",
                "pip install -U google-genai 또는 api='generate_content' 사용",
            )
            # NotSupported 는 dataclass(예외 아님) → error_from_exception 이 ErrorInfo 로 바꿔 준다
            return CallResult(provider=self.name, model=model, api=INTERACTIONS, status="error", error=error_from_exception(ns))
        gen_cfg: dict[str, Any] = {"max_output_tokens": max_output_tokens}
        body: dict[str, Any] = {"model": model, "input": prompt, "store": False}  # 기본 store=true(서버 저장) 이므로 명시적으로 끈다
        if system:
            body["system_instruction"] = system
        if json_schema:
            body["response_format"] = {"type": "text", "mime_type": "application/json", "schema": json_schema}
        # kwargs: Interactions 의 generation_config 키(temperature, thinking_level, top_p, seed, stop_sequences …)는 generation_config 로,
        #         최상위 키(store, labels, service_tier, previous_interaction_id, safety_settings …)는 body 로.
        top_level = {"store", "labels", "service_tier", "previous_interaction_id", "safety_settings", "cached_content", "tools", "background", "response_modalities"}
        for k, v in kwargs.items():
            (body if k in top_level else gen_cfg)[k] = v
        body["generation_config"] = gen_cfg

        t0 = self.now()
        try:
            it = interactions.create(timeout=self.timeout_s, **body)
        except Exception as exc:  # noqa: BLE001
            latency = self.elapsed_ms(t0)
            return CallResult(provider=self.name, model=model, api=INTERACTIONS, status="error", latency_ms=latency, error=error_from_exception(exc))
        latency = self.elapsed_ms(t0)

        status_str = _get(it, "status")
        status_str = str(getattr(status_str, "value", status_str)) if status_str is not None else None
        u = _get(it, "usage")
        usage = normalize_interactions_usage(u) if u is not None else None
        errors_list = _get(it, "errors") or []
        raw: dict[str, Any] = {
            "id": _get(it, "id"),
            "model": str(_get(it, "model")) if _get(it, "model") is not None else None,
            "status": status_str,
            "service_tier": str(_get(it, "service_tier")) if _get(it, "service_tier") is not None else None,
            "errors": [str(e) for e in errors_list][:5],
            "body_sent": {k: v for k, v in body.items() if k != "response_format"},
            "note": "Interactions 응답 객체에는 HTTP 헤더가 없음(sdk_http_response 미제공) → response_headers 비어 있음",
        }
        text = _get(it, "output_text")
        ok = status_str in (None, "completed") and not errors_list
        error = None
        if not ok:
            error = make_error(
                category=ErrorCategory.UNKNOWN,
                status_code=200,
                provider_type="interaction.status",
                provider_code=status_str,
                message=f"interaction status={status_str} errors={raw['errors']}",
            )
        return CallResult(
            provider=self.name,
            model=model,
            api=INTERACTIONS,
            status="ok" if ok else "error",
            text=text,
            usage=usage,
            latency_ms=latency,
            request_id=_get(it, "id"),
            finish_reason=status_str,
            service_tier=raw["service_tier"],
            response_headers={},
            error=error,
            raw=raw,
        )

    # ---------------- ③ 토큰 카운트 ----------------
    def count_tokens(self, prompt: str, *, model: str | None = None) -> int | NotSupported:
        """POST /v1beta/models/{model}:countTokens — 과금 안 됨(billing 문서). SDK 응답은 total_tokens, cached_content_token_count 만 노출."""
        model = model or self.default_model
        if self.mode == "NO_KEY":
            return self.not_supported("count_tokens", self.no_key_error().message, "AI Studio 에서 무료 키 발급 후 재실행")
        try:
            resp = self.client.models.count_tokens(model=model, contents=prompt)
            self.last_error = None
            return int(resp.total_tokens or 0)
        except Exception as exc:  # noqa: BLE001
            self.last_error = error_from_exception(exc)
            return self.not_supported("count_tokens", f"countTokens 실패: [{self.last_error.category}] {self.last_error.message}", "키/모델 확인 후 재시도")

    # ---------------- ⑥ 헬스 ----------------
    def health(self) -> HealthResult:
        """GET /v1beta/models/{default_model} (client.models.get) — 토큰 소비 없음. 레이트리밋 헤더는 Gemini 에 없어 ratelimit={}."""
        via = "GET /v1beta/models/{model}"
        if self.mode == "NO_KEY":
            return HealthResult(provider=self.name, ok=False, status_code=None, latency_ms=0.0, checked_via=via, error=self.no_key_error())
        t0 = self.now()
        try:
            m = self.client.models.get(model=self.default_model)
            latency = self.elapsed_ms(t0)
            # Model 객체에는 HTTP 헤더가 없다. 200 을 기록(예외가 없으면 SDK 가 200 을 받은 것: errors.APIError.raise_for_response 는 200 외 전부 raise).
            return HealthResult(
                provider=self.name,
                ok=True,
                status_code=200,
                latency_ms=latency,
                checked_via=via,
                ratelimit={},
                request_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            latency = self.elapsed_ms(t0)
            err = error_from_exception(exc)
            return HealthResult(provider=self.name, ok=False, status_code=err.status_code, latency_ms=latency, checked_via=via, error=err, request_id=err.request_id)

    # ---------------- ④ ⑤ 기간별 Usage / 비용 (API 없음) ----------------
    def usage_report(
        self,
        start: datetime,
        end: datetime,
        *,
        bucket: str = "1d",
        group_by: tuple[str, ...] = ("model",),
    ) -> UsageReport | NotSupported:
        return self.not_supported(
            "usage_report",
            "Gemini API 에는 기간별 Usage 엔드포인트가 없음(AI Studio 대시보드 전용). Admin 키 개념도 없어 어떤 키로도 불가 — "
            "간접 수단은 Google Cloud OAuth(ADC, Project Viewer 이상) 가 필요하며 Auth key 로 보낸 요청은 서비스 계정 usage metrics 에 기록되지 않음",
            "https://aistudio.google.com/usage · Cloud Monitoring 메트릭 generativelanguage.googleapis.com/generate_content_usage_output_token_count"
            "(OAuth, BETA) · apicompare.usagelog.aggregate()",
        )

    def cost_report(self, start: datetime, end: datetime) -> UsageReport | NotSupported:
        return self.not_supported(
            "cost_report",
            "Gemini API 에는 비용 조회 엔드포인트가 없음. 실비는 Paid tier 에서만 Cloud Billing 리포트/BigQuery export(결제계정 권한, 최대 24h 지연) 로 확인. "
            "Free tier 는 $0, Prepay 잔액은 AI Studio 에서만 확인",
            "cost() 로컬 계산(pricing.PRICE_TABLE, 2027-01-01 인상 예고 반영) · Cloud Billing 리포트 'Service = Gemini API, Group by SKU' · BigQuery billing export",
        )


__all__ = [
    "GeminiAdapter",
    "normalize_generate_content_usage",
    "normalize_interactions_usage",
    "error_from_exception",
    "extract_provider_code",
    "strip_model_prefix",
]
