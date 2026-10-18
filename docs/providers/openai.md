# OpenAI API 조사
> 작성: kimbong · 기준일: 2026-10-19 · SDK: openai==3.35.1 (Python 3.12)
> 배지 규칙: `[LIVE]` 직접 호출해 확인 / `[DOCS]` 공식 문서 근거 / `[OBSERVED]` 관찰했지만 재현 안 함 / `[BLOCKED: 사유]` 키·권한 없음
> 제목(##, ###)은 바꾸지 않는다. 취합 스크립트가 같은 제목끼리 붙인다.
## 0. 요약 (5줄 이내)
- 모델 호출은 **Responses API(`POST /v1/responses`)** 를 기본으로 쓴다. Chat Completions 는 지원 유지(종료 미공지)지만 GPT-5.4+ 에서 `tools` + `reasoning_effort≠none` 조합이 400 이다(10/18 관찰).
- 응답 `usage` 에 `input_tokens / output_tokens / total_tokens` 가 모두 있고 reasoning 토큰은 `output_tokens` 에 포함되어 output 단가로 과금된다(10/18 `total_tokens=150` 관찰).
- 기간별 Usage/Costs API(`/v1/organization/usage/*`, `/v1/organization/costs`)는 **Admin API 키(조직 Owner 생성) 필수** → §4 Usage 조회는 `[BLOCKED: no admin key]`(표준 키로는 403 `Missing scopes: api.usage.read`, 10/19 실측), §5 는 Costs API 미호출·로컬 계산만 `[LIVE]`. 단가는 3사 모두 API 로 미제공이므로 로컬 가격표로 계산한다.
- 429 하나에 크레딧 소진(`insufficient_quota`/`credit_balance_exhausted`, 10/18 관찰)·속도 제한·지출 한도가 섞여 있어 `error.type/code` 로 분기해야 한다. SDK 기본 timeout 600s·재시도 2회는 latency 비교 시 30s·0회로 통일.
- `GET /v1/models` 는 135개(10/18 관찰) 모델의 `id/created/owned_by/shutdown_date` 만 주고 컨텍스트·단가·capability 는 없다 → 모델 스펙 테이블은 문서에서 수동 구축.
## 0.1 키 발급·인증
- 키 환경변수: `OPENAI_API_KEY`(표준 키, 모든 생성·조회 엔드포인트) / `OPENAI_ADMIN_KEY`(Admin 키, Usage·Costs·Spend Limit 등 Administration 엔드포인트 전용). SDK 3.35.1 은 두 변수와 `OPENAI_ORG_ID`, `OPENAI_PROJECT_ID` 를 자동으로 읽는다. 키가 하나도 없으면 `Missing credentials. Please pass an api_key, workload_identity, admin_api_key, or set the OPENAI_API_KEY or OPENAI_ADMIN_KEY environment variable.`
- 키 종류: ① 표준(Project) 키 — 권한 All / Restricted / Read Only ② Admin 키 — 조직 Owner 만 생성, Administration 엔드포인트 전용이며 일반 엔드포인트에는 사용 불가(예시 값 접두어 `sk-admin…`, 공식 규칙으로 명시된 것은 아님) ③ Service Account 키(프로젝트 소속, 사람 계정과 분리) ④ Workload Identity Federation 단기 토큰(SDK 생성자 `workload_identity`, 프로젝트 서비스 계정에 매핑). 모두 `Authorization: Bearer <key>` 헤더, 선택 헤더 `OpenAI-Organization` / `OpenAI-Project`.
- 발급 경로: platform.openai.com 로그인 → 프로젝트 Settings → API Keys → `+ Create new secret key` (https://platform.openai.com/settings/organization/api-keys). 생성 직후 한 번만 노출되므로 바로 `export OPENAI_API_KEY=...`. Admin 키는 Organization settings → Admin keys (https://platform.openai.com/settings/organization/admin-keys) 에서 Owner 가 생성(API 로는 `POST /organization/admin_api_keys {name, expires_in_seconds≤1년}`, `scopes` 파라미터 없음).
- 무료 티어 / 최소 충전: 신규 API 계정은 선불(prepaid). 공식 help 문서에 무료 체험 크레딧 지급 명시 없음(검색 요약에 '무료 크레딧이 있다면 먼저 소진' 문구만, confidence ~0.6). rate-limits 가이드에 Free 티어(허용 지역 필수, 월 $100 한도) 행이 있으나 RPM/TPM 수치 미기재. 최소 충전 $5, 기본값 $10, 자동 충전 기본 ON, 구매 크레딧 1년 후 만료(help 8264644 검색 요약 기반, 본문 403으로 직접 열람 실패, confidence ~0.7). 누적 $5 → Build(월 $500 한도), $100 → Launch, $500 → Grow. **실습은 최소 $5 충전을 전제로 계획.**
## 1. 모델 목록 조회 [LIVE]
### 엔드포인트
- `GET https://api.openai.com/v1/models` (10/18 관찰 135개), 개별 조회 `GET /v1/models/{model}`. 필수 헤더 `Authorization: Bearer $OPENAI_API_KEY`, 바디 없음, 토큰 과금 없음(가격 페이지에 모델 목록 요금 없음 — 간접 근거).
### 인증
- 표준 API 키(Read Only 권한으로도 충분). Admin 키로는 호출 불가(일반 엔드포인트).
### 응답 필드
| 필드 | 타입 | 설명 |
|---|---|---|
| `object` / `data[].object` | `"list"` / `"model"` | 컨테이너 / 항목 |
| `data[].id` | str | 모델 ID (예 `gpt-5.4-mini`) |
| `data[].created` | int | Unix 초 |
| `data[].owned_by` | str | `openai`, `system` 등 |
| `data[].shutdown_date` | str or null | 종료 예정일. SDK 3.35.1 `types/model.py` 의 `Model.shutdown_date: Optional[str]` 로 접근 가능 (CORRECTED: "REST 문서에만 있다" 는 주장은 틀림) |
### 주의점
- 컨텍스트 윈도우·최대 출력·단가·capability 필드가 **없다**(Gemini `models.list` 는 토큰 한도 포함). 스펙은 문서(https://developers.openai.com/api/docs/models/{model-id}, 예 gpt-5.4-mini → context 400K, max output 128K)에서만 확인 → 모델 스펙 테이블을 로컬에 하드코딩(`ModelInfo.context_window=None`).
- TTS·임베딩·이미지·Realtime 등 비텍스트 모델이 섞여 있어 접두어/용도 필터링이 필요하다. 종료 예정 모델(deprecations 페이지, 2026-10-18 기준)은 아래 표 — `shutdown_date` 를 모델 테이블에 함께 저장해 자동 경고하도록 설계 권장.

| 모델 | shutdown_date | 비고 |
|---|---|---|
| `gpt-4o-2024-05-13`, `gpt-4.1-nano` | 2026-10-23 | 이번 주 종료 |
| `gpt-5`, `gpt-5-mini`, `gpt-5-nano` | 2026-12-11 | PoC 기간 내 종료 → 비권장. gpt-5-nano 대체 `gpt-5.6-luna` |
| `gpt-4o`, `gpt-4o-mini`, `gpt-4.1` | 2027-01-14 | |
| `gpt-5.4-nano` | 2027-04-01 | |
| `gpt-5.4-mini`, `gpt-6-luna` 등 | 미공지 | gpt-5.4-mini 는 models 페이지 메인 목록에서 사라졌지만 호출 가능(10/18) |
### 예제
```python
from openai import OpenAI
client = OpenAI()  # OPENAI_API_KEY 자동 로드
for m in client.models.list():
    if m.id.startswith("gpt-"):
        print(m.id, m.owned_by, m.created, m.shutdown_date)
```
```bash
curl https://api.openai.com/v1/models -H "Authorization: Bearer $OPENAI_API_KEY"
```
### 출처
- https://developers.openai.com/api/reference/resources/models/methods/list
- https://developers.openai.com/api/docs/models
- https://developers.openai.com/api/docs/models/gpt-5.4-mini
## 2. 모델 호출 [LIVE]
### 엔드포인트
- 주: `POST https://api.openai.com/v1/responses` — quickstart·API overview 가 먼저 안내하는 권장 경로. `input`(문자열 또는 메시지 배열), `instructions`(시스템), `reasoning={"effort": ...}`, `max_output_tokens`, `store`(기본 true), `service_tier`, `text.format`(Structured Outputs).
- 보조: `POST https://api.openai.com/v1/chat/completions` — `messages=[{role, content}]`, `max_completion_tokens`(`max_tokens` 는 deprecated, reasoning 모델과 비호환), `reasoning_effort`, `response_format`. 공식 문구: 'While Chat Completions remains supported, Responses is recommended for all new projects.' deprecations 페이지에 종료 공지 없음 → **"지원 유지, 종료 미공지"** 로 기술('무기한 지원' 표현은 현행 문서에 없음).
- 필수 헤더: `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json`.
### 인증
- 표준 API 키(All 또는 해당 엔드포인트가 허용된 Restricted 키).
### 응답 필드
| 항목 | Responses (`/v1/responses`) | Chat Completions (`/v1/chat/completions`) |
|---|---|---|
| 요청 입력 / 길이 제한 | `input`, `instructions` / `max_output_tokens` | `messages[]` / `max_completion_tokens` |
| 출력 텍스트 | `output[]`(type=`message`) → `content[].text`; SDK 편의 속성 `output_text` | `choices[0].message.content` |
| 종료 상태 | `status` (`completed`/`incomplete`), `incomplete_details.reason` | `choices[0].finish_reason` |
| reasoning / Structured Outputs | `reasoning={"effort": "low"}` / `text.format` | `reasoning_effort="low"` / `response_format` |
| usage 입력 | `usage.input_tokens`, `usage.input_tokens_details.cached_tokens` | `usage.prompt_tokens`, `usage.prompt_tokens_details.cached_tokens` |
| usage 출력 | `usage.output_tokens`, `usage.output_tokens_details.reasoning_tokens` | `usage.completion_tokens`, `usage.completion_tokens_details.reasoning_tokens` |
| usage 합계 | `usage.total_tokens` | `usage.total_tokens` |
| 스트리밍 usage | `response.completed` 이벤트의 `response.usage`(통상 동작, 가이드 미명시) | `stream_options={"include_usage": True}` 필수 → `[DONE]` 직전 추가 chunk |
| tools + reasoning | 가능. hosted tools(web/file search, code interpreter, MCP) 는 Responses 전용 | **GPT-5.4+ 에서 `tools` + `reasoning_effort≠none` 불가 → 400** |
| 공통 | `id`, `model`, `service_tier`(실제 처리 티어; `fast` 로 보내도 `priority` 로 표기), `usage` | |
### 주의점
- **10/18 관찰**: `gpt-5.4-mini` Responses 호출 성공. 같은 모델로 Chat Completions 에 function tools + `reasoning_effort` 를 함께 보내면 **HTTP 400 `invalid_request_error`**. 마이그레이션 가이드 근거: "GPT-5.4부터 Chat Completions 는 reasoning_effort 가 none 이 아닐 때 tool calling 을 지원하지 않음". 관찰된 `error.message` 원문은 노트북 §2 가 저장하는 `evidence/openai/02_call.json` 에 기록한다(이 문서에는 아직 원문 미수록). GPT-6 계열은 tool calling 자체가 Responses 필수 → 도구·reasoning 비교 실험은 Responses 로 통일.
- `store` 기본 true(30일 보관) → 비교 실험에서는 `store=False` 를 고려. `model` 은 레퍼런스상 optional 이지만 항상 명시.
- `max_output_tokens` 도달 시 `status="incomplete"`, `incomplete_details.reason="max_output_tokens"` 이고 visible output 없이 reasoning 토큰만 과금될 수 있다(reasoning 가이드는 초기엔 25,000 토큰 여유 권고). `reasoning.effort` 값 `none|minimal|low|medium|high|xhigh|max` 는 모델별 지원이 다르다(GPT-6 Astra 는 `none` 불가(400), GPT-6.1 Sol 은 `none/minimal` 불가, gpt-5.4-mini 기본 `none`).
- 스트리밍 이벤트 형식이 다르다(Responses typed events vs Chat delta chunk). Chat 의 usage details 하위 필드는 SDK 타입상 전부 Optional(None 가능), Responses 는 필수 int → None 방어는 Chat 경로에만. `service_tier`(`auto|default|flex|fast|ultrafast`)는 티어마다 단가가 달라(§5) 응답 값을 usage 와 함께 기록한다.
### 예제
```python
from openai import OpenAI
client = OpenAI(timeout=30.0, max_retries=0)
r = client.responses.create(
    model="gpt-5.4-mini", instructions="You are concise.",
    input="Say hello in Korean.", max_output_tokens=64, store=False)
print(r.status, r.output_text, r.usage.total_tokens, r.service_tier)
```
```bash
curl https://api.openai.com/v1/responses -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-5.4-mini","input":"Say hello in Korean.","max_output_tokens":64}'
```
### 출처
- https://developers.openai.com/api/docs/quickstart
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/reference/python/resources/responses/methods/create
- https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create
## 3. Token Usage [LIVE]
### 엔드포인트
- 매 응답의 `usage` 객체(`POST /v1/responses`, `POST /v1/chat/completions`), 별도 호출 불필요. 헤더 `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json`.
- 사전 카운트: `POST https://api.openai.com/v1/responses/input_tokens` (`client.responses.input_tokens.count(...)`) → `{object: "response.input_tokens", input_tokens: int}`. 과금·rate limit 포함 여부는 문서에 없음.
### 인증
- 표준 API 키.
### 응답 필드
| Responses 필드 | Chat Completions 필드 | 의미 / `UsageNormalized` 매핑 |
|---|---|---|
| `usage.input_tokens` | `usage.prompt_tokens` | 캐시 포함 총 입력 → `input_tokens` |
| `usage.input_tokens_details.cached_tokens` | `usage.prompt_tokens_details.cached_tokens` | 캐시 읽기(입력에 포함) → `cached_input_tokens` |
| `usage.input_tokens_details.cache_write_tokens` | `usage.prompt_tokens_details.cache_write_tokens` | 캐시 쓰기(GPT-5.6+ 1.25배 과금) → `cache_write_tokens` |
| `usage.output_tokens` | `usage.completion_tokens` | reasoning 포함 총 출력 → `output_tokens` |
| `usage.output_tokens_details.reasoning_tokens` | `usage.completion_tokens_details.reasoning_tokens` | 출력에 포함된 추론 토큰 → `reasoning_tokens`(더하지 말 것) |
| `usage.total_tokens` | `usage.total_tokens` | input + output → `total_tokens` (`total_is_computed=False`) |
### 주의점
- **10/18 관찰**: `usage.total_tokens=150` (gpt-5.4-mini Responses). `total` 필드가 있다(Anthropic 은 없어서 계산). reasoning 토큰은 보이지 않지만 `output_tokens` 에 포함되어 output 단가로 과금된다(예: output 1186 중 reasoning 1024) → 비용 계산은 `output_tokens` 전체를 사용.
- CORRECTED: "스트리밍 시 마지막 chunk 에 전체 usage" 는 Chat 기본 동작이 아니다. `stream_options={"include_usage": True}` 를 줘야 `data: [DONE]` 직전에 usage chunk 가 온다. Responses 스트리밍은 `response.completed` 이벤트의 `response.usage` 가 통상 동작이나 streaming 가이드에 명시되지 않음(실측 필요).
- 두 엔드포인트 필드명이 달라 정규화 레이어가 필요하다. Usage API(§4)에만 보이는 `input_cache_write_tokens`, `input_cache_write_12h_tokens` 는 호출 응답에는 없다. 프롬프트 캐시 최소 1,024 visible tokens, TTL 30분(`prompt_cache_options.ttl="30m"`).
- tiktoken 로컬 추정은 평문에만 유효(역할·경계 토큰·도구 스키마·이미지 미반영). 최신 모델 인코딩 매핑은 미검증(uncertain) → `encoding_for_model` 실패 시 `o200k_base` fallback.
### 예제
```python
r = client.responses.create(model="gpt-5.4-mini", input="hi", max_output_tokens=32)
u = r.usage
print(u.input_tokens, u.output_tokens, u.total_tokens,
      u.input_tokens_details.cached_tokens, u.output_tokens_details.reasoning_tokens)
print(client.responses.input_tokens.count(model="gpt-5.4-mini", input="hi").input_tokens)  # 사전 카운트
```
```bash
curl https://api.openai.com/v1/responses/input_tokens -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" -d '{"model":"gpt-5.4-mini","input":"hi"}'
```
### 출처
- https://developers.openai.com/api/docs/guides/reasoning
- https://developers.openai.com/api/reference/python/resources/responses/methods/create
- https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create
- https://developers.openai.com/api/docs/guides/token-counting
## 4. Usage 조회 [BLOCKED: no admin key]
### 엔드포인트
- `GET https://api.openai.com/v1/organization/usage/completions` — `start_time`(필수, Unix 초), `end_time`, `bucket_width`(`1m|1h|1d`, 기본 `1d`), `limit`(1d: 기본 7/최대 31, 1h: 24/168, 1m: 60/1440), `group_by[]`(`project_id, user_id, api_key_id, model, batch, service_tier, api_source`), 필터 `project_ids/user_ids/api_key_ids/models/batch`, `page`(커서). 헤더 `Authorization: Bearer $OPENAI_ADMIN_KEY`.
- 종류별 엔드포인트 11개: `/usage/embeddings, /images, /moderations, /audio_speeches, /audio_transcriptions, /vector_stores, /code_interpreter_sessions, /web_search_calls, /file_search_calls, /decisions` (hosted tool 비용 비교 시 web/file search 호출 수는 별도 집계).
### 인증
- **Admin API 키 필수.** 공식 근거: Administration overview 의 "To access these endpoints, create an Admin API key" 와 "Admin API keys cannot be used for non-administration endpoints", Usage/Costs 레퍼런스·Cookbook 예제가 모두 `OPENAI_ADMIN_KEY` 사용. 발급: 조직 Owner → https://platform.openai.com/settings/organization/admin-keys (또는 `POST /organization/admin_api_keys`). RBAC 상 'Usage — View usage dashboard and export' 권한도 Org owner 프리셋에만 포함 → Owner 가 아닌 팀원은 대시보드 Usage 조회조차 못 할 수 있다.
- 표준(프로젝트) 키로 호출 시 **403 `PermissionDeniedError` — 'You have insufficient permissions for this operation. Missing scopes: api.usage.read.'**(2026-10-19 실측, `probe_usage_api_with_standard_key()`; 바디가 `{"error": "<문장>"}` 형태로 type/code 없음). 커뮤니티의 404 보고와 다름(CORRECTED: CLI 레퍼런스에 'Admin endpoints require an admin API key' 문구는 없음). `api.usage.read` 스코프 이름은 오류 메시지로만 확인되고 공식 문서에는 미기재.
### 응답 필드
| 필드 | 설명 |
|---|---|
| `object`, `has_more`, `next_page` | `"page"` 컨테이너 + 커서 페이지네이션 |
| `data[].start_time`, `data[].end_time` | 버킷 경계(Unix 초) |
| `data[].results[].input_tokens`, `output_tokens`, `num_model_requests` | 버킷 합계·요청 수 |
| `data[].results[].input_cached_tokens`, `input_uncached_tokens`, `input_cache_write_tokens`, `input_cache_write_12h_tokens` | 캐시 세부(쓰기 토큰은 Usage API 에만 보임) |
| `data[].results[].input_text_tokens`, `output_text_tokens`, `input_image_tokens`, `output_image_tokens`, `input_audio_tokens`, `output_audio_tokens` | 모달리티별 |
| `data[].results[].project_id`, `user_id`, `api_key_id`, `model`, `batch`, `service_tier`, `api_source` | `group_by` 지정 시에만 채워짐(미지정 시 null). `api_source` 는 `agents_api|unlabeled` 만 |
### 주의점
- 학생 팀이 조직 Owner 가 아니면 Admin 키 발급 불가 → 대시보드(platform.openai.com → Usage) 수동 확인 또는 **시뮬레이터가 호출마다 응답 usage 를 자체 로깅(`usagelog.append`)해 집계**하는 설계가 현실적.
- 커서 기반 페이지네이션 필수, 1m 버킷은 최대 1440개(24h). `user_id` 와 `project_id` 그룹/필터 조합은 조직·기간에 따라 400 가능. 데이터 반영 지연(freshness)에 대한 공식 서술 없음 → 호출 직후 조회하면 늦게 나타날 수 있어 수 분~수 시간 후 재조회(실측 과제).
- 2026-08-04 부터 `api_key_id` 차원 지원 → 팀원별 프로젝트 키를 따로 발급하면 `group_by=["api_key_id"]` 로 1인별 사용량 분리 가능. 표준 키 클라이언트와 Admin 키 클라이언트는 분리 생성(인증 방식 미해결 시 'Could not resolve authentication method').
### 예제
```python
import os, time
from openai import OpenAI
admin = OpenAI(admin_api_key=os.environ["OPENAI_ADMIN_KEY"])  # 표준 키 클라이언트와 분리
page = admin.admin.organization.usage.completions(
    start_time=int(time.time()) - 7 * 86400, bucket_width="1d", group_by=["model"])
for b in page.data:
    print(b.start_time, [(r.model, r.input_tokens, r.output_tokens, r.num_model_requests) for r in b.results])
```
```bash
curl "https://api.openai.com/v1/organization/usage/completions?start_time=$(($(date +%s)-604800))&bucket_width=1d&group_by=model" \
  -H "Authorization: Bearer $OPENAI_ADMIN_KEY"
```
### 출처
- https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/completions
- https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/completions
- https://developers.openai.com/cookbook/examples/completions_usage_api
- https://developers.openai.com/api/reference/cli
## 5. 비용 확인 [LIVE]
### 엔드포인트
- ① 실비: `GET https://api.openai.com/v1/organization/costs` — `start_time`(필수), `end_time`, `bucket_width="1d"` 만 지원, `limit`(기본 7, 1~180), `group_by[]`(`project_id, user_id, line_item, api_key_id, api_source`), 필터 `project_ids/api_key_ids/line_items`, `page`. 헤더 `Authorization: Bearer $OPENAI_ADMIN_KEY`.
- ② 호출별 예상 비용: **API 미제공** → 응답 usage × 공식 단가를 로컬 계산(availability `partial`, 키 불필요). 단가는 어떤 API 응답에도 없다(`GET /v1/models` 에 price 없음). 문서 URL 뒤에 `.md` 를 붙이면(https://developers.openai.com/api/docs/pricing.md) Markdown 표를 받을 수 있어 반자동 갱신 스크립트는 가능(포맷 보증 없음).
- 예산 보호(Admin 키): `GET/POST/DELETE /organization/spend_limit` (`{currency:"USD", interval:"month", threshold_amount:<cents>}`, 도달 시 429), `POST/GET/DELETE /organization/spend_alerts`.
### 인증
- Costs API / Spend Limit API: Admin API 키 필수(§4 와 동일) → 이번 조사에서는 **미호출**(Admin 키 없음, `cost_report()` 는 `NotSupported`). 로컬 계산(`pricing.estimate_cost()`, 키 불필요·가격표 수동 유지)만 LIVE 로 확인했고 `evidence/openai/05_costs.json` 도 그 결과다. 배지 `[LIVE]` 는 로컬 계산 기준.
### 응답 필드
| 필드 | 설명 |
|---|---|
| `data[].results[].amount.value`, `amount.currency` | 달러 float (예 `0.06`), 소문자 ISO-4217 `"usd"` |
| `data[].results[].line_item` | 과금 항목(모델별 `group_by` 없음 → 간접 구분) |
| `data[].results[].project_id`, `user_id`, `api_key_id`, `api_source` | `group_by` 지정 시 |
| `data[].results[].quantity`, `quantity_unit` | `tokens | 1000_tokens | duration_seconds | duration_minutes | duration_hours | gibibyte_hours | images | characters | null` |
| `has_more`, `next_page` | 커서 |
### 주의점
- 비용 공식(USD, 단가 $/1M): `(input − cached − cache_write)×in + cached×cached_in + cache_write×in×1.25(GPT-5.6+ 만, 이전 모델 1.0) + output(reasoning 포함)×out`. `pricing.estimate_cost()` 가 이 식을 구현한다.
- 같은 모델도 `service_tier` 별 단가가 다르다: Flex 50%, Batch 50%, Fast(구 Priority) 약 2배, Ultrafast 6배(gpt-6-astra, gpt-6.1-sol 만). 리전 처리(data residency)·FedRAMP 엔드포인트는 2026-03-05 이후 출시 모델에 10% 가산. 272K 초과 long-context 구간은 gpt-5.4, gpt-5.6-*, gpt-6-* 에 별도 단가(예 gpt-5.4 input $5.00).
- Costs API 는 1d 버킷만, 모델별 `group_by` 불가 → 모델 간 비용 비교는 로컬 계산에 의존. 단위 불일치: Costs `amount.value` 는 달러, Spend Limit `threshold_amount` 는 센트(int)·`currency` 는 대문자 `USD`.
- uncertain: 'Costs 엔드포인트는 인보이스와 정합(reconcile)' 문구는 검색 스니펫만 확인(원문 403, Cookbook 본문에는 없음). Batch/Flex "50% 할인" 은 gpt-5.4 표 값에서 산술적으로 50% 이지만 전 모델 보증 없음 → 모델별 표 값을 그대로 기록. 가격은 자주 바뀌고 신규 명칭(gpt-5.6-sol/terra/luna, gpt-6-astra)이 많으니 가격표에 `as_of`·출처를 반드시 함께 기록.
### 예제
```python
PRICE = {"gpt-5.4-mini": (0.75, 0.075, 4.50)}  # $/1M: input, cached, output (as_of 2026-10-18)
def cost_usd(model, u):
    i, c, o = PRICE[model]
    cached = u.input_tokens_details.cached_tokens
    return ((u.input_tokens - cached) * i + cached * c + u.output_tokens * o) / 1e6
print(f"{cost_usd('gpt-5.4-mini', r.usage):.6f}")
```
```bash
curl "https://api.openai.com/v1/organization/costs?start_time=$(($(date +%s)-604800))&group_by=line_item" \
  -H "Authorization: Bearer $OPENAI_ADMIN_KEY"
```
### 출처
- https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/costs
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/models/gpt-5.4-mini
- https://developers.openai.com/cookbook/examples/completions_usage_api

단가표 (USD / 1M tokens, as_of 2026-10-18, 출처: https://developers.openai.com/api/docs/pricing)

| 모델 | input | cached | output | 비고 |
|---|---|---|---|---|
| gpt-5.4-mini | 0.75 | 0.075 | 4.50 | 10/18 실습 모델. 종료 미공지 |
| gpt-5.4 | 2.50 | 0.25 | 15.00 | 272K 초과 구간 input $5.00. Batch/Flex $1.25/$0.13/$7.50 |
| gpt-5.4-nano | 0.20 | 0.02 | 1.25 | 2027-04-01 종료 예정 |
| gpt-6-luna | 0.10 | 0.01 | 0.50 | 현행 최저가, 종료 미공지. 캐시 쓰기 1.25배 |
| gpt-6-astra / gpt-6.1-sol | 10.00 / 2.00 | 1.00 / 0.10 | 50.00 / 10.00 | quickstart 기본 모델(astra). reasoning `none` 불가. Ultrafast 6배 |
| gpt-5.6-sol / terra / luna | 4.00 / 2.00 / 0.20 | 0.40 / 0.20 / 0.02 | 20.00 / 12.00 / 1.20 | 캐시 쓰기 1.25배 |
| gpt-5-mini / gpt-5-nano | 0.25 / 0.05 | 0.025 / 0.005 | 2.00 / 0.40 | 2026-12-11 종료 예정 → PoC 비권장 |
| gpt-4.1 / gpt-4o-mini | 2.00 / 0.15 | 0.50 / 0.075 | 8.00 / 0.60 | 2027-01-14 종료 예정 |

인상 예고: 2026-10-18 기준 OpenAI pricing 페이지에 날짜가 명시된 단가 인상 공지는 없음(Gemini 와 다름). 실질 비용 변동 요인은 종료 일정(§1 표)·service_tier 배수·리전 10% 가산이다.
## 6. 상태 및 오류 확인 [LIVE]
### 엔드포인트
- 헬스체크: `GET /v1/models` (토큰 과금 없음, 키·네트워크 검증; 공식 권고가 아닌 합리적 관행 — uncertain). 생성 경로까지 확인하려면 `max_output_tokens` 최소의 `responses.create`.
- 서비스 상태: https://status.openai.com (APIs 그룹에 Responses / Chat Completions 컴포넌트 별도). CORRECTED: Statuspage API 제공 — `GET https://status.openai.com/api/v2/status.json` → `{"status":{"description":"All Systems Operational","indicator":"none"}}`, `GET /api/v2/components.json` 에 'Chat Completions', 'Responses', 'Agents', 'Fine-tuning', 'Embeddings', 'Batch', 'Realtime' 컴포넌트별 상태. 인증 불필요 → 프로그래매틱 상태 조회 가능.
- 오류: 모든 엔드포인트가 HTTP status + 바디 `{"error": {"message", "type", "code", "param"}}`.
### 인증
- 표준 API 키(status.openai.com 은 인증 불필요).
### 응답 필드
| 필드 / 헤더 | 설명 |
|---|---|
| `error.message`, `error.type`, `error.code`, `error.param` | SDK 예외에서 `e.body`(이미 error 내부 dict — `_client._make_status_error` 가 `body["error"]` 를 벗겨 넘김), `e.status_code`, `e.request_id`. 예외: Admin 엔드포인트 403 은 바디가 `{"error": "<문장>"}` 라 `e.body` 가 문자열(2026-10-19 실측) |
| `x-ratelimit-{limit,remaining,reset}-requests`, `x-ratelimit-{limit,remaining,reset}-tokens` | 한도 6종(reset 예 `1s`, `6m0s`). 프로젝트 범위 `x-ratelimit-{limit,remaining,reset}-project-tokens` 3종 추가 → 총 10개 |
| `retry-after`, `x-should-retry`, `x-stainless-retry-count` | 대기 초(SDK 는 120s 초과면 재시도 안 함) / 서버 재시도 힌트(최우선) / SDK 재시도 횟수 |
| `x-request-id`, `openai-processing-ms` | 로그 상관키(`response._request_id`, `APIStatusError.request_id`) / 서버 처리 시간(네트워크 시간과 분리) |
### 주의점
- **10/18 관찰**: 401 `code=expired_secret_key`(만료된 키 사용), 429 `type=insufficient_quota code=credit_balance_exhausted`(선불 크레딧 소진). 공식 error-codes 페이지에는 `invalid_api_key`, `rate_limit_exceeded`, `model_not_found`, `expired_secret_key` 문자열이 나열되어 있지 않다 → 노트북 §6 에서 더미 키(`INVALID-KEY-FOR-TEST`)·잘못된 모델명으로 `error.code` 실측.
- 429 가 크레딧 소진·속도 제한·지출 한도에 모두 쓰이므로 반드시 `error.type/code` 로 분기한다. 과금/쿼터 429 와 4xx 는 재시도 금지, SDK 재시도와 자체 재시도를 중첩하지 않는다.
- SDK 기본 `timeout=600s`, `max_retries=2`(연결오류·408·409·429·5xx, 재전송 안전한 요청만, 지수 백오프+지터, 스트림 소비 중 오류는 재시도 안 함). **latency 비교 실험은 `OpenAI(timeout=30.0, max_retries=0)`** 으로 통일(ProviderAdapter 기본값과 동일)하고 `x-stainless-retry-count` 로 재시도 없음을 검증. 현재 한도·티어는 https://platform.openai.com/settings/organization/limits.
### 예제
```python
import openai
client = openai.OpenAI(timeout=30.0, max_retries=0)
try:
    raw = client.responses.with_raw_response.create(model="gpt-5.4-mini", input="ping", max_output_tokens=16)
    print(raw.headers.get("x-ratelimit-remaining-tokens"), raw.headers.get("x-request-id"), raw.parse().output_text)
except openai.APIStatusError as e:   # 400/401/403/404/429/5xx 공통 (InternalServerError 포함)
    print(e.status_code, e.body.get("type"), e.body.get("code"), e.request_id)  # e.body 는 이미 error 내부 dict
except (openai.APITimeoutError, openai.APIConnectionError) as e:
    print(type(e).__name__)          # status_code 없음 → TIMEOUT / NETWORK
```
```bash
curl -s https://status.openai.com/api/v2/status.json
```
### 출처
- https://developers.openai.com/api/docs/guides/error-codes
- https://developers.openai.com/api/docs/guides/rate-limits
- https://github.com/openai/openai-python
- https://status.openai.com/

오류 매핑표

| HTTP | Provider type / code | SDK 예외 | 의미 | ErrorCategory |
|---|---|---|---|---|
| 400 | `invalid_request_error` / (param 별) | `BadRequestError` | 잘못된 파라미터. Chat Completions 에서 GPT-5.4+ `tools`+`reasoning_effort≠none`(10/18 관찰), reasoning 모델에 `max_tokens` 사용 등 | BAD_REQUEST |
| 401 | `invalid_request_error` / `expired_secret_key`(10/18 관찰), `invalid_api_key`(더미 키 10/18 실측, "Incorrect API key provided"), 조직 미소속, IP 미허용 | `AuthenticationError` | 키 무효·만료 | AUTH |
| 403 | — / 지역 미지원; Admin 엔드포인트에 표준 키 사용 시 'Missing scopes: api.usage.read'(2026-10-19 실측, 바디 `{"error": "<문장>"}` 로 type/code 없음) | `PermissionDeniedError` | 권한·지역 | PERMISSION |
| 404 | `invalid_request_error` / `model_not_found`(10/18 실측) | `NotFoundError` | 모델·리소스 없음 | NOT_FOUND |
| 429 | `insufficient_quota` / `credit_balance_exhausted`(10/18 관찰) | `RateLimitError` | 선불 크레딧 소진 → 재시도 금지, 충전 필요 | QUOTA_EXHAUSTED |
| 429 | `rate_limit_error` / `slow_down`, "Rate limit reached" | `RateLimitError` | RPM/TPM 초과 → `retry-after` 후 재시도 | RATE_LIMIT |
| 429 | — / `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`, `organization_usage_limit_exceeded` | `RateLimitError` | 지출·사용 한도(Spend Limit API 도달 포함) | SPEND_LIMIT |
| 500 | `server_error` 등 | `InternalServerError` | 서버 오류 | SERVER |
| 503 | `service_unavailable_error` / `server_is_overloaded` | `InternalServerError` | 과부하(Anthropic 의 529 에 대응) | OVERLOADED |
| 408 / 504 또는 status 없음 | — | `APITimeoutError` | 요청 타임아웃(기본 600s → 30s 로 설정) | TIMEOUT |
| status 없음 | — | `APIConnectionError` | DNS·연결 실패 | NETWORK |
## 7. 호출 예제 [LIVE]
### 엔드포인트
- `POST https://api.openai.com/v1/responses` (헤더 `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json`). Chat Completions 동등 예제는 `POST /v1/chat/completions` + `{model, messages}` → `choices[0].message.content`.
### 인증
- 표준 API 키. `pip install openai` → `export OPENAI_API_KEY=...` → `OpenAI()` 가 자동 로드. 노트북에서는 python-dotenv 로 `.env` 를 읽고 키를 셀에 하드코딩하지 않는다.
### 응답 필드
- `id`, `model`(실제 스냅샷), `status`, `output_text`(SDK 편의 속성), `usage.{input_tokens, output_tokens, total_tokens}`(§3), `service_tier`.
### 주의점
- **10/18 관찰**: `gpt-5.4-mini` Responses 호출 성공. quickstart 예제 모델명은 문서 시점마다 바뀜(현재 페이지는 `gpt-6-astra`, $10/$1/$50 로 실습용으로는 비쌈).
- CORRECTED: "저비용 모델로 gpt-5.4-mini 또는 gpt-5-nano 권장" 중 gpt-5-nano 는 2026-12-11 종료 예정이라 PoC 기간상 부적절. 현행 최저가·종료 미공지 모델은 **gpt-6-luna**($0.10/$0.01/$0.50). gpt-5.4-mini 는 종료 미공지로 사용 가능하나 models 페이지 메인 목록에서 사라졌으므로 `GET /v1/models` 실측과 대조 후 확정(킥오프 질문 4).
- 비교 실험 공통 조건: `max_output_tokens` 고정, 시스템 프롬프트 고정, `reasoning.effort` 명시, `store=False`, `timeout=30`, `max_retries=0`.
### 예제
```python
import time
from openai import OpenAI
client = OpenAI(timeout=30.0, max_retries=0)  # reads OPENAI_API_KEY
t0 = time.perf_counter()
r = client.responses.create(model="gpt-5.4-mini",
    input="Write a one-sentence bedtime story about a unicorn.", max_output_tokens=64)
print(r.output_text, r.usage.input_tokens, r.usage.output_tokens, r.usage.total_tokens, f"{time.perf_counter()-t0:.2f}s")
```
```bash
curl https://api.openai.com/v1/responses -H "Content-Type: application/json" \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -d '{"model":"gpt-5.4-mini","input":"Write a one-sentence bedtime story about a unicorn."}'
```
### 출처
- https://developers.openai.com/api/docs/quickstart
- https://github.com/openai/openai-python
- https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create
## 8. 다른 Provider와 다른 점
- **엔드포인트 이원화**: Responses(`/v1/responses`, 권장)와 Chat Completions(지원 유지)가 공존하고 usage 필드명이 다르다(`input_tokens/output_tokens` vs `prompt_tokens/completion_tokens`). Anthropic(messages)·Gemini(generateContent)는 단일 주 엔드포인트 → Simulator 의 OpenAI 어댑터만 `api="responses"|"chat_completions"` 분기와 usage 정규화가 필요하다.
- **GPT-5.4+ Chat 의 tools+reasoning 400**: 도구 호출·reasoning 비교 실험은 Responses 로 통일해야 하고, 기업 기존 연동이 Chat 기준이면 변환 계층이 필요하다(킥오프 질문 12).
- **`total_tokens` 제공**: Anthropic 은 input/output 만 주므로 `UsageNormalized.total_is_computed` 플래그로 출처를 구분한다.
- **reasoning 토큰이 output 에 포함**(`output_tokens_details.reasoning_tokens` 로만 분리). Gemini 는 `thoughtsTokenCount` 가 별도라 합산이 필요 → Simulator 의 '출력 토큰' 정의를 "reasoning 포함" 으로 명시.
- **모델 목록에 스펙 없음**: `/v1/models` 는 컨텍스트·단가·capability 를 주지 않음(Gemini 는 토큰 한도 포함) → 모델 스펙 테이블을 문서 기반으로 수동 유지하고 `shutdown_date` 로 자동 경고.
- **기간별 Usage/Costs API 는 있지만 Admin 키(Owner) 필수**: Gemini 는 해당 API 자체가 없고, OpenAI 는 권한이 선결 조건 → Simulator 는 호출마다 usage 를 자체 로깅하는 경로(`usagelog`)를 기본으로 두고 Admin API 는 선택 기능으로. Costs API 가 USD 를 직접 반환(1d)하지만 모델별 group_by 가 없어 모델 간 비용 비교는 로컬 계산(토큰×단가, `service_tier` 배수 포함)에 의존.
- **Rate-limit 헤더 10종 + Retry-After 가 매 응답에 포함** → Simulator 가 실시간 잔여 한도를 모니터링·경고할 수 있다(`HEADER_WHITELIST_PREFIXES` 의 `x-ratelimit-`).
- **SDK 기본 timeout 600s·재시도 2회** → latency 비교에서는 `timeout=30, max_retries=0` 으로 끄고 `x-stainless-retry-count`·`openai-processing-ms` 로 서버 처리 시간을 분리 측정.
- **사전 토큰 카운팅 엔드포인트 존재**(`POST /v1/responses/input_tokens`; Anthropic count_tokens·Gemini countTokens 와 대응) → 3사 공통 `count_tokens()` 인터페이스 가능. 과금 여부는 미확정.
- **429 의 의미가 3갈래**(크레딧 소진 / 속도 제한 / 지출 한도) → ErrorCategory 매핑은 HTTP 코드만으로는 불가, `error.type/code` 필수. Anthropic 의 크레딧 소진은 메시지('credit balance is too low')로 판별(상태코드 400/402 미확정), Gemini 는 402 라 3사 모두 코드가 다르다.
- **선불 결제 최소 $5(기본 $10), 크레딧 1년 만료, 무료 체험 크레딧 미확인**(Gemini 는 무료 티어 존재) → 팀 예산 계획 시 OpenAI 는 충전을 전제로. 문서 도메인도 platform.openai.com → developers.openai.com 으로 이전(301)되어 출처 URL 갱신 필요.
## 9. 미해결 질문
- [ ] 신규 계정 무료 체험(trial) 크레딧 지급 여부와 최소 충전 $5 / 기본 $10 / 1년 만료 — help.openai.com 403 으로 본문 직접 확인 불가(confidence ~0.6 / ~0.7).
- [x] 에러 코드 문자열 `invalid_api_key`, `rate_limit_exceeded`, `model_not_found`, `expired_secret_key` 가 공식 error-codes 페이지에 미기재 → 더미 키·잘못된 모델명으로 `error.code` 실측 완료(10/18, `evidence/openai/06_errors.json`: 401 `invalid_api_key`, 404 `model_not_found`, 둘 다 type=`invalid_request_error`). `rate_limit_exceeded` 는 미실측.
- [x] Admin 엔드포인트를 표준 키로 호출했을 때 403 `Missing scopes: api.usage.read` 인지 404 인지 → **403 으로 실측 확정**(2026-10-19, 노트북 §4 `probe_usage_api_with_standard_key()`; 바디 `{"error": "<문장>"}`). 남은 것: Admin 키 접두어 `sk-admin…` 은 예시 값 기준으로 공식 규칙 미확인.
- [ ] `POST /v1/responses/input_tokens` 의 과금·rate limit 포함 여부, Responses 스트리밍 `response.completed` 이벤트의 usage 포함 여부(가이드 미명시) — 실측.
- [ ] Chat Completions usage 의 공식 필드 테이블과 Responses create 레퍼런스의 usage 정의 섹션 — 페이지가 너무 커서(50만자) 직접 읽지 못함, 예시 JSON 으로만 확인.
- [ ] pricing 페이지의 신규 모델명(gpt-5.6-sol/terra/luna, gpt-6-astra 등)과 `GET /v1/models` 실측 결과 대조 → 실습 모델 최종 확정(gpt-5.4-mini vs gpt-6-luna).
- [ ] Usage/Costs API 데이터 반영 지연(freshness) — 공식 서술 없음, 실측 과제. 'Costs 엔드포인트는 인보이스와 정합' 문구의 원문 존재 여부(검색 스니펫만 확인).
- [ ] 10/18 관찰한 Chat tools+reasoning 400 의 `error.message` 원문을 `evidence/openai/02_call.json` 에 저장하고 이 문서 §2 에 인용.
## 10. 출처
- https://developers.openai.com/api/reference/resources/models/methods/list
- https://developers.openai.com/api/docs/models · https://developers.openai.com/api/docs/models/gpt-5.4-mini
- https://developers.openai.com/api/docs/quickstart
- https://developers.openai.com/api/reference/resources/responses/methods/create
- https://developers.openai.com/api/reference/python/resources/responses/methods/create
- https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create
- https://developers.openai.com/api/docs/guides/reasoning · https://developers.openai.com/api/docs/guides/token-counting
- https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/completions
- https://developers.openai.com/api/reference/python/resources/admin/subresources/organization/subresources/usage/methods/completions
- https://developers.openai.com/api/reference/typescript/resources/admin/subresources/organization/subresources/usage/methods/costs
- https://developers.openai.com/cookbook/examples/completions_usage_api
- https://developers.openai.com/api/reference/cli
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/guides/error-codes · https://developers.openai.com/api/docs/guides/rate-limits
- https://developers.openai.com/api/docs/api-reference/debugging-requests
- https://github.com/openai/openai-python
- https://status.openai.com/ (Statuspage API: /api/v2/status.json, /api/v2/components.json)
- https://platform.openai.com/settings/organization/api-keys · https://platform.openai.com/settings/organization/admin-keys · https://platform.openai.com/settings/organization/limits
