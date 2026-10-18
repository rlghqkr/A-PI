"""환경변수(.env) 로딩. 키 값은 절대 로그/출력에 남기지 않는다 — 존재 여부(bool)만 노출한다."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT / ".env"

KEY_VARS: tuple[str, ...] = (
    "OPENAI_API_KEY",
    "OPENAI_ADMIN_KEY",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_ADMIN_KEY",
    "GEMINI_API_KEY",
)

_loaded = False


def load_env(override: bool = False) -> None:
    """프로젝트 루트의 .env 를 읽는다. 이미 설정된 쉘 환경변수는 덮어쓰지 않는다(override=False)."""
    global _loaded
    if ENV_PATH.exists():
        load_dotenv(ENV_PATH, override=override)
    _loaded = True


def keys() -> dict[str, bool]:
    """어떤 키가 설정돼 있는지 bool 로만 돌려준다. 값은 절대 반환하지 않는다."""
    load_env()
    return {k: bool(os.getenv(k)) for k in KEY_VARS}


def get_key(name: str) -> str | None:
    """키 값을 돌려준다. 어댑터 내부에서만 사용한다. 노트북에서 print 하지 말 것."""
    load_env()
    value = os.getenv(name)
    return value or None


def known_secret_values() -> list[str]:
    """evidence 저장 시 '실제 키 값이 그대로 들어있는지' 검사하는 데 쓴다."""
    load_env()
    return [v for k in KEY_VARS if (v := os.getenv(k))]
