# Anthropic Claude API 조사

> 작성: kimbong · 기준일: 2026-10-19 · SDK: anthropic==1.15.0 (Python 3.12)
> 배지 규칙: `[LIVE]` 직접 호출해 확인 / `[DOCS]` 공식 문서 근거 / `[OBSERVED]` 관찰했지만 재현 안 함 / `[BLOCKED: 사유]` 키·권한 없음
> 제목(##, ###)은 바꾸지 않는다. 취합 스크립트가 같은 제목끼리 붙인다.

## 0. 요약 (5줄 이내)
- 호출 엔드포인트는 `POST /v1/messages` 하나(스트리밍은 같은 URL에 `stream: true`, 배치는 `/v1/messages/batches`). 응답 `content`는 블록 배열이고 `stop_reason`에 `refusal`이 있다.
- 현행 모델(Opus 5.5 / Sonnet 5.5 / Haiku 5.5 / Fable 5.1)은 thinking 기본 ON이며 `temperature/top_p/top_k`는 SDK 1.x에서 파라미터 자체가 제거됨(넘기면 클라이언트 TypeError, `extra_body`로 보내면 서버 400).
- `usage`에 `total_tokens`가 없고 `input_tokens`는 비캐시 입력만이라 `total_input = input + cache_creation + cache_read`를 로컬에서 계산해야 한다. thinking 토큰은 `output_tokens`에 포함되어 output 단가로 과금.
- 기간별 Usage/Cost API(`/v1/organizations/usage_report/messages`, `/v1/organizations/cost_report`)는 조직(Organization) + Admin 키 필수, SDK 미지원(raw HTTP). 단가는 3사 공통으로 API 미제공.
- 과부하는 503이 아닌 **529 overloaded_error**, 티어 월 지출 한도는 **429 + enforced_spend_limit_reached(retry-after 없음)**, 사용자 설정 한도는 **400**. SDK 예외는 `APIStatusError`로 받아 `status_code`로 분기(`InternalServerError`만 잡으면 529 누락).
## 0.1 키 발급·인증
- 키 환경변수: `ANTHROPIC_API_KEY` (SDK가 자동 읽음). Admin API는 별도 `ANTHROPIC_ADMIN_KEY`로 두는 것을 권장(apicompare 어댑터 관례).
- 키 종류: ① Personal key `sk-ant…api03…`(본인 권한, 조직 탈퇴 시 비활성) ② Service account key(CI/프로덕션용) ③ Workspace key(레거시, 특정 workspace 소속) ④ Admin API key `sk-ant…admin01…`(조직 관리·Usage/Cost·Rate Limits API 전용, **Messages API 호출 불가**) ⑤ OAuth bearer token(`org:admin` scope) / Workload Identity Federation 단기 토큰. 멀티-workspace 키는 매 요청 `anthropic-workspace-id` 헤더 필수.
- 발급 경로: https://platform.claude.com 콘솔 로그인 → Settings > API keys (platform.claude.com/settings/keys) → `Create key` → 이름·만료(3h/1d/7d/30d/custom/Never)·Linked account(personal 또는 service account)·workspace 범위 선택 → 생성 시 한 번만 표시되므로 즉시 복사. 요청 헤더는 `Authorization: Bearer <key>`(1차) 또는 `x-api-key: <key>`(레거시, SDK 기본). Admin 키는 조직 admin 역할만 Console > Admin keys에서 생성 가능.
- 무료 티어 / 최소 충전: 공식 pricing FAQ("Are there free tiers or trials?")에 **신규 가입 시 소액 무료 크레딧 지급**이 명시되어 있으나 금액은 미공개(CORRECTED: "무료 크레딧 없음"은 부정확). 이후는 선불 크레딧(Console > Settings > Billing > Buy credits, 구매 후 1년 만료, 환불 불가). **최소 구매 금액은 조회한 공식 문서에서 확인되지 않음(open question)**. 사용 티어(Evaluation → Start → Build → Scale → Custom)는 결제 이력으로 자동 승급, 월 지출 한도 Start $500 / Build $1,000 / Scale $200,000. Max 5x/20x·Team 구독자는 월 $100/$200/최대 $500(Team 풀) API 크레딧을 Console 조직에 연동 가능(7일 대기 후 claim, 결제 주기 말 소멸). 토큰 카운팅과 모델 목록 조회는 무료.
## 1. 모델 목록 조회 [DOCS]
### 엔드포인트
- `GET https://api.anthropic.com/v1/models` — 조직이 사용 가능한 모델 목록(최신 우선). 쿼리: `limit`(기본 20, 1~1000), `after_id`/`before_id`(커서), `lifecycle[]`(active|deprecated|retired; 기본 active+deprecated).
- `GET https://api.anthropic.com/v1/models/{model_id}` — 단일 모델 조회, alias → 실제 ID 해석.
- 필수 헤더: `x-api-key`(또는 `Authorization: Bearer`), `anthropic-version: 2023-06-01`. `anthropic-beta` 헤더는 모델 엔드포인트에서 deprecated.
### 인증
- 일반 API 키(personal/service account/workspace). Admin 키 불필요. 토큰 과금 없음(무료).
### 응답 필드
| 필드 | 타입 | 의미 |
|---|---|---|
| `data[].id` | string | 모델 ID(예: `claude-opus-5-5`) |
| `data[].display_name` | string | 표시명(예: "Claude Opus 5.5") |
| `data[].created_at` | RFC3339 | 출시일(미상이면 epoch 값 가능) |
| `data[].lifecycle` / `deprecated_at` / `retires_at` | string | active·deprecated·retired, 폐기 일정 |
| `data[].line` | string|null | haiku·sonnet·opus·fable·mythos |
| `data[].max_input_tokens` | int|null | 컨텍스트 윈도우 → `ModelInfo.context_window` |
| `data[].max_tokens` | int|null | `max_tokens` 파라미터 상한 → `ModelInfo.max_output_tokens` |
| `data[].capabilities` | dict | thinking/effort/image_input/pdf_input/structured_outputs/server_tools 등 지원표(`supported: true/false` 리프) |
| `has_more`, `first_id`, `last_id` | - | 커서 페이지네이션 |
### 주의점
- 현행 모델 ID는 **날짜 접미사 없는 고정 스냅샷**이며 alias와 동일: `claude-fable-5-1`, `claude-opus-5-5`, `claude-opus-5`, `claude-opus-4-8`, `claude-sonnet-5-5`, `claude-sonnet-5`, `claude-sonnet-4-6`, `claude-haiku-5-5` (모두 1M 컨텍스트 / 128K 출력). 4.5 이하만 `claude-haiku-4-5-20251001`, `claude-opus-4-5-20251101`, `claude-sonnet-4-5-20250929` 같은 날짜형 full id가 별도로 존재한다(로컬 레퍼런스 models.md 기준).
- 가격 필드는 없다 → Simulator는 id→단가 테이블을 로컬에 유지(`pricing.PRICE_TABLE`).
- `capabilities`는 SDK에서 untyped dict이므로 bracket 접근(`m.capabilities["thinking"]["types"]["adaptive"]["supported"]`). JSON 저장은 `m.to_dict()`.
- 조직이 쓸 수 없는 모델은 목록에 나오지 않고, 호출 시 존재하지 않는 모델과 똑같이 `404 not_found_error("model: <id>")`를 돌려준다(둘을 구분 불가).
- 목록은 모델별 서비스 상태(장애 여부)를 알려주지 않는다. `lifecycle` 미지정 시 retired는 제외.
### 예제
```python
import anthropic
client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
for m in client.models.list():  # auto-paginates (.data 를 쓰지 말 것)
    print(m.id, m.display_name, m.max_input_tokens, m.max_tokens, m.lifecycle)
m = client.models.retrieve("claude-opus-5-5")
print(m.capabilities["thinking"]["types"]["adaptive"]["supported"])
```
### 출처
- https://platform.claude.com/docs/en/api/models/list.md · https://platform.claude.com/docs/en/api/models/retrieve.md · https://platform.claude.com/docs/en/about-claude/models/overview.md · https://platform.claude.com/docs/en/api/overview.md
## 2. 모델 호출 [DOCS]
### 엔드포인트
- `POST https://api.anthropic.com/v1/messages` — Messages API(유일한 기본 호출 경로). 필수 바디: `model`, `max_tokens`, `messages[]`(role user|assistant, content는 string 또는 블록 배열). 선택: `system`, `thinking({type: adaptive, display: summarized|omitted})`, `output_config({effort: low|medium|high|xhigh|max, format: JSON schema})`, `tools`, `stream`, `stop_sequences`, `metadata`, `service_tier`, `cache_control`.
- 변형: ② 같은 URL + `"stream": true` = SSE(`message_start → content_block_delta → message_delta → message_stop`) ③ `POST /v1/messages/batches` = 비동기 배치(50% 할인, 24h 내) ④ `POST /v1/messages/count_tokens` = 사전 토큰 계산.
- 필수 헤더: `x-api-key`(또는 `Authorization: Bearer`), `anthropic-version: 2023-06-01`, `content-type: application/json` (SDK 자동 설정). 레거시 Text Completions(`/v1/complete`)는 SDK 1.x에서 제거.
### 인증
- 일반 API 키. **Admin 키로는 호출 불가.** 선불 크레딧 잔액 필요.
### 응답 필드
| 필드 | 의미 |
|---|---|
| `id` (`msg_...`), `type='message'`, `role='assistant'`, `model` | 식별자·실제 사용 모델 |
| `content[]` | 블록 배열: `TextBlock{type:'text', text}`, `ThinkingBlock{thinking, signature}`, `RedactedThinkingBlock`, `ToolUseBlock{id, name, input}`, `ServerToolUseBlock` ... |
| `stop_reason` | `end_turn` · `max_tokens` · `stop_sequence` · `tool_use` · `pause_turn` · **`refusal`** · `model_context_window_exceeded` |
| `stop_sequence`, `stop_details{type:'refusal', category}` | 중단 세부 |
| `usage` | §3 참조 |
| `._request_id` | SDK 객체 속성(헤더 `request-id`, `req_...`) |
### 주의점
- `content`는 배열 → `block.type == 'text'`를 걸러 `.text`를 읽는다(thinking 블록이 앞에 올 수 있음). API는 stateless라 멀티턴은 전체 history를 매번 전송.
- **temperature / top_p / top_k 제거**: SDK 1.x `messages.create` 시그니처에 파라미터가 없어(로컬 1.15.0에서 확인) 그냥 넘기면 클라이언트 `TypeError`. 서버의 400을 보려면 `extra_body={"temperature": 0.2}`로 보내야 한다. 구모델도 `extra_body`로만 가능.
- **thinking 기본 ON(adaptive)**: `thinking: {type: "disabled"}`는 Opus 5.5 불가(400), Sonnet 5.5는 `between_tools`로만 OFF, Haiku 5.5는 effort ≤ high에서 disabled 허용. 비교 실험은 `output_config.effort`를 고정해 통제. `display: omitted`(현행 기본)여도 thinking 토큰 과금은 동일.
- 현행 모델에서 assistant prefill(마지막 메시지 assistant) 400, `tool_choice: any|tool` 400. 첫 메시지가 반드시 user여야 하는지는 문서 간 상충(§9).
- `stop_reason == 'refusal'`(안전 분류기)과 `model_context_window_exceeded`를 Format 판정 전에 처리. 구조화 출력은 `output_config.format`.
- 비스트리밍 요청이 10분 초과 예상(`max_tokens > 21,333`)이면 SDK가 `ValueError` → `stream=True` 또는 `messages.stream()` 필수.
### 예제
```python
import anthropic
client = anthropic.Anthropic()
msg = client.messages.create(model="claude-haiku-5-5", max_tokens=300,
    messages=[{"role": "user", "content": "안녕, 한 문장으로 자기소개 해줘"}])
print("".join(b.text for b in msg.content if b.type == "text"))
print(msg.stop_reason, msg.usage)
# 서버 400 재현(샘플링 파라미터): client.messages.create(..., extra_body={"temperature": 0.2})
```
### 출처
- https://platform.claude.com/docs/en/api/messages/create.md · https://platform.claude.com/docs/en/build-with-claude/working-with-messages.md · https://platform.claude.com/docs/en/get-started.md · https://platform.claude.com/docs/en/build-with-claude/streaming.md
## 3. Token Usage [DOCS]
### 엔드포인트
- 응답 내 `usage` 객체(`POST /v1/messages`, 모든 응답에 포함). 스트리밍 시 `message_start.message.usage`(input + 캐시 필드 + 초기 output)와 `message_delta.usage`(누적 output; server_tool_use 시 input/cache도 갱신) → `stream.get_final_message().usage`로 합산값.
- 사전 계산: `POST https://api.anthropic.com/v1/messages/count_tokens` (무료, 별도 RPM; 응답 `{"input_tokens": N}`, `model` 필수, 출력 토큰은 사전 계산 불가).
### 인증
- 일반 API 키(usage, count_tokens 모두).
### 응답 필드
| 필드 | 의미 |
|---|---|
| `usage.input_tokens` | **마지막 캐시 브레이크포인트 이후의 비캐시 입력** (총 입력이 아님) |
| `usage.output_tokens` | 출력 토큰, **thinking 포함**, 과금 기준 총합 |
| `usage.cache_creation_input_tokens` | 캐시 쓰기(int|null) |
| `usage.cache_read_input_tokens` | 캐시 읽기(int|null) |
| `usage.cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` | 캐시 쓰기 TTL별 분해(단가 1.25x / 2x) |
| `usage.output_tokens_details.thinking_tokens` | output_tokens 중 추론 분해(재토크나이즈 근사, Optional) |
| `usage.server_tool_use.web_search_requests` / `web_fetch_requests` | 서버 툴 횟수 |
| `usage.service_tier` (standard|priority|batch), `usage.speed` (standard|fast), `usage.inference_geo` | 비용 배수 결정 필드 |

**total 없음 → 계산식(UsageNormalized 매핑)**

| 공통 필드 | Anthropic 산출식 |
|---|---|
| `input_tokens` (과금 관점 총 입력) | `total_input = input_tokens + cache_creation_input_tokens + cache_read_input_tokens` |
| `cached_input_tokens` | `cache_read_input_tokens` |
| `cache_write_tokens` | `cache_creation_input_tokens` |
| `output_tokens` | `output_tokens` (thinking 포함, 그대로) |
| `reasoning_tokens` | `output_tokens_details.thinking_tokens` (더하지 말 것, 이미 포함) |
| `total_tokens` | `total_input + output_tokens`, `total_is_computed=True` |
| rate-limit 관점 입력(ITPM) | `input_tokens + cache_creation_input_tokens` (cache_read 미포함) — 과금 관점과 별도 컬럼 |
### 주의점
- **total_tokens 필드가 없다**(OpenAI와 다름). 캐시 히트 시 `input_tokens`가 매우 작게 나오므로 합산하지 않으면 토큰·비용 비교가 왜곡된다.
- thinking 토큰은 `output_tokens`에 포함되어 과금되고 `max_tokens`에도 포함된다. `thinking_tokens` 분해가 beta 헤더(`thinking-token-count-2026-05-13`) 없이 항상 채워지는지는 미확인(§9) → None 가드.
- `count_tokens`는 추정치이며 캐시 로직 미적용. 서버 툴(web_search 등)·url/file 소스 이미지가 포함된 요청은 400.
- Claude 4.7+ 토크나이저는 동일 텍스트에서 약 30% 더 많은 토큰 → Provider 간 "토큰 수" 비교는 비용($) 기준도 함께. tiktoken으로 Claude 토큰을 추정하면 15~20% 이상 틀림.
- TTFT는 첫 `content_block_delta(text_delta)` 기준으로 측정하고, `display: omitted`가 TTFT를 단축한다는 점을 비교 조건에 기록.
### 예제
```python
msg = client.messages.create(model="claude-haiku-5-5", max_tokens=512,
    messages=[{"role": "user", "content": "Hello"}])
u = msg.usage
total_in = u.input_tokens + (u.cache_creation_input_tokens or 0) + (u.cache_read_input_tokens or 0)
print(total_in, u.output_tokens, total_in + u.output_tokens, u.output_tokens_details)
pre = client.messages.count_tokens(model="claude-haiku-5-5",
    messages=[{"role": "user", "content": "Hello"}]).input_tokens
```
### 출처
- https://platform.claude.com/docs/en/api/messages/create.md · https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md · https://platform.claude.com/docs/en/build-with-claude/token-counting.md · https://platform.claude.com/docs/en/build-with-claude/thinking.md
## 4. Usage 조회 [BLOCKED: org + admin key]
### 엔드포인트
- `GET https://api.anthropic.com/v1/organizations/usage_report/messages?starting_at=<RFC3339>&ending_at=...&bucket_width=1d&group_by[]=model`
- 필수: `starting_at`. 선택: `ending_at`, `bucket_width`(1m|1h|1d, 기본 1d), `group_by[]`(model|workspace_id|api_key_id|account_id|service_account_id|service_tier|context_window|inference_geo|speed), 필터 `models[]`, `workspace_ids[]`, `api_key_ids[]`, `account_ids[]`, `service_account_ids[]`, `service_tiers[]`(standard|batch|priority|flex|flex_discount|priority_on_demand), `context_window[]`(0-200k|200k-1M), `inference_geos[]`, `speeds[]`, `limit`, `page`.
- 버킷 한도: 1m 기본 60/최대 1,440(24h), 1h 기본 24/최대 168, 1d 기본 7/최대 31 → 더 긴 기간은 `next_page` 커서로 반복. 데이터 지연 약 5분, 권장 폴링 1회/분.
- 헤더: `x-api-key: $ANTHROPIC_ADMIN_KEY`, `anthropic-version: 2023-06-01`.
### 인증
- **Admin API key(`sk-ant…admin01…`)** 또는 `org:admin` OAuth 토큰, 또는 workspace에 스코프되지 않은 personal/service account key. 일반 workspace 키는 401/403.
- **조직(Organization) 계정 필수.** 개인 Console 계정은 Settings > Organization에서 조직 생성 → admin 역할로 Admin 키 발급. 이번 조사는 키·조직이 없어 BLOCKED.
### 응답 필드
| 필드 | 의미 |
|---|---|
| `data[].starting_at`, `data[].ending_at` | 버킷 구간 |
| `data[].results[].uncached_input_tokens` | 비캐시 입력(Messages 응답의 `input_tokens`와 **이름이 다름**) |
| `results[].cache_creation.ephemeral_5m_input_tokens` / `ephemeral_1h_input_tokens` | 캐시 쓰기 |
| `results[].cache_read_input_tokens`, `results[].output_tokens` | 캐시 읽기, 출력 |
| `results[].server_tool_use.web_search_requests` | 서버 툴 |
| `results[].model`, `workspace_id`(null=기본), `api_key_id`(null=Playground), `account_id`, `service_account_id`, `service_tier`, `context_window`, `speed`, `inference_geo` | group_by 차원 |
| `has_more`, `next_page` | 페이지네이션 |
### 주의점
- **SDK 미지원**: Python SDK 1.15.0에 이 엔드포인트 메서드가 없다(curl-only 문서) → `requests`/`httpx2`/curl로 raw HTTP. 조직 정보(`GET /v1/organizations/me`)만 `client.beta.organization.retrieve()`로 가능해 Admin 키 유효성 체크에 활용.
- **혼동 경고**: `client.beta.organization.analytics.usage_report / cost_report`는 `/v1/organizations/analytics/*`(Claude Enterprise Analytics API, 별도 Analytics 키)이며 Console 조직의 `usage_report/messages` · `cost_report`와 다른 것이다. Rate Limits API(`client.organization.rate_limits.list(model=...)`)는 SDK에 있음.
- 코드 실행(code execution) 사용량은 usage 엔드포인트에 없고 cost 엔드포인트에만 있음. Claude Platform on AWS에서는 미제공. `group_by[]=inference_geo` 시 2026-02 이전 모델은 `not_available`.
- Claude Code 사용량은 별도 `GET /v1/organizations/usage_report/claude_code?starting_at=YYYY-MM-DD`(Admin 키, 무료)로 분리 집계.
- 키가 없어도 대안은 있다: 호출마다 `usagelog.append()`로 기록 → `usagelog.aggregate(start, end, group_by)`로 자체 집계(`UsageReport.source="usagelog"`). 대시보드: platform.claude.com/usage, platform.claude.com/usage/limits.
### 예제
```python
import os, httpx2 as httpx  # SDK 미지원 → raw HTTP
r = httpx.get("https://api.anthropic.com/v1/organizations/usage_report/messages",
    params={"starting_at": "2026-10-01T00:00:00Z", "ending_at": "2026-10-18T00:00:00Z",
            "bucket_width": "1d", "group_by[]": "model"},
    headers={"x-api-key": os.environ["ANTHROPIC_ADMIN_KEY"], "anthropic-version": "2023-06-01"})
for b in r.json()["data"]: print(b["starting_at"], b["results"])
```
```bash
curl "https://api.anthropic.com/v1/organizations/usage_report/messages?starting_at=2026-10-01T00:00:00Z&bucket_width=1d&group_by[]=model" \
  -H "x-api-key: $ANTHROPIC_ADMIN_KEY" -H "anthropic-version: 2023-06-01"
```
### 출처
- https://platform.claude.com/docs/en/manage-claude/usage-cost-api.md · https://platform.claude.com/docs/en/api/beta/organization/usage_report/retrieve_messages.md · https://platform.claude.com/docs/en/manage-claude/admin-api.md · https://platform.claude.com/docs/en/manage-claude/authentication.md
## 5. 비용 확인 [BLOCKED: org + admin key]
### 엔드포인트
- (A) 사후 실비: `GET https://api.anthropic.com/v1/organizations/cost_report?starting_at=...&ending_at=...&group_by[]=description` — `bucket_width=1d`만 가능, `group_by[]`(workspace_id|description), `limit`(기본 7, 최대 31), `page`. 헤더: `x-api-key: $ANTHROPIC_ADMIN_KEY`, `anthropic-version: 2023-06-01`.
- (B) 호출 단위 예상 비용: API 없음 → §3의 usage 토큰 × 공식 단가표(https://platform.claude.com/docs/en/about-claude/pricing) 로컬 계산. **단가는 어떤 API로도 노출되지 않음**(Models API에 가격 필드 없음).
### 인증
- (A) Admin API key + 조직 계정(§4와 동일) → 이번 조사는 BLOCKED. (B) 자격증명 불필요(공개 단가표) → 키 없이도 `adapter.cost()`로 계산 가능.
### 응답 필드
| 필드 | 의미 |
|---|---|
| `data[].results[].amount` | **센트 단위 decimal string**(예 `"123.45"` = $1.2345) → `Decimal` 파싱 후 /100 |
| `results[].currency` | `"USD"` |
| `results[].cost_type` | tokens · web_search · code_execution · session_usage |
| `results[].token_type` | uncached_input_tokens · cache_creation.ephemeral_5m_input_tokens · cache_creation.ephemeral_1h_input_tokens · cache_read_input_tokens · output_tokens |
| `results[].model`, `description`, `service_tier`(standard|batch), `context_window`, `speed`, `inference_geo`, `workspace_id` | **`group_by[]=description`을 줘야만 채워짐**(아니면 null) |
| `has_more`, `next_page` | 페이지네이션 |
### 주의점
- 1회 호출의 실제 청구액을 돌려주는 필드는 어떤 응답에도 없다 → 호출 단위 비용은 반드시 로컬 계산(`CostEstimate`). 단가표는 코드/설정에 하드코딩하고 변동 시 수동 갱신.
- `cost_report`는 1d 버킷만(시간별 비용은 `usage_report` 토큰 × 단가표로 근사), 약 5분 지연, Priority Tier 비용 미포함.
- Haiku 5.5는 요청별 **캐시 읽기/쓰기 포함 총 입력**이 100,000 토큰을 넘으면 전 구간 2단 단가(0.50 / 2.50) 적용. `inference_geo: us` 1.1x는 이 위에 중첩.
- 캐시 읽기 배수는 모델별로 다름: Opus 5.5·Sonnet 5.5 0.05x, Fable 5.1 0.025x, 그 외 0.1x. 캐시 쓰기 5m 1.25x / 1h 2x. Batch 50% 할인. thinking 토큰은 output 단가.
- [uncertain] Max/Team 구독 크레딧 등 프로모션 크레딧 차감이 `cost_report`에 어떻게 반영되는지(총 사용액 vs 실제 청구액) 문서상 불명확. 크레딧 잔액·월 지출 한도를 읽는 공개 API는 Console 조직에 없음(Spend Limits API는 Claude Enterprise 전용) → 잔액 가드는 `cost_report` 누계 ÷ 자체 입력 예산으로.
### 예제
```python
PRICE = {"claude-opus-5-5": (4, 20, 5, 0.20), "claude-sonnet-5-5": (2, 10, 2.5, 0.10),
         "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01)}  # $/MTok: in, out, cache_write_5m, cache_read
def cost_usd(model, u):
    pin, pout, pw, pr = PRICE[model]
    return (u.input_tokens*pin + u.output_tokens*pout + (u.cache_creation_input_tokens or 0)*pw
            + (u.cache_read_input_tokens or 0)*pr) / 1_000_000
print(f"${cost_usd(msg.model, msg.usage):.6f}")  # apicompare: adapter.cost(model, usage)
```
### 출처
- https://platform.claude.com/docs/en/about-claude/pricing.md · https://platform.claude.com/docs/en/api/beta/organization/cost_report/retrieve.md · https://platform.claude.com/docs/en/manage-claude/usage-cost-api.md · https://claude.com/pricing

단가표 (USD / 1M tokens, as_of 2026-10-18, 출처: https://platform.claude.com/docs/en/about-claude/pricing)

| 모델 | input | cached | output | 비고 |
|---|---|---|---|---|
| claude-fable-5-1 | 10.00 | 0.25 (0.025x) | 50.00 | 캐시 쓰기 5m 12.50 / 1h 20 |
| claude-opus-5-5 | 4.00 | 0.20 (0.05x) | 20.00 | 캐시 쓰기 5m 5 / 1h 8; Batch 2/10; Fast mode 8/40 |
| claude-opus-5 · 4.8 · 4.7 · 4.6 · 4.5 | 5.00 | 0.50 | 25.00 | 캐시 쓰기 5m 6.25 / 1h 10 |
| claude-sonnet-5-5 | 2.00 | 0.10 (0.05x) | 10.00 | 캐시 쓰기 5m 2.50 / 1h 4; Batch 1/5 |
| claude-sonnet-5 | 2.00 | 0.20 | 10.00 | 캐시 쓰기 5m 2.50 / 1h 4 |
| claude-sonnet-4-6 · 4.5 | 3.00 | 0.30 | 15.00 | 캐시 쓰기 5m 3.75 / 1h 6 |
| claude-haiku-5-5 (총 입력 ≤100K) | 0.10 | 0.01 | 0.50 | 캐시 쓰기 5m 0.125 / 1h 0.20; Batch 0.05/0.25 |
| claude-haiku-5-5 (총 입력 >100K) | 0.50 | 0.05 | 2.50 | 캐시 쓰기 5m 0.625 / 1h 1 |
| claude-haiku-4-5 | 1.00 | 0.10 | 5.00 | 캐시 쓰기 5m 1.25 / 1h 2 |

- 공통 배수: Batch API 50% 할인, `inference_geo: us` 1.1x, 1M 컨텍스트 전체 표준 단가(long-context 프리미엄 없음, Haiku 5.5 2단 제외), thinking 토큰 = output 단가. 토큰 카운팅·모델 목록 무료.
- 인상 예고: 조사 시점 공식 pricing 페이지에 **예정된 가격 인상 공지는 확인되지 않음**(Gemini와 다름). 단, 4.7+ 토크나이저가 동일 텍스트에 약 30% 더 많은 토큰을 만들어 실효 비용이 오를 수 있고, Haiku 5.5의 100K 구간 단가 점프(5x)가 사실상 인상 요인이다.
## 6. 상태 및 오류 확인 [DOCS]
### 엔드포인트
- 헬스체크: 전용 `/health` 없음. 가장 저렴한 연결+인증 확인은 `GET https://api.anthropic.com/v1/models`(토큰 과금 0; 200=OK, 401=키, 403=권한). 모델 단위는 `POST /v1/messages/count_tokens`(무료, 별도 RPM 5,000+), 추론 경로까지 보려면 `claude-haiku-5-5`에 `max_tokens=16` "ping". Admin 키 검증 `GET /v1/organizations/me`.
- 오류는 모든 엔드포인트의 HTTP status + 바디 `{"type":"error","error":{"type":...,"message":...,"details":{"error_code":...}?},"request_id":"req_..."}` + 헤더(`request-id`, `retry-after`, `anthropic-ratelimit-*`). 스트리밍 중 오류는 **HTTP 200 뒤 SSE `error` 이벤트**로 도착.
- 장애 공지: status.anthropic.com(로컬 참고자료 기준, 공식 페이지로 재확인 못함). Console: platform.claude.com/usage/limits, platform.claude.com/settings/billing.
### 인증
- 일반 API 키(`/v1/models`, `count_tokens`, `messages`). `/v1/organizations/me`, Rate Limits API는 Admin 자격증명.
### 응답 필드
- 오류 본문: `type='error'`, `error.type`, `error.message`, `error.details.error_code`(선택), `request_id` → `ErrorInfo.provider_type / provider_code / message / request_id`.
- rate-limit 헤더: `retry-after`(초; 모든 429에 있는 건 아님) · `anthropic-ratelimit-requests-limit/-remaining/-reset`(RFC3339) · `anthropic-ratelimit-tokens-limit/-remaining/-reset`(현재 가장 제한적인 토큰 한도, 천 단위 반올림) · `anthropic-ratelimit-input-tokens-*` · `anthropic-ratelimit-output-tokens-*` · `anthropic-priority-input/output-tokens-*`(Priority Tier) · `anthropic-fast-*`(fast mode). 한도 종류 RPM / ITPM(비캐시 입력; cache_read 미포함) / OTPM, 토큰 버킷 방식. `HEADER_WHITELIST_PREFIXES`의 `anthropic-ratelimit-`, `anthropic-priority-`, `request-id`, `retry-after`가 그대로 저장된다.
- SDK 기본값(1.15.0 로컬 확인): `DEFAULT_MAX_RETRIES=2`(지수 백오프, retry-after 준수; 연결 오류·408·409·429·>=500 재시도), `DEFAULT_TIMEOUT=Timeout(connect=5.0, read=600, write=600, pool=600)`. 조정: `anthropic.Anthropic(timeout=30.0, max_retries=0)` 또는 `client.with_options(timeout=5.0, max_retries=5).messages.create(...)`. 타임아웃은 `anthropic.APITimeoutError`. 로그 `ANTHROPIC_LOG=debug`, 베이스 URL `ANTHROPIC_BASE_URL`.
### 주의점
- **529 vs 503**: 과부하는 `529 overloaded_error`(503 아님). SDK 1.15.0에서 `anthropic.OverloadedError`는 `InternalServerError`의 하위가 아니라 `APIStatusError`의 직계 자식(로컬 MRO 확인) → `except InternalServerError`만 두면 529가 빠진다. `RequestTooLargeError`(413)도 같은 구조.
- **권고**: 모든 HTTP 오류를 `except anthropic.APIStatusError as e`로 받아 `e.status_code` / `e.type`(body.error.type, 없으면 None) / `e.response.headers.get("retry-after")` / `e._request_id`로 분기 → `errors.make_error(e, status_code=..., provider_type=..., provider_code=..., retry_after=..., request_id=...)`. 구체 클래스를 먼저 쓰고 싶으면 `RateLimitError → APIStatusError → APIConnectionError` 순. `APIConnectionError`는 `APIStatusError`의 형제(TypeScript와 다름).
- **429 네 가지 경우**: (a) 순간 rate limit(RPM/ITPM/OTPM, `retry-after` 있음) → RATE_LIMIT (b) 티어 월 지출 한도: `error.details.error_code=enforced_spend_limit_reached`, `retry-after` 없음, 다음 달 1일 00:00 UTC까지 지속 → SPEND_LIMIT (c) acceleration limit(급격한 사용 증가) → RATE_LIMIT (d) Claude Code workspace spend limit(`retry-after` 있음) → 현 분류기에서는 RATE_LIMIT(code 미확인).
- **사용자 설정 한도는 400**: `invalid_request_error` + "You have reached your specified API usage limits"(workspace 한도는 "...specified workspace API usage limits") → SPEND_LIMIT. 크레딧 소진은 "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits." 문구 → QUOTA_EXHAUSTED(문구 기반 분류, 상태코드는 매트릭스에 미기재).
- 404는 존재하지 않는 모델과 조직 미허용 모델을 구분하지 않음. 키 만료(생성 시 지정) 후 401. 비스트리밍 10분 초과 예상 시 SDK `ValueError`(HTTP 오류 아님).
- latency 비교 시 `max_retries=0`으로 통일(기본 2회 재시도가 latency를 왜곡). 응답 헤더 전체는 `with_raw_response`로.
### 예제
```python
import anthropic, time
client = anthropic.Anthropic(timeout=30.0, max_retries=0)
try:
    t0 = time.perf_counter()
    raw = client.messages.with_raw_response.create(model="claude-haiku-5-5", max_tokens=16,
        messages=[{"role": "user", "content": "ping"}])
    print("OK", round(time.perf_counter()-t0, 3), raw.headers.get("anthropic-ratelimit-requests-remaining"), raw.headers.get("request-id"))
except anthropic.APIStatusError as e:   # 400/401/403/404/413/429/500/504/529 모두 여기서 status_code 로 분기
    print(e.status_code, e.type, e.response.headers.get("retry-after"), e._request_id)
except anthropic.APIConnectionError as e:  # APITimeoutError 포함(형제 클래스, 마지막에)
    print("network/timeout", type(e).__name__)
```
### 출처
- https://platform.claude.com/docs/en/api/errors.md · https://platform.claude.com/docs/en/api/rate-limits.md · https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python.md · https://platform.claude.com/docs/en/api/overview.md

오류 매핑표

| HTTP | Provider type / code | SDK 예외 | 의미 | ErrorCategory |
|---|---|---|---|---|
| 400 | `invalid_request_error` | `BadRequestError` | 잘못된 파라미터, 미지원 파라미터(temperature·thinking.disabled·prefill·tool_choice any), 32MB 초과 등 | BAD_REQUEST |
| 400 | `invalid_request_error` + "...specified API usage limits" | `BadRequestError` | **사용자/workspace 설정 지출 한도** 도달 | SPEND_LIMIT |
| 400 (문구 기준) | "Your credit balance is too low..." | `BadRequestError` | 선불 크레딧 소진 | QUOTA_EXHAUSTED |
| 401 | `authentication_error` | `AuthenticationError` | 키 누락·오류·만료·폐기 | AUTH |
| 402 | `billing_error` | `APIStatusError`(전용 클래스 없음) | 결제 문제 | QUOTA_EXHAUSTED |
| 403 | `permission_error` | `PermissionDeniedError` | 권한 없음, 지역/검증 제한, Admin 전용 엔드포인트에 일반 키 | PERMISSION |
| 404 | `not_found_error` | `NotFoundError` | 엔드포인트/모델 없음 **또는 조직 미허용 모델**(구분 불가) | NOT_FOUND |
| 409 | `conflict_error` | `ConflictError` | 충돌(SDK 자동 재시도 대상) | BAD_REQUEST |
| 413 | `request_too_large` | `RequestTooLargeError`(APIStatusError 직계) | Messages·count_tokens 32MB, Batch 256MB, Files 500MB 초과 | BAD_REQUEST |
| 422 | - | `UnprocessableEntityError` | 처리 불가 엔티티 | BAD_REQUEST |
| 429 | `rate_limit_error` (+ `retry-after`) | `RateLimitError` | RPM/ITPM/OTPM 초과, acceleration limit | RATE_LIMIT |
| 429 | `rate_limit_error` + `details.error_code=enforced_spend_limit_reached` (retry-after 없음) | `RateLimitError` | **티어 월 지출 한도** 도달 | SPEND_LIMIT |
| 500 | `api_error` | `InternalServerError` | 내부 오류(백오프 재시도) | SERVER |
| 504 | `timeout_error` | `InternalServerError`(>=500) | 서버 처리 타임아웃 → 스트리밍/Batch 권장 | TIMEOUT |
| 529 | `overloaded_error` | `OverloadedError`(APIStatusError 직계, **InternalServerError 아님**) | API 과부하(503 아님) | OVERLOADED |
| (없음) | - | `APITimeoutError` | 클라이언트 timeout(기본 600초, 2회 재시도 후) | TIMEOUT |
| (없음) | - | `APIConnectionError` | 네트워크 실패(`.__cause__`에 httpx2 예외) | NETWORK |
| 200 | `stop_reason='refusal'` / SSE `error` 이벤트 | 예외 없음 | 안전 분류기 거절 / 스트리밍 중 오류(바디 `error.type`으로 재분류) | CONTENT_BLOCKED / type별 |
## 7. 호출 예제 [DOCS]
### 엔드포인트
- `POST https://api.anthropic.com/v1/messages` (headers: `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json`).
### 인증
- `ANTHROPIC_API_KEY` 환경변수(또는 `anthropic.Anthropic(api_key=...)`). `.env` + python-dotenv 권장, 코드에 하드코딩 금지(노출 시 즉시 삭제). 선불 크레딧(또는 Max/Team 연동 크레딧) 잔액 필요.
### 응답 필드
- `msg.id`, `msg.model`, `msg.content[i].type / .text`, `msg.stop_reason`, `msg.usage.input_tokens`, `msg.usage.output_tokens`, `msg.usage.cache_*_input_tokens`, `msg.usage.output_tokens_details.thinking_tokens`, `msg._request_id`. curl 응답 JSON도 동일 구조: `{"id":"msg_...","type":"message","role":"assistant","content":[{"type":"text","text":"..."}],"model":"claude-haiku-5-5","stop_reason":"end_turn","stop_sequence":null,"usage":{"input_tokens":12,"output_tokens":6}}`.
### 주의점
- 설치 `pip install anthropic` (Python 3.10+). **시스템 Python 3.9에서는 pip가 0.125.0(마지막 0.x)을 설치**해 `httpx2`/`output_config`/`between_tools`가 없는 구 SDK로 실습이 꼬인다 → 노트북 첫 셀에 `assert sys.version_info >= (3,10)`과 `assert anthropic.__version__.startswith('1.')`. 이 저장소는 uv로 1.15.0 고정.
- 예제 모델은 가장 저렴한 `claude-haiku-5-5`($0.10/$0.50 per MTok) 권장. Opus 5.5는 $4/$20.
- 현행 모델은 thinking 기본 ON이라 짧은 질문에도 `output_tokens`가 커질 수 있음 → 비교 실험은 `output_config={"effort": "low"}`로 통제(Haiku 5.5만 `thinking: disabled` 허용, Opus 5.5 불가).
- `temperature` 등 샘플링 파라미터는 공통 파라미터 세트에서 제외(SDK 1.x TypeError / extra_body 400).
- 스트리밍: `with client.messages.stream(...) as s: for text in s.text_stream: ...; final = s.get_final_message()`. 비동기: `AsyncAnthropic` + `await`(Jupyter 이벤트 루프에서 그대로 동작). CLI 대안: `brew install anthropics/tap/ant` → `ant messages create --model ... --max-tokens ... --message '{...}'`.
- 노트북 셀 순서 권장: ① 모델 목록 → ② 단일 호출 + latency → ③ usage 해부 → ④ 비용 계산 → ⑤ 예외 처리. 키 없는 환경에서는 `get_adapter("anthropic").mode == "NO_KEY"` 경로로 `[BLOCKED: no key]`가 찍히는지 확인.
### 예제
```python
import anthropic  # pip install anthropic ; export ANTHROPIC_API_KEY=...
client = anthropic.Anthropic()
msg = client.messages.create(model="claude-haiku-5-5", max_tokens=300,
    messages=[{"role": "user", "content": "대한민국의 수도는?"}])
print("".join(b.text for b in msg.content if b.type == "text"))
print(msg.usage.input_tokens, msg.usage.output_tokens, msg.stop_reason)
```
```bash
curl https://api.anthropic.com/v1/messages -H "x-api-key: $ANTHROPIC_API_KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-haiku-5-5","max_tokens":300,"messages":[{"role":"user","content":"대한민국의 수도는?"}]}'
```
### 출처
- https://platform.claude.com/docs/en/get-started.md · https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python.md · https://platform.claude.com/docs/en/build-with-claude/working-with-messages.md · https://platform.claude.com/docs/en/get-api-key.md
## 8. 다른 Provider와 다른 점
- **usage에 total_tokens가 없다** — input / output / cache_creation / cache_read를 따로 주고 총합은 클라이언트 계산. → Simulator 공통 스키마에 `total_tokens(계산값)` 컬럼과 Provider별 산출식을 명시(`UsageNormalized.total_is_computed`).
- **input_tokens는 "마지막 캐시 브레이크포인트 이후" 토큰만** — 캐시 히트 시 매우 작게 나오므로 `input + cache_creation + cache_read`로 합산하지 않으면 비용·토큰 비교가 왜곡된다. → 과금 관점(캐시 포함)과 rate-limit 관점(cache_read 제외) 입력을 별도 컬럼으로.
- **thinking 토큰이 output_tokens에 포함·output 단가 과금, 현행 모델은 thinking 기본 ON** — 타 Provider의 비추론 모델과 비교할 때 `output_config.effort`를 고정하거나 `reasoning_tokens` 열을 따로 기록. 모델별 thinking 제어 가능 여부(Opus 5.5 불가 / Sonnet 5.5 between_tools / Haiku 5.5 disabled)를 어댑터에 반영.
- **temperature / top_p / top_k 제거(SDK 1.x TypeError, 서버 400)** — OpenAI/Gemini와 "temperature 고정" 공통 조건 설계가 Claude에서는 불가 → 모델별 파라미터 어댑터(`generate(**kwargs)`에서 Claude는 샘플링 키를 드롭하거나 명시적으로 거부).
- **기간별 Usage/Cost API는 Admin 키 + 조직 계정 + SDK 미지원(raw HTTP)** — 개인 계정 불가. 학생 팀은 Console에서 조직 생성 → admin 역할 → Admin 키 발급이 선행 작업. 그 전까지는 `usagelog.aggregate()`가 대안.
- **모델 메타데이터가 풍부** — `GET /v1/models`가 `max_input_tokens`, `max_tokens`, `capabilities`, `lifecycle/retires_at`를 돌려줘(OpenAI는 컨텍스트 미제공) 모델 선택 UI에 활용 가능. 단 가격은 없음.
- **모델 ID가 날짜 접미사 없는 고정 스냅샷(= alias)** — OpenAI의 날짜형 스냅샷, Gemini의 `-latest` 패턴과 다르고, 없는 모델과 조직 미허용 모델이 모두 404 not_found_error.
- **과부하 529 / 처리 타임아웃 504 / 티어 지출 한도 429+enforced_spend_limit_reached / 사용자 한도 400** — 오류 분류를 Provider별로 매핑해야 하며 SDK에서는 `APIStatusError` + `status_code` 분기가 안전(`OverloadedError`는 `InternalServerError` 하위가 아님).
- **Rate limit이 응답 헤더로 매우 상세히 노출**(`anthropic-ratelimit-requests/tokens/input-tokens/output-tokens-limit/remaining/reset` + `retry-after`) — 호출마다 remaining을 로깅하면 실시간 잔여 한도 대시보드가 쉬움. 설정된 한도 자체는 Admin 키로 Rate Limits API(SDK 포함) 조회 가능.
- **content가 블록 배열, stop_reason에 refusal·model_context_window_exceeded** — Format 준수 판정 전에 블록 타입 필터링과 refusal 처리(CONTENT_BLOCKED)를 먼저. 구조화 출력은 `output_config.format`(JSON schema).
- **4.7+ 토크나이저가 동일 텍스트에 약 30% 더 많은 토큰** — Provider 간 "토큰 수" 비교는 토크나이저 차이를 반영해 비용($) 기준도 함께 비교해야 공정.
- **선불 크레딧(1년 만료) + 티어별 월 지출 한도(Start $500 / Build $1,000 / Scale $200K), Max/Team 구독자는 월 $100~$500 API 크레딧 연동 가능** — 팀원 중 Max/Team 구독자가 있으면 PoC 비용을 크레딧으로 충당. Workspace별 spend limit·rate limit을 설정할 수 있어 팀원/실험별 workspace로 비용 격리 + `group_by[]=workspace_id` 집계가 동시에 가능.
## 9. 미해결 질문
- [ ] 최소 크레딧 구매 금액(과거 $5?)과 신규 가입 무료 크레딧의 **금액** — 공식 pricing/get-api-key/authentication/support 문서에서 미확인. Console Billing(platform.claude.com/settings/billing)에서 실제 가입 후 확인.
- [ ] `usage.output_tokens_details.thinking_tokens`가 beta 헤더(`thinking-token-count-2026-05-13`) 없이 모든 요청에 기본 포함되는지 — 레퍼런스에는 표준 필드로 기재, 실제 호출로 검증 권장.
- [ ] Python SDK PyPI 최신 릴리스 버전 — GitHub main pyproject.toml은 1.15.0, 이 저장소의 uv 환경도 `anthropic.__version__ == 1.15.0`으로 확인됨(PyPI 상 더 새로운 릴리스 유무는 미확인).
- [ ] 서비스 상태 페이지 URL(status.anthropic.com) — 로컬 참고자료에서만 확인, 허용 도메인 내 공식 문서에서 재확인 못함.
- [ ] `cost_report`에 Max/Team 연동 프로모션 크레딧 차감이 어떻게 반영되는지(총 사용액 vs 실제 청구액).
- [ ] Admin API key 생성 절차 세부(Console 메뉴 경로) — "조직 admin 역할만 생성 가능"까지만 확인.
- [ ] Evaluation 티어(신규 조직)의 구체적 RPM/ITPM 수치 — Start 티어보다 낮다고만 명시.
- [ ] `messages[0].role`이 반드시 user여야 하는지 — 공식 release notes(2024-10-08)는 제약 해제, 로컬 참고자료는 400으로 상충. 실습 노트북에서 직접 확인(마지막 메시지 assistant prefill은 4.6+에서 확실히 400).
- [ ] 크레딧 소진 오류의 HTTP 상태코드 — 매트릭스는 메시지 원문만 확인("credit balance is too low"); apicompare `classify_http`는 400/429 어느 쪽이든 문구로 QUOTA_EXHAUSTED 분류.
- [ ] Claude Code workspace spend limit 429의 `details.error_code` 값 — 미확인이라 현 분류기에서는 RATE_LIMIT으로 떨어짐.
## 10. 출처
- §1 모델 목록: https://platform.claude.com/docs/en/api/models/list.md · https://platform.claude.com/docs/en/api/models/retrieve.md · https://platform.claude.com/docs/en/about-claude/models/overview.md · https://platform.claude.com/docs/en/api/overview.md
- §2·§7 호출/예제: https://platform.claude.com/docs/en/api/messages/create.md · https://platform.claude.com/docs/en/build-with-claude/working-with-messages.md · https://platform.claude.com/docs/en/get-started.md · https://platform.claude.com/docs/en/build-with-claude/streaming.md · https://platform.claude.com/docs/en/get-api-key.md
- §3 Usage: https://platform.claude.com/docs/en/build-with-claude/prompt-caching.md · https://platform.claude.com/docs/en/build-with-claude/token-counting.md · https://platform.claude.com/docs/en/build-with-claude/thinking.md
- §4 Usage API / Admin: https://platform.claude.com/docs/en/manage-claude/usage-cost-api.md · https://platform.claude.com/docs/en/api/beta/organization/usage_report/retrieve_messages.md · https://platform.claude.com/docs/en/api/beta/organization/cost_report/retrieve.md · https://platform.claude.com/docs/en/manage-claude/admin-api.md · https://platform.claude.com/docs/en/manage-claude/authentication.md
- §5 비용: https://platform.claude.com/docs/en/about-claude/pricing.md · https://claude.com/pricing
- §6 오류/SDK: https://platform.claude.com/docs/en/api/errors.md · https://platform.claude.com/docs/en/api/rate-limits.md · https://platform.claude.com/docs/en/cli-sdks-libraries/sdks/python.md · https://github.com/anthropics/anthropic-sdk-python/blob/main/MIGRATION.md
