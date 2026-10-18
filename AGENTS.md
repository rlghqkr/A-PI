# A-PI: Multi-LLM Simulator PoC

로그베이스(Logbase) 기업 연계 PoC 과제 저장소다. 2026 AI클러스터 청년인턴십연계 인재양성프로그램, 과제 05.

> 상태: **킥오프 전 (2026-10-18 작성)**. "미정"으로 표시된 항목은 10/20 킥오프 이후 확정되면 이 파일을 갱신한다.

## 무엇을 만드는가

같은 Prompt와 입력 데이터를 여러 LLM(최대 3~4개)에 동시에 보내고, 결과를 한 화면에서 비교하는 내부 도구.

| 기능 | 내용 |
|---|---|
| ① Multi-LLM 동시 실행 및 결과 비교 | 응답 결과, 성공/실패, 응답시간, Input/Output Token, 예상 API 비용, JSON 등 지정 Format 준수 여부를 병렬 표시 |
| ② 테스트 시나리오와 Custom Prompt | 사전 정의 시나리오 선택 또는 직접 입력. 예: 상품 이미지/속성 분석, 상품 설명·Marketing Copy 생성, 데이터 요약·구조화, 비정형 텍스트 → JSON 변환, 일반 분석·추론 |
| ③ AI 모델 Benchmark | 응답시간, Token, 예상 비용, 실행 성공 여부, JSON Schema/Format 준수, 출력 누락·오류 비교. 결과를 JSON으로 조회·복사하거나 저장 |

비교 대상 Provider 예시: OpenAI, Anthropic Claude, Google Gemini, OpenRouter 또는 공개 API 지원 모델.

## 기업 제공 자료 (킥오프 때 수령 예정)

- AI Model Simulator 화면설계 및 기능 요구사항
- PoC용 업무 시나리오 및 테스트 Prompt 3~5종
- Sample Data: 상품정보, 공개 이미지, 가상 데이터
- 비교 대상 AI Model 및 Provider 목록
- API 호출 예제 및 기본 연동 정보
- 모델별 비용 계산 기준정보

수령하면 `docs/` 아래에 정리하고 이 목록에 경로를 적는다. 기업 자료는 PoC 수행 목적으로만 쓰고 외부에 올리지 않는다.

## 기술 스택

**PoC 본 개발 스택은 미정.** 기업이 제시한 후보: Python, FastAPI, React 또는 Next.js, Docker, Git, OpenAI/Claude/Gemini API, OpenRouter, PostgreSQL 또는 SQLite. 모든 기술을 다 써야 하는 것은 아니며, 실제 적용 기술은 기업과 조율한다. 킥오프 후 아래 "본 개발" 칸을 채운다.

**사전조사 환경(확정, 2026-10-19)**
- Python 3.12 + `uv` (시스템 Python 3.9는 쓰지 않는다 — `anthropic` 1.x·`google-genai`가 3.10+ 필요)
- 패키지 `src/apicompare/`: 3사 Provider 어댑터 + 공통 데이터 모델 + 오류 분류 + 단가표 + usage 자체 적재 + evidence 저장. **PoC Provider 어댑터 계층의 초안**이므로 본 개발 때 `backend/providers/`로 승격한다.
- SDK: `openai` 3.x(Responses API 기본), `anthropic` 1.x, `google-genai` 2.x(`google-generativeai`는 deprecated — 쓰지 않는다)
- 실행: `uv sync --group dev` → `uv run jupyter lab` 또는 `uv run python -m apicompare.demo <provider>` · 테스트: `uv run pytest` · 상세: `docs/HOWTO_RUN.md`

**본 개발(킥오프 후 확정)**
- 백엔드:
- 프론트엔드:
- DB:
- 배포:

## 제약과 규칙

**API Key와 비용**
- PoC 전용 API Key는 기업이 발급하며, 정해진 사용량·비용 한도 안에서만 쓴다. 한도와 비용 확인 방법은 킥오프에서 확인한다 (**미정**).
- 한도 초과가 예상되면 사용 전에 기업 멘토와 운영진에게 알리고 협의한다.
- 실제 유료 호출 전에는 대상 모델, 호출 횟수, 예상 비용을 팀에 알리고 확인을 받는다. 개발·테스트는 mock 응답이나 저렴한 모델로 먼저 한다.
- API Key는 `.env`에만 두고 `.gitignore`에 넣는다. 코드, 커밋, 로그, Slack에 평문으로 남기지 않는다.

**데이터**
- 고객 운영 데이터와 Production DB는 쓰지 않는다. 공개·가상 데이터와 실시간 API 호출 결과만 사용한다.
- 운영 DB 접근은 제공되지 않는다. 개발 환경의 테이블은 접근 가능하다.
- 로그베이스의 핵심 상용 Source Code는 제공되지 않는다. 개발 결과는 별도 PoC Repository에서 관리한다.

**비교의 공정성**
- 모델 간 비교 시 Prompt, 입력, 통제 가능한 파라미터(system prompt, max_output_tokens, effort/thinking 수준)를 같게 맞춘다. 다르면 결과에 명시한다.
- `temperature`는 공통 파라미터로 쓸 수 없다: Claude 현행 모델은 400으로 거부(SDK 1.x는 파라미터 자체 제거), Gemini 3.6+/4는 무시한다. 재시도는 3사 모두 0회로 고정해 응답시간 비교를 왜곡하지 않는다.
- 가격·모델 목록·Token 계산 방식은 각 Provider 공식 문서 기준으로 하고, 비용 기준표(`src/apicompare/pricing.py`)에 출처와 확인 날짜를 남긴다. 단가는 3사 모두 API로 제공되지 않는다.
- reasoning/thinking 토큰은 3사 모두 output 단가로 과금되며 output_tokens에 포함돼 있다(더하지 않는다). Anthropic은 total_tokens 필드가 없어 계산값이다.

## 사전 조사 항목 (기업 요청)

OpenAI, Anthropic Claude, Google Gemini의 API 구조를 조사하고, Provider별 차이와 공통으로 수집 가능한 항목을 비교한다. 가능하면 간단한 호출 예제를 준비한다.

| # | 항목 | 조사 내용 |
|---|---|---|
| 1 | 모델 목록 조회 | 현재 API로 사용 가능한 모델 목록과 모델 정보 조회 방법 |
| 2 | 모델 호출 | Prompt 전달과 응답을 받는 기본 API와 호출 방법 |
| 3 | Token Usage | 1회 호출 시 Input/Output/Total Token 확인 방법 |
| 4 | Usage 조회 | 일정 기간의 API 사용량 조회 방법 |
| 5 | 비용 확인 | API 비용 또는 예상 비용 확인·계산 방법 |
| 6 | 상태 및 오류 | 연결 성공 여부, Timeout, 인증 오류, Rate Limit 확인 방법 |
| 7 | 호출 예제 | Python 등으로 간단히 실행 가능한 API 호출 Sample |

**산출물 위치(2026-10-19 확정)**
- 비교표(생성물, 손편집 금지): `docs/COMPARISON.md` ← `uv run python scripts/build_comparison.py`
- Provider 상세(사람이 쓰는 문서, 템플릿 `docs/templates/PROVIDER_TEMPLATE.md`): `docs/providers/{openai,anthropic,gemini}.md`
- 취합 단위(작성자 1명 = 파일 1개, 21셀): `matrix/<이름>.yaml` ← `matrix/_template.yaml`, 검증 `scripts/validate_matrix.py`
- 실측 증거(마스킹된 JSON): `evidence/<provider>/<항목>.json` — 배지 `[LIVE]`/`[OBSERVED]`/`[DOCS]`/`[BLOCKED: 사유]`의 근거
- 실습 노트북(증거 생성기, 산출물 아님): `notebooks/00_setup_check → 10_openai → 20_anthropic → 30_gemini → 90_compare`
- 킥오프 질문: `docs/KICKOFF_QUESTIONS.md` · 취합 절차: `docs/MERGE_PROCESS.md`

**조사에서 확정된 사실(요약)**
- 기간별 Usage·비용을 3사 공통으로 뽑는 API는 없다. OpenAI·Anthropic은 Admin 키(조직 Owner/Admin) 필수, Gemini는 API 자체가 없음(AI Studio 대시보드). → Simulator는 호출마다 응답 usage를 자체 적재해 집계한다(`apicompare.usagelog`).
- OpenAI는 Responses API를 기본으로 쓴다(GPT-5.4+에서 Chat Completions는 tools+reasoning 불가, 실측 400). Gemini는 generateContent(유지) + Interactions(권장) 공존.
- Anthropic 과부하는 529(503 아님), SDK에서는 `APIStatusError.status_code`로 분기. Gemini SDK는 `retry_options`를 명시하지 않으면 재시도 0회(문서와 다름).

## 일정

| 날짜 | 내용 |
|---|---|
| 10/19(월) | 프로젝트 시작 |
| 10/20(화) 14:00~16:00 | 킥오프 (오프라인) |
| 매주 월·수·금 | 정기 리뷰 (Google Meet, 20~30분). 1주차 금요일 최종 리뷰는 약 30분 |
| 10/28(수) | 외부 특강. 이날 리뷰는 14:30 이전에 마친다 |
| 11/6(금) | 최종 발표 및 수료식 |

교육시간은 09:30~17:30이며, 멘토링도 이 시간 안에 한다. 소통은 Discord 채널, 협업은 GitHub Repository·Issue 기반.

## 팀 Slack 채널 (A-PI_AI 워크스페이스)

기업·운영진과의 공식 소통은 Discord다. Slack은 팀 내부 작업 공간이다.

| 채널 | ID | 용도 | 봇 | 결과 저장 위치 |
|---|---|---|---|---|
| #00-공지 | C0CA00J7WNR | 일정, 결정사항, 기업 안내 공유 | 없음 | Notion `프로젝트` DB |
| #01-회의 | C0CA3AC9HML | 정기 리뷰, 킥오프, 기업 질문 모음 | A-PI Hermes | Notion 회의록 |
| #10-조사 | C0CA905KJLC | Provider API 사전 조사, 모델·가격 확인 | A-PI Hermes | Notion 조사 페이지 |
| #20-개발 | C0CA3AEQCFQ | 구현 논의, 로컬 실행·테스트 (A-PI Hermes 홈 채널) | A-PI Hermes | Notion `개발일지 전체 보기` DB, 로컬 A-PI 폴더 |
| #21-pr-리뷰 | C0CA908RRC4 | GitHub PR 작업, 코드 리뷰 | Claude | GitHub |
| #30-벤치마크 | C0CA00Q862Z | 모델 비교 실행, API 비용 기록 | A-PI Hermes | Google Sheets (Drive `A-PI(아피)` 폴더) |

- A-PI Hermes와 Claude는 같은 채널에 두지 않는다.
- 유료 API 호출은 #30-벤치마크에서만 한다.
- 결정된 사항은 #00-공지에 한 줄로 남긴다.

## 문서 저장소

- **Notion**: `A-PI` 페이지 (ID `3faccf3ec2e88031b715dcf5458bb14f`). 정리된 문서(회의록, 조사, 개발일지, 결정)를 둔다.
- **Google Drive**: `A-PI(아피)` 폴더. 원본 파일(기업 제공 자료, PDF, 이미지, 발표 자료)과 벤치마크 결과 시트를 둔다. 폴더 ID는 A-PI Hermes 프로필의 `SOUL.md`에만 있다(공개 저장소에는 적지 않는다).

## 킥오프에서 확인할 것

- [ ] 1~3번 기능의 필수 범위와 우선순위
- [ ] 비교 대상 모델·Provider 확정 목록
- [ ] API 사용 한도, 비용 확인 방법, 한도 초과 시 절차
- [ ] 기술 스택 지정 여부 (백엔드, 프론트엔드, DB)
- [ ] 결과물 형태: 웹 화면 필수 여부, 배포 필요 여부
- [ ] PoC Repository 위치와 접근 권한
- [ ] 산출물 공개 범위 (포트폴리오, 코드 공개 가능 여부)
- [ ] 성공 기준과 최종 발표 형식

## 저장소 구조 (2026-10-19 기준, 사전조사 단계)

PoC 본 개발 구조는 킥오프 후 확정한다. `src/apicompare/`는 그대로 Provider 어댑터 계층으로 승격할 계획이다.

```
A-PI/
├── AGENTS.md / CLAUDE.md          # 프로젝트 규칙 (CLAUDE.md는 Slack Claude·클라우드 세션용, AGENTS.md를 include)
├── README.md · docs/HOWTO_RUN.md  # 실행 방법
├── pyproject.toml · uv.lock · .python-version(3.12)
├── .env.example                   # 키 변수명만. 실제 키는 .env (gitignored)
├── .gitattributes                 # *.ipynb → nbstripout (출력 커밋 금지)
├── src/apicompare/                # ★ 공통 코드 (PoC 어댑터 초안)
│   ├── models.py                  # ModelInfo / UsageNormalized / CallResult / ErrorInfo / NotSupported / UsageReport / CostEstimate
│   ├── providers/{base,openai_adapter,anthropic_adapter,gemini_adapter}.py
│   ├── errors.py                  # ErrorCategory + 3사 매핑 + redact()
│   ├── pricing.py                 # 단가표(as_of·출처·인상 예고) + estimate_cost()
│   ├── usagelog.py                # 호출별 usage 자체 적재 + 기간 집계 (④의 3사 공통 경로)
│   ├── evidence.py                # 실측 증거 저장/배지
│   └── demo.py                    # python -m apicompare.demo <provider> (Jupyter 없이 7항목)
├── notebooks/                     # 00_setup_check, 10_openai, 20_anthropic, 30_gemini, 90_compare (증거 생성기)
├── evidence/<provider>/           # 01_models … 07_example .json (마스킹됨)
├── matrix/                        # _template.yaml, matrix_entry.schema.json, <이름>.yaml, _merged.yaml(생성물)
├── scripts/                       # validate_matrix.py, build_comparison.py, check_secrets.sh
├── docs/
│   ├── COMPARISON.md              # 3×7 비교표 (생성물)
│   ├── providers/*.md             # Provider 상세
│   ├── templates/                 # PROVIDER_TEMPLATE.md, CELL_CARD.md
│   ├── MERGE_PROCESS.md · KICKOFF_QUESTIONS.md
│   └── (기업 제공 자료는 킥오프 후 docs/company/ 에)
├── tests/
└── data/                          # usage_log.jsonl (gitignored)
```
