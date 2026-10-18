# 실행 방법 (HOWTO_RUN)

대상: 팀원 3~5명. 목표는 "내 노트북에서 노트북 00 → 90 이 돌아가고 evidence 가 남는 상태". 모든 명령은 **저장소 루트**에서 `uv run ...` 으로 실행한다(시스템 Python 사용 금지).

## 0. 준비물

- `uv` (https://docs.astral.sh/uv/ — `curl -LsSf https://astral.sh/uv/install.sh | sh` 또는 `brew install uv`)
- git, VS Code(+ Jupyter 확장) 또는 브라우저(Jupyter Lab)
- API 키: OpenAI 는 개인 키 1개면 충분. Anthropic/Gemini 키가 없어도 **NO_KEY 모드로 전체 노트북이 돈다**(해당 셀은 `[BLOCKED: no key]`).

## 1. 설치

```bash
git clone <repo> A-PI && cd A-PI
uv sync --group dev            # .python-version(3.12) 에 맞는 Python 을 uv 가 받아 .venv 생성 + SDK + Jupyter
cp .env.example .env           # 키는 .env 에만. .env 는 gitignore 대상
uv run python -c "from apicompare.config import keys; print(keys())"   # {'OPENAI_API_KEY': True, ...} — 값은 절대 출력되지 않는다
```

`make setup` 은 위 `uv sync` 에 `nbstripout --install`(노트북 출력이 커밋되지 않게 git filter 등록)을 더한 것이다.

## 2. 키 발급 (3종)

키는 생성 직후 한 번만 보인다 → 바로 `.env` 에 붙인다. Slack/Notion/Drive/스크린샷에 올리지 않는다. 노출됐으면 즉시 폐기(revoke)하고 재발급.

### OpenAI — 프로젝트 키 + (선택) Admin 키
1. https://platform.openai.com 로그인 → 프로젝트 선택 → **Settings → API keys → Create new secret key** → `.env` 의 `OPENAI_API_KEY`.
2. 신규 계정은 선불 결제. 최소 충전 $5(기본 $10). 무료 체험 크레딧 지급은 공식 문서에서 확인되지 않음.
3. **Admin 키**(④ Usage 조회 / ⑤ 비용 확인 API 전용): 조직 **Owner** 만 생성 가능. **Settings → Organization → Admin keys** → `.env` 의 `OPENAI_ADMIN_KEY`. 일반 엔드포인트에는 쓸 수 없고, 일반 키로는 Usage/Costs API 를 호출할 수 없다. Owner 가 아니면 이 두 항목은 `[BLOCKED: no admin key]` 로 두고 킥오프에서 기업에 요청한다(docs/KICKOFF_QUESTIONS.md A-1).

### Anthropic Claude — Console 키
1. https://platform.claude.com 에서 Console 가입/로그인 → **Settings → API keys → Create key**(이름·만료 선택) → `.env` 의 `ANTHROPIC_API_KEY`.
2. **Settings → Billing** 에서 크레딧 확인. 공식 pricing FAQ 에 "신규 사용자에게 소량의 무료 크레딧" 이 명시돼 있다(금액 미공개). 부족하면 선불 크레딧 구매(1년 만료). 모델 목록·count_tokens 는 무료.
3. Admin 키(usage_report/cost_report)는 **조직(Organization) 계정 + admin 역할**이어야 생성 가능. 개인 계정은 불가 → 보통 `[BLOCKED: org + admin key]`.

### Google Gemini — AI Studio 키
1. https://aistudio.google.com/apikey → Google 계정 로그인 → ToS 동의 시 프로젝트+키 자동 생성(또는 **Create API key**) → `.env` 의 `GEMINI_API_KEY`.
2. 신규 계정은 **Free tier** 로 시작(Flash/Flash-Lite 계열 $0; 모델별 RPM/RPD 는 AI Studio Rate limits 페이지에서 로그인 후 확인). Free tier 입력은 제품 개선에 사용될 수 있으므로 **기업 샘플 데이터는 보내지 않는다**.
3. 2026-05-28 이후 신규 키는 서비스 계정에 바인딩된 "auth key" 가 기본이다. 기간별 Usage/비용 API 는 없음(AI Studio 대시보드) → ④⑤ 는 `dashboard_only`/로컬 계산.

## 3. 노트북 실행

### VS Code
1. 저장소 폴더를 열고 `notebooks/00_setup_check.ipynb` 를 연다.
2. 오른쪽 위 **Select Kernel → Python Environments → `.venv` (Python 3.12)** 를 고른다. 커널 이름을 고정하려면 아래 한 번 실행 후 **A-PI (uv 3.12)** 를 선택:
   ```bash
   uv run python -m ipykernel install --user --name a-pi --display-name "A-PI (uv 3.12)"
   ```
3. 첫 셀(버전 assert)이 통과하면 환경은 끝.

### Jupyter Lab
```bash
uv run jupyter lab        # 또는 make lab
```

### 순서
`00_setup_check` → `10_openai` → `20_anthropic` → `30_gemini` → `90_compare`

- 00: 버전·키 존재 여부·health·단가표·evidence 배지 (유료 호출 없음)
- 10/20/30: Provider 별 7개 섹션. 각 섹션 마지막 셀이 `save_evidence()` 로 `evidence/<provider>/<항목>.json` 을 남긴다. ②③⑤⑦ 은 **유료 호출 1~2회**(`max_output_tokens<=64`, 보통 $0.001 미만). 키가 없으면 해당 섹션은 BLOCKED 로 기록되고 넘어간다.
- 90: evidence 를 읽어 3사 비교표 + usagelog 집계 + 배지표 (호출 없음)

노트북은 산출물이 아니라 **evidence 생성기**다. 커밋 전 `make strip`(nbstripout) 으로 출력을 지운다 — `.gitattributes` 가 있어 `git add` 시 자동으로도 지워진다.

## 4. Jupyter 없이: CLI

```bash
uv run python -m apicompare.demo openai --no-paid        # ①④⑥ 무료 항목만
uv run python -m apicompare.demo openai                  # 7항목 전부 (유료 1~2회, 호출 전 예상 비용 출력)
uv run python -m apicompare.demo gemini --items 1,6      # 항목 번호 지정
make demo-free                                           # 3사 무료 항목
```

같은 evidence 파일을 남기므로 노트북 대신 써도 된다.

## 5. Colab 대안 (로컬 설치가 안 될 때)

1. 저장소를 Drive 에 올리지 말고 `git clone` 셀로 받는다. `!pip install -U "openai>=3,<4" "anthropic>=1,<2" "google-genai>=2.3,<3" pyyaml jsonschema pandas python-dotenv` 후 `import sys; sys.path.insert(0, "src")`.
2. 키는 **Colab Secrets(왼쪽 🔑)** 에 `OPENAI_API_KEY` 등 이름으로 넣고 `from google.colab import userdata; os.environ["OPENAI_API_KEY"] = userdata.get("OPENAI_API_KEY")` 로 환경변수에 올린다. 노트북 셀에 키를 쓰지 않는다.
3. Colab 런타임 Python 버전이 3.12 미만이면 노트북 첫 셀 assert 가 실패한다 — 그 경우 `sys.version_info >= (3, 10)` 까지만 완화해도 SDK 는 동작하지만, 결과 문서에는 "Colab 3.x 에서 실행" 을 적는다.
4. 생성된 `evidence/*.json` 은 다운로드해서 PR 로 올린다(마스킹된 JSON 이지만 올리기 전 `make secrets`).

## 6. 문제 해결

| 증상 | 원인 / 조치 |
|---|---|
| `anthropic 0.x` 가 설치됨, `output_config`/`httpx2` 없음 | 시스템 Python 3.9 로 `pip install anthropic` 을 했기 때문(pip 가 requires_python 으로 마지막 0.x 를 고름). `uv sync` 로 만든 `.venv` 를 쓰고 `uv run` 으로 실행. 노트북 셀1 assert 가 이걸 잡는다 |
| VS Code 커널 목록에 `.venv` 가 안 보임 | `uv run python -m ipykernel install --user --name a-pi --display-name "A-PI (uv 3.12)"` 후 VS Code 재시작 → **A-PI (uv 3.12)** 선택 |
| `ModuleNotFoundError: apicompare` | 저장소 루트가 아닌 곳에서 실행했거나 `uv sync` 전. 루트에서 `uv sync --group dev` |
| `ImportError ... openai_adapter` | 어댑터가 아직 없음(병행 작업 중). 00 노트북은 "어댑터 미작성" 으로 표시하고 지나간다 |
| `keys()` 가 전부 False | `.env` 가 루트에 없거나 변수명이 다름. `cp .env.example .env` 후 변수명 그대로 사용 |
| OpenAI 429 `insufficient_quota` | 크레딧 소진(rate limit 아님). 충전 또는 다른 팀원 키. 재시도하지 말 것 |
| Anthropic 400 `temperature` | 현행 Claude 모델은 temperature/top_p/top_k 거부. SDK 1.x 는 파라미터 자체를 없앴다(넘기면 클라이언트 TypeError) → 비교 조건에서 제외 |
| Anthropic 529 | 과부하(503 아님). SDK 예외는 `APIStatusError.status_code` 로 분기 |
| Gemini 429 `RESOURCE_EXHAUSTED` | Free tier RPM/RPD 초과. 한도는 프로젝트 단위, RPD 는 태평양시 자정 리셋 |
| Gemini 가 재시도를 안 함 | google-genai 2.31 은 `retry_options` 미지정 시 재시도 0회(문서의 '4회' 와 다름). 비교 실험에서는 오히려 원하는 동작 |
| `git add` 시 nbstripout 오류 | `uv run nbstripout --install --attributes .gitattributes` 재실행 |

## 7. 비용 가드

- 모든 호출은 `max_output_tokens <= 64`(어댑터 기본값). 노트북·demo 에서 더 키우지 않는다.
- SDK 재시도는 3사 모두 `max_retries=0`, `timeout_s=30` — latency 비교 왜곡 방지 + 중복 과금 방지.
- 유료 호출 전 `pricing.estimate_cost()` 로 예상 상한을 보고, 모델은 저가 모델(`gpt-5.4-mini`/`gpt-6-luna`, `claude-haiku-5-5`, `gemini-3.8-flash`)만 쓴다. 종료 예정 모델(`gpt-5-nano`·`gpt-5-mini` 2026-12-11, `gpt-4o-mini`·`gpt-4.1` 2027-01-14)과 신규 사용자 접근이 제한된 Gemini 2.5 는 쓰지 않는다.
- **개인 키 사용분은 개인 부담**이다. 기업 키가 오기 전 실측은 항목당 1~2회로 끝낸다(모두 합쳐도 보통 $0.05 미만). 유료 호출은 `#30-벤치마크` 채널에서만 한다.
- 호출 로그(`data/usage_log.jsonl`)는 토큰·비용·지연·오류 분류만 저장하고 프롬프트/응답 원문은 저장하지 않는다. gitignore 대상.
