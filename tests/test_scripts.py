"""scripts/validate_matrix.py, scripts/build_comparison.py 동작 테스트 (네트워크/키 불필요)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


validate_matrix = _load("validate_matrix")
build_comparison = _load("build_comparison")

PROVIDERS = ("openai", "anthropic", "gemini")
ITEMS = ("models_list", "generate", "token_usage", "usage_report", "cost", "status_errors", "example")


def _entry(provider: str, item: str, **over) -> dict:
    base = {
        "provider": provider,
        "item": item,
        "availability": "api",
        "endpoint": f"GET /{provider}/{item}",
        "auth": "standard_key",
        "sdk_call": "",
        "response_fields": ["id"],
        "common_fields": ["model_id"],
        "caveats": "",
        "evidence": "docs",
        "blocked_reason": "",
        "sources": [f"https://docs.example/{provider}/{item}"],
        "confidence": 0.8,
    }
    base.update(over)
    return base


def _full_doc(author: str, **cell_overrides: dict) -> dict:
    """21셀 전부 있는 문서. cell_overrides 키는 'provider/item'."""
    entries = []
    for p in PROVIDERS:
        for it in ITEMS:
            entries.append(_entry(p, it, **cell_overrides.get(f"{p}/{it}", {})))
    return {"author": author, "as_of": "2026-10-19", "entries": entries}


def _write(path: Path, doc: dict) -> Path:
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


# --------------------------------------------------------------------------- build_comparison
def test_build_reports_conflict_and_writes_files(tmp_path: Path):
    matrix_dir = tmp_path / "matrix"
    matrix_dir.mkdir()
    (matrix_dir / "_parts").mkdir()
    # _template/_merged 는 무시되어야 한다
    _write(matrix_dir / "_template.yaml", _full_doc("<slack_handle>"))
    _write(matrix_dir / "_merged.yaml", {"junk": True})

    _write(
        matrix_dir / "alice.yaml",
        _full_doc(
            "alice",
            **{
                "openai/usage_report": {"availability": "api", "endpoint": "GET /v1/organization/usage/completions", "confidence": 0.9},
                "openai/cost": {"evidence": "blocked", "blocked_reason": "admin key", "availability": "partial"},
            },
        ),
    )
    _write(
        matrix_dir / "bob.yaml",
        _full_doc(
            "bob",
            **{
                "openai/usage_report": {
                    "availability": "partial",
                    "endpoint": "GET /v1/organization/usage/*",
                    "confidence": 0.6,
                    "sources": ["https://docs.example/bob-usage"],
                },
                # 둘 다 blocked 여야 배지가 BLOCKED 로 남는다 (한 명이라도 docs 면 docs > blocked 로 승격)
                "openai/cost": {"evidence": "blocked", "blocked_reason": "admin key", "availability": "partial"},
                # 한 명만 blocked 인 셀: 다른 사람의 docs 가 이긴다
                "anthropic/cost": {"evidence": "blocked", "blocked_reason": "org + admin key"},
            },
        ),
    )

    out = tmp_path / "docs" / "COMPARISON.md"
    merged_path = matrix_dir / "_merged.yaml"
    evidence_dir = tmp_path / "evidence"  # 비어 있음
    providers_docs = tmp_path / "providers"  # 없음

    res = build_comparison.build(matrix_dir, out, merged_path, evidence_dir=evidence_dir, providers_docs_dir=providers_docs)

    assert res["source_kind"] == "authors"
    assert sorted(res["authors"]) == ["alice", "bob"]
    assert len(res["merged"]) == 21

    fields = {(c["provider"], c["item"], c["field"]) for c in res["conflicts"]}
    assert ("openai", "usage_report", "availability") in fields
    assert ("openai", "usage_report", "endpoint") in fields

    cell = next(m for m in res["merged"] if m["provider"] == "openai" and m["item"] == "usage_report")
    assert cell["availability"] == "partial", "보수적인 값 채택"
    assert "(@alice: api — https://docs.example/openai/usage_report)" in cell["caveats"], "반대 의견 보존"
    assert "GET /v1/organization/usage/completions" in cell["endpoint"] and "GET /v1/organization/usage/*" in cell["endpoint"]
    assert cell["primary_author"] == "alice"  # 같은 등급(docs)이면 confidence 높은 쪽

    blocked = next(m for m in res["merged"] if m["provider"] == "openai" and m["item"] == "cost")
    assert build_comparison.badge_text(blocked) == "[BLOCKED: admin key]"
    upgraded = next(m for m in res["merged"] if m["provider"] == "anthropic" and m["item"] == "cost")
    assert upgraded["evidence"] == "docs" and build_comparison.badge_text(upgraded) == "[DOCS]", "docs > blocked"

    # 파일 생성 + 내용
    assert out.exists() and merged_path.exists()
    md = out.read_text(encoding="utf-8")
    assert "GENERATED" in md and "수정은 matrix/*.yaml 로" in md
    for h in ["## 1. 3×7 비교표", "## 2. 공통 수집 가능 항목", "## 3. Provider별 차이", "## 4. 공통 Usage 스키마",
              "## 5. 충돌(author 간 불일치)", "## 6. BLOCKED 목록", "## 7. 미해결 질문", "## 8. evidence 현황"]:
        assert h in md
    assert "@alice: api" in md and "@bob: partial" in md
    assert "(docs/providers/openai.md 작성 후 생성됨)" in md
    assert "notebooks/10_openai.ipynb" in md and "admin key" in md
    assert "[BLOCKED: no evidence]" in md  # evidence 디렉터리가 비어 있음

    merged_doc = yaml.safe_load(merged_path.read_text(encoding="utf-8"))
    assert merged_doc["cells"] == 21 and len(merged_doc["conflicts"]) >= 2
    assert merged_path.read_text(encoding="utf-8").startswith("# GENERATED FILE — 손편집 금지")


def test_build_falls_back_to_parts_then_empty(tmp_path: Path):
    matrix_dir = tmp_path / "matrix"
    (matrix_dir / "_parts").mkdir(parents=True)
    _write(matrix_dir / "_template.yaml", _full_doc("<slack_handle>"))
    _write(matrix_dir / "_parts" / "openai.yaml", {"author": "agent", "as_of": "2026-10-19", "entries": [_entry("openai", "models_list", evidence="docs")]})

    res = build_comparison.build(matrix_dir, tmp_path / "C.md", matrix_dir / "_merged.yaml", evidence_dir=tmp_path / "ev", providers_docs_dir=tmp_path / "pd")
    assert res["source_kind"] == "parts" and len(res["merged"]) == 1
    md = (tmp_path / "C.md").read_text(encoding="utf-8")
    assert "❓ (미작성)" in md and "미작성 셀 20개" in md

    # 아무 파일도 없을 때
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    res2 = build_comparison.build(empty_dir, tmp_path / "E.md", empty_dir / "_merged.yaml", evidence_dir=tmp_path / "ev", providers_docs_dir=tmp_path / "pd")
    assert res2["source_kind"] == "none" and res2["merged"] == []
    assert "작성자 매트릭스가 아직 없습니다" in (tmp_path / "E.md").read_text(encoding="utf-8")


def test_evidence_file_source_upgrades_badge(tmp_path: Path):
    """YAML 은 docs 인데 evidence/<p>/<key>.json 이 live 면 배지는 LIVE."""
    import json

    ev_dir = tmp_path / "evidence"
    (ev_dir / "openai").mkdir(parents=True)
    (ev_dir / "openai" / "01_models.json").write_text(json.dumps({"source": "live", "note": "", "saved_at": "2026-10-19T00:00:00+00:00"}), encoding="utf-8")
    merged, conflicts = build_comparison.merge_cell([{**_entry("openai", "models_list", evidence="docs"), "_author": "a"}], evidence_dir=ev_dir)
    assert merged["evidence"] == "live" and merged["evidence_yaml"] == "docs" and conflicts == []
    assert build_comparison.badge_text(merged) == "[LIVE]"


def test_read_md_section(tmp_path: Path):
    p = tmp_path / "openai.md"
    p.write_text("# T\n\n## 8. 다른 Provider와 다른 점\n\n- a\n- b\n\n## 9. 미해결 질문\n\n- [ ] q\n\n## 10. 출처\n", encoding="utf-8")
    assert build_comparison.read_md_section(p, "## 8.") == "- a\n- b"
    assert build_comparison.read_md_section(p, "## 9.") == "- [ ] q"
    assert build_comparison.read_md_section(p, "## 99.") is None
    assert build_comparison.read_md_section(tmp_path / "nope.md", "## 8.") is None


# --------------------------------------------------------------------------- validate_matrix
def test_validate_template_passes_schema():
    errors, warnings = validate_matrix.validate_file(ROOT / "matrix" / "_template.yaml")
    assert errors == []
    assert any("placeholder" in w for w in warnings)


def test_validate_catches_schema_violations_and_duplicates(tmp_path: Path):
    doc = _full_doc("carol")
    doc["entries"][0]["availability"] = "maybe"  # enum 위반
    doc["entries"][1]["bogus"] = 1  # additionalProperties 위반
    doc["entries"].append(_entry("openai", "models_list"))  # 중복 셀
    del doc["as_of"]  # 필수 누락
    path = _write(tmp_path / "carol.yaml", doc)

    errors, warnings = validate_matrix.validate_file(path, evidence_dir=tmp_path / "ev")
    joined = "\n".join(errors)
    assert "'maybe' is not one of" in joined
    assert "bogus" in joined
    assert "'as_of' is a required property" in joined
    assert "중복" in joined
    assert validate_matrix.main([str(path)]) == 1


def test_validate_warnings_blocked_reason_and_live_evidence(tmp_path: Path):
    doc = _full_doc(
        "dave",
        **{
            "gemini/usage_report": {"evidence": "blocked", "blocked_reason": ""},
            "openai/models_list": {"evidence": "live"},
        },
    )
    path = _write(tmp_path / "dave.yaml", doc)
    errors, warnings = validate_matrix.validate_file(path, evidence_dir=tmp_path / "ev")
    assert errors == []
    assert any("blocked_reason 이 비어 있음" in w for w in warnings)
    assert any("evidence=live 인데" in w and "01_models.json" in w for w in warnings)
    assert validate_matrix.main([str(path), "--evidence-dir", str(tmp_path / "ev")]) == 0
    assert validate_matrix.main([str(path), "--evidence-dir", str(tmp_path / "ev"), "--strict"]) == 1


def test_validate_reports_missing_cells(tmp_path: Path):
    path = _write(tmp_path / "part.yaml", {"author": "erin", "as_of": "2026-10-19", "entries": [_entry("openai", "models_list")]})
    errors, warnings = validate_matrix.validate_file(path, evidence_dir=tmp_path / "ev")
    assert errors == []
    assert any("누락 셀 20/21" in w for w in warnings)


def test_validate_bad_yaml(tmp_path: Path):
    path = tmp_path / "bad.yaml"
    path.write_text("author: x\nentries: [\n", encoding="utf-8")
    errors, _ = validate_matrix.validate_file(path)
    assert errors and "YAML 파싱 실패" in errors[0]
