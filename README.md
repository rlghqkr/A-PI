# A-PI 사전조사 — LLM Provider API 구조 비교

로그베이스 PoC "Multi-LLM Simulator" 사전 과제. OpenAI / Anthropic Claude / Google Gemini 의 API 를 7개 항목으로 조사하고 비교한다.

- 무엇을 읽나 → `docs/COMPARISON.md` (3×7 비교표, 생성물) · `docs/providers/*.md` (Provider 상세)
- 어떻게 실행하나 → `docs/HOWTO_RUN.md`
- 어떻게 합치나 → `docs/MERGE_PROCESS.md` · `matrix/_template.yaml`
- 킥오프 질문 → `docs/KICKOFF_QUESTIONS.md`

```bash
uv sync --group dev                    # Python 3.12 가상환경 + 의존성
cp .env.example .env                   # 키는 .env 에만
uv run python -m apicompare.demo openai --no-paid   # Jupyter 없이 무료 항목 실행
uv run jupyter lab                     # notebooks/10_openai.ipynb 부터
```
