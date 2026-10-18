#!/usr/bin/env python
"""matrix/<author>.yaml 검증기.

    uv run python scripts/validate_matrix.py matrix/_template.yaml matrix/<handle>.yaml [--strict]

검사 항목
  1. YAML 파싱 + matrix/matrix_entry.schema.json(JSON Schema 2020-12) 검증            → 위반 시 ERROR
  2. (provider, item) 21셀 중 누락 / 중복                                              → 누락 WARN, 중복 ERROR
  3. evidence=blocked 인데 blocked_reason 이 비어 있음                                   → WARN
  4. evidence=live 인데 evidence/<provider>/<evidence키>.json 이 없음                   → WARN
     (item → evidence 키 매핑은 apicompare.ITEM_BY_YAML)

종료코드: ERROR 가 하나라도 있으면 1, 아니면 0. --strict 이면 WARN 도 1 로 취급.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:  # 패키지가 설치되지 않은 환경에서도 동작
    sys.path.insert(0, str(ROOT / "src"))

from apicompare import ITEM_BY_YAML, PROVIDERS  # noqa: E402

SCHEMA_PATH = ROOT / "matrix" / "matrix_entry.schema.json"
EVIDENCE_DIR = ROOT / "evidence"
ALL_CELLS = {(p, y) for p in PROVIDERS for y in ITEM_BY_YAML}


def load_schema(path: Path = SCHEMA_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _fmt_path(err_path) -> str:
    out = ""
    for p in err_path:
        out += f"[{p}]" if isinstance(p, int) else f".{p}"
    return out.lstrip(".") or "<root>"


def validate_doc(doc: object, *, schema: dict | None = None, evidence_dir: Path | None = None) -> tuple[list[str], list[str]]:
    """파싱된 YAML 객체 하나를 검사한다. (errors, warnings) 를 돌려준다."""
    errors: list[str] = []
    warnings: list[str] = []
    schema = schema or load_schema()
    evidence_dir = evidence_dir or EVIDENCE_DIR

    if not isinstance(doc, dict):
        return [f"최상위가 매핑(author/as_of/entries)이 아닙니다: {type(doc).__name__}"], warnings

    validator = Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        errors.append(f"schema: {_fmt_path(err.absolute_path)}: {err.message}")

    entries = doc.get("entries")
    if not isinstance(entries, list):
        return errors, warnings

    seen: dict[tuple[str, str], int] = {}
    for i, e in enumerate(entries):
        if not isinstance(e, dict):
            continue
        provider, item = e.get("provider"), e.get("item")
        if provider in PROVIDERS and item in ITEM_BY_YAML:
            key = (provider, item)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] == 2:
                errors.append(f"entries[{i}]: ({provider}, {item}) 셀이 중복됨")
        ev = e.get("evidence")
        if ev == "blocked" and not str(e.get("blocked_reason") or "").strip():
            warnings.append(f"entries[{i}] ({provider}, {item}): evidence=blocked 인데 blocked_reason 이 비어 있음")
        if ev == "live" and provider in PROVIDERS and item in ITEM_BY_YAML:
            ev_key = ITEM_BY_YAML[item][0]
            ev_path = evidence_dir / provider / f"{ev_key}.json"
            if not ev_path.exists():
                warnings.append(
                    f"entries[{i}] ({provider}, {item}): evidence=live 인데 {ev_path.relative_to(ROOT) if ev_path.is_relative_to(ROOT) else ev_path} 없음"
                )

    missing = sorted(ALL_CELLS - set(seen))
    if missing:
        warnings.append(f"누락 셀 {len(missing)}/21: " + ", ".join(f"{p}/{y}" for p, y in missing))

    if str(doc.get("author", "")).strip() in ("", "<slack_handle>"):
        warnings.append("author 가 placeholder(<slack_handle>) 입니다 — 머지 전 실제 핸들로 바꿔 주세요")

    return errors, warnings


def validate_file(path: Path, *, schema: dict | None = None, evidence_dir: Path | None = None) -> tuple[list[str], list[str]]:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [f"파일 없음: {path}"], []
    except yaml.YAMLError as exc:
        return [f"YAML 파싱 실패: {exc}"], []
    return validate_doc(doc, schema=schema, evidence_dir=evidence_dir)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", help="검증할 matrix YAML 파일")
    ap.add_argument("--strict", action="store_true", help="경고도 실패로 취급")
    ap.add_argument("--evidence-dir", default=None, help="evidence 디렉터리(기본 evidence/)")
    args = ap.parse_args(argv)

    schema = load_schema()
    evidence_dir = Path(args.evidence_dir) if args.evidence_dir else None
    total_err = total_warn = 0
    for f in args.files:
        path = Path(f)
        errors, warnings = validate_file(path, schema=schema, evidence_dir=evidence_dir)
        total_err += len(errors)
        total_warn += len(warnings)
        status = "FAIL" if errors else ("WARN" if warnings else "OK")
        print(f"[{status}] {path}")
        for e in errors:
            print(f"  ERROR {e}")
        for w in warnings:
            print(f"  WARN  {w}")

    print(f"\n{len(args.files)} file(s): {total_err} error(s), {total_warn} warning(s)")
    if total_err or (args.strict and total_warn):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
