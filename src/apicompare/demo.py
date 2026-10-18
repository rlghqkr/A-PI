"""Jupyter 없이 7개 조사 항목을 순서대로 실행하고 evidence 를 남기는 CLI.

    uv run python -m apicompare.demo openai                 # 7항목 전부 (②③⑤⑦ 은 유료 호출 1~2회)
    uv run python -m apicompare.demo gemini --items 1,6     # 무료 항목만
    uv run python -m apicompare.demo anthropic --no-paid    # 유료 호출 제외(①④⑥)

유료 호출은 max_output_tokens(기본 64) 로 제한하며, 호출 전에 예상 최대 비용을 출력한다.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone

from . import ITEMS, PROVIDERS
from .config import keys
from .errors import ErrorCategory, make_error
from .evidence import save_evidence, summary
from .models import NotSupported, to_dict
from .providers import get_adapter
from . import usagelog

PAID_ITEMS = {2, 3, 5, 7}
DEFAULT_PROMPT = "대한민국의 수도를 한 문장으로 알려줘."


def _print(title: str, obj) -> None:
    print(f"\n=== {title} ===")
    if isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(to_dict(obj), ensure_ascii=False, indent=2, default=str)[:3000])


def run(provider: str, items: set[int], *, model: str | None, prompt: str, max_output_tokens: int) -> None:
    adapter = get_adapter(provider, default_model=model) if model else get_adapter(provider)
    model = model or adapter.default_model
    print(f"[{provider}] mode={adapter.mode} model={model} keys={keys()}")
    blocked_note = "no key" if adapter.mode == "NO_KEY" else ""
    result = None

    if 1 in items:
        models = adapter.list_models()
        payload = {"count": len(models), "models": [to_dict(m) for m in models[:60]]}
        src = "live" if models else "blocked"
        save_evidence(provider, "01_models", payload, src, note=blocked_note if not models else "", model=model)
        _print("① 모델 목록 조회", {"count": len(models), "first": [m.id for m in models[:10]]})

    if 2 in items or 3 in items or 7 in items:
        if adapter.mode == "NO_KEY":
            for key in ("02_call", "03_usage", "07_example"):
                n = int(key[:2])
                if n in items:
                    save_evidence(provider, key, {"error": to_dict(adapter.no_key_error())}, "blocked", note="no key", model=model)
            _print("②③⑦", "키가 없어 BLOCKED 로 기록")
        else:
            result = adapter.generate(prompt, model=model, max_output_tokens=max_output_tokens)
            ok = result.status == "ok"
            if 2 in items:
                save_evidence(provider, "02_call", result, "live" if ok else "blocked", note="" if ok else (result.error.category if result.error else "error"), model=model)
                _print("② 모델 호출", {"status": result.status, "text": result.text, "latency_ms": result.latency_ms, "finish_reason": result.finish_reason, "error": to_dict(result.error)})
            if 3 in items:
                pre = adapter.count_tokens(prompt, model=model)
                payload = {"usage": to_dict(result.usage), "count_tokens_pre_call": to_dict(pre), "raw_usage": result.usage.raw if result.usage else None}
                save_evidence(provider, "03_usage", payload, "live" if ok and result.usage else "blocked", note="" if ok else "call failed", model=model)
                _print("③ Token Usage", payload)
            if 7 in items:
                save_evidence(provider, "07_example", {"call": to_dict(result), "note": "노트북 §7 의 SDK 직접 호출 예제와 동일 요청"}, "live" if ok else "blocked", model=model)

    if 4 in items:
        now = datetime.now(timezone.utc)
        rep = adapter.usage_report(now - timedelta(days=7), now)
        if isinstance(rep, NotSupported):
            # 배지는 짧게: 키 없음 → "no key", Admin 키 개념이 있는데 없음 → "no admin key", API 자체가 없음 → "no api"
            note = blocked_note or ("no admin key" if adapter.admin_key_env else "no api")
            save_evidence(provider, "04_usage_api", to_dict(rep), "blocked", note=note, model=model)
        else:
            save_evidence(provider, "04_usage_api", to_dict(rep), "live", model=model)
        local = usagelog.aggregate(now - timedelta(days=7), now)
        _print("④ Usage 조회", {"admin_api": to_dict(rep), "usagelog(자체 집계)": to_dict(local)})

    if 5 in items:
        if result is not None and result.usage is not None:
            cost = adapter.cost(model, result.usage)
            usagelog.append(result, cost if not isinstance(cost, NotSupported) else None, run_id="demo")
            now = datetime.now(timezone.utc)
            crep = adapter.cost_report(now - timedelta(days=7), now)
            payload = {"local_estimate": to_dict(cost), "cost_report": to_dict(crep)}
            save_evidence(provider, "05_costs", payload, "live" if not isinstance(cost, NotSupported) else "blocked", model=model)
            _print("⑤ 비용 확인", payload)
        else:
            save_evidence(provider, "05_costs", {"note": "②가 실행되지 않아 계산할 usage 가 없음"}, "blocked", note=blocked_note or "no call", model=model)

    if 6 in items:
        h = adapter.health()
        errors = {}
        if adapter.mode == "LIVE":
            bad = get_adapter(provider, api_key="INVALID-KEY-FOR-TEST", timeout_s=adapter.timeout_s)
            # OpenAI Responses 는 max_output_tokens 최소 16 (8 이면 모델 조회 전에 400 integer_below_min_value 가 나서 404 를 못 본다)
            errors["bad_key"] = to_dict(bad.generate("ping", model=model, max_output_tokens=16).error)
            errors["bad_model"] = to_dict(adapter.generate("ping", model="model-does-not-exist-123", max_output_tokens=16).error)
            quick = get_adapter(provider, timeout_s=0.001)
            errors["timeout"] = to_dict(quick.generate("ping", model=model, max_output_tokens=16).error)
        else:
            errors["note"] = "키가 없어 의도적 오류 재현은 생략"
        payload = {"health": to_dict(h), "intentional_errors": errors}
        save_evidence(provider, "06_errors", payload, "live" if h.ok else "blocked", note="" if h.ok else (blocked_note or (h.error.category if h.error else "health failed")), model=model)
        _print("⑥ 상태 및 오류 확인", payload)

    _print("evidence 요약", summary(provider))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("provider", choices=PROVIDERS)
    ap.add_argument("--items", default="1,2,3,4,5,6,7", help="실행할 항목 번호(쉼표 구분)")
    ap.add_argument("--no-paid", action="store_true", help="유료 호출 항목(②③⑤⑦) 제외")
    ap.add_argument("--model", default=None)
    ap.add_argument("--prompt", default=DEFAULT_PROMPT)
    ap.add_argument("--max-output-tokens", type=int, default=64)
    args = ap.parse_args(argv)

    items = {int(x) for x in args.items.split(",") if x.strip()}
    if args.no_paid:
        items -= PAID_ITEMS
    bad = items - {n for n in range(1, 8)}
    if bad:
        raise SystemExit(f"잘못된 항목 번호: {sorted(bad)} (1~7)")
    if items & PAID_ITEMS:
        print(f"주의: 항목 {sorted(items & PAID_ITEMS)} 은 유료 호출을 포함합니다 (max_output_tokens={args.max_output_tokens}, 호출 1~2회, 보통 $0.001 미만).")
    run(args.provider, items, model=args.model, prompt=args.prompt, max_output_tokens=args.max_output_tokens)


if __name__ == "__main__":
    main()
