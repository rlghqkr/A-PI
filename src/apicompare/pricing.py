"""단가표 + 비용 계산.

세 Provider 모두 단가를 API 로 노출하지 않는다 → 공식 pricing 페이지를 날짜(as_of)·출처와 함께 로컬 테이블로 관리한다.
가격 인상이 예고된 모델(Gemini 3.8 Flash 2027-01-01, Gemini 4 Argon 2026-12-01)은 scheduled_changes 에 적어 두고 note 로 경고한다.

비용 공식 (단위: USD / 1M tokens)
- OpenAI   : (input − cached − cache_write)×in + cached×cached_in + cache_write×in×cache_write_multiplier + output×out
             (reasoning 토큰은 output 에 이미 포함. GPT-5.6+ 는 캐시 쓰기 1.25배 — prompt caching 가이드 기준)
- Anthropic: base_input×in + cache_write×cache_write_5m + cached×cache_read + output×out
             (base_input = input − cached − cache_write = 응답의 input_tokens. Haiku 5.5 는 총 입력 >100K 면 2단 단가)
- Gemini   : (input − cached)×in + cached×cached_in + output×out  (output = candidates + thoughts, 캐시 읽기 ≈ 입력 단가의 10%)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import CostEstimate, NotSupported, UsageNormalized

OPENAI_PRICING = "https://developers.openai.com/api/docs/pricing"
ANTHROPIC_PRICING = "https://platform.claude.com/docs/en/about-claude/pricing"
GEMINI_PRICING = "https://ai.google.dev/gemini-api/docs/pricing"


@dataclass(frozen=True)
class Price:
    provider: str
    model: str
    input: float
    output: float
    cached_input: float | None = None  # 캐시 읽기 단가 (None 이면 Gemini 처럼 input×0.1 로 계산)
    cache_write_5m: float | None = None  # Anthropic 5분 캐시 쓰기 단가
    cache_write_multiplier: float = 1.0  # OpenAI: GPT-5.6+ 1.25, 그 외 1.0
    as_of: str = "2026-10-18"
    source: str = ""
    note: str = ""
    long_context: dict | None = None  # {"threshold": 100000, "input":…, "output":…, "cache_write_5m":…, "cached_input":…}
    scheduled_changes: list[dict] = field(default_factory=list)  # [{"effective_from": "2027-01-01", "input": 1.5, "output": 7.5}]


PRICE_TABLE: list[Price] = [
    # ---------------- OpenAI (input / cached / output) ----------------
    Price("openai", "gpt-5.4-mini", 0.75, 4.50, cached_input=0.075, source=OPENAI_PRICING, note="오늘 실습에 사용한 모델. 종료 미공지"),
    Price("openai", "gpt-5.4", 2.50, 15.00, cached_input=0.25, source=OPENAI_PRICING, note="272K 초과 long-context 구간은 별도 단가(input $5.00)"),
    Price("openai", "gpt-5.4-nano", 0.20, 1.25, cached_input=0.02, source=OPENAI_PRICING, note="2027-04-01 종료 예정"),
    Price("openai", "gpt-6-luna", 0.10, 0.50, cached_input=0.01, cache_write_multiplier=1.25, source=OPENAI_PRICING, note="현행 최저가 모델"),
    Price("openai", "gpt-6.1-sol", 2.00, 10.00, cached_input=0.10, cache_write_multiplier=1.25, source=OPENAI_PRICING),
    Price("openai", "gpt-6-astra", 10.00, 50.00, cached_input=1.00, cache_write_multiplier=1.25, source=OPENAI_PRICING),
    Price("openai", "gpt-5.6-sol", 4.00, 20.00, cached_input=0.40, cache_write_multiplier=1.25, source=OPENAI_PRICING),
    Price("openai", "gpt-5.6-terra", 2.00, 12.00, cached_input=0.20, cache_write_multiplier=1.25, source=OPENAI_PRICING),
    Price("openai", "gpt-5.6-luna", 0.20, 1.20, cached_input=0.02, cache_write_multiplier=1.25, source=OPENAI_PRICING),
    Price("openai", "gpt-4.1", 2.00, 8.00, cached_input=0.50, source=OPENAI_PRICING, note="2027-01-14 종료 예정"),
    Price("openai", "gpt-4o-mini", 0.15, 0.60, cached_input=0.075, source=OPENAI_PRICING, note="2027-01-14 종료 예정"),
    Price("openai", "gpt-5-mini", 0.25, 2.00, cached_input=0.025, source=OPENAI_PRICING, note="2026-12-11 종료 예정 — PoC 기간상 비권장"),
    Price("openai", "gpt-5-nano", 0.05, 0.40, cached_input=0.005, source=OPENAI_PRICING, note="2026-12-11 종료 예정 — PoC 기간상 비권장"),
    # ---------------- Anthropic (input / output / 5m cache write / cache read) ----------------
    Price("anthropic", "claude-opus-5-5", 4.00, 20.00, cached_input=0.20, cache_write_5m=5.00, source=ANTHROPIC_PRICING),
    Price("anthropic", "claude-sonnet-5-5", 2.00, 10.00, cached_input=0.10, cache_write_5m=2.50, source=ANTHROPIC_PRICING),
    Price(
        "anthropic", "claude-haiku-5-5", 0.10, 0.50, cached_input=0.01, cache_write_5m=0.125, source=ANTHROPIC_PRICING,
        note="프롬프트(캐시 포함 총 입력) 100K 초과 시 2단 단가",
        long_context={"threshold": 100_000, "input": 0.50, "output": 2.50, "cache_write_5m": 0.625, "cached_input": 0.05},
    ),
    Price("anthropic", "claude-fable-5-1", 10.00, 50.00, cached_input=0.25, cache_write_5m=12.50, source=ANTHROPIC_PRICING),
    Price("anthropic", "claude-opus-5", 5.00, 25.00, cached_input=0.50, cache_write_5m=6.25, source=ANTHROPIC_PRICING),
    Price("anthropic", "claude-sonnet-5", 2.00, 10.00, cached_input=0.20, cache_write_5m=2.50, source=ANTHROPIC_PRICING),
    Price("anthropic", "claude-haiku-4-5", 1.00, 5.00, cached_input=0.10, cache_write_5m=1.25, source=ANTHROPIC_PRICING),
    # ---------------- Gemini (input / output incl. thinking) ----------------
    Price(
        "gemini", "gemini-3.8-flash", 0.75, 3.75, as_of="2026-10-16", source=GEMINI_PRICING, note="Free tier 제공. 2027-01-01 부터 $1.50/$7.50",
        scheduled_changes=[{"effective_from": "2027-01-01", "input": 1.50, "output": 7.50}],
    ),
    Price(
        "gemini", "gemini-3.6-flash", 0.75, 3.75, as_of="2026-10-16", source=GEMINI_PRICING, note="2027-01-01 부터 $1.50/$7.50",
        scheduled_changes=[{"effective_from": "2027-01-01", "input": 1.50, "output": 7.50}],
    ),
    Price("gemini", "gemini-3.5-flash-lite", 0.30, 2.50, as_of="2026-10-16", source=GEMINI_PRICING),
    Price("gemini", "gemini-3.1-flash-lite", 0.25, 1.50, as_of="2026-10-16", source=GEMINI_PRICING),
    Price("gemini", "gemini-3-flash-preview", 0.50, 3.00, as_of="2026-10-16", source=GEMINI_PRICING),
    Price("gemini", "gemini-3.1-pro-preview", 2.00, 12.00, as_of="2026-10-16", source=GEMINI_PRICING, note="프롬프트 ≤200K 기준"),
    Price(
        "gemini", "gemini-4-argon", 2.00, 10.00, as_of="2026-10-16", source=GEMINI_PRICING, note="Free tier 없음. 2026-12-01 부터 $4/$20",
        scheduled_changes=[{"effective_from": "2026-12-01", "input": 4.00, "output": 20.00}],
    ),
    Price("gemini", "gemini-2.5-flash", 0.30, 2.50, as_of="2026-10-16", source=GEMINI_PRICING, note="2.5 세대는 신규 사용자 접근 제한"),
    Price("gemini", "gemini-2.5-flash-lite", 0.10, 0.40, as_of="2026-10-16", source=GEMINI_PRICING, note="2.5 세대는 신규 사용자 접근 제한"),
    Price("gemini", "gemini-2.5-pro", 1.25, 10.00, as_of="2026-10-16", source=GEMINI_PRICING, note="프롬프트 ≤200K 기준 (>200K $2.50/$15.00)"),
]


def get_price(provider: str, model: str) -> Price | None:
    """정확히 일치하는 모델 → 없으면 접두 일치(날짜 스냅샷 id 대응, 예: gpt-5.4-mini-2026-03-17)."""
    exact = [p for p in PRICE_TABLE if p.provider == provider and p.model == model]
    if exact:
        return exact[0]
    candidates = [p for p in PRICE_TABLE if p.provider == provider and model.startswith(p.model)]
    if candidates:
        return max(candidates, key=lambda p: len(p.model))
    return None


def estimate_cost(
    provider: str,
    model: str,
    usage: UsageNormalized,
    *,
    service_tier: str | None = None,
) -> CostEstimate | NotSupported:
    price = get_price(provider, model)
    if price is None:
        return NotSupported(provider, "cost", f"단가표에 없는 모델: {model}", f"{provider} 공식 pricing 페이지에서 확인 후 pricing.PRICE_TABLE 에 추가")

    cached = max(usage.cached_input_tokens, 0)
    cache_write = max(usage.cache_write_tokens, 0)
    total_input = max(usage.input_tokens, 0)
    output = max(usage.output_tokens, 0)
    m = 1_000_000
    breakdown: dict[str, float] = {}
    note_parts: list[str] = []

    if provider == "openai":
        uncached = max(total_input - cached - cache_write, 0)
        breakdown["input"] = uncached * price.input / m
        breakdown["cached_input"] = cached * (price.cached_input if price.cached_input is not None else price.input * 0.1) / m
        breakdown["cache_write"] = cache_write * price.input * price.cache_write_multiplier / m
        breakdown["output"] = output * price.output / m
        if usage.reasoning_tokens:
            note_parts.append(f"output 에 reasoning {usage.reasoning_tokens} 토큰 포함(output 단가)")
    elif provider == "anthropic":
        p_in, p_out = price.input, price.output
        p_cw = price.cache_write_5m if price.cache_write_5m is not None else price.input * 1.25
        p_cr = price.cached_input if price.cached_input is not None else price.input * 0.1
        if price.long_context and total_input > price.long_context["threshold"]:
            lc = price.long_context
            p_in, p_out, p_cw, p_cr = lc["input"], lc["output"], lc["cache_write_5m"], lc["cached_input"]
            note_parts.append(f"총 입력 {total_input} > {lc['threshold']} → 2단 단가 적용")
        base_input = max(total_input - cached - cache_write, 0)
        breakdown["input"] = base_input * p_in / m
        breakdown["cache_write"] = cache_write * p_cw / m
        breakdown["cached_input"] = cached * p_cr / m
        breakdown["output"] = output * p_out / m
        if usage.reasoning_tokens:
            note_parts.append(f"output 에 thinking {usage.reasoning_tokens} 토큰 포함(output 단가)")
    elif provider == "gemini":
        uncached = max(total_input - cached, 0)
        breakdown["input"] = uncached * price.input / m
        breakdown["cached_input"] = cached * (price.cached_input if price.cached_input is not None else price.input * 0.1) / m
        breakdown["output"] = output * price.output / m
        if usage.reasoning_tokens:
            note_parts.append(f"output 에 thoughts {usage.reasoning_tokens} 토큰 포함(output 단가)")
    else:
        return NotSupported(provider, "cost", f"알 수 없는 provider: {provider}")

    if service_tier and service_tier not in ("standard", "default", "auto", None):
        note_parts.append(f"service_tier={service_tier}: 표준 단가로 계산함(Flex/Batch 50%, Priority/Fast 배수는 미반영)")
    if price.scheduled_changes:
        ch = price.scheduled_changes[0]
        note_parts.append(f"{ch['effective_from']} 부터 ${ch['input']}/${ch['output']} 로 변경 예고")
    if price.note:
        note_parts.append(price.note)

    return CostEstimate(
        usd=round(sum(breakdown.values()), 8),
        breakdown={k: round(v, 8) for k, v in breakdown.items()},
        price_as_of=price.as_of,
        price_source=price.source,
        model=price.model,
        effective_from=price.scheduled_changes[0]["effective_from"] if price.scheduled_changes else None,
        note="; ".join(note_parts),
    )
