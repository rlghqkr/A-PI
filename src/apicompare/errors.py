"""오류 분류 체계 + 비밀값 마스킹.

3사 오류를 하나의 ErrorCategory 로 매핑한다 (검증된 조사 매트릭스 기준):
- OpenAI   : HTTP + error.type/error.code. 429 는 rate limit / 크레딧 소진(insufficient_quota, credit_balance_exhausted)
             / 지출 한도(*_spend_limit_exceeded) 세 경우가 같은 코드를 쓰므로 code 로 구분. 503 server_is_overloaded → OVERLOADED.
- Anthropic: 과부하는 503 이 아니라 529 overloaded_error. 티어 지출 한도는 429 + details.error_code=enforced_spend_limit_reached
             (retry-after 없음). 사용자 설정 한도는 400 invalid_request_error('...usage limits'). 크레딧 소진은 상태코드가 문서에 단정돼 있지 않아
             (400 또는 402) 메시지 'credit balance is too low' 로 판별한다.
             SDK 에서는 InternalServerError 만 잡으면 529 를 놓친다 → APIStatusError 로 받아 status_code 로 분기.
- Gemini   : error.code 가 snake_case 문자열(rate_limit_exceeded, quota_exceeded, model_not_found …), 선불 소진은 402 payment_required,
             목록에 없는 코드는 HTTP status 의 snake_case 로 폴백 → 패턴 매칭.
"""

from __future__ import annotations

import re
from enum import Enum

from .models import ErrorInfo


class ErrorCategory(str, Enum):
    AUTH = "AUTH"
    PERMISSION = "PERMISSION"
    NOT_FOUND = "NOT_FOUND"
    BAD_REQUEST = "BAD_REQUEST"
    RATE_LIMIT = "RATE_LIMIT"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    SPEND_LIMIT = "SPEND_LIMIT"
    OVERLOADED = "OVERLOADED"
    SERVER = "SERVER"
    TIMEOUT = "TIMEOUT"
    NETWORK = "NETWORK"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    UNKNOWN = "UNKNOWN"


# 출력/저장 전 반드시 거치는 마스킹 패턴. 더미 키("sk-proj-INVALID")는 짧아서 마스킹되지 않는다.
_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9_\-.=]{12,}"),
    re.compile(r"\borg-[A-Za-z0-9]{12,}"),
    re.compile(r"\bproj_[A-Za-z0-9]{12,}"),
    re.compile(r"\bntn_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[abp]-[A-Za-z0-9\-]{10,}"),
]

QUOTA_CODES = {"insufficient_quota", "credit_balance_exhausted", "payment_required", "billing_error"}
SPEND_CODES = {
    "organization_spend_limit_exceeded",
    "project_spend_limit_exceeded",
    "organization_usage_limit_exceeded",
    "enforced_spend_limit_reached",
}
OVERLOAD_CODES = {"server_is_overloaded", "service_unavailable_error", "overloaded_error", "service_unavailable", "unavailable"}
CONTENT_CODES = {"safety", "recitation", "prohibited_content", "spii", "blocklist", "content_blocked", "refusal"}


def redact(text: str) -> str:
    """문자열 안의 키/토큰 모양을 ***REDACTED*** 로 바꾼다."""
    if not isinstance(text, str):
        return text
    out = text
    for pattern in _SECRET_PATTERNS:
        out = pattern.sub("***REDACTED***", out)
    return out


def has_secret(text: str) -> bool:
    return isinstance(text, str) and any(p.search(text) for p in _SECRET_PATTERNS)


def classify_http(
    status_code: int | None,
    provider_type: str | None = None,
    provider_code: str | None = None,
    message: str = "",
) -> ErrorCategory:
    """HTTP status + Provider 오류 type/code + 메시지 → ErrorCategory."""
    t = (provider_type or "").lower()
    c = (provider_code or "").lower()
    m = (message or "").lower()
    codes = {t, c}

    if codes & CONTENT_CODES:
        return ErrorCategory.CONTENT_BLOCKED
    if status_code is None:
        return ErrorCategory.TIMEOUT if ("timeout" in m or "timed out" in m) else ErrorCategory.NETWORK
    if status_code == 401:
        return ErrorCategory.AUTH
    if status_code == 403:
        return ErrorCategory.PERMISSION
    if status_code == 404:
        return ErrorCategory.NOT_FOUND
    if status_code == 402:
        return ErrorCategory.QUOTA_EXHAUSTED
    if status_code in (408, 504):
        return ErrorCategory.TIMEOUT
    if status_code == 400:
        if "usage limits" in m or "spend limit" in m:
            return ErrorCategory.SPEND_LIMIT
        if "credit balance" in m:
            return ErrorCategory.QUOTA_EXHAUSTED
        return ErrorCategory.BAD_REQUEST
    if status_code in (409, 413, 416, 422):
        return ErrorCategory.BAD_REQUEST
    if status_code == 429:
        # 지출 한도 코드가 더 구체적이므로 먼저 본다 (OpenAI 가 type=insufficient_quota 와 함께 보낼 수 있음)
        if codes & SPEND_CODES:
            return ErrorCategory.SPEND_LIMIT
        if codes & QUOTA_CODES or "credit balance" in m or "insufficient_quota" in m:
            return ErrorCategory.QUOTA_EXHAUSTED
        return ErrorCategory.RATE_LIMIT
    if status_code == 529:
        return ErrorCategory.OVERLOADED
    if status_code == 503:
        return ErrorCategory.OVERLOADED if (codes & OVERLOAD_CODES or "overload" in m) else ErrorCategory.SERVER
    if status_code >= 500:
        return ErrorCategory.SERVER
    return ErrorCategory.UNKNOWN


def make_error(
    exc: BaseException | None = None,
    *,
    status_code: int | None = None,
    provider_type: str | None = None,
    provider_code: str | None = None,
    message: str = "",
    retry_after: str | None = None,
    request_id: str | None = None,
    category: ErrorCategory | None = None,
) -> ErrorInfo:
    """어댑터가 SDK 예외에서 뽑은 정보를 ErrorInfo 로 만든다. 메시지는 항상 redact 를 거친다."""
    cat = category or classify_http(status_code, provider_type, provider_code, message)
    return ErrorInfo(
        category=cat.value,
        status_code=status_code,
        provider_type=provider_type,
        provider_code=provider_code,
        message=redact(message or (str(exc) if exc else ""))[:500],
        retry_after=retry_after,
        request_id=request_id,
        exception_class=type(exc).__name__ if exc is not None else None,
    )
