# 킥오프(10/20 14:00) 질문 목록

사전조사(OpenAI / Anthropic Claude / Google Gemini API 구조 비교)에서 나온, 기업과 합의해야 PoC 설계가 확정되는 질문들.
`[BLOCKED]` 로 남은 매트릭스 셀이 근거다.

## A. 키와 권한

1. **Usage·비용 집계 API용 Admin 키**(OpenAI Admin API key, Anthropic Admin API key)를 제공해 주시나요?
   - OpenAI `GET /v1/organization/usage/*`, `/costs` 와 Anthropic `usage_report/messages`, `cost_report` 는 모두 Admin 키 필수이고, Gemini 는 해당 API 자체가 없습니다.
   - 제공이 어렵다면 **Simulator 가 호출마다 응답 usage 를 자체 DB 에 적재해 집계**하는 방식(3사 공통으로 가능한 유일한 경로)으로 확정해도 되나요?
2. Gemini 키 경로는 **AI Studio(Gemini Developer API, Free/Paid tier)** 인가요, **Vertex AI(Gemini Enterprise Agent Platform, ADC/OAuth)** 인가요? 두 경로는 인증·과금·Usage 조회 방식이 전혀 다릅니다.
3. 지급되는 키의 종류와 범위: OpenAI 프로젝트 키 권한(All/Restricted), Anthropic 조직 소속 workspace 키인지, 팀원별 개별 키(OpenAI `api_key_id` / Anthropic workspace 로 1인별 비용 분리 가능)인지 공용 1개인지. 전달 채널과 폐기 시점.

## B. 비교 대상과 예산

4. 비교 대상 모델 확정 목록. 후보: OpenAI `gpt-5.4-mini` / `gpt-6-luna`(최저가), Anthropic `claude-haiku-5-5` / `claude-sonnet-5-5`, Gemini `gemini-3.8-flash` / `gemini-3.6-flash`.
   - 종료 예정 모델(`gpt-5-nano`·`gpt-5-mini` 2026-12-11, `gpt-4o-mini`·`gpt-4.1` 2027-01-14)과 신규 사용자 접근이 제한된 Gemini 2.5 계열은 제외해도 되나요?
5. Provider 별 예산(USD)·한도 정책. OpenAI project spend limit, Anthropic workspace spend limit, Gemini billing tier(Tier 1 은 10분 롤링 $10 한도)를 기업이 설정해 두나요? 초과 임박 시 누구에게 어떻게 알리나요?
6. OpenRouter 를 4번째 Provider 로 포함하나요? 포함 시 키 제공 여부와 "같은 모델, 다른 경로" 취급 방법.

## C. 비용 계산 기준

7. '예상 API 비용' 계산의 기준 단가표는 기업이 제공하는 **모델별 비용 계산 기준정보**인가요, 공식 pricing 페이지(as_of 날짜 기록)를 우리가 유지하나요?
   - 단가는 세 Provider 모두 API 로 제공되지 않아 로컬 테이블이 필요합니다. Gemini 는 가격 인상이 예고돼 있습니다(4 Argon 2026-12-01, 3.8 Flash 2027-01-01).
8. 캐시 토큰(cached / cache write)·reasoning/thinking 토큰·Batch/Flex/Priority 티어 배수를 비용에 어떻게 반영하길 원하나요?
9. Token Usage 표시: reasoning/thinking 토큰(OpenAI `reasoning_tokens`, Anthropic `thinking_tokens`, Gemini `thoughtsTokenCount`)을 Output 에 포함해 보여줄지, 별도 컬럼으로 분리할지. Anthropic 은 `total_tokens` 필드가 없어 계산값으로 표시됩니다.

## D. 비교 공정성과 호출 방식

10. "동일 조건" 정의: Claude 현행 모델은 `temperature` 를 거부(400)하고 Gemini 3.6+/4 는 무시하며 Claude 는 thinking 이 기본 ON 입니다. 비교 조건을 **max_output_tokens + 시스템 프롬프트 고정 + effort 명시**로 단순화해도 되나요?
11. 재시도 정책: latency 비교를 위해 SDK 자동 재시도를 0 으로 끄고 측정하는 것에 동의하나요? 429 발생 시 Simulator 가 자동 재시도할지, 실패로 표시할지.
12. OpenAI 는 **Responses API** 를 기본으로 채택해도 되나요? (Chat Completions 는 GPT-5.4+ 에서 tools + reasoning 조합이 400 — 실측.) 기업 기존 연동 예제가 Chat Completions 기준이면 어느 쪽을 따르나요? Gemini 는 Interactions vs generateContent 중 선호가 있나요?
13. 응답시간 측정 기준: 클라이언트 측정 vs 서버 헤더(`openai-processing-ms` 등). TTFT 포함 여부.

## E. 데이터와 저장

14. 응답 저장 정책: OpenAI Responses(`store` 기본 true, 30일)·Gemini Interactions(`store` 기본 true)는 서버에 저장됩니다. 기업 샘플 데이터 특성상 `store=false` 로 고정해야 하나요?
15. Gemini **Free tier 입력은 제품 개선에 사용될 수 있습니다.** 기업 샘플 데이터(상품정보·이미지)를 Free tier 로 보내도 되나요? (Paid tier 는 미사용)
16. 호출 로그(프롬프트 해시, usage, latency, 오류 코드)를 SQLite/PostgreSQL 에 저장해도 되는지, 프롬프트 원문 저장 가능 여부, 보존 기간.

## F. 운영

17. 기업 측 대시보드(OpenAI Usage/Costs 탭, Claude Console Usage/Cost, AI Studio Usage)의 수치를 주기적으로 공유해 줄 수 있나요? (Owner 가 아닌 팀원은 대시보드도 못 볼 수 있습니다.)
18. 속도 제한 티어(OpenAI Build/Launch…, Anthropic Evaluation/Start…, Gemini Free/Tier 1)가 동시 3~4모델 병렬 호출 부하에 충분한가요?
19. Provider 서비스 상태 표시(`status.openai.com/api/v2/status.json`, `status.anthropic.com`; Gemini 는 공개 피드 미확인)를 Simulator 화면에 넣기를 원하나요?
20. 결과물 저장소(기업 GitHub org vs 팀 private repo)와 사전조사 문서·어댑터 코드의 포트폴리오 공개 가능 범위.
