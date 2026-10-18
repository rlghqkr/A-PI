"""A-PI 사전조사: OpenAI / Anthropic Claude / Google Gemini API 구조 비교 도구.

- 조사 항목 7개는 ITEMS 에 고정돼 있다. 노트북 섹션 제목, evidence 파일명, matrix YAML 의 item 키가 모두 여기서 나온다.
- 세 Provider 어댑터(providers/)는 같은 데이터 모델(models.py)로 결과를 돌려준다.
- 이 패키지는 Multi-LLM Simulator PoC 의 Provider 어댑터 계층 초안이기도 하다.
"""

from __future__ import annotations

__version__ = "0.1.0"

# (evidence 키, matrix YAML item 키, 과제 원문 항목명)
ITEMS: list[tuple[str, str, str]] = [
    ("01_models", "models_list", "모델 목록 조회"),
    ("02_call", "generate", "모델 호출"),
    ("03_usage", "token_usage", "Token Usage"),
    ("04_usage_api", "usage_report", "Usage 조회"),
    ("05_costs", "cost", "비용 확인"),
    ("06_errors", "status_errors", "상태 및 오류 확인"),
    ("07_example", "example", "호출 예제"),
]
ITEM_BY_EVIDENCE: dict[str, tuple[str, str]] = {e: (y, k) for e, y, k in ITEMS}
ITEM_BY_YAML: dict[str, tuple[str, str]] = {y: (e, k) for e, y, k in ITEMS}

PROVIDERS: tuple[str, ...] = ("openai", "anthropic", "gemini")
PROVIDER_LABEL: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic Claude",
    "gemini": "Google Gemini",
}
