"""호출별 usage 자체 적재 + 기간별 집계.

조사 결론: 기간별 Usage/비용을 3사 공통으로 뽑는 API 는 없다(OpenAI·Anthropic 은 Admin 키, Gemini 는 API 없음).
→ Multi-LLM Simulator 는 호출마다 응답 usage 를 자체 저장해 집계해야 한다. 이 모듈이 그 최소 구현이다(PoC 에서는 SQLite 테이블로 옮긴다).
저장하는 것: 토큰·비용·latency·오류 분류. 저장하지 않는 것: 프롬프트 원문, 응답 원문, 키.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .config import ROOT
from .models import CallResult, CostEstimate, UsageBucket, UsageReport

LOG_PATH = ROOT / "data" / "usage_log.jsonl"


def append(
    result: CallResult,
    cost: CostEstimate | None = None,
    *,
    run_id: str = "",
    key_owner: str = "personal",  # personal | company — 키 값·접두어는 절대 기록하지 않는다
    path: Path | None = None,
) -> Path:
    path = path or LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    u = result.usage
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "key_owner": key_owner,
        "provider": result.provider,
        "model": result.model,
        "api": result.api,
        "status": result.status,
        "latency_ms": round(result.latency_ms, 1),
        "input_tokens": u.input_tokens if u else None,
        "cached_input_tokens": u.cached_input_tokens if u else None,
        "output_tokens": u.output_tokens if u else None,
        "reasoning_tokens": u.reasoning_tokens if u else None,
        "total_tokens": u.total_tokens if u else None,
        "cost_usd": cost.usd if cost else None,
        "request_id": result.request_id,
        "error_category": result.error.category if result.error else None,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def load(path: Path | None = None) -> list[dict]:
    path = path or LOG_PATH
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def aggregate(
    start: datetime | None = None,
    end: datetime | None = None,
    *,
    group_by: tuple[str, ...] = ("provider", "model"),
    path: Path | None = None,
) -> UsageReport:
    """기간 [start, end) 의 로그를 group_by 기준으로 합산한다. 시각은 UTC ISO 문자열로 비교한다."""
    rows = load(path)
    s = start.astimezone(timezone.utc).isoformat() if start else None
    e = end.astimezone(timezone.utc).isoformat() if end else None
    rows = [r for r in rows if (s is None or r["ts"] >= s) and (e is None or r["ts"] < e)]

    groups: dict[tuple, dict] = defaultdict(lambda: {"input": 0, "output": 0, "requests": 0, "cost": 0.0, "has_cost": False})
    for r in rows:
        key = tuple(str(r.get(g)) for g in group_by)
        g = groups[key]
        g["input"] += r.get("input_tokens") or 0
        g["output"] += r.get("output_tokens") or 0
        g["requests"] += 1
        if r.get("cost_usd") is not None:
            g["cost"] += r["cost_usd"]
            g["has_cost"] = True

    buckets = [
        UsageBucket(
            start=s or (rows[0]["ts"] if rows else ""),
            end=e or (rows[-1]["ts"] if rows else ""),
            group=dict(zip(group_by, key)),
            input_tokens=g["input"],
            output_tokens=g["output"],
            requests=g["requests"],
            cost_usd=round(g["cost"], 8) if g["has_cost"] else None,
        )
        for key, g in sorted(groups.items())
    ]
    return UsageReport(
        provider=",".join(sorted({r["provider"] for r in rows})) or "none",
        source="usagelog",
        buckets=buckets,
        note=f"{len(rows)} calls from {path or LOG_PATH}",
    )
