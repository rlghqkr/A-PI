"""실측 증거 저장. 노트북 각 섹션의 마지막 셀이 save_evidence() 를 호출한다.

- evidence/<provider>/<item>.json 하나가 매트릭스 셀 하나의 근거다.
- source: live(실측) | observed(관찰했지만 재현 안 함) | docs(공식 문서 예시) | blocked(키·권한 없음)
- 저장 전에 민감 헤더를 마스킹하고 문자열을 redact() 한다. 실제 키 값이 그대로 들어 있으면 저장을 거부한다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ITEM_BY_EVIDENCE, PROVIDERS
from .config import ROOT, known_secret_values
from .errors import redact
from .models import to_dict

EVIDENCE_DIR = ROOT / "evidence"
RANK = {"live": 3, "observed": 2, "docs": 1, "blocked": 0}
SENSITIVE_HEADER_KEYS = {
    "authorization",
    "x-api-key",
    "x-goog-api-key",
    "openai-organization",
    "openai-project",
    "anthropic-organization-id",
    "anthropic-workspace-id",
    "cookie",
    "set-cookie",
}


def _scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if str(k).lower() in SENSITIVE_HEADER_KEYS:
                out[k] = "***"
            else:
                out[k] = _scrub(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str):
        return redact(obj)
    return obj


def save_evidence(
    provider: str,
    item: str,
    payload: Any,
    source: str,
    *,
    note: str = "",
    model: str | None = None,
    base_dir: Path | None = None,
) -> Path:
    if provider not in PROVIDERS:
        raise ValueError(f"provider 는 {PROVIDERS} 중 하나: {provider}")
    if item not in ITEM_BY_EVIDENCE:
        raise ValueError(f"item 은 {list(ITEM_BY_EVIDENCE)} 중 하나: {item}")
    if source not in RANK:
        raise ValueError(f"source 는 {list(RANK)} 중 하나: {source}")

    doc = {
        "provider": provider,
        "item": item,
        "item_ko": ITEM_BY_EVIDENCE[item][1],
        "source": source,
        "note": note,
        "model": model,
        "saved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "payload": _scrub(to_dict(payload)),
    }
    text = json.dumps(doc, ensure_ascii=False, indent=2, default=str)
    for secret in known_secret_values():
        if secret and secret in text:
            raise ValueError("실제 API 키 값이 evidence 에 포함되어 저장을 거부합니다. 출력에서 키를 제거하세요.")

    path = (base_dir or EVIDENCE_DIR) / provider / f"{item}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def load_evidence(provider: str, base_dir: Path | None = None) -> dict[str, dict]:
    d = (base_dir or EVIDENCE_DIR) / provider
    if not d.exists():
        return {}
    out = {}
    for p in sorted(d.glob("*.json")):
        if p.name.startswith("raw_"):
            continue
        try:
            out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
    return out


def badge(provider: str, item: str, base_dir: Path | None = None) -> str:
    """문서용 배지 문자열. evidence 파일이 없으면 [BLOCKED: no evidence]."""
    doc = load_evidence(provider, base_dir).get(item)
    if not doc:
        return "[BLOCKED: no evidence]"
    src = doc.get("source", "blocked")
    if src == "blocked":
        return f"[BLOCKED: {doc.get('note') or 'unknown'}]"
    return f"[{src.upper()}]"


def summary(provider: str, base_dir: Path | None = None) -> list[dict]:
    docs = load_evidence(provider, base_dir)
    return [
        {"item": e, "item_ko": k, "badge": badge(provider, e, base_dir), "saved_at": docs.get(e, {}).get("saved_at")}
        for e, (_, k) in ITEM_BY_EVIDENCE.items()
    ]
