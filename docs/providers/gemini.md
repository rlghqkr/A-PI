# Google Gemini API 조사

> 작성: kimbong · 기준일: 2026-10-19 · SDK: google-genai==2.31.0 (Python 3.12)
> 배지 규칙: `[LIVE]` 직접 호출해 확인 / `[DOCS]` 공식 문서 근거 / `[OBSERVED]` 관찰했지만 재현 안 함 / `[BLOCKED: 사유]` 키·권한 없음
> 제목(##, ###)은 바꾸지 않는다. 취합 스크립트가 같은 제목끼리 붙인다.
> 현재 저장소 .env 에 GEMINI_API_KEY 가 없어 7개 항목 모두 `[DOCS]` 다. 키 발급 후 노트북(`uv run python -m apicompare.demo gemini`)으로 `[LIVE]` 승격 예정.

## 0. 요약 (5줄 이내)

- 모델 목록·호출·토큰 usage·오류 확인은 표준 API 키 하나(헤더 `x-goog-api-key`)로 전부 가능하고, 모델 메타데이터(컨텍스트·출력 한도, thinking 지원)는 3사 중 가장 풍부하다.
- 호출 API 가 2개 공존한다: `generateContent`(완전 지원, 유지) 와 신규 권장 `Interactions`(`POST /v1beta/interactions`). usage 필드명이 서로 달라 어댑터 정규화가 필수다.
- 기간별 Usage/Cost 를 돌려주는 1급 API 가 없다(OpenAI Admin Usage·Anthropic Usage Admin API 와의 가장 큰 차이). AI Studio 대시보드 또는 Google Cloud OAuth 가 필요한 간접 수단(Cloud Monitoring BETA 토큰 메트릭, BigQuery billing export)만 있다.
- 단가는 API 로 제공되지 않아 로컬 계산(출력 단가는 thinking 토큰 포함). 2026-12-01 / 2027-01-01 가격 인상이 예고돼 있다.
- SDK 함정 2개: ① `retry_options` 미지정 시 재시도 없음(문서의 '4회' 와 다름) ② Gemini 4·3.6+ 모델은 temperature/top_p/top_k 를 무시하고 deprecation warning 헤더를 돌려준다.

## 0.1 키 발급·인증

- 키 환경변수: `GEMINI_API_KEY` (또는 `GOOGLE_API_KEY`; 둘 다 설정되면 `GOOGLE_API_KEY` 우선). REST 는 헤더 `x-goog-api-key: $GEMINI_API_KEY` (Bearer 아님). SDK 는 `genai.Client()` 가 환경변수를 자동 인식.
- 키 종류:
  - ① **Auth key** — 2026-05-28 부터 AI Studio 신규 키 기본값. Google Cloud 서비스 계정에 바인딩되며 기본적으로 Generative Language API(Gemini API)로 제한. 단, Auth key 로 보낸 요청은 '서비스 계정 usage metrics 에 기록되지 않음'(§4 참조).
  - ② **Standard key(legacy)** — 프로젝트에 과금/쿼터만 연결, 호출자 식별 불가. '제한 없는(unrestricted) standard key' 는 API 가 거부하고, API 제한이 걸린 standard key 만 동작. 2026-05-07 부터 장기 휴면 unrestricted key 차단 → 오래된 키로 PoC 를 재개하면 401/403 전에 API 제한 설정을 먼저 확인.
  - ③ Live API 용 ephemeral token(별도, 이번 조사 범위 밖).
  - 모든 키는 Google Cloud 프로젝트에 귀속되며 발급에는 Project Editor 등 IAM 권한이 필요. Viewer 역할은 대시보드 열람만 가능하고 키 생성/삭제 불가.
- 발급 경로: https://aistudio.google.com/apikey 에 Google 계정으로 로그인 → ToS 동의 시 신규 사용자는 프로젝트+키가 자동 생성됨 → 'Create API key' 로 추가 생성. 기존 Cloud 계정 사용자는 프로젝트를 AI Studio 로 import. 레이트리밋 실제 수치는 https://aistudio.google.com/rate-limit 에서 로그인 후 확인(문서 정적 텍스트에 없음).
- 무료 티어 / 최소 충전:
  - **Free tier 있음.** 모든 신규 계정은 Free tier 로 시작(rate-limits 문서 'Free: An active project or free trial', 지출 한도 N/A). 신용카드 불필요 여부는 공식 문서에 명시가 없고 키 자동 발급 흐름상 **불필요로 추정**(confidence 0.7). Free tier 제공 모델: 2.5 Pro/Flash/Flash-Lite, 3.x Flash/Flash-Lite 계열. **Gemini 4 Argon·3.1 Pro Preview 는 Free tier 없음.** Free tier 데이터는 제품 개선에 사용될 수 있음(Paid tier 는 미사용).
  - **Paid(Tier 1) 전환**: AI Studio Projects 페이지 'Set up billing' → 결제수단 등록 + **최소 $5 선불(prepay)** 또는 Postpay(과도기 배정, 선택지 아님). 선불 상한 $5,000, Prepay 크레딧은 Gemini API 전용. Tier 2 = 누적 $100 지출 + 3일, Tier 3 = 누적 $1,000 + 30일. Tier 는 결제계정 단위로 상속.
  - **Tier 별 10분 롤링 지출 한도**: Tier 1 $10 / Tier 2 $50 / Tier 3 $200 / Free N/A → 초과 시 429 RESOURCE_EXHAUSTED. Billing tier cap: Tier 1 $250, Tier 2 $2,000, Tier 3 $20,000~$100,000+. 부하 테스트 시 Tier 1 의 실질 상한은 10분 $10.
  - 선불 잔액 소진 시 HTTP 402 `payment_required`. Google Cloud $300 무료 체험 크레딧은 AI Studio Gemini API 비용에 사용 불가. Google AI Pro/Ultra 개인 구독은 API usage tier 와 무관(웹 UI 혜택만).
  - 한도는 API 키가 아니라 **프로젝트 단위**(RPM/TPM/RPD), RPD 는 태평양시 자정 리셋.

## 1. 모델 목록 조회 [DOCS]

### 엔드포인트
- `GET https://generativelanguage.googleapis.com/v1beta/models` — 페이지네이션(`pageSize` 기본 50, 최대 1000, `pageToken`)
- `GET https://generativelanguage.googleapis.com/v1beta/models/{model}` — 단일 모델
- 필수 헤더: `x-goog-api-key: $GEMINI_API_KEY`
### 인증
- 표준 Gemini API 키. 추가 권한 불필요.
### 응답 필드
| 필드 | 설명 | 공통 매핑(ModelInfo) |
|---|---|---|
| `name` | `models/gemini-3.8-flash` 형식 | `id` |
| `baseModelId`, `version`, `displayName`, `description` | 식별·설명 | `display_name` |
| `inputTokenLimit` | 컨텍스트 한도 | `context_window` |
| `outputTokenLimit` | 최대 출력 토큰 | `max_output_tokens` |
| `supportedGenerationMethods[]` | generateContent, countTokens 등 (SDK: `supported_actions`) | `capabilities` |
| `thinking` (bool), `temperature`, `maxTemperature`, `topP`, `topK` | thinking 지원·기본 샘플링 값 | `capabilities` |
| `nextPageToken` | 다음 페이지 | - |
### 주의점
- 가격·지식 컷오프·deprecation 날짜는 **포함되지 않음** → 가격은 pricing 페이지, 수명주기는 deprecations 페이지. `ModelInfo.shutdown_date` 는 Gemini 에서 None.
- SDK Model 객체 속성은 snake_case(`input_token_limit` 등)이며 `supportedGenerationMethods` 는 `supported_actions` 로 노출(README 예제 기반, 속성명 세부 confidence 0.75).
- 2.5 세대 모델은 deprecated 는 아니지만 '과거 사용자만 접근 가능' → 목록에 보여도 신규 프로젝트는 호출이 거부될 수 있음. 신규 프로젝트는 3.5 Flash-Lite / 3.8 Flash 권장. changelog: gemini-3.7-flash·3.5-flash 는 2026-10-08 retire(3.8/3.6 으로 자동 라우팅), gemini-4-argon 2026-10-13 GA, gemini-2.0-flash 2026-06-01 shutdown.
### 예제
```python
from google import genai
client = genai.Client()  # GEMINI_API_KEY 환경변수 사용
for m in client.models.list():
    print(m.name, m.input_token_limit, m.output_token_limit, m.supported_actions)
info = client.models.get(model="gemini-3.8-flash")
```
```bash
curl "https://generativelanguage.googleapis.com/v1beta/models?pageSize=100" -H "x-goog-api-key: $GEMINI_API_KEY"
```
### 출처
- https://ai.google.dev/api/models
- https://github.com/googleapis/python-genai
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations

## 2. 모델 호출 [DOCS]

### 엔드포인트
| 경로 | 메서드·URL | 상태 |
|---|---|---|
| (A) generateContent | `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` (스트리밍 `:streamGenerateContent`) | 'remains fully supported' — 유지 |
| (B) Interactions | `POST https://generativelanguage.googleapis.com/v1beta/interactions` (스트리밍 `stream=true`, SSE `event_type: step.delta` 등) | 신규 개발 **권장**, 2026-06 GA |
| (C) OpenAI 호환 | `https://generativelanguage.googleapis.com/v1beta/openai/` (chat.completions, models.list, embeddings) | beta, 일부 파라미터 무시 |
- 필수 헤더: `x-goog-api-key: $GEMINI_API_KEY`, `Content-Type: application/json`. 기본 API 버전 v1beta(`HttpOptions(api_version='v1')` 로 변경 가능).
### 인증
- 표준 Gemini API 키. SDK 는 `GEMINI_API_KEY`/`GOOGLE_API_KEY` 자동 인식.
### 응답 필드
| API | 핵심 필드 |
|---|---|
| generateContent | `candidates[].content.parts[].text`, `candidates[].finishReason`(STOP/MAX_TOKENS/SAFETY/RECITATION/BLOCKLIST/PROHIBITED_CONTENT/SPII/MALFORMED_FUNCTION_CALL/CONTINUATION…), `candidates[].safetyRatings`, `promptFeedback`, `usageMetadata`(+`serviceTier`), `modelVersion`, `responseId`, `modelStatus` |
| Interactions | `id`, `model`, `status`(in_progress/requires_action/completed/failed/cancelled/incomplete/queued), `steps[]`, `output_text`(SDK), `usage`, `errors[]`, `service_tier`, `labels`, `created`/`updated` |
| usage 필드명 차이 | generateContent: `promptTokenCount` / `candidatesTokenCount` / `thoughtsTokenCount` / `totalTokenCount` ↔ Interactions: `total_input_tokens` / `total_output_tokens` / `total_thought_tokens` / `total_tokens` |
- 요청 측 옵션: generateContent 는 `systemInstruction`, `generationConfig`, `tools`, `safetySettings`, `cachedContent`, `serviceTier`(standard/priority/flex → 과금 배수), `store`, `labels`(실험 ID 태깅에 유용), `continuationToken`. Interactions 는 `system_instruction`, `generation_config{max_output_tokens, thinking_level…}`, `previous_interaction_id`(서버측 대화 이어가기), `store`(기본 true), `stream`, `background`.
### 주의점
- **generateContent(유지) vs Interactions(권장)**: Quickstart·text-generation·tokens 가이드는 모두 Interactions 만 다룬다. 'generateContent 는 fully supported 지만 신규 개발은 Interactions 권장' 서술은 interactions / migrate-to-interactions 문서에 있다. (CORRECTED: Quickstart 에 'Generate Content API (Legacy)' 섹션은 존재하지 않는다.) Interactions 는 google-genai >= 2.3.0 필요(2.31.0 충족). REST `Api-Revision: 2026-05-20` 헤더는 2026-06-08 이후 무시됨.
- **temperature 무시**: Gemini 4 및 3.6+ 모델은 `temperature`/`top_p`/`top_k` 커스텀 값을 무시하고 **deprecation warning 헤더**를 반환 → 응답 헤더를 로깅하면 파라미터를 무시한 모델을 자동 감지할 수 있다. 3사 동일 샘플링 조건 비교가 불가능한 모델이 있음을 결과 문서에 명시해야 한다.
- Interactions 는 기본 `store=true`(서버 저장) → 불필요하면 `store=False`. 두 API 의 usage 필드명이 다르므로 `CallResult.api` 를 `generate_content | interactions` 로 구분하고 `UsageNormalized` 로 정규화.
- 2.5 모델은 신규 사용자 접근 제한 → 기본 모델은 `gemini-3.8-flash`.
### 예제
```python
from google import genai
client = genai.Client()
resp = client.models.generate_content(model="gemini-3.8-flash", contents="Why is the sky blue?")
print(resp.text, resp.candidates[0].finish_reason, resp.response_id)
it = client.interactions.create(model="gemini-3.8-flash", input="Hi", store=False)  # 신규 권장 방식, 서버 저장 끄기
print(it.output_text, it.id, it.status)
```
```bash
curl -X POST "https://generativelanguage.googleapis.com/v1beta/interactions" -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" -d '{"model":"gemini-3.8-flash","input":"Explain how AI works in a few words"}'
```
### 출처
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/interactions
- https://ai.google.dev/gemini-api/docs/text-generation
- https://ai.google.dev/gemini-api/docs/migrate-to-interactions

## 3. Token Usage [DOCS]

### 엔드포인트
- 응답 내 `usageMetadata` (`POST …/models/{model}:generateContent`) / `interaction.usage` (`POST …/v1beta/interactions`)
- 사전 카운트: `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:countTokens` (body: `contents` 또는 `generateContentRequest`) — **과금 안 됨**('GetTokens requests are not billed'), inference quota 에도 미포함.
### 인증
- 표준 Gemini API 키.
### 응답 필드
| 필드(generateContent) | 의미 | Interactions 대응 | UsageNormalized(과금 관점) |
|---|---|---|---|
| `promptTokenCount` | 입력(캐시 토큰 포함) | `total_input_tokens` | `input_tokens` 에 포함 |
| `toolUsePromptTokenCount` | 도구 호출 프롬프트 | `total_tool_use_tokens` | `input_tokens` 에 포함 |
| `cachedContentTokenCount` | 캐시된 입력(prompt 에 포함) | `total_cached_tokens` | `cached_input_tokens` |
| `candidatesTokenCount` | 출력(응답 본문) | `total_output_tokens` | `output_tokens` 에 포함 |
| `thoughtsTokenCount` | thinking 토큰(출력 단가 과금) | `total_thought_tokens` | `output_tokens` 에 포함, `reasoning_tokens` |
| `totalTokenCount` | = prompt + toolUsePrompt + thoughts + candidates | `total_tokens` | `total_tokens` (응답 제공, 계산 아님) |
| `promptTokensDetails[]`, `cacheTokensDetails[]`, `candidatesTokensDetails[]`, `toolUsePromptTokensDetails[]` | 모달리티별 `{modality: TEXT/IMAGE/VIDEO/AUDIO/DOCUMENT, tokenCount}` | `*_tokens_by_modality[]` | `raw` |
| countTokens: `totalTokens`, `cachedContentTokenCount`, `promptTokensDetails[]` | 사전 카운트 | - | `count_tokens()` |
- SDK 는 snake_case: `response.usage_metadata.prompt_token_count / candidates_token_count / thoughts_token_count / cached_content_token_count / total_token_count`.
### 주의점
- thinking 토큰은 별도 필드지만 **과금은 출력 단가로 합산** → 과금 관점 `output_tokens = candidatesTokenCount + thoughtsTokenCount`. `totalTokenCount` 정의상 candidates 와 thoughts 는 분리돼 있어 이중 계산이 아니며, Interactions 의 thinking 문서 예시(62 + 171 + 297 = 530)도 `total_output_tokens` 가 thought 를 제외함을 보여준다.
- 비공식 이슈: Gemini API vs Vertex 에서 `candidatesTokenCount` 에 thinking 포함 여부가 다르다는 GitHub 보고가 있어 **실제 응답으로 합산식 검증 필요**(§9).
- SDK `CountTokensResponse` 는 `total_tokens`, `cached_content_token_count` 만 노출 → 모달리티별 사전 분석은 REST 직접 호출. Long decode(continuation) 사용 시 prompt/total 은 모든 hop 의 합. 토큰 ≈ 4자, 100 토큰 ≈ 60~80 영어 단어.
### 예제
```python
resp = client.models.generate_content(model="gemini-3.8-flash", contents=prompt)
u = resp.usage_metadata
out_tokens = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)  # 과금 관점 output
print(u.prompt_token_count, out_tokens, u.cached_content_token_count, u.total_token_count)
pre = client.models.count_tokens(model="gemini-3.8-flash", contents=prompt)
print(pre.total_tokens)  # 과금 없음. Interactions 는 it.usage.total_input_tokens / total_output_tokens / total_thought_tokens / total_tokens
```
```bash
curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:countTokens" -H "x-goog-api-key: $GEMINI_API_KEY" \
  -H "Content-Type: application/json" -d '{"contents":[{"parts":[{"text":"hello"}]}]}'
```
### 출처
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/api/tokens
- https://ai.google.dev/gemini-api/docs/tokens
- https://ai.google.dev/gemini-api/docs/thinking

## 4. Usage 조회 [DOCS]

### 엔드포인트
- **Gemini API 자체에는 기간별 사용량(토큰/요청/비용) 집계 엔드포인트가 없음.** API 가 없는 것은 사실이므로 BLOCKED 가 아니라 `dashboard_only` 로 기록.
- 공식 경로(대시보드): AI Studio Dashboard > Usage https://aistudio.google.com/usage (모델별 요청·토큰), Rate limits/Quota https://aistudio.google.com/rate-limit?timeRange=last-28-days, Projects 페이지(Tier 확인). 대시보드 백엔드 권한: Usage = `monitoring.timeSeries.list`, Rate limit = `cloudquotas.quotas.get`, Spend/Billing cap = `billing.resourceCosts.get` / `billing.resourcebudgets.read`.
- 간접(프로그래매틱, 모두 Google Cloud OAuth2 필요):
  - ① Cloud Console 'APIs & Services' 대시보드 — Generative Language API 의 Traffic/Errors/Latency(응답코드별).
  - ② **Cloud Monitoring** `GET https://monitoring.googleapis.com/v3/projects/{project}/timeSeries?filter=metric.type="…"` — Gemini 전용 토큰 메트릭 `generativelanguage.googleapis.com/generate_content_usage_output_token_count` (**BETA**, labels `model`, `output_modality`, `thinking_enabled`), `quota/generate_content_{free_tier|paid_tier|paid_tier_2|paid_tier_3}_input_token_count/usage`, `quota/generate_content_free_tier_requests/usage`, `quota/generate_requests_per_model/usage` (labels `limit_name`, `method`, `model`; resource `generativelanguage.googleapis.com/Location`; DELTA INT64; 샘플링 후 최대 150초 지연). 일반 메트릭 `serviceruntime.googleapis.com/api/request_count`, `api/request_latencies`, `quota/allocation/usage`, `quota/exceeded`, `quota/limit` 는 요청·쿼터 단위(토큰 없음).
  - ③ **Cloud Billing → BigQuery export** 테이블 `gcp_billing_export_v1_<BILLING_ACCOUNT_ID>` — Paid tier(결제계정 연결) + 사전 export 활성화 필수. US/EU 멀티리전 데이터셋이면 첫 활성화 시 전월부터 소급(최대 5일), 리전 데이터셋은 비소급. 비용 데이터 지연 '보통 하루 이내, 24시간 초과 가능'.
  - ④ **Paid tier 전용 'Logs and datasets'** — GenerateContent/StreamGenerateContent/BatchGenerateContent/Interactions(OpenAI 호환 포함) 요청·응답 전문을 AI Studio 에 저장(기본 55일, 7/14/28/55일 선택), CSV/JSONL/Google Sheets export. Interactions 는 기본 저장, generateContent 는 opt-in. 'Storage for Gemini API logs are only available for projects on the Gemini API paid tier'. 호출 단위 감사 로그 대체 수단.
### 인증
- AI Studio 대시보드: Google 계정 로그인(`login_only`). Cloud Monitoring / APIs & Services: Cloud 프로젝트 IAM(Viewer 이상) + OAuth2(ADC/서비스계정, scope `cloud-platform` 또는 `monitoring.read`) — **Gemini API 키로는 불가**. BigQuery export: 결제계정 관리자 권한 + Paid tier. Cloud Billing 리포트 열람: `billing.accounts.getSpendingInformation`(Billing Account Viewer 이상) 또는 `billing.resourceCosts.get`.
### 응답 필드
| 소스 | 필드 |
|---|---|
| Cloud Monitoring | `timeSeries[].points[].{interval, value}`, `metric.labels.{model, output_modality, thinking_enabled, response_code, method, limit_name}` |
| BigQuery export | `service.description`('Gemini API'), `sku.description`(토큰 종류), `project.id`, `usage_start_time`, `usage.amount`, `usage.unit`, `usage.amount_in_pricing_units`, `usage.pricing_unit`, `cost`, `credits[]` |
| Cloud Billing 리포트 UI | Service 열 'Gemini API', 'Group by SKU + Services filter Gemini API' 로 SKU 별 비용 |
### 주의점
- OpenAI Admin Usage API / Anthropic Usage & Cost Admin API 에 해당하는 1급 엔드포인트가 없음 → 3사 공통 수집 항목은 **'응답 내 usage 필드'로 한정**. Simulator 는 호출마다 `usage_metadata` 를 자체 DB(`usagelog.append`)에 적재해 `usagelog.aggregate()` 로 집계하는 것이 사실상 유일한 공통 경로. 어댑터 `usage_report()` 는 `NotSupported` 또는 `UsageReport(source="usagelog")`.
- **Auth key 로 보낸 요청은 '서비스 계정 usage metrics 에 기록되지 않음'**(api-key 문서). 2026-05-28 이후 신규 키는 Auth key 이므로 Cloud Console/Monitoring 기반 간접 집계가 더 불완전할 수 있음 — Generative Language API 메트릭에도 영향을 주는지는 미확인(§9).
- Cloud Monitoring 토큰 메트릭은 BETA, 쿼터 메트릭은 요청/쿼터 단위. 결제 데이터는 최대 24시간 지연. 비교 서술은 'Gemini 만 usage API 전무' 가 아니라 'Gemini 는 Cloud Monitoring 경유(비용 없음, BETA, OAuth 필요)' 가 정확.
### 예제
```python
from apicompare import usagelog                       # Gemini API 키로는 불가 → 호출별 usage 를 자체 적재해 집계(3사 공통 경로)
report = usagelog.aggregate(start, end, group_by=("model",))
from google.cloud import monitoring_v3                # (선택) Cloud Monitoring, OAuth ADC(gcloud auth application-default login) 필요
c = monitoring_v3.MetricServiceClient()
series = c.list_time_series(name=f"projects/{PROJECT}", interval=interval, view="FULL",
    filter='metric.type="generativelanguage.googleapis.com/generate_content_usage_output_token_count"')
```
```bash
curl "https://monitoring.googleapis.com/v3/projects/$PROJECT/timeSeries?filter=metric.type%3D%22generativelanguage.googleapis.com/generate_content_usage_output_token_count%22&interval.startTime=2026-10-01T00:00:00Z&interval.endTime=2026-10-19T00:00:00Z" \
  -H "Authorization: Bearer $(gcloud auth print-access-token)"   # OAuth, API 키 불가
```
### 출처
- https://ai.google.dev/gemini-api/docs/billing
- https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h
- https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list
- https://ai.google.dev/gemini-api/docs/logs-datasets (그 외 troubleshoot-ai-studio, api-key, rate-limits 는 §10)

## 5. 비용 확인 [DOCS]

### 엔드포인트
- **호출별/기간별 비용을 반환하는 엔드포인트 없음** → `availability: partial`(로컬 계산). 단가표: https://ai.google.dev/gemini-api/docs/pricing ('Last updated 2026-10-16 UTC').
- (간접) Google Cloud Billing Pricing API: `GET https://cloudbilling.googleapis.com/v2beta/skus?filter=service="…"`, `GET https://cloudbilling.googleapis.com/v1beta/skus/{SKU_ID}/prices` — filter 는 service 필드만 지원하므로 먼저 `GET /v2beta/services` 로 서비스 ID 확보. **Gemini Developer API SKU 노출 여부 미검증**이며 공개 SKU 그룹 'Gen AI Gemini Models' 는 전부 Vertex AI(C7E2-9256-1C43) 소속 → 두 가격표는 별개 제품 표면.
- 실제 청구액: Paid tier 면 Cloud Console Billing 리포트(최대 24h 지연)·BigQuery export(§4), Prepay 잔액은 AI Studio 에서만 관리.
### 인증
- 로컬 계산: 불필요(`none`). Cloud Billing 리포트/BigQuery: 결제계정 OAuth 권한 + Paid tier. Pricing API 공개 SKU: Cloud 프로젝트 API 키 + Cloud Billing API 활성화.
### 응답 필드
| 소스 | 필드 |
|---|---|
| 로컬 계산(`CostEstimate`) | `usd`, `breakdown{input, cached, output}`, `price_as_of`, `price_source`, `effective_from` |
| Pricing API | `skus[].{name, displayName, service}`, `prices[].rate.tiers[].{startAmount, listPrice{currencyCode, units, nanos}}`, `prices[].unitInfo{unit, unitDescription, unitQuantity}` |
### 주의점
- 계산식: `cost = (promptTokenCount − cachedContentTokenCount + toolUsePromptTokenCount) × 입력단가 + cachedContentTokenCount × 캐시단가 + (candidatesTokenCount + thoughtsTokenCount) × 출력단가` (USD / 1M). 출력 단가는 thinking 포함('response pricing is the sum of output tokens and thinking tokens'). 모달리티별 단가(오디오 입력 별도)는 `promptTokensDetails[]` 로 분해.
- 가격 인상이 **날짜별로 예약**돼 있어 Simulator 단가표는 '적용일(effective_from)' 컬럼으로 관리(`pricing.py` 의 `scheduled_changes`). 2.5 Pro / 3.1 Pro 는 프롬프트 200k 기준 2단 요금. Batch/Flex = Standard 50%, Priority = 1.8배(`serviceTier` 로 결정). 컨텍스트 캐시 읽기 ≈ 입력단가 10% + 시간당 저장료 별도.
- Free tier 는 $0 이지만 데이터가 제품 개선에 사용될 수 있음(Paid tier 미사용). Gemini 2.5 Flash Image(Nano Banana)는 2026-10-02 shut down.
### 예제
```python
PRICE = {"gemini-3.8-flash": (0.75, 3.75), "gemini-3.5-flash-lite": (0.30, 2.50)}  # USD / 1M (in, out incl. thinking)
u = resp.usage_metadata
cached = u.cached_content_token_count or 0
in_tok = (u.prompt_token_count or 0) - cached + (u.tool_use_prompt_token_count or 0)
out_tok = (u.candidates_token_count or 0) + (u.thoughts_token_count or 0)
p_in, p_out = PRICE["gemini-3.8-flash"]
cost_usd = (in_tok * p_in + cached * p_in * 0.1 + out_tok * p_out) / 1e6
```
```bash
curl "https://cloudbilling.googleapis.com/v2beta/services?key=$GOOGLE_CLOUD_API_KEY"   # 서비스 ID 확보 후 /v2beta/skus?filter=service=... (Gemini SKU 노출 여부 미검증)
```
### 출처
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/billing
- https://docs.cloud.google.com/billing/docs/how-to/get-pricing-information-api
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery

단가표 (USD / 1M tokens, as_of 2026-10-16, 출처: https://ai.google.dev/gemini-api/docs/pricing)

| 모델 | input | cached | output | 비고 |
|---|---|---|---|---|
| gemini-4-argon | 2.00 | ≈0.20 | 10.00 | **2026-12-01 부터 4.00 / 20.00**. Free tier 없음. 2026-10-13 GA |
| gemini-3.8-flash | 0.75 | ≈0.075 | 3.75 | **2027-01-01 부터 1.50 / 7.50**. Free tier 제공. 신규 프로젝트 기본 후보 |
| gemini-3.6-flash | 0.75 | ≈0.075 | 3.75 | 2027-01-01 부터 1.50 / 7.50. 3.6+ 는 temperature 무시 |
| gemini-3.5-flash-lite | 0.30 | ≈0.03 | 2.50 | Free tier 제공 |
| gemini-3.1-flash-lite | 0.25 | ≈0.025 | 1.50 | |
| gemini-3-flash-preview | 0.50 | ≈0.05 | 3.00 | preview |
| gemini-3.1-pro-preview | 2.00 | ≈0.20 | 12.00 | ≤200k 프롬프트 기준. Free tier 없음 |
| gemini-2.5-pro | 1.25 | ≈0.125 | 10.00 | >200k 는 2.50 / 15.00. 2.5 세대는 과거 사용자만 접근 |
| gemini-2.5-flash | 0.30 | ≈0.03 | 2.50 | 2.5 세대는 과거 사용자만 접근 |
| gemini-2.5-flash-lite | 0.10 | ≈0.01 | 0.40 | 2.5 세대는 과거 사용자만 접근 |

- `cached` 열은 매트릭스의 '캐시 읽기 ≈ 입력단가 10%' 근사값(시간당 저장료 별도)이며 모델별 공식 수치는 pricing 페이지에서 재확인. output 은 thinking 토큰 포함. Batch/Flex 50%, Priority 1.8배. Free tier 는 해당 모델 $0.

## 6. 상태 및 오류 확인 [DOCS]

### 엔드포인트
- 헬스체크(가장 저렴): `GET https://generativelanguage.googleapis.com/v1beta/models/{model}` (`client.models.get`, 토큰 소비 없음) 또는 `POST …/models/{model}:countTokens`(과금 안 됨). 200 이면 키·네트워크·모델 접근 OK, 401/403 이면 인증 문제. 실제 생성 경로(429 포함)까지 확인하려면 `max_output_tokens=1~5` 의 generateContent 1회(Free tier 면 무료).
- 오류는 모든 엔드포인트의 HTTP status + 바디 `{"error":{"code":"…","message":"…"}}`. SSE 스트리밍은 `event_type: "error"`.
- 필수 헤더: `x-goog-api-key: $GEMINI_API_KEY`.
### 인증
- 표준 Gemini API 키.
### 응답 필드
| 필드 | 설명 | ErrorInfo 매핑 |
|---|---|---|
| HTTP status | 4xx/5xx | `status_code` |
| `error.code` | **snake_case 문자열**(rate_limit_exceeded, model_not_found…). 표에 없는 코드는 HTTP status 의 snake_case 로 폴백 | `provider_code` |
| `error.message` | 사람이 읽는 메시지(유출 키: 'Your API key was reported as leaked') | `message`(redact) |
| `error.status` (구 포맷) | gRPC 이름(INVALID_ARGUMENT, PERMISSION_DENIED, RESOURCE_EXHAUSTED, UNAVAILABLE…) | `provider_type` |
| `error.details[]` | 추가 정보(429 바디 `retryDelay`/RetryInfo 는 비공식 보고) | `raw` |
| SDK `e.code`(int), `e.message`, `e.status`, `e.details`, `e.response` | `google.genai.errors.APIError` 기반 | 위와 동일 |
### 주의점
- **레이트리밋 헤더 없음**: `Retry-After`, `x-ratelimit-*` 류 응답 헤더가 공식 문서에 없다(OpenAI·Anthropic 과의 차이). `HealthResult.ratelimit` 은 Gemini 에서 빈 dict, `retry_after` 는 None. 현재 사용량·한도는 AI Studio 에서만 확인. 한도는 프로젝트 단위이며 RPM·TPM·RPD 중 하나라도 초과하면 429, Paid tier 10분 롤링 지출 한도($10/$50/$200) 초과도 429 RESOURCE_EXHAUSTED. Priority inference 는 표준 한도의 0.3배 기본.
- **error.code snake_case + gRPC 명 병존**: 신 포맷 `error.code`(snake_case)와 구 포맷 `error.status`(gRPC) 가 문서에 병기되고 SDK `APIError.status` 는 gRPC 이름을 담음 → 둘 다 기록(`provider_code`, `provider_type`). 목록에 없는 코드는 HTTP status snake_case 폴백이므로 어댑터는 **화이트리스트가 아닌 패턴 매칭**.
- **402 payment_required**: 선불 잔액 소진 시 별도 상태코드(OpenAI 는 429 insufficient_quota, Anthropic 은 400 credit balance) → `QUOTA_EXHAUSTED`.
- **SDK 재시도 기본값 함정(CORRECTED)**: troubleshooting 문서는 '429/5xx/timeout 을 지수 백오프로 기본 4회 자동 재시도' 라 쓰지만, google-genai 2.31.0 소스는 `HttpOptions.retry_options=None` → `_api_client.retry_args(None)` 이 `tenacity.stop_after_attempt(1)` 을 반환해 **retry_options 를 명시하지 않으면 재시도 없음**. `HttpRetryOptions()` 를 넘겼을 때의 기본값이 attempts=5(초기 호출 포함), initial_delay 1.0s, max_delay 60s, exp_base 2, jitter 1, http_status_codes (408, 429, 500, 502, 503, 504). apicompare 는 세 Provider 모두 `max_retries=0` 으로 고정하므로 Gemini 는 기본값 그대로가 0회와 일치하고, OpenAI/Anthropic SDK(기본 2회)는 명시적으로 0 으로 내려야 공정 비교가 된다.
- **timeout**: `HttpOptions(timeout=<ms>)` 단위가 **밀리초**(httpx 전달 시 /1000). 기본 timeout 수치는 조사 문서에서 확인되지 않아 명시 권장(apicompare `timeout_s=30` → `timeout=30_000`). 매우 짧은 timeout 이 500 으로 보고되는 이슈(GitHub #1330) 존재. 요청 단위로도 `config={'http_options': {...}}` 전달 가능. REST 직접 호출 시 권고: 1s→2s→4s→8s 지수 백오프 + 지터, 408/429/5xx 만 재시도.
- uncertain: `models.get` 이 '토큰 소비/과금 없음' 이라는 공식 문장은 없음(메타데이터 조회 성격상 타당). `countTokens` 미과금은 billing 문서로 확인. `models.get` 은 429 경로를 검증하지 못하므로 '생성 경로 확인' 은 별도.
### 예제
```python
from google import genai
from google.genai import errors, types
client = genai.Client(http_options=types.HttpOptions(timeout=30_000,   # ms. retry_options 미지정 = 재시도 없음
    retry_options=types.HttpRetryOptions(attempts=1)))                   # 명시적으로 0회 재시도(3사 통일)
try:
    client.models.get(model="gemini-3.8-flash")  # 200 이면 연결·인증 OK
except errors.ClientError as e:   # 4xx
    print("client", e.code, e.status, e.message)
except errors.ServerError as e:   # 5xx
    print("server", e.code, e.status, e.message)
```
```bash
curl -s -o /dev/null -w "%{http_code}\n" "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash" -H "x-goog-api-key: INVALID-KEY-FOR-TEST"   # 400/401/403 재현
```
### 출처
- https://ai.google.dev/gemini-api/docs/api-errors
- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://github.com/googleapis/python-genai/blob/main/google/genai/errors.py

오류 매핑표

| HTTP | Provider type / code | SDK 예외 | 의미 | ErrorCategory |
|---|---|---|---|---|
| 400 | INVALID_ARGUMENT / `invalid_request`, `parameter_unknown` ; FAILED_PRECONDITION / `failed_precondition` | `errors.ClientError` (e.code=400) | 잘못된 요청·파라미터 ; 결제 미설정 등 선행조건 미충족 | BAD_REQUEST |
| 401 | UNAUTHENTICATED / `authentication` | `ClientError` (e.code=401) | 키 누락·무효·만료, 유출 키 차단 | AUTH |
| 402 | - / `payment_required` | `ClientError` (e.code=402) | 선불 잔액 소진 | QUOTA_EXHAUSTED |
| 403 | PERMISSION_DENIED / `permission_denied` | `ClientError` (e.code=403) | 키 권한·API 제한·모델 접근 불가(2.5 세대 신규 사용자 등) | PERMISSION |
| 404 | NOT_FOUND / `not_found`, `model_not_found` | `ClientError` (e.code=404) | 모델·리소스 없음 | NOT_FOUND |
| 409 / 416 | ABORTED / `already_exists`, `aborted` ; OUT_OF_RANGE / `out_of_range` | `ClientError` | 충돌 ; 범위 초과 | BAD_REQUEST |
| 429 | RESOURCE_EXHAUSTED / `rate_limit_exceeded`, `too_many_requests` | `ClientError` (e.code=429) | 분당 RPM/TPM 초과 (Retry-After 헤더 없음) | RATE_LIMIT |
| 429 | RESOURCE_EXHAUSTED / `quota_exceeded` | `ClientError` (e.code=429) | 일일 RPD 초과(태평양시 자정 리셋) | RATE_LIMIT (현행 classify_http; 의미상 일일 쿼터) |
| 429 | RESOURCE_EXHAUSTED / (코드 미문서화) | `ClientError` (e.code=429) | Paid tier 10분 롤링 지출 한도($10/$50/$200) 초과 | RATE_LIMIT (현행; 코드로 구분 불가 → SPEND_LIMIT 분류는 §9 미해결) |
| 499 | CANCELLED / `cancelled` | `ClientError` | 클라이언트 취소 | UNKNOWN (classify_http 미처리) |
| 500 / 501 | INTERNAL / `api_error` ; UNIMPLEMENTED / `unimplemented` | `errors.ServerError` (e.code=500/501) | 서버 내부 오류 ; 미구현 | SERVER |
| 503 | UNAVAILABLE / `service_unavailable` | `ServerError` (e.code=503) | 과부하 | OVERLOADED |
| 504 | DEADLINE_EXCEEDED / `deadline_exceeded` | `ServerError` (e.code=504) | 서버측 시간 초과 | TIMEOUT |
| - | (status None) | `httpx.TimeoutException` / `httpx.ConnectError` 등 | 클라이언트 timeout / 네트워크 | TIMEOUT / NETWORK |
| 200 | `finishReason`: SAFETY, RECITATION, BLOCKLIST, PROHIBITED_CONTENT, SPII / `promptFeedback.blockReason`; error.code `safety`, `recitation`, `prohibited_content`, `spii`, `blocklist`, `content_blocked` | 예외 없음(응답 검사) | 생성 차단(HTTP 는 200) | CONTENT_BLOCKED |
| 200/400 | `malformed_function_call`, `malformed_tool_call`, `unexpected_tool_call`, `too_many_tool_calls`, `missing_thought_signature`, `no_image` | `ClientError` 또는 응답 검사 | 도구 호출·생성 오류 | BAD_REQUEST |

- rate-limit 헤더: **없음**(공식 문서 미기재). 429 바디 `retryDelay` 는 비공식 보고만 → `ErrorInfo.retry_after` 는 None 유지.
- SDK 기본 timeout / retry: timeout 기본 수치 미확인(ms 단위, 명시 권장) / **retry 기본 0회**(문서 '4회' 와 불일치, 소스 기준). 408·429·5xx 만 재시도 대상.

## 7. 호출 예제 [DOCS]

### 엔드포인트
- `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`
- `POST https://generativelanguage.googleapis.com/v1beta/interactions`
- (OpenAI 호환) `https://generativelanguage.googleapis.com/v1beta/openai/` — `OpenAI(api_key=GEMINI_API_KEY, base_url=…).chat.completions.create(model="gemini-3.8-flash", …)`
- 필수 헤더: `x-goog-api-key: $GEMINI_API_KEY`, `Content-Type: application/json`
### 인증
- Gemini API 키(`GEMINI_API_KEY` 환경변수 또는 `genai.Client(api_key=...)`). REST 는 `x-goog-api-key` 헤더.
### 응답 필드
| SDK 경로 | 필드 |
|---|---|
| generateContent | `resp.text`, `resp.candidates[0].finish_reason`, `resp.usage_metadata.*`, `resp.model_version`, `resp.response_id` |
| Interactions | `interaction.output_text`, `interaction.id`, `interaction.status`, `interaction.usage.*` |
### 주의점
- 설치: `pip install -U google-genai`(README 권고: 예기치 않은 업데이트 방지를 위해 `< 3.0.0` 핀), Python >= 3.10. 레거시 `import google.generativeai`(`genai.GenerativeModel`)는 2025-11-30 deprecated, 'Not actively maintained' → **사용 금지**(정확한 지원 종료일은 미확인).
- (CORRECTED) Quickstart 에 'Generate Content API (Legacy)' 섹션은 **없다**. Quickstart·text-generation·tokens 가이드는 모두 Interactions API 만 다루며, generateContent 는 interactions / migrate-to-interactions 문서에서 'remains fully supported, we recommend the Interactions API for all new development' 로 서술된다. 노트북은 두 경로를 모두 실측해 `CallResult.api` 로 구분.
- Vertex AI(현 명칭 'Gemini Enterprise Agent Platform') 는 `genai.Client(vertexai=True 또는 enterprise=True, project=, location="global")` + ADC(`gcloud auth application-default login`), 호스트 aiplatform.googleapis.com, 결제 활성화 필수, OAuth Bearer 토큰 — API 키 흐름과 다름. PoC 는 AI Studio 키 경로가 단순.
- OpenAI 호환 엔드포인트는 openai 라이브러리 하나로 OpenAI+Gemini 를 호출할 수 있어 구현을 단순화하지만 beta 이며 일부 파라미터가 무시됨.
### 예제
```python
from google import genai                              # pip install -U "google-genai<3.0.0" ; export GEMINI_API_KEY=...
client = genai.Client()
resp = client.models.generate_content(model="gemini-3.8-flash", contents="Explain how AI works in a few words")
print(resp.text)
u = resp.usage_metadata
print(u.prompt_token_count, u.candidates_token_count, u.thoughts_token_count, u.total_token_count)
```
```bash
curl -X POST "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent" \
  -H "x-goog-api-key: $GEMINI_API_KEY" -H "Content-Type: application/json" \
  -d '{"contents":[{"parts":[{"text":"Explain how AI works in a few words"}]}]}'
```
### 출처
- https://ai.google.dev/gemini-api/docs/quickstart
- https://ai.google.dev/gemini-api/docs/migrate
- https://github.com/googleapis/python-genai
- https://ai.google.dev/gemini-api/docs/openai

## 8. 다른 Provider와 다른 점

- **모델 목록 메타데이터가 가장 풍부**: `inputTokenLimit`/`outputTokenLimit`/`supportedGenerationMethods`/`thinking`/기본 temperature 를 API 가 돌려줌(OpenAI 는 컨텍스트 한도 미제공). → Simulator 함의: 모델 카탈로그(컨텍스트 한도 검증)를 Gemini 만 API 로 자동 구성 가능, 가격은 여전히 수동.
- **호출 API 2개 공존**: Interactions(OpenAI Responses 유사, `previous_interaction_id` 서버측 상태, 기본 `store=true`) + 완전 지원되는 generateContent. usage 필드명이 다름. → 어댑터는 `api="generate_content"|"interactions"` 두 경로를 모두 지원하고 `UsageNormalized` 로 정규화; 기본 `store=False`.
- **thinking 토큰 분리 노출 + 출력 단가 합산 + total 필드 존재**: `thoughtsTokenCount` 가 별도이고 `totalTokenCount` 가 응답에 있음(Anthropic 은 total 없음). → `output_tokens = candidates + thoughts`, `total_is_computed=False`.
- **countTokens 가 무료 제공**(OpenAI 는 `POST /v1/responses/input_tokens`, Anthropic 은 `count_tokens` 로 3사 모두 사전 카운트 가능; 과금 여부는 Gemini·Anthropic 만 무료 명시, OpenAI 는 문서 미기재). → `count_tokens()` 구현 가능, 헬스체크 대안으로도 사용.
- **기간별 Usage/비용 집계 API 없음**: OpenAI Admin Usage/Costs·Anthropic Usage & Cost Admin API 에 해당하는 1급 엔드포인트가 없고, Cloud Monitoring(BETA 토큰 메트릭, OAuth)·BigQuery export(Paid+사전 설정) 같은 Google Cloud 자격증명 기반 간접 수단만 존재. → 3사 공통 Usage 집계는 '호출별 usage 자체 적재(usagelog)' 로 설계해야 하며, Gemini `usage_report()` 는 `NotSupported` 또는 `source="usagelog"`.
- **레이트리밋 응답 헤더 미문서화**(`Retry-After`, `x-ratelimit-*` 없음). 한도는 API 키가 아닌 프로젝트 단위(RPM/TPM/RPD + Paid tier 10분 롤링 지출 한도), 실제 수치는 AI Studio 로그인 후만 확인. → `HealthResult.ratelimit` 은 Gemini 에서 비어 있고, 백오프는 헤더가 아닌 자체 정책으로.
- **오류 코드가 snake_case 문자열 + gRPC 이름 병존**, 선불 소진은 **402 payment_required** 별도. 미등록 코드는 HTTP status snake_case 폴백. → `provider_code`/`provider_type` 둘 다 기록, 패턴 매칭 분류. 과부하는 503(Anthropic 의 529 와 다름).
- **SDK 재시도 기본 0회**(문서 '4회' 와 불일치, 소스 기준) vs OpenAI/Anthropic SDK 기본 2회. → 지연·오류 통계를 공정하게 비교하려면 세 Provider 모두 재시도 횟수를 명시적으로 고정(`max_retries=0`). timeout 단위도 ms 로 다름.
- **Gemini 4·3.6+ 는 temperature/top_p/top_k 무시**(+deprecation warning 헤더). → 3사 동일 샘플링 조건 비교가 불가능한 모델을 결과표에 플래그; 응답 헤더 로깅으로 자동 감지.
- **Free tier 가 실질 존재**(신용카드 없이 키 자동 발급 추정, 공식 명시 없음)해 PoC 초기 비용 0, Paid 전환은 최소 $5 선불. $300 Cloud 체험 크레딧은 사용 불가. → 팀원 전원이 각자 Free tier 키로 실측 가능하되 Free tier 데이터는 제품 개선에 사용될 수 있음(민감 프롬프트 금지).
- **2.5 세대는 deprecated 가 아닌데도 '과거 사용자만 접근 가능'**, 가격 인상이 날짜별 예고(2026-12-01, 2027-01-01). → 카탈로그 기본 후보는 3.8 Flash / 3.5 Flash-Lite, 단가표에 `effective_from`.
- **인증이 서비스 계정 기반 Auth key 로 전환**(2026-05-28~), 제한 없는 standard key 거부, 헤더는 `x-goog-api-key`(Bearer 아님), Auth key 요청은 서비스 계정 usage metrics 에 미기록. **OpenAI 호환 엔드포인트**(`/v1beta/openai/`, beta·일부 파라미터 무시)와 **Vertex AI**(ADC/OAuth·aiplatform 호스트·Cloud Billing)는 별도 경로. → `x-goog-api-key` 는 민감 헤더로 마스킹, 간접 Usage 집계는 신뢰하지 않음, PoC 는 AI Studio 키 + google-genai 네이티브 경로를 기본으로 하고 호환 엔드포인트는 선택 실험.

## 9. 미해결 질문

- [ ] Free tier 의 모델별 RPM/TPM/RPD 구체 수치 — rate-limits 문서 정적 텍스트에 없고 AI Studio(https://aistudio.google.com/rate-limit) 로그인 후 동적 표시 → 키 발급 후 실측 캡처(숫자만 기록, 스크린샷 금지).
- [ ] Free tier 에 신용카드가 전혀 필요 없는지 — api-key/billing 문서에 '신규 사용자는 ToS 동의 시 프로젝트+키 자동 생성', '신규 계정은 Free tier 로 시작' 만 있고 카드 불필요 명시 문장 없음(confidence 0.7) → 팀원 1명이 신규 계정으로 발급 흐름 확인.
- [ ] google-generativeai(레거시 SDK)의 정확한 지원 종료일 — 'deprecated as of November 30th, 2025', 'Not actively maintained' 만 확인, bug-fix 종료일 미기재.
- [ ] Google Cloud Billing Pricing API(`cloudbilling.googleapis.com/v2beta/skus`)에 Gemini Developer API(Generative Language API) SKU 와 단가가 실제로 노출되는지 — 공개 SKU 그룹 'Gen AI Gemini Models' 는 Vertex AI 소속.
- [ ] Auth key 요청이 '서비스 계정 usage metrics 에 기록되지 않음' 이라는 문구가 Cloud Console APIs&Services 대시보드 / Cloud Monitoring 의 Generative Language API 메트릭(`generate_content_usage_output_token_count` 포함)에도 영향을 주는지 → OAuth 가능한 팀원이 실측.
- [ ] `candidatesTokenCount` 에 thinking 토큰이 포함되는지(Gemini API vs Vertex 차이 GitHub 이슈) → 실제 응답으로 `prompt + toolUsePrompt + thoughts + candidates == totalTokenCount` 검증, 비용 계산식 중복 여부 확정.
- [ ] 429 응답 바디의 `retryDelay`/RetryInfo 포함 여부 — 사용자 보고만 있고 공식 문서 없음 → Free tier 에서 의도적 429 유발 후 바디 기록(`retry_after` 추출 가능성).
- [ ] 10분 롤링 지출 한도 초과 429 의 `error.code` 가 `rate_limit_exceeded` 와 구분되는지 — 구분 가능하면 `SPEND_LIMIT`, 불가하면 `RATE_LIMIT` 유지(현행 classify_http).
- [ ] SDK `Model` 객체에서 `supportedGenerationMethods` 의 정확한 속성명(`supported_actions` 추정) 및 `GenerateContentResponseUsageMetadata` 전체 속성명(`tool_use_prompt_token_count` 포함) — README/문서 예제 기반, 실측으로 확정.
- [ ] SDK 기본 timeout 수치(HttpOptions.timeout 미지정 시) — 조사 문서에 없음 → 소스/실측 확인 후 apicompare 어댑터에 ms 변환 명시.
- [ ] Gemini 4·3.6+ 의 deprecation warning 헤더 정확한 이름 — text-generation 문서는 '헤더 반환' 만 언급 → 실측 후 `filter_headers()` 화이트리스트에 추가 여부 결정.

## 10. 출처

- https://ai.google.dev/gemini-api/docs/libraries
- https://googleapis.github.io/python-genai/
- https://github.com/googleapis/python-genai
- https://github.com/googleapis/python-genai/blob/main/google/genai/errors.py
- https://ai.google.dev/gemini-api/docs/api-key
- https://ai.google.dev/gemini-api/docs/billing
- https://ai.google.dev/gemini-api/docs/rate-limits
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/google-ai-plans
- https://ai.google.dev/api/models
- https://ai.google.dev/gemini-api/docs/models
- https://ai.google.dev/gemini-api/docs/deprecations
- https://ai.google.dev/gemini-api/docs/changelog
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/gemini-api/docs/interactions
- https://ai.google.dev/api/interactions
- https://ai.google.dev/gemini-api/docs/text-generation
- https://ai.google.dev/gemini-api/docs/migrate-to-interactions
- https://ai.google.dev/gemini-api/docs/interactions-breaking-changes-may-2026
- https://ai.google.dev/gemini-api/docs/api-versions
- https://ai.google.dev/api/tokens
- https://ai.google.dev/gemini-api/docs/tokens
- https://ai.google.dev/gemini-api/docs/generate-content/tokens
- https://ai.google.dev/gemini-api/docs/thinking
- https://docs.cloud.google.com/apis/docs/monitoring
- https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list
- https://docs.cloud.google.com/monitoring/api/metrics_gcp_d_h
- https://ai.google.dev/gemini-api/docs/troubleshoot-ai-studio
- https://ai.google.dev/gemini-api/docs/logs-datasets
- https://docs.cloud.google.com/billing/docs/how-to/reports
- https://docs.cloud.google.com/billing/docs/how-to/get-pricing-information-api
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-setup
- https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery-tables/standard-usage
- https://docs.cloud.google.com/billing/docs/reference/pricing-api/rest/v2beta/skus/list
- https://cloud.google.com/skus/sku-groups/gen-ai-gemini-models
- https://ai.google.dev/gemini-api/docs/api-errors
- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://ai.google.dev/gemini-api/docs/quickstart
- https://ai.google.dev/gemini-api/docs/migrate
- https://ai.google.dev/gemini-api/docs/openai
