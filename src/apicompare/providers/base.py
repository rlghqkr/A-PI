"""Provider 어댑터 공통 인터페이스. 세 어댑터(openai/anthropic/gemini)가 이 클래스를 상속한다.

조사 항목과 메서드의 대응
    ① 모델 목록 조회  → list_models()
    ② 모델 호출       → generate()
    ③ Token Usage    → generate().usage (UsageNormalized) + count_tokens()
    ④ Usage 조회      → usage_report()  (Admin 키 없거나 API 없으면 NotSupported)
    ⑤ 비용 확인       → cost() (로컬 계산) + cost_report() (Admin 키 있을 때만)
    ⑥ 상태·오류 확인  → health() + generate() 의 CallResult.error
    ⑦ 호출 예제       → 노트북 §7 (어댑터 없이 SDK 직접 호출)

공통 규칙
- 생성자 기본값은 timeout_s=30, max_retries=0. 재시도를 0 으로 통일해야 세 Provider 의 latency 비교가 왜곡되지 않는다
  (OpenAI/Anthropic SDK 기본 2회, Gemini SDK 는 retry_options 미지정 시 0회 — 문서와 다름).
- generate() 는 예외를 밖으로 던지지 않는다. 실패는 CallResult(status="error", error=ErrorInfo).
- 키가 없으면(mode == "NO_KEY") list_models() 는 [], health() 는 ok=False(AUTH), generate() 는 error AUTH 를 돌려준다.
- 응답 헤더는 filter_headers() 화이트리스트만 저장한다(Authorization 등 유출 방지).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from .. import PROVIDER_LABEL
from ..config import get_key
from ..errors import ErrorCategory, make_error
from ..models import (
    CallResult,
    CostEstimate,
    ErrorInfo,
    HealthResult,
    ModelInfo,
    NotSupported,
    UsageNormalized,
    UsageReport,
)
from .. import pricing

HEADER_WHITELIST_PREFIXES: tuple[str, ...] = (
    "x-ratelimit-",
    "anthropic-ratelimit-",
    "anthropic-priority-",
    "openai-processing-ms",
    "openai-version",
    "x-request-id",
    "request-id",
    "retry-after",
    "x-should-retry",
    "x-stainless-retry-count",
    "date",
    "content-type",
    "x-envoy-upstream-service-time",
    "server-timing",
)


class ProviderAdapter(ABC):
    name: str = ""  # openai | anthropic | gemini
    key_env: str = ""  # 예: OPENAI_API_KEY
    admin_key_env: str | None = None  # 예: OPENAI_ADMIN_KEY
    default_model: str = ""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        admin_key: str | None = None,
        timeout_s: float = 30.0,
        max_retries: int = 0,
        default_model: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else get_key(self.key_env)
        if admin_key is not None:
            self.admin_key = admin_key
        else:
            self.admin_key = get_key(self.admin_key_env) if self.admin_key_env else None
        self.timeout_s = timeout_s
        self.max_retries = max_retries
        if default_model:
            self.default_model = default_model

    # ---------------- 공통 유틸 ----------------
    @property
    def label(self) -> str:
        return PROVIDER_LABEL.get(self.name, self.name)

    @property
    def mode(self) -> str:
        return "LIVE" if self.api_key else "NO_KEY"

    def no_key_error(self) -> ErrorInfo:
        return make_error(
            category=ErrorCategory.AUTH,
            message=f"{self.key_env} 가 설정되지 않았습니다 (.env 확인). 키 없이 실행 → 이 항목은 [BLOCKED: no key].",
        )

    @staticmethod
    def now() -> float:
        return time.perf_counter()

    @staticmethod
    def elapsed_ms(t0: float) -> float:
        return round((time.perf_counter() - t0) * 1000.0, 1)

    @staticmethod
    def filter_headers(headers: Any) -> dict[str, str]:
        """화이트리스트 접두어에 맞는 헤더만 소문자 키로 돌려준다."""
        if not headers:
            return {}
        out: dict[str, str] = {}
        try:
            items = headers.items()
        except AttributeError:
            return {}
        for k, v in items:
            lk = str(k).lower()
            if lk.startswith(HEADER_WHITELIST_PREFIXES):
                out[lk] = str(v)
        return out

    def not_supported(self, item: str, reason: str, alternative: str = "") -> NotSupported:
        return NotSupported(self.name, item, reason, alternative)

    # ---------------- 조사 항목 ①~③, ⑥ (필수 구현) ----------------
    @abstractmethod
    def list_models(self) -> list[ModelInfo]:
        """① 사용 가능한 모델 목록. 키 없으면 []."""

    @abstractmethod
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
        """② 모델 호출. 절대 예외를 던지지 않는다. api 로 호출 경로 선택(예: OpenAI "responses"|"chat_completions")."""

    @abstractmethod
    def count_tokens(self, prompt: str, *, model: str | None = None) -> int | NotSupported:
        """③ 사전 토큰 카운트. 제공되지 않으면 NotSupported."""

    @abstractmethod
    def health(self) -> HealthResult:
        """⑥ 가장 저렴한 연결·인증 확인(토큰 과금 없는 호출)."""

    # ---------------- 조사 항목 ④, ⑤ (기본: 미지원) ----------------
    def usage_report(
        self,
        start: datetime,
        end: datetime,
        *,
        bucket: str = "1d",
        group_by: tuple[str, ...] = ("model",),
    ) -> UsageReport | NotSupported:
        return self.not_supported("usage_report", "이 어댑터는 기간별 Usage API 를 구현하지 않음", "usagelog.aggregate() 로 자체 집계")

    def cost_report(self, start: datetime, end: datetime) -> UsageReport | NotSupported:
        return self.not_supported("cost_report", "이 어댑터는 실비 조회 API 를 구현하지 않음", "cost() 로컬 계산")

    def cost(self, model: str, usage: UsageNormalized, *, service_tier: str | None = None) -> CostEstimate | NotSupported:
        """⑤ 호출 단위 예상 비용(로컬 계산). 단가는 pricing.PRICE_TABLE."""
        return pricing.estimate_cost(self.name, model, usage, service_tier=service_tier)
