"""공통 데이터 모델. 세 Provider 어댑터가 모두 이 타입으로 결과를 돌려준다.

규칙
- UsageNormalized 는 '과금 관점' 토큰이다.
    input_tokens  = 캐시 읽기/쓰기까지 포함한 총 입력
                    (OpenAI: usage.input_tokens / prompt_tokens — cached 포함,
                     Anthropic: input_tokens + cache_creation_input_tokens + cache_read_input_tokens,
                     Gemini: promptTokenCount(캐시 포함) + toolUsePromptTokenCount)
    output_tokens = reasoning/thinking 토큰을 포함한 총 출력 (3사 모두 output 단가로 과금)
                    (OpenAI: output_tokens(reasoning 포함), Anthropic: output_tokens(thinking 포함),
                     Gemini: candidatesTokenCount + thoughtsTokenCount)
    total_tokens  = input_tokens + output_tokens
                    (OpenAI/Gemini 는 응답에 total 이 있고, Anthropic 은 없어서 계산 → total_is_computed=True)
- 어댑터는 예외를 밖으로 던지지 않는다. 실패는 CallResult(status="error", error=ErrorInfo) 로 돌려준다.
- 제공되지 않는 기능(예: Gemini 기간별 Usage API)은 NotSupported 객체로 돌려준다(예외 아님).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from typing import Any, Literal

Evidence = Literal["live", "docs", "observed", "blocked"]
Mode = Literal["LIVE", "NO_KEY"]


@dataclass
class ModelInfo:
    provider: str
    id: str
    display_name: str | None = None
    context_window: int | None = None  # OpenAI: None(API 미제공) / Anthropic: max_input_tokens / Gemini: input_token_limit
    max_output_tokens: int | None = None  # Anthropic: max_tokens / Gemini: output_token_limit
    created_at: str | None = None
    shutdown_date: str | None = None  # OpenAI: shutdown_date / Anthropic: retires_at / Gemini: 없음
    lifecycle: str | None = None  # Anthropic: active | deprecated | retired
    capabilities: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageNormalized:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int = 0  # input_tokens 에 포함된 캐시 읽기 토큰
    cache_write_tokens: int = 0  # input_tokens 에 포함된 캐시 쓰기 토큰 (Anthropic cache_creation 등)
    reasoning_tokens: int = 0  # output_tokens 에 포함된 추론 토큰 (더하지 말 것)
    total_is_computed: bool = False
    raw: dict[str, Any] = field(default_factory=dict)  # Provider 원본 usage 필드


@dataclass
class ErrorInfo:
    category: str  # errors.ErrorCategory 값
    status_code: int | None = None
    provider_type: str | None = None  # OpenAI error.type / Anthropic error.type / Gemini error.status
    provider_code: str | None = None  # OpenAI error.code / Anthropic details.error_code / Gemini error.code
    message: str = ""  # redact() 통과한 메시지
    retry_after: str | None = None
    request_id: str | None = None
    exception_class: str | None = None


@dataclass
class CallResult:
    provider: str
    model: str
    api: str  # responses | chat_completions | messages | generate_content | interactions
    status: Literal["ok", "error"]
    text: str | None = None
    usage: UsageNormalized | None = None
    latency_ms: float = 0.0
    request_id: str | None = None
    finish_reason: str | None = None
    service_tier: str | None = None
    response_headers: dict[str, str] = field(default_factory=dict)  # 화이트리스트 헤더만
    error: ErrorInfo | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthResult:
    provider: str
    ok: bool
    status_code: int | None
    latency_ms: float
    checked_via: str  # 예: "GET /v1/models"
    error: ErrorInfo | None = None
    ratelimit: dict[str, str] = field(default_factory=dict)
    request_id: str | None = None


@dataclass
class NotSupported:
    provider: str
    item: str
    reason: str
    alternative: str = ""


@dataclass
class UsageBucket:
    start: str
    end: str
    group: dict[str, str]
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int | None = None
    cost_usd: float | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageReport:
    provider: str
    source: Literal["admin_api", "usagelog", "dashboard_only"]
    buckets: list[UsageBucket] = field(default_factory=list)
    note: str = ""


@dataclass
class CostEstimate:
    usd: float
    breakdown: dict[str, float]
    price_as_of: str
    price_source: str
    model: str = ""
    effective_from: str | None = None
    note: str = ""


def to_dict(obj: Any) -> Any:
    """dataclass → dict (중첩 포함). JSON 저장용."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    if isinstance(obj, list):
        return [to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    return obj
