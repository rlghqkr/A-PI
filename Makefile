# A-PI 사전조사 — 자주 쓰는 명령. 모든 실행은 저장소 루트에서 `uv run ...` 으로 통일한다.
#   make setup      uv sync --group dev + nbstripout --install (노트북 출력 커밋 방지)
#   make check      pytest
#   make demo-free  3사 무료 항목(①④⑥)만 — 유료 호출 없음
#   make build      validate(전체 matrix) + build_comparison → docs/COMPARISON.md
#   make secrets    키 모양 문자열 검사
#   make strip      notebooks/*.ipynb 출력 제거
#   make lab        uv run jupyter lab

UV ?= uv
MATRIX_FILES := $(filter-out matrix/_merged.yaml,$(wildcard matrix/*.yaml)) $(wildcard matrix/_parts/*.yaml)
NOTEBOOKS := $(wildcard notebooks/*.ipynb)

.PHONY: setup check demo-free build validate secrets strip lab help

help:
	@sed -n '2,9p' Makefile

setup:
	$(UV) sync --group dev
	$(UV) run nbstripout --install --attributes .gitattributes

check:
	$(UV) run pytest

demo-free:
	-$(UV) run python -m apicompare.demo openai --no-paid
	-$(UV) run python -m apicompare.demo anthropic --no-paid
	-$(UV) run python -m apicompare.demo gemini --no-paid

validate:
	$(UV) run python scripts/validate_matrix.py $(MATRIX_FILES)

build: validate
	$(UV) run python scripts/build_comparison.py

secrets:
	bash scripts/check_secrets.sh

strip:
	@if [ -n "$(NOTEBOOKS)" ]; then $(UV) run nbstripout $(NOTEBOOKS); else echo "notebooks/*.ipynb 없음"; fi

lab:
	$(UV) run jupyter lab
