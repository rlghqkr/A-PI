#!/usr/bin/env python
"""matrix/*.yaml 을 author 별로 모아 셀 단위로 머지 → matrix/_merged.yaml + docs/COMPARISON.md 생성.

    uv run python scripts/build_comparison.py [--matrix-dir matrix] [--out docs/COMPARISON.md] [--merged matrix/_merged.yaml]

입력 규칙
  - matrix/*.yaml 중 _template.yaml, _merged.yaml, _parts/ 는 제외한다.
  - 작성자 파일이 0개면 matrix/_parts/*.yaml 을 대신 사용한다(에이전트/Provider별 부분 파일).
  - 깨진 파일은 경고만 내고 건너뛴다. 스키마 검증은 scripts/validate_matrix.py 가 담당한다.

머지 규칙 (셀 = provider × item)
  1. evidence 우선순위 live > observed > docs > blocked. evidence/<provider>/<key>.json 의 source 도 같은 순위로 비교해 더 높은 쪽을 배지로 쓴다.
  2. 같은 등급이면 confidence 가 높은 엔트리를 대표(primary)로 삼는다.
  3. availability 가 다르면 보수적인 값(api > partial > dashboard_only > none 순서에서 더 뒤)을 채택하고,
     반대 의견은 caveats 에 "(@author: <값> — <첫 source>)" 로 보존한다. unknown 은 의견 없음으로 취급한다.
  4. endpoint 가 다르면 둘 다 나열한다. response_fields / common_fields / sources 는 합집합.

docs/COMPARISON.md 는 생성물이다. 손으로 고치지 말고 matrix/<author>.yaml 을 고친 뒤 다시 실행한다.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from apicompare import ITEM_BY_YAML, ITEMS, PROVIDER_LABEL, PROVIDERS  # noqa: E402
from apicompare import evidence as evidence_mod  # noqa: E402
from apicompare.models import UsageNormalized  # noqa: E402

EVIDENCE_RANK = {"live": 3, "observed": 2, "docs": 1, "blocked": 0}
AVAIL_ORDER = ["api", "partial", "dashboard_only", "none"]  # 뒤쪽이 더 보수적
AVAIL_ICON = {"api": "✅", "partial": "⚠️", "dashboard_only": "🖥️", "none": "❌", "unknown": "❓"}
NOTEBOOK_OF = {"openai": "10_openai", "anthropic": "20_anthropic", "gemini": "30_gemini"}
EXCLUDED_FILES = {"_template.yaml", "_merged.yaml"}
ITEM_INDEX = {y: i + 1 for i, (_, y, _) in enumerate(ITEMS)}  # yaml 키 → 1..7

# ③ Token Usage 공통 스키마 — models.py 의 UsageNormalized docstring 을 표로 옮긴 정적 정보
USAGE_FORMULAS: dict[str, dict[str, str]] = {
    "input_tokens": {
        "설명": "캐시 읽기/쓰기까지 포함한 총 입력(과금 관점)",
        "openai": "usage.input_tokens (Responses) / prompt_tokens (Chat) — cached 포함",
        "anthropic": "input_tokens + cache_creation_input_tokens + cache_read_input_tokens",
        "gemini": "promptTokenCount(캐시 포함) + toolUsePromptTokenCount",
    },
    "output_tokens": {
        "설명": "reasoning/thinking 을 포함한 총 출력(3사 모두 output 단가)",
        "openai": "usage.output_tokens (reasoning 포함)",
        "anthropic": "usage.output_tokens (thinking 포함)",
        "gemini": "candidatesTokenCount + thoughtsTokenCount",
    },
    "total_tokens": {
        "설명": "input_tokens + output_tokens",
        "openai": "usage.total_tokens (응답 제공)",
        "anthropic": "응답에 없음 → 계산 (total_is_computed=True)",
        "gemini": "usageMetadata.totalTokenCount (응답 제공)",
    },
    "cached_input_tokens": {
        "설명": "input_tokens 에 포함된 캐시 읽기",
        "openai": "input_tokens_details.cached_tokens",
        "anthropic": "cache_read_input_tokens",
        "gemini": "cachedContentTokenCount",
    },
    "cache_write_tokens": {
        "설명": "input_tokens 에 포함된 캐시 쓰기",
        "openai": "input_tokens_details.cache_write_tokens (GPT-5.6+ 1.25배 과금)",
        "anthropic": "cache_creation_input_tokens (5m 1.25배 / 1h 2배)",
        "gemini": "없음 (0)",
    },
    "reasoning_tokens": {
        "설명": "output_tokens 에 포함된 추론 토큰 (더하지 말 것)",
        "openai": "output_tokens_details.reasoning_tokens",
        "anthropic": "output_tokens_details.thinking_tokens",
        "gemini": "thoughtsTokenCount",
    },
    "total_is_computed": {
        "설명": "total 을 로컬에서 계산했는지",
        "openai": "False",
        "anthropic": "True",
        "gemini": "False",
    },
    "raw": {
        "설명": "Provider 원본 usage 필드(dict)",
        "openai": "usage.model_dump()",
        "anthropic": "usage.model_dump()",
        "gemini": "usage_metadata.model_dump()",
    },
}


# --------------------------------------------------------------------------- 입력
def discover_matrix_files(matrix_dir: Path) -> tuple[list[Path], str]:
    """작성자 파일 목록과 출처('authors'|'parts'|'none')."""
    files = sorted(p for p in matrix_dir.glob("*.yaml") if p.name not in EXCLUDED_FILES and not p.name.startswith("_merged"))
    if files:
        return files, "authors"
    parts = sorted((matrix_dir / "_parts").glob("*.yaml")) if (matrix_dir / "_parts").exists() else []
    if parts:
        return parts, "parts"
    return [], "none"


def load_matrix_files(paths: list[Path]) -> tuple[dict[str, list[dict]], list[str]]:
    """author → entries 목록. 깨진 파일은 warnings 에 적고 건너뛴다. 같은 author 가 여러 파일에 있으면 합친다."""
    by_author: dict[str, list[dict]] = {}
    warnings: list[str] = []
    for p in paths:
        try:
            doc = yaml.safe_load(p.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError) as exc:
            warnings.append(f"{p}: 읽기 실패 — {exc}")
            continue
        if not isinstance(doc, dict) or not isinstance(doc.get("entries"), list):
            warnings.append(f"{p}: author/entries 구조가 아니어서 건너뜀")
            continue
        author = str(doc.get("author") or p.stem).strip() or p.stem
        if author == "<slack_handle>":
            author = p.stem
        for i, e in enumerate(doc["entries"]):
            if not isinstance(e, dict) or e.get("provider") not in PROVIDERS or e.get("item") not in ITEM_BY_YAML:
                warnings.append(f"{p}: entries[{i}] provider/item 이 유효하지 않아 건너뜀")
                continue
            entry = dict(e)
            entry["_author"] = author
            entry["_file"] = str(p)
            entry["_as_of"] = str(doc.get("as_of", ""))
            by_author.setdefault(author, []).append(entry)
    return by_author, warnings


# --------------------------------------------------------------------------- 머지
def _s(v: Any) -> str:
    return str(v).strip() if v is not None else ""


def _uniq(seq) -> list:
    out: list = []
    for x in seq:
        if x not in out and x not in ("", None):
            out.append(x)
    return out


def _avail_rank(v: str) -> int:
    return AVAIL_ORDER.index(v) if v in AVAIL_ORDER else -1


def evidence_file_source(provider: str, yaml_item: str, evidence_dir: Path | None) -> tuple[str | None, str]:
    """evidence/<provider>/<key>.json 의 (source, note). 없으면 (None, '')."""
    key = ITEM_BY_YAML[yaml_item][0]
    doc = evidence_mod.load_evidence(provider, evidence_dir).get(key)
    if not doc:
        return None, ""
    return doc.get("source"), _s(doc.get("note"))


def merge_cell(entries: list[dict], *, evidence_dir: Path | None = None) -> tuple[dict, list[dict]]:
    """같은 (provider,item) 의 엔트리들을 하나로. (merged_entry, conflicts)"""
    provider, item = entries[0]["provider"], entries[0]["item"]
    conflicts: list[dict] = []

    ranked = sorted(
        entries,
        key=lambda e: (EVIDENCE_RANK.get(_s(e.get("evidence")), -1), float(e.get("confidence") or 0)),
        reverse=True,
    )
    primary = ranked[0]
    authors = _uniq(e["_author"] for e in entries)

    # evidence 배지: YAML 최고 등급 vs evidence 파일 source
    yaml_ev = _s(primary.get("evidence")) or "docs"
    file_src, file_note = evidence_file_source(provider, item, evidence_dir)
    badge_src = yaml_ev
    if file_src in EVIDENCE_RANK and EVIDENCE_RANK[file_src] > EVIDENCE_RANK.get(yaml_ev, -1):
        badge_src = file_src
    blocked_reason = _s(primary.get("blocked_reason")) or next((_s(e.get("blocked_reason")) for e in ranked if _s(e.get("blocked_reason"))), "")
    if badge_src == "blocked" and not blocked_reason:
        blocked_reason = file_note or "unknown"

    # availability: 보수적 값 채택, 반대 의견 보존
    opinions = [(e["_author"], _s(e.get("availability")), e) for e in ranked if _s(e.get("availability")) in AVAIL_ORDER]
    dissent_notes: list[str] = []
    if opinions:
        chosen = max(opinions, key=lambda t: _avail_rank(t[1]))[1]
        values = _uniq(v for _, v, _ in opinions)
        if len(values) > 1:
            conflicts.append(
                {
                    "provider": provider,
                    "item": item,
                    "field": "availability",
                    "values": {a: v for a, v, _ in opinions},
                    "chosen": chosen,
                    "rule": "보수적 값 채택",
                }
            )
            for a, v, e in opinions:
                if v != chosen:
                    srcs = e.get("sources") or []
                    first_src = _s(srcs[0]) if srcs else "출처 없음"
                    dissent_notes.append(f"(@{a}: {v} — {first_src})")
    else:
        chosen = _s(primary.get("availability")) or "unknown"

    # endpoint: 다르면 둘 다
    endpoints = _uniq(_s(e.get("endpoint")) for e in ranked)
    if len(endpoints) > 1:
        conflicts.append(
            {
                "provider": provider,
                "item": item,
                "field": "endpoint",
                "values": {e["_author"]: _s(e.get("endpoint")) for e in ranked if _s(e.get("endpoint"))},
                "chosen": " | ".join(endpoints),
                "rule": "모두 나열",
            }
        )

    auths = _uniq(_s(e.get("auth")) for e in ranked if _s(e.get("auth")) not in ("", "unknown"))
    auth = auths[0] if auths else (_s(primary.get("auth")) or "unknown")
    if len(auths) > 1:
        dissent_notes.append("auth 의견 상이: " + ", ".join(f"@{e['_author']}={_s(e.get('auth'))}" for e in ranked if _s(e.get("auth"))))

    caveats = _uniq(_s(e.get("caveats")) for e in ranked) + dissent_notes
    merged = {
        "provider": provider,
        "item": item,
        "item_ko": ITEM_BY_YAML[item][1],
        "evidence_key": ITEM_BY_YAML[item][0],
        "availability": chosen,
        "endpoint": " | ".join(endpoints) if endpoints else "",
        "auth": auth,
        "sdk_call": next((_s(e.get("sdk_call")) for e in ranked if _s(e.get("sdk_call"))), ""),
        "response_fields": _uniq(f for e in ranked for f in (e.get("response_fields") or [])),
        "common_fields": _uniq(f for e in ranked for f in (e.get("common_fields") or [])),
        "caveats": " / ".join(caveats),
        "evidence": badge_src,
        "evidence_yaml": yaml_ev,
        "evidence_file": file_src,
        "blocked_reason": blocked_reason if badge_src == "blocked" else _s(primary.get("blocked_reason")),
        "sources": _uniq(_s(s) for e in ranked for s in (e.get("sources") or [])),
        "confidence": primary.get("confidence"),
        "authors": authors,
        "primary_author": primary["_author"],
        "conflicts": [c["field"] for c in conflicts],
    }
    return merged, conflicts


def merge_all(by_author: dict[str, list[dict]], *, evidence_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    cells: dict[tuple[str, str], list[dict]] = {}
    for entries in by_author.values():
        for e in entries:
            cells.setdefault((e["provider"], e["item"]), []).append(e)
    merged: list[dict] = []
    conflicts: list[dict] = []
    for provider in PROVIDERS:
        for _, yaml_item, _ in ITEMS:
            group = cells.get((provider, yaml_item))
            if not group:
                continue
            m, c = merge_cell(group, evidence_dir=evidence_dir)
            merged.append(m)
            conflicts.extend(c)
    return merged, conflicts


def badge_text(cell: dict | None) -> str:
    if cell is None:
        return "[BLOCKED: 미작성]"
    src = cell.get("evidence") or "docs"
    if src == "blocked":
        return f"[BLOCKED: {cell.get('blocked_reason') or 'unknown'}]"
    return f"[{src.upper()}]"


# --------------------------------------------------------------------------- 외부 문서
def read_md_section(path: Path, heading_prefix: str) -> str | None:
    """'## 8.' 로 시작하는 섹션 본문(다음 '## ' 전까지). 파일/섹션이 없으면 None."""
    if not path.exists():
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            if line.startswith(heading_prefix):
                inside = True
                continue
        elif inside:
            out.append(line)
    if not inside:
        return None
    text = "\n".join(out).strip()
    return text or "(비어 있음)"


# --------------------------------------------------------------------------- 렌더링
def _esc(s: str) -> str:
    return _s(s).replace("|", "/").replace("\n", " ")


def _short(s: str, n: int = 70) -> str:
    s = _esc(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def render_markdown(
    merged: list[dict],
    conflicts: list[dict],
    *,
    authors: list[str],
    source_kind: str,
    files: list[Path],
    warnings: list[str],
    evidence_dir: Path | None = None,
    providers_docs_dir: Path | None = None,
    now: datetime | None = None,
) -> str:
    now = now or datetime.now(timezone.utc).astimezone()
    providers_docs_dir = providers_docs_dir or (ROOT / "docs" / "providers")
    cell_of = {(m["provider"], m["item"]): m for m in merged}
    L: list[str] = []

    L.append("# OpenAI / Anthropic Claude / Google Gemini API 구조 비교")
    L.append("")
    L.append(f"> **GENERATED {now.strftime('%Y-%m-%d %H:%M %Z')} — 수정은 matrix/*.yaml 로** (`uv run python scripts/build_comparison.py`)")
    L.append(">")
    if source_kind == "none":
        L.append("> 작성자 매트릭스가 아직 없습니다. `cp matrix/_template.yaml matrix/<handle>.yaml` 로 시작하세요. 아래 표는 빈 상태입니다.")
    else:
        src_label = "matrix/*.yaml" if source_kind == "authors" else "matrix/_parts/*.yaml (작성자 파일이 없어 부분 파일 사용)"
        L.append(f"> 입력: {src_label} · 작성자 {len(authors)}명: {', '.join('@' + a for a in authors) or '-'} · 셀 {len(merged)}/21")
    if warnings:
        L.append(">")
        L.append("> 경고: " + " / ".join(_esc(w) for w in warnings))
    L.append(">")
    L.append("> 배지: `[LIVE]` 직접 호출 확인 · `[OBSERVED]` 관찰만 · `[DOCS]` 공식 문서 근거 · `[BLOCKED: 사유]` 키/권한 없음 · 아이콘: ✅ api · ⚠️ partial · 🖥️ dashboard_only · ❌ none · ❓ unknown")
    L.append("")

    # 1. 3×7
    L.append("## 1. 3×7 비교표")
    L.append("")
    L.append("| 항목 | " + " | ".join(PROVIDER_LABEL[p] for p in PROVIDERS) + " |")
    L.append("|---|" + "---|" * len(PROVIDERS))
    for idx, (_, yaml_item, ko) in enumerate(ITEMS, start=1):
        row = [f"{idx}. {ko}"]
        for p in PROVIDERS:
            c = cell_of.get((p, yaml_item))
            if c is None:
                row.append("❓ (미작성)")
                continue
            icon = AVAIL_ICON.get(c["availability"], "❓")
            parts = [f"{icon} {c['availability']}"]
            if c["endpoint"]:
                parts.append(f"`{_short(c['endpoint'])}`")
            parts.append(f"**{badge_text(c)}**")
            parts.append(f"키: {c['auth']}")
            row.append("<br>".join(parts))
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    # 2. 공통 수집 가능 항목
    L.append("## 2. 공통 수집 가능 항목")
    L.append("")
    L.append("3사 모두 `api` 또는 `partial` 인 항목과, 각 Provider 의 `common_fields` 교집합.")
    L.append("")
    any_common = False
    for _, yaml_item, ko in ITEMS:
        cells = [cell_of.get((p, yaml_item)) for p in PROVIDERS]
        if any(c is None for c in cells):
            continue
        if all(c["availability"] in ("api", "partial") for c in cells):
            any_common = True
            sets = [set(c["common_fields"]) for c in cells]
            inter = set.intersection(*sets) if sets else set()
            ordered = [f for f in cells[0]["common_fields"] if f in inter]
            fields_txt = ", ".join(f"`{f}`" for f in ordered) if ordered else "(common_fields 교집합 없음 — YAML 에 채워 주세요)"
            avail_txt = " / ".join(f"{PROVIDER_LABEL[p]} {AVAIL_ICON[c['availability']]}" for p, c in zip(PROVIDERS, cells))
            L.append(f"- **{ko}** — {avail_txt} — 공통 필드: {fields_txt}")
    if not any_common:
        L.append("- (3사 모두 api/partial 로 확정된 항목이 아직 없음)")
    L.append("")

    # 3. Provider별 차이
    L.append("## 3. Provider별 차이")
    L.append("")
    for p in PROVIDERS:
        L.append(f"### {PROVIDER_LABEL[p]}")
        L.append("")
        body = read_md_section(providers_docs_dir / f"{p}.md", "## 8.")
        L.append(body if body is not None else f"(docs/providers/{p}.md 작성 후 생성됨)")
        L.append("")

    # 4. 공통 Usage 스키마
    L.append("## 4. 공통 Usage 스키마")
    L.append("")
    L.append("`apicompare.models.UsageNormalized` — 과금 관점 토큰. 어댑터 3개가 모두 이 형태로 돌려준다 (models.py docstring 기준).")
    L.append("")
    L.append("| 필드 | 설명 | OpenAI | Anthropic Claude | Google Gemini |")
    L.append("|---|---|---|---|---|")
    for f in dc_fields(UsageNormalized):
        info = USAGE_FORMULAS.get(f.name, {})
        L.append(
            f"| `{f.name}` | {info.get('설명', '')} | {_esc(info.get('openai', ''))} | {_esc(info.get('anthropic', ''))} | {_esc(info.get('gemini', ''))} |"
        )
    L.append("")
    L.append("비용은 `apicompare.pricing.estimate_cost()` 가 이 스키마로 계산한다(단가는 3사 모두 API 미제공 → `PRICE_TABLE` 로컬 관리, as_of·출처 기록).")
    L.append("")

    # 5. 충돌
    L.append("## 5. 충돌(author 간 불일치)")
    L.append("")
    if conflicts:
        L.append("| Provider | 항목 | 필드 | 의견 | 채택 | 규칙 |")
        L.append("|---|---|---|---|---|---|")
        for c in conflicts:
            opinions = ", ".join(f"@{a}: {_esc(v)}" for a, v in c["values"].items())
            L.append(f"| {PROVIDER_LABEL[c['provider']]} | {ITEM_BY_YAML[c['item']][1]} | {c['field']} | {opinions} | {_esc(c['chosen'])} | {c['rule']} |")
        L.append("")
        L.append("해결은 10/20 머지 시간에 당사자가 출처를 들고 결정한다(docs/MERGE_PROCESS.md). 결정 후 각자 YAML 을 고치고 다시 생성.")
    else:
        L.append("- 없음" + (" (작성자 1명 또는 입력 없음)" if len(authors) < 2 else ""))
    L.append("")

    # 6. BLOCKED
    L.append("## 6. BLOCKED 목록")
    L.append("")
    blocked = [m for m in merged if m["evidence"] == "blocked"]
    missing_cells = [(p, y, ko) for p in PROVIDERS for _, y, ko in ITEMS if (p, y) not in cell_of]
    if blocked:
        by_reason: dict[str, list[dict]] = {}
        for m in blocked:
            by_reason.setdefault(m["blocked_reason"] or "unknown", []).append(m)
        L.append("| 사유 | 건수 | 셀 |")
        L.append("|---|---|---|")
        for reason, ms in sorted(by_reason.items(), key=lambda kv: -len(kv[1])):
            L.append(f"| {_esc(reason)} | {len(ms)} | " + ", ".join(f"{PROVIDER_LABEL[m['provider']]}/{m['item_ko']}" for m in ms) + " |")
        L.append("")
        L.append("기업 키가 오면 할 일:")
        L.append("")
        for m in blocked:
            nb = NOTEBOOK_OF[m["provider"]]
            L.append(
                f"- {PROVIDER_LABEL[m['provider']]} / {m['item_ko']} — 사유: {_esc(m['blocked_reason'] or 'unknown')} → "
                f"`notebooks/{nb}.ipynb` §{ITEM_INDEX[m['item']]} 재실행 후 `evidence/{m['provider']}/{m['evidence_key']}.json` 갱신"
            )
    else:
        L.append("- BLOCKED 셀 없음")
    if missing_cells:
        L.append("")
        L.append(f"미작성 셀 {len(missing_cells)}개: " + ", ".join(f"{PROVIDER_LABEL[p]}/{ko}" for p, _, ko in missing_cells))
    L.append("")

    # 7. 미해결 질문
    L.append("## 7. 미해결 질문")
    L.append("")
    any_q = False
    for p in PROVIDERS:
        body = read_md_section(providers_docs_dir / f"{p}.md", "## 9.")
        if body is None:
            continue
        any_q = True
        L.append(f"### {PROVIDER_LABEL[p]}")
        L.append("")
        L.append(body)
        L.append("")
    if not any_q:
        L.append("(docs/providers/*.md 의 '## 9. 미해결 질문' 작성 후 생성됨)")
        L.append("")
    L.append("기업과 합의할 질문은 [docs/KICKOFF_QUESTIONS.md](KICKOFF_QUESTIONS.md) 에 모아 둔다.")
    L.append("")

    # 8. evidence 현황
    L.append("## 8. evidence 현황")
    L.append("")
    L.append("`apicompare.evidence.summary()` — evidence/<provider>/<항목>.json 의 source 배지 (노트북/`python -m apicompare.demo` 가 생성).")
    L.append("")
    L.append("| 항목 | " + " | ".join(PROVIDER_LABEL[p] for p in PROVIDERS) + " |")
    L.append("|---|" + "---|" * len(PROVIDERS))
    summaries = {p: {row["item"]: row for row in evidence_mod.summary(p, evidence_dir)} for p in PROVIDERS}
    for ev_key, yaml_item, ko in ITEMS:
        cells = []
        for p in PROVIDERS:
            row = summaries[p].get(ev_key, {})
            b = row.get("badge", "[BLOCKED: no evidence]")
            saved = row.get("saved_at")
            cells.append(f"{b}" + (f"<br><sub>{saved[:16]}</sub>" if saved else ""))
        L.append(f"| {ko} | " + " | ".join(cells) + " |")
    L.append("")
    return "\n".join(L) + "\n"


def write_merged_yaml(path: Path, merged: list[dict], conflicts: list[dict], *, authors: list[str], files: list[Path], now: datetime) -> None:
    doc = {
        "generated_at": now.isoformat(timespec="seconds"),
        "generated_by": "scripts/build_comparison.py",
        "authors": authors,
        "input_files": [str(f.relative_to(ROOT)) if f.is_relative_to(ROOT) else str(f) for f in files],
        "cells": len(merged),
        "conflicts": conflicts,
        "entries": merged,
    }
    header = (
        "# GENERATED FILE — 손편집 금지. scripts/build_comparison.py 가 matrix/<author>.yaml 을 머지해 만든다.\n"
        "# 고칠 것이 있으면 자기 matrix/<author>.yaml 을 고치고 `uv run python scripts/build_comparison.py` 를 다시 실행한다.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(header + yaml.safe_dump(doc, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")


def build(
    matrix_dir: Path,
    out: Path,
    merged_path: Path,
    *,
    evidence_dir: Path | None = None,
    providers_docs_dir: Path | None = None,
    now: datetime | None = None,
) -> dict:
    """전체 파이프라인. 테스트에서 호출하기 쉽도록 결과를 dict 로 돌려준다."""
    now = now or datetime.now(timezone.utc).astimezone()
    files, kind = discover_matrix_files(matrix_dir)
    by_author, warnings = load_matrix_files(files)
    merged, conflicts = merge_all(by_author, evidence_dir=evidence_dir)
    authors = list(by_author)
    write_merged_yaml(merged_path, merged, conflicts, authors=authors, files=files, now=now)
    md = render_markdown(
        merged,
        conflicts,
        authors=authors,
        source_kind=kind,
        files=files,
        warnings=warnings,
        evidence_dir=evidence_dir,
        providers_docs_dir=providers_docs_dir,
        now=now,
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    return {
        "files": files,
        "source_kind": kind,
        "authors": authors,
        "merged": merged,
        "conflicts": conflicts,
        "warnings": warnings,
        "out": out,
        "merged_path": merged_path,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix-dir", default=str(ROOT / "matrix"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "COMPARISON.md"))
    ap.add_argument("--merged", default=str(ROOT / "matrix" / "_merged.yaml"))
    ap.add_argument("--evidence-dir", default=None)
    ap.add_argument("--providers-docs-dir", default=None)
    args = ap.parse_args(argv)

    res = build(
        Path(args.matrix_dir),
        Path(args.out),
        Path(args.merged),
        evidence_dir=Path(args.evidence_dir) if args.evidence_dir else None,
        providers_docs_dir=Path(args.providers_docs_dir) if args.providers_docs_dir else None,
    )
    print(f"입력({res['source_kind']}): {len(res['files'])} file(s), 작성자 {len(res['authors'])}명, 셀 {len(res['merged'])}/21, 충돌 {len(res['conflicts'])}건")
    for w in res["warnings"]:
        print(f"  WARN {w}")
    for c in res["conflicts"]:
        print(f"  CONFLICT {c['provider']}/{c['item']} {c['field']}: {c['values']} → {c['chosen']}")
    print(f"→ {res['merged_path']}")
    print(f"→ {res['out']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
