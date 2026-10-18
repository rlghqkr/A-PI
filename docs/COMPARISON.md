# OpenAI / Anthropic Claude / Google Gemini API 구조 비교

> **GENERATED 2026-10-19 01:43 KST — 수정은 matrix/*.yaml 로** (`uv run python scripts/build_comparison.py`)
>
> 입력: matrix/*.yaml · 작성자 1명: @kimbong · 셀 21/21
>
> 배지: `[LIVE]` 직접 호출 확인 · `[OBSERVED]` 관찰만 · `[DOCS]` 공식 문서 근거 · `[BLOCKED: 사유]` 키/권한 없음 · 아이콘: ✅ api · ⚠️ partial · 🖥️ dashboard_only · ❌ none · ❓ unknown

## 1. 3×7 비교표

| 항목 | OpenAI | Anthropic Claude | Google Gemini |
|---|---|---|---|
| 1. 모델 목록 조회 | ✅ api<br>`GET /v1/models ; GET /v1/models/{model}`<br>**[LIVE]**<br>키: standard_key | ✅ api<br>`GET https://api.anthropic.com/v1/models / GET /v1/models/{model_id} (…`<br>**[DOCS]**<br>키: standard_key | ✅ api<br>`GET https://generativelanguage.googleapis.com/v1beta/models ; GET htt…`<br>**[DOCS]**<br>키: standard_key |
| 2. 모델 호출 | ✅ api<br>`POST /v1/responses (권장) ; POST /v1/chat/completions (지원 유지, 종료 미공지)`<br>**[LIVE]**<br>키: standard_key | ✅ api<br>`POST https://api.anthropic.com/v1/messages (stream: true 로 SSE; 배치 PO…`<br>**[DOCS]**<br>키: standard_key | ✅ api<br>`POST https://generativelanguage.googleapis.com/v1beta/models/{model}:…`<br>**[DOCS]**<br>키: standard_key |
| 3. Token Usage | ✅ api<br>`응답 내 usage (POST /v1/responses, POST /v1/chat/completions) ; 사전 카운트 P…`<br>**[LIVE]**<br>키: standard_key | ⚠️ partial<br>`응답 내 usage 객체 (POST /v1/messages) / 사전 계산: POST https://api.anthropic…`<br>**[DOCS]**<br>키: standard_key | ✅ api<br>`응답 내 usageMetadata (…:generateContent) ; interaction.usage (…/v1beta/…`<br>**[DOCS]**<br>키: standard_key |
| 4. Usage 조회 | ✅ api<br>`GET /v1/organization/usage/completions (+ embeddings, images, moderat…`<br>**[BLOCKED: no admin key]**<br>키: admin_key | ✅ api<br>`GET https://api.anthropic.com/v1/organizations/usage_report/messages?…`<br>**[BLOCKED: org + admin key]**<br>키: admin_key | 🖥️ dashboard_only<br>`없음(대시보드: https://aistudio.google.com/usage). 간접: GET https://monitori…`<br>**[DOCS]**<br>키: login_only |
| 5. 비용 확인 | ⚠️ partial<br>`GET /v1/organization/costs (Admin 키, 1d 버킷) ; 호출별 비용은 API 미제공 → 로컬 계산…`<br>**[LIVE]**<br>키: admin_key | ⚠️ partial<br>`GET https://api.anthropic.com/v1/organizations/cost_report?starting_a…`<br>**[BLOCKED: org + admin key]**<br>키: admin_key | ⚠️ partial<br>`비용 엔드포인트 없음(로컬 계산). 단가표: https://ai.google.dev/gemini-api/docs/pricin…`<br>**[DOCS]**<br>키: none |
| 6. 상태 및 오류 확인 | ✅ api<br>`헬스체크 GET /v1/models ; 상태 GET https://status.openai.com/api/v2/status.…`<br>**[LIVE]**<br>키: standard_key | ✅ api<br>`헬스체크: GET https://api.anthropic.com/v1/models (무료; Admin 키 검증 GET /v1…`<br>**[DOCS]**<br>키: standard_key | ✅ api<br>`헬스체크 GET https://generativelanguage.googleapis.com/v1beta/models/{mod…`<br>**[DOCS]**<br>키: standard_key |
| 7. 호출 예제 | ✅ api<br>`POST https://api.openai.com/v1/responses`<br>**[LIVE]**<br>키: standard_key | ✅ api<br>`POST https://api.anthropic.com/v1/messages (headers: x-api-key, anthr…`<br>**[DOCS]**<br>키: standard_key | ✅ api<br>`POST https://generativelanguage.googleapis.com/v1beta/models/{model}:…`<br>**[DOCS]**<br>키: standard_key |

## 2. 공통 수집 가능 항목

3사 모두 `api` 또는 `partial` 인 항목과, 각 Provider 의 `common_fields` 교집합.

- **모델 목록 조회** — OpenAI ✅ / Anthropic Claude ✅ / Google Gemini ✅ — 공통 필드: `model_id`
- **모델 호출** — OpenAI ✅ / Anthropic Claude ✅ / Google Gemini ✅ — 공통 필드: `model_id`, `text`, `input_tokens`, `output_tokens`, `finish_reason`, `latency`, `request_id`, `http_status`
- **Token Usage** — OpenAI ✅ / Anthropic Claude ⚠️ / Google Gemini ✅ — 공통 필드: `input_tokens`, `output_tokens`, `cached_input_tokens`, `reasoning_tokens`
- **비용 확인** — OpenAI ⚠️ / Anthropic Claude ⚠️ / Google Gemini ⚠️ — 공통 필드: `model_id`
- **상태 및 오류 확인** — OpenAI ✅ / Anthropic Claude ✅ / Google Gemini ✅ — 공통 필드: `http_status`
- **호출 예제** — OpenAI ✅ / Anthropic Claude ✅ / Google Gemini ✅ — 공통 필드: `model_id`, `text`, `input_tokens`, `output_tokens`, `request_id`

## 3. Provider별 차이

### OpenAI

- **엔드포인트 이원화**: Responses(`/v1/responses`, 권장)와 Chat Completions(지원 유지)가 공존하고 usage 필드명이 다르다(`input_tokens/output_tokens` vs `prompt_tokens/completion_tokens`). Anthropic(messages)·Gemini(generateContent)는 단일 주 엔드포인트 → Simulator 의 OpenAI 어댑터만 `api="responses"|"chat_completions"` 분기와 usage 정규화가 필요하다.
- **GPT-5.4+ Chat 의 tools+reasoning 400**: 도구 호출·reasoning 비교 실험은 Responses 로 통일해야 하고, 기업 기존 연동이 Chat 기준이면 변환 계층이 필요하다(킥오프 질문 12).
- **`total_tokens` 제공**: Anthropic 은 input/output 만 주므로 `UsageNormalized.total_is_computed` 플래그로 출처를 구분한다.
- **reasoning 토큰이 output 에 포함**(`output_tokens_details.reasoning_tokens` 로만 분리). Gemini 는 `thoughtsTokenCount` 가 별도라 합산이 필요 → Simulator 의 '출력 토큰' 정의를 "reasoning 포함" 으로 명시.
- **모델 목록에 스펙 없음**: `/v1/models` 는 컨텍스트·단가·capability 를 주지 않음(Gemini 는 토큰 한도 포함) → 모델 스펙 테이블을 문서 기반으로 수동 유지하고 `shutdown_date` 로 자동 경고.
- **기간별 Usage/Costs API 는 있지만 Admin 키(Owner) 필수**: Gemini 는 해당 API 자체가 없고, OpenAI 는 권한이 선결 조건 → Simulator 는 호출마다 usage 를 자체 로깅하는 경로(`usagelog`)를 기본으로 두고 Admin API 는 선택 기능으로. Costs API 가 USD 를 직접 반환(1d)하지만 모델별 group_by 가 없어 모델 간 비용 비교는 로컬 계산(토큰×단가, `service_tier` 배수 포함)에 의존.
- **Rate-limit 헤더 10종 + Retry-After 가 매 응답에 포함** → Simulator 가 실시간 잔여 한도를 모니터링·경고할 수 있다(`HEADER_WHITELIST_PREFIXES` 의 `x-ratelimit-`).
- **SDK 기본 timeout 600s·재시도 2회** → latency 비교에서는 `timeout=30, max_retries=0` 으로 끄고 `x-stainless-retry-count`·`openai-processing-ms` 로 서버 처리 시간을 분리 측정.
- **사전 토큰 카운팅 엔드포인트 존재**(`POST /v1/responses/input_tokens`; Anthropic count_tokens·Gemini countTokens 와 대응) → 3사 공통 `count_tokens()` 인터페이스 가능. 과금 여부는 미확정.
- **429 의 의미가 3갈래**(크레딧 소진 / 속도 제한 / 지출 한도) → ErrorCategory 매핑은 HTTP 코드만으로는 불가, `error.type/code` 필수. Anthropic 의 크레딧 소진은 400, Gemini 는 402 라 3사 모두 코드가 다르다.
- **선불 결제 최소 $5(기본 $10), 크레딧 1년 만료, 무료 체험 크레딧 미확인**(Gemini 는 무료 티어 존재) → 팀 예산 계획 시 OpenAI 는 충전을 전제로. 문서 도메인도 platform.openai.com → developers.openai.com 으로 이전(301)되어 출처 URL 갱신 필요.

### Anthropic Claude

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

### Google Gemini

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

## 4. 공통 Usage 스키마

`apicompare.models.UsageNormalized` — 과금 관점 토큰. 어댑터 3개가 모두 이 형태로 돌려준다 (models.py docstring 기준).

| 필드 | 설명 | OpenAI | Anthropic Claude | Google Gemini |
|---|---|---|---|---|
| `input_tokens` | 캐시 읽기/쓰기까지 포함한 총 입력(과금 관점) | usage.input_tokens (Responses) / prompt_tokens (Chat) — cached 포함 | input_tokens + cache_creation_input_tokens + cache_read_input_tokens | promptTokenCount(캐시 포함) + toolUsePromptTokenCount |
| `output_tokens` | reasoning/thinking 을 포함한 총 출력(3사 모두 output 단가) | usage.output_tokens (reasoning 포함) | usage.output_tokens (thinking 포함) | candidatesTokenCount + thoughtsTokenCount |
| `total_tokens` | input_tokens + output_tokens | usage.total_tokens (응답 제공) | 응답에 없음 → 계산 (total_is_computed=True) | usageMetadata.totalTokenCount (응답 제공) |
| `cached_input_tokens` | input_tokens 에 포함된 캐시 읽기 | input_tokens_details.cached_tokens | cache_read_input_tokens | cachedContentTokenCount |
| `cache_write_tokens` | input_tokens 에 포함된 캐시 쓰기 | input_tokens_details.cache_write_tokens (GPT-5.6+ 1.25배 과금) | cache_creation_input_tokens (5m 1.25배 / 1h 2배) | 없음 (0) |
| `reasoning_tokens` | output_tokens 에 포함된 추론 토큰 (더하지 말 것) | output_tokens_details.reasoning_tokens | output_tokens_details.thinking_tokens | thoughtsTokenCount |
| `total_is_computed` | total 을 로컬에서 계산했는지 | False | True | False |
| `raw` | Provider 원본 usage 필드(dict) | usage.model_dump() | usage.model_dump() | usage_metadata.model_dump() |

비용은 `apicompare.pricing.estimate_cost()` 가 이 스키마로 계산한다(단가는 3사 모두 API 미제공 → `PRICE_TABLE` 로컬 관리, as_of·출처 기록).

## 5. 충돌(author 간 불일치)

- 없음 (작성자 1명 또는 입력 없음)

## 6. BLOCKED 목록

| 사유 | 건수 | 셀 |
|---|---|---|
| org + admin key | 2 | Anthropic Claude/Usage 조회, Anthropic Claude/비용 확인 |
| no admin key | 1 | OpenAI/Usage 조회 |

기업 키가 오면 할 일:

- OpenAI / Usage 조회 — 사유: no admin key → `notebooks/10_openai.ipynb` §4 재실행 후 `evidence/openai/04_usage_api.json` 갱신
- Anthropic Claude / Usage 조회 — 사유: org + admin key → `notebooks/20_anthropic.ipynb` §4 재실행 후 `evidence/anthropic/04_usage_api.json` 갱신
- Anthropic Claude / 비용 확인 — 사유: org + admin key → `notebooks/20_anthropic.ipynb` §5 재실행 후 `evidence/anthropic/05_costs.json` 갱신

## 7. 미해결 질문

### OpenAI

- [ ] 신규 계정 무료 체험(trial) 크레딧 지급 여부와 최소 충전 $5 / 기본 $10 / 1년 만료 — help.openai.com 403 으로 본문 직접 확인 불가(confidence ~0.6 / ~0.7).
- [x] 에러 코드 문자열 `invalid_api_key`, `rate_limit_exceeded`, `model_not_found`, `expired_secret_key` 가 공식 error-codes 페이지에 미기재 → 더미 키·잘못된 모델명으로 `error.code` 실측 완료(10/18, `evidence/openai/06_errors.json`: 401 `invalid_api_key`, 404 `model_not_found`, 둘 다 type=`invalid_request_error`). `rate_limit_exceeded` 는 미실측.
- [x] Admin 엔드포인트를 표준 키로 호출했을 때 403 `Missing scopes: api.usage.read` 인지 404 인지 → **403 으로 실측 확정**(2026-10-19, 노트북 §4 `probe_usage_api_with_standard_key()`; 바디 `{"error": "<문장>"}`). 남은 것: Admin 키 접두어 `sk-admin…` 은 예시 값 기준으로 공식 규칙 미확인.
- [ ] `POST /v1/responses/input_tokens` 의 과금·rate limit 포함 여부, Responses 스트리밍 `response.completed` 이벤트의 usage 포함 여부(가이드 미명시) — 실측.
- [ ] Chat Completions usage 의 공식 필드 테이블과 Responses create 레퍼런스의 usage 정의 섹션 — 페이지가 너무 커서(50만자) 직접 읽지 못함, 예시 JSON 으로만 확인.
- [ ] pricing 페이지의 신규 모델명(gpt-5.6-sol/terra/luna, gpt-6-astra 등)과 `GET /v1/models` 실측 결과 대조 → 실습 모델 최종 확정(gpt-5.4-mini vs gpt-6-luna).
- [ ] Usage/Costs API 데이터 반영 지연(freshness) — 공식 서술 없음, 실측 과제. 'Costs 엔드포인트는 인보이스와 정합' 문구의 원문 존재 여부(검색 스니펫만 확인).
- [ ] 10/18 관찰한 Chat tools+reasoning 400 의 `error.message` 원문을 `evidence/openai/02_call.json` 에 저장하고 이 문서 §2 에 인용.

### Anthropic Claude

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

### Google Gemini

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

기업과 합의할 질문은 [docs/KICKOFF_QUESTIONS.md](KICKOFF_QUESTIONS.md) 에 모아 둔다.

## 8. evidence 현황

`apicompare.evidence.summary()` — evidence/<provider>/<항목>.json 의 source 배지 (노트북/`python -m apicompare.demo` 가 생성).

| 항목 | OpenAI | Anthropic Claude | Google Gemini |
|---|---|---|---|
| 모델 목록 조회 | [LIVE]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> |
| 모델 호출 | [LIVE]<br><sub>2026-10-18T16:18</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:21</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:23</sub> |
| Token Usage | [LIVE]<br><sub>2026-10-18T16:18</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:21</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:23</sub> |
| Usage 조회 | [BLOCKED: no admin key]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> |
| 비용 확인 | [LIVE]<br><sub>2026-10-18T16:18</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:21</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:23</sub> |
| 상태 및 오류 확인 | [LIVE]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:27</sub> |
| 호출 예제 | [LIVE]<br><sub>2026-10-18T16:18</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:21</sub> | [BLOCKED: no key]<br><sub>2026-10-18T16:23</sub> |

