# LLM Provider API 사전 조사 정리

> 템플릿: `docs/templates/LLM_Provider_API_조사_템플릿.md` · 담당 Provider: **OpenAI**
> 근거 컬럼은 `실행` / `문서` / `미확인` 중 하나다. 한 행 안에서 근거가 다른 부분은 셀 안에 `(문서)`, `(미확인: 이유)`로 표시했다.

---

## 1. 문서 개요

| 항목 | 기입 내용 |
| --- | --- |
| 작성자 | 박기호 / A-PI 팀 |
| 담당 Provider | OpenAI(ChatGPT) |
| 작성일 | 2026-10-20 |
| 조사 기준일 | 2026-10-20 (공식 문서, 가격표, API 실행 모두 이날 다시 확인). 2026-10-19 실행 결과를 쓴 곳은 셀에 날짜를 적었다 |
| 조사 방법 | 둘 다 (실제 API 실행 + 공식 문서 확인) |
| 실행 환경 | Python 3.12 (uv), macOS 26.4, SDK `openai==3.35.1` (내부 HTTP 클라이언트 httpx2). 응답 원본 수집은 `httpx`로 직접 호출 |
| 사용한 API 키 종류 | 일반 API 키(표준 프로젝트 키, 개인 선불 크레딧)만. Admin 키 없음 → Usage·Costs API는 403까지만 확인 |
| 공식 문서 URL | API Reference https://developers.openai.com/api/reference/overview · 가격 https://developers.openai.com/api/docs/pricing · 오류 코드 https://developers.openai.com/api/docs/guides/error-codes · Rate limit https://developers.openai.com/api/docs/guides/rate-limits |
| 첨부 파일 | 예제 `examples/openai/example.py` · 콘솔 출력 `examples/openai/example_output.txt` · 응답 원본은 `evidence/openai/template_20261020/` 아래: 호출 ① `responses_call.json`, 호출 ② `stream_responses.json`, 호출 ③ `chat_completions.json`, 무료 확인(모델 목록·오류 재현·사전 카운트) `free_checks.json`, 2026-10-19 오류 원본 `errors_20261019.json`, 2026-10-19 로컬 Timeout 재현 `local_timeout_20261019.json` |

**이 조사에 쓴 유료 호출** (2026-10-20, 모델 `gpt-5.4-mini`, 표준 티어)

| # | 호출 | 입력 / 출력 토큰 | 비용 (USD) |
| --- | --- | --- | --- |
| ① | Responses, 4장 공통 조건 (`example.py`) | 45 / 100 | 0.000484 |
| ② | 같은 요청, 스트리밍 | 45 / 101 | 0.000488 |
| ③ | 같은 요청, Chat Completions | 45 / 105 | 0.000506 |
| | **합계** | | **0.001478** (약 2원) |

모델 목록 조회, 입력 토큰 사전 카운트, 오류 재현(400, 401, 403, 404)은 토큰을 생성하지 않아 과금되지 않는다. 이 무료 확인은 같은 날 두 번 돌렸고, `free_checks.json`과 이 문서에는 두 번째 결과를 실었다.

---

## 2. 작성 가이드

세 Provider 결과를 그대로 나란히 놓고 비교할 수 있도록 아래 규칙을 지킵니다.

1. **근거를 항목마다 표시합니다.** `실행` = 실제 API를 호출해 응답으로 확인, `문서` = 공식 문서에서만 확인, `미확인` = 둘 다 못 함. 실행 결과와 문서가 다르면 둘 다 적고 7장에 올립니다.
2. **필드 이름은 HTTP 응답 원본(JSON) 기준**으로 적습니다. SDK가 채워 넣는 `null` 값이나 다르게 부르는 이름은 괄호로 병기합니다.
3. **숫자에는 단위와 기준일**을 붙입니다. 가격은 "$/백만 토큰", 한도는 "요청/분"처럼 쓰고 가격 페이지 URL을 같이 적습니다.
4. **코드는 복사해서 바로 실행되는 최소 형태**로 적습니다. API 키는 환경변수로 읽고 문서에는 절대 넣지 않습니다.
5. **실행 결과는 응답 원본 JSON**을 긴 텍스트만 줄여 그대로 붙입니다. 요약하지 않습니다.
6. **모르는 것은 `미확인` + 이유**(Admin 키 없음, 대량 요청 필요 등)로 적고 7장에 모읍니다.
7. **같은 프롬프트, 같은 조건**(최대 출력 토큰, temperature, 추론·thinking 설정)으로 호출합니다. 조건은 4장에 적습니다.

3장 표의 공통 컬럼

| 컬럼 | 적는 내용 |
| --- | --- |
| 확인할 내용 | 템플릿에 미리 적혀 있음. 필요하면 행 추가 |
| 조사 결과 | Endpoint, 필드명, 값, 제약사항. 코드·필드는 백틱(`)으로 감쌈 |
| 근거 | 실행 / 문서 / 미확인 |
| 참고 URL | 근거가 된 공식 문서 페이지 링크 |

**이 문서에서 달리한 점**

- 4장 공통 호출 조건에 `store=false`를 **추가**했다. OpenAI Responses는 기본값이 `store=true`라서 응답이 30일간 저장된다. 출력 결과에는 영향이 없다.
- 추론 설정은 템플릿대로 모델 기본값이다. 다만 OpenAI는 모델마다 기본값이 달라서(`gpt-5.4-mini`는 `none`, `gpt-6-luna`는 `medium`) 7장에 제약으로 올렸다.
- 한 행에 실행 확인 부분과 문서 확인 부분이 섞인 경우, 근거 컬럼에는 행의 핵심 답에 해당하는 값을 적었다. 나머지 부분은 셀 안에 `(문서)`로 표시했다. 실행과 문서가 실제로 다른 두 행(3.3 캐시 토큰 필드, 3.6 Timeout)만 `실행 / 문서`로 적고 7장에 올렸다.

---

## 3. Provider별 조사 시트

요청서의 조사 항목 6개를 같은 순서로 두었습니다. 7번째 항목인 호출 예제는 4장에 적습니다.

### 3.1 모델 목록 조회

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| 호출 방법 (HTTP Method·Endpoint, SDK 메서드) | `GET https://api.openai.com/v1/models` / SDK `client.models.list()`. 2026-10-20 실행 시 200, 135개 | 실행 | https://developers.openai.com/api/reference/resources/models/methods/list |
| 인증 방식과 필요한 키 종류 | `Authorization: Bearer $OPENAI_API_KEY`, 일반 API 키로 호출된다. Admin 키는 일반 엔드포인트에 쓸 수 없다(문서) | 실행 | https://developers.openai.com/api/reference/administration/overview |
| 응답 주요 필드 (모델 ID, 표시 이름, 출시일, 상태) | 최상위 `object: "list"`, `data[]`. 항목 필드는 `id`, `object: "model"`, `created`(Unix 초), `owned_by`, `shutdown_date`(종료 예정일, 없으면 `null`) 다섯 개뿐이다. **표시 이름 필드는 없다.** 출시일은 `created`, 상태는 `shutdown_date`로 대신 본다 | 실행 | https://developers.openai.com/api/reference/resources/models/methods/list |
| 모델 정보 포함 범위 (컨텍스트 길이, 최대 출력 토큰, 지원 기능) | **포함 안 됨.** 모델 문서 페이지(`/api/docs/models/<id>`)에서 따로 확인해 표로 관리해야 한다 | 실행 | https://developers.openai.com/api/docs/models |
| 단가 포함 여부 | 포함 안 됨. 가격 페이지에서만 확인한다 | 실행 | https://developers.openai.com/api/docs/pricing |
| 페이지네이션·필터 (limit, 커서, 상태 필터) | **없음.** `?limit=2`를 붙여도 135개 전부가 오고 `has_more` 필드도 없다. 레퍼런스에도 쿼리 파라미터가 없다(문서). 비텍스트 모델(TTS, 임베딩, 이미지, Realtime, moderation)이 섞여 있어 클라이언트에서 걸러야 한다 | 실행 | https://developers.openai.com/api/reference/resources/models/methods/list |
| 단건 조회 API 유무 | 있음. `GET /v1/models/{model}` (`client.models.retrieve(id)`). `gpt-5.4-mini` 결과 `{"id":"gpt-5.4-mini","object":"model","created":1773451123,"owned_by":"system","shutdown_date":null}` | 실행 | https://developers.openai.com/api/reference/resources/models/methods/retrieve |
| 호출 시 비용·토큰 소모 여부 | 토큰을 생성하지 않고 가격표에도 항목이 없다. 응답에 `x-ratelimit-*` 헤더도 붙지 않았다(실행) | 문서 | https://developers.openai.com/api/docs/pricing |

**현재 사용 가능한 모델** (2026-10-20 기준, 단가는 가격 페이지의 표준 티어, 입력 272K 이하 구간)

| 모델 ID | 입력 / 출력 단가 ($/백만 토큰) | 최대 입력 / 출력 토큰 | 지원 기능 (이미지·JSON·추론) | 상태 (사용 가능 / 중단 예정) |
| --- | --- | --- | --- | --- |
| `gpt-5.4-mini` (이번 실행 모델) | 0.75 / 4.50 (캐시 입력 0.075) | 272,000 / 128,000 (컨텍스트 400,000) | 이미지 입력 ○ · Structured Outputs ○ · effort `none`(기본)/`low`/`medium`/`high`/`xhigh` | 사용 가능, 종료 공지 없음 |
| `gpt-5.4-nano` | 0.20 / 1.25 (캐시 0.02) | 272,000 / 128,000 (컨텍스트 400,000) | 이미지 ○ · JSON ○ · effort `none`(기본)/`low`/`medium`/`high`/`xhigh` | **2027-04-01 종료 예정** (대체 `gpt-6-luna`) |
| `gpt-5.4` | 2.50 / 15.00 (캐시 0.25). 272K 초과 구간 5.00 / 22.50 | 미확인(모델 페이지에 최대 입력 미기재) / 128,000 (컨텍스트 1,050,000) | 이미지 ○ · JSON ○ · effort `none`(기본)/`low`/`medium`/`high`/`xhigh` | 사용 가능, 종료 공지 없음 |
| `gpt-6-luna` (종료 공지 없는 모델 중 최저가) | 0.10 / 0.50 (캐시 0.01, 캐시 쓰기 0.125) | 922,000 / 128,000 (컨텍스트 1,050,000) | 이미지 ○ · JSON ○ · effort `none`/`low`/`medium`(기본)/`high`/`xhigh`/`max` | 사용 가능, 종료 공지 없음 |
| `gpt-6.1-sol` | 2.00 / 10.00 (캐시 0.10, 캐시 쓰기 2.50) | 922,000 / 128,000 (컨텍스트 1,050,000) | 이미지 ○ · JSON ○ · effort `low`/`medium`(기본)/`high`/`xhigh`/`max` (`none`·`minimal` 불가) | 사용 가능, 종료 공지 없음 |
| `gpt-6-astra` | 10.00 / 50.00 (캐시 1.00, 캐시 쓰기 12.50) | 922,000 / 128,000 (컨텍스트 1,050,000) | 이미지 ○ · JSON ○ · effort `low`/`medium`/`high`/`xhigh`/`max` (`none` 불가, 기본값 미기재) | 사용 가능, 종료 공지 없음 |

근거: 단가, 스펙, 종료일은 `문서`다(가격 페이지, 모델 페이지, deprecations 페이지, 2026-10-20 확인). `실행`으로 확인한 것은 두 가지다. 여섯 모델 모두 목록에 있다. `shutdown_date`는 `gpt-5.4-nano`만 `2027-04-01`이고 나머지 다섯은 `null`이다.
참고 URL: https://developers.openai.com/api/docs/pricing · https://developers.openai.com/api/docs/models/gpt-5.4-mini · https://developers.openai.com/api/docs/deprecations

**PoC 기간(~11/6) 안이나 직후에 종료되는 모델**
- `gpt-4.1-nano`, `gpt-4o-2024-05-13`은 2026-10-23(3일 뒤)에 종료된다. API `shutdown_date`와 문서가 같다.
- `gpt-5-mini-2025-08-07`, `gpt-5-nano-2025-08-07` 스냅샷은 2026-12-11에 종료된다. API(2026-10-19 실행)와 문서가 같다.
- 별칭 `gpt-5-mini`, `gpt-5-nano`는 API `shutdown_date`가 `null`이고, 같은 날 종료되는지 문서에 없다(7장).
- 표의 모델보다 싼 구형 모델(`gpt-5-nano` 0.05/0.40, `gpt-4.1-nano` 0.10/0.40)은 모두 위 종료 대상이다.

### 3.2 모델 호출

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| 기본 호출 API (HTTP Method·Endpoint, SDK 메서드) | **권장** `POST /v1/responses` (`client.responses.create`). 호환 `POST /v1/chat/completions` (`client.chat.completions.create`). 두 API 모두 공통 조건으로 실행해 200 | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| 필수 파라미터 | 실제로 보낸 것은 `model` + `input`(Responses), `model` + `messages`(Chat)이다. 레퍼런스에는 모든 바디 파라미터가 optional로 표시돼 있다(문서). 출력 상한은 Responses `max_output_tokens`(선택, 주면 **16 이상**: 8을 주면 400)이다. Chat은 `max_completion_tokens`이고, 구식 `max_tokens`는 400 `unsupported_parameter`(2026-10-19 실행) | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| system prompt 전달 방식 (메시지 역할 / 별도 파라미터) | Responses: **별도 파라미터** `instructions`(문자열). `input` 배열에 `role: "system"`/`"developer"` 메시지로 넣을 수도 있고, `previous_response_id`로 이어 쓰면 이전 instructions는 이어지지 않는다(문서). Chat: `messages[0] = {"role": "system", ...}` | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| HTTP 직접 호출 시 필수 헤더 | `Authorization: Bearer $OPENAI_API_KEY`, `Content-Type: application/json`. 선택 헤더 `OpenAI-Organization`, `OpenAI-Project`, `X-Client-Request-Id`(문서) | 실행 | https://developers.openai.com/api/reference/overview |
| 응답 텍스트 위치 (JSON 경로) | Responses: `output[?type=="message"].content[?type=="output_text"].text` (SDK 편의 속성 `output_text`). 이번 응답은 `output[0].content[0].text`. Chat: `choices[0].message.content` | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| 종료 사유 필드와 값 (정상 / 잘림 / 거절) | Responses: `status`. 정상 = `completed`(실행). 그 밖의 값은 `incomplete` / `failed` / `in_progress` / `cancelled` / `queued`(문서). 잘림 = `incomplete` + `incomplete_details.reason: "max_output_tokens"`이고, reason에는 `content_filter` / `max_messages` / `steered`도 있다(문서). 거절 = content 항목 `type: "refusal"`(문서). Chat: `finish_reason` = `stop`(정상, 실행), `length`(잘림) / `content_filter` / `tool_calls` / `function_call`(deprecated), 거절은 `message.refusal`(문서) | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create · https://developers.openai.com/api/reference/resources/chat |
| 요청 ID 위치 (헤더 / 본문) | **응답 헤더** `x-request-id` (예 `req_6acd917c9b204d6d84d4898a64845cf4`, SDK `resp._request_id`). 본문 `id`(`resp_…`, `chatcmpl-…`)는 응답 객체 ID라 요청 ID와 다르다. 클라이언트가 직접 붙이는 `X-Client-Request-Id` 요청 헤더도 있다(ASCII만, 512자 이하, 위반 시 400. 문서) | 실행 | https://developers.openai.com/api/reference/overview |
| 구조화 출력(JSON) 지원 방식 | Responses: `text.format = {"type": "json_schema", "name": ..., "schema": {...}, "strict": true}`. Chat: `response_format = {"type": "json_schema", "json_schema": {"name", "schema", "strict"}}`(한 단계 더 중첩). `{"type": "json_object"}`(구 JSON 모드)는 신규 모델에 비권장. 기본값 `{"type": "text"}`는 실행 응답에서 확인 | 문서 | https://developers.openai.com/api/docs/guides/structured-outputs |
| 이미지 입력 지원 방식 | Responses: `input` 메시지 content에 `{"type": "input_image", "image_url": "<URL 또는 data:base64>", "detail": "auto"}` 또는 `file_id`. `detail`은 `low` / `high` / `auto`(기본) / `original`. Chat: `{"type": "image_url", "image_url": {"url": ..., "detail": ...}}`(객체) | 문서 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| 모델별 파라미터 제약 (temperature, 추론·thinking 설정, 최대 출력) | 추론: `reasoning.effort`(Responses) / `reasoning_effort`(Chat). 값은 모델마다 다르다(3.1 표, 문서). **`gpt-5.4-mini` Chat에서 function tools + `reasoning_effort="low"`면 400**(2026-10-19 실행). 문서상 `gpt-6-astra`·`gpt-6.1-sol`은 Chat에서 function calling 자체를 지원하지 않는다. temperature는 보내지 않았고, 응답 원본에 `temperature: 1.0`, `top_p: 0.98`이 나왔다. 모델별 temperature 허용 여부는 미확인(유료 호출 필요). 최대 출력은 3.1 표 | 실행 | https://developers.openai.com/api/docs/guides/reasoning |
| 스트리밍 지원 여부 | 지원. Responses `stream: true`로 실행하면 SSE 이벤트가 이 순서로 온다: `response.created` → `response.in_progress` → `response.output_item.added` → `response.content_part.added` → `response.output_text.delta`(93회) → `response.output_text.done` → `response.content_part.done` → `response.output_item.done` → `response.completed`. Chat `stream: true` → `chat.completion.chunk`(문서, 미실행) | 실행 | https://developers.openai.com/api/reference/resources/responses/streaming-events |

**응답 원본** (호출 ①, `POST /v1/responses`, 2026-10-20. `tool_usage` 블록과 본문 텍스트 일부만 생략. 전체는 `evidence/openai/template_20261020/responses_call.json`)

```json
{
  "id": "resp_0b498348618fc412016ad6bb8b96b887d0809f4ddc27d4d136",
  "object": "response",
  "created_at": 1792457611,
  "status": "completed",
  "access_programs": null,
  "background": false,
  "billing": { "payer": "developer" },
  "completed_at": 1792457613,
  "error": null,
  "frequency_penalty": 0.0,
  "incomplete_details": null,
  "instructions": "당신은 쇼핑몰 상품 설명을 작성하는 전문가입니다.",
  "max_output_tokens": 1024,
  "max_tool_calls": null,
  "model": "gpt-5.4-mini-2026-03-17",
  "moderation": null,
  "output": [
    {
      "id": "msg_0b498348618fc412016ad6bb8cb4fc87d0b6273d3e7812f110",
      "type": "message",
      "status": "completed",
      "content": [
        {
          "type": "output_text",
          "annotations": [],
          "logprobs": [],
          "text": "편안한 착용감과 깔끔한 음질을 갖춘 무선 블루투스 이어폰으로, 일상과 운동 모두에 잘 어울립니다.  \n빠르고 안정적인 블루투스 연결을 지원해 … (생략) … 언제 어디서나 부담 없이 즐겨보세요."
        }
      ],
      "phase": "final_answer",
      "role": "assistant"
    }
  ],
  "parallel_tool_calls": true,
  "presence_penalty": 0.0,
  "previous_response_id": null,
  "prompt_cache_key": null,
  "prompt_cache_retention": "24h",
  "reasoning": { "context": "current_turn", "effort": "none", "mode": "standard", "summary": null },
  "safety_identifier": null,
  "service_tier": "default",
  "store": false,
  "temperature": 1.0,
  "text": { "format": { "type": "text" }, "verbosity": "medium" },
  "tool_choice": "auto",
  "tool_usage": "… (생략: image_gen 토큰 0, web_search 0회) …",
  "tools": [],
  "top_logprobs": 0,
  "top_p": 0.98,
  "truncation": "disabled",
  "usage": {
    "input_tokens": 45,
    "input_tokens_details": { "cache_write_tokens": 0, "cached_tokens": 0 },
    "output_tokens": 100,
    "output_tokens_details": { "reasoning_tokens": 0 },
    "total_tokens": 145
  },
  "user": null,
  "metadata": {}
}
```

**같은 요청의 Chat Completions 응답 원본** (호출 ③, `POST /v1/chat/completions`, 본문 텍스트 일부만 생략)

```json
{
  "id": "chatcmpl-EasOrIvCxi40IfTtzHFQ7uFVGagMZ",
  "object": "chat.completion",
  "created": 1792457629,
  "model": "gpt-5.4-mini-2026-03-17",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "세련된 디자인과 편안한 착용감으로 … (생략) … 실용성과 만족도를 높여줍니다.",
        "refusal": null,
        "annotations": []
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 45,
    "completion_tokens": 105,
    "total_tokens": 150,
    "prompt_tokens_details": { "cached_tokens": 0, "audio_tokens": 0 },
    "completion_tokens_details": {
      "reasoning_tokens": 0,
      "audio_tokens": 0,
      "accepted_prediction_tokens": 0,
      "rejected_prediction_tokens": 0
    }
  },
  "service_tier": "default",
  "system_fingerprint": null
}
```

### 3.3 Token Usage

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| usage 객체 위치 (JSON 경로) | 최상위 `usage` (Responses, Chat 모두). 생성 응답마다 붙어 오므로 따로 조회할 필요가 없다 | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| Input 토큰 필드 | Responses `usage.input_tokens` / Chat `usage.prompt_tokens`. 캐시 읽기·쓰기 토큰을 포함한 총 입력이다(문서. 이번 실행은 캐시 0이라 포함 여부를 검증할 수 없었다) | 실행 | https://developers.openai.com/api/docs/guides/token-counting |
| Output 토큰 필드 | Responses `usage.output_tokens` / Chat `usage.completion_tokens`. reasoning 토큰과 보이지 않는 formatting 토큰을 포함한 총 출력이다(문서. 이번 실행은 reasoning 0) | 실행 | https://developers.openai.com/api/docs/guides/token-counting |
| Total 토큰 필드 유무 (없으면 계산식) | **있음.** `usage.total_tokens` = input + output (145 = 45 + 100, 세 호출 모두 일치) | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| 추론(Thinking·Reasoning) 토큰 필드와 Output 포함 여부 | Responses `usage.output_tokens_details.reasoning_tokens` / Chat `usage.completion_tokens_details.reasoning_tokens`. 필드는 실행으로 확인했다(effort `none`이라 0). **Output에 이미 포함**돼 있어 더하지 않는다. output 단가로 과금된다(문서. 가이드 예: output 1,186 중 reasoning 1,024) | 실행 | https://developers.openai.com/api/docs/guides/reasoning |
| 캐시 토큰 필드 | 읽기: Responses `input_tokens_details.cached_tokens` / Chat `prompt_tokens_details.cached_tokens`. 쓰기: Responses `input_tokens_details.cache_write_tokens`(실행 응답에 있음). Chat `prompt_tokens_details.cache_write_tokens`는 문서에 optional로 정의돼 있지만 **이번 Chat 응답 원본에는 없었다**(7장). 캐시는 지원 모델에서 자동으로 켜지고, GPT-5.5 이하 모델은 `cached_tokens`가 128 단위로 내림돼 보고된다(문서) | 실행 / 문서 | https://developers.openai.com/api/docs/guides/prompt-caching |
| 호출 전 토큰 세기 API 유무와 비용 | **유무: 있음.** `POST /v1/responses/input_tokens` (`client.responses.input_tokens.count`) → `{"object": "response.input_tokens", "input_tokens": 45}`. 실제 호출의 `input_tokens` 45와 일치했고(role 등 formatting 토큰 포함), 응답에 rate-limit 헤더는 없었다. **비용: 미확인**(과금·rate limit 문구가 문서에 없음, 7장) | 실행 | https://developers.openai.com/api/reference/resources/responses/subresources/input_tokens |
| 스트리밍 응답에서 usage 받는 방법 | Responses: 마지막 `response.completed` 이벤트의 `response.usage`. 실행으로 input 45 / output 101 / total 146을 확인했고 별도 옵션은 필요 없었다. Chat: `stream_options: {"include_usage": true}`를 줘야 `data: [DONE]` 직전 chunk(`choices: []`)에 usage가 온다. 스트림이 끊기면 그 chunk를 못 받을 수 있다(문서, 미실행) | 실행 | https://developers.openai.com/api/reference/resources/responses/streaming-events · https://developers.openai.com/api/reference/resources/chat |

**실행 결과** (4장의 공통 프롬프트 기준, `gpt-5.4-mini`, 2026-10-20)

| 모델 | 입력 토큰 | 출력 토큰 | 추론 토큰 | 총 토큰 (계산 / 응답값) |
| --- | --- | --- | --- | --- |
| `gpt-5.4-mini` · Responses ① | 45 | 100 | 0 | 145 / 145 |
| `gpt-5.4-mini` · Responses 스트리밍 ② | 45 | 101 | 0 | 146 / 146 |
| `gpt-5.4-mini` · Chat Completions ③ | 45 | 105 | 0 | 150 / 150 |

같은 조건이어도 생성 결과가 달라서 출력 토큰은 호출마다 다르다(100~105). 사전 카운트 API 값 45는 세 호출의 입력과 모두 같았다.

### 3.4 Usage 조회 (기간별 사용량)

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| 기간별 사용량 조회 API 유무 (HTTP Method·Endpoint) | 있음. `GET /v1/organization/usage/completions`. 종류별 엔드포인트도 따로 있다: `/usage/embeddings`, `/images`, `/moderations`, `/audio_speeches`, `/audio_transcriptions`, `/vector_stores`, `/code_interpreter_sessions`, `/web_search_calls`, `/file_search_calls`, `/decisions` | 문서 | https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions |
| 필요한 키·권한 (일반 키 / Admin·조직 키 / 콘솔 로그인) | **Admin API 키 필수.** 일반 키로 부르면 **403** `"You have insufficient permissions for this operation. Missing scopes: api.usage.read. …"`이 오고, 바디가 `{"error": "<문장>"}`라 `type`과 `code`가 없다(2026-10-20 실행). Admin 키는 조직 Settings → Admin keys(https://platform.openai.com/settings/organization/admin-keys)에서 만든다. RBAC 가이드상 admin API key 관리 권한은 **Org owner** 역할에만 있다(문서) | 실행 | https://developers.openai.com/api/reference/administration/overview · https://developers.openai.com/api/docs/guides/rbac |
| 조회 단위 (분 / 시간 / 일)와 조회 가능 기간 | `bucket_width` = `1m` / `1h` / `1d`(기본). 한 번에 받는 버킷 수 `limit`(기본/최대)은 1d 7/31, 1h 24/168, 1m 60/1440이다. `start_time`(Unix 초, 필수)부터 `end_time`까지 조회하고, 넘치면 `next_page` 커서로 이어 받는다. 과거 며칠까지 조회되는지는 미확인(문서에 없음, Admin 키가 없어 실측 불가, 7장) | 문서 | https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions |
| 필터·그룹 기준 (모델, API 키, 프로젝트·워크스페이스, 사용자) | `group_by`: `project_id`, `user_id`, `api_key_id`, `model`, `batch`, `service_tier`, `api_source`. 필터: `project_ids`, `user_ids`, `api_key_ids`, `models`, `batch` | 문서 | (위와 같음) |
| 응답 필드 (입력 / 출력 / 캐시 토큰, 요청 수) | 최상위 `object: "page"`, `data[]`, `has_more`, `next_page`. 버킷: `start_time`, `end_time`, `results[]`. results 필수: `input_tokens`(캐시 포함), `output_tokens`, `num_model_requests`. 선택: `input_cached_tokens`, `input_uncached_tokens`, `input_cache_write_tokens`, 모달리티별(`input_text_tokens`, `input_image_tokens`, `input_audio_tokens` 등), 그룹 키 | 문서 | (위와 같음) |
| 데이터 반영 지연 시간 | 미확인. 공식 개발자 문서에 반영 지연 문구가 없고, Admin 키가 없어 실측도 못 했다(7장) | 미확인 | https://developers.openai.com/cookbook/examples/completions_usage_api |
| 콘솔 대시보드에서 보는 방법 (메뉴 경로) | platform.openai.com → Usage (https://platform.openai.com/usage). service tier, line item 등으로 묶어 볼 수 있다. 대시보드 보기 권한(Usage Read)은 기본 역할 중 **Org owner**에만 있고, 커스텀 역할로 줄 수 있다(RBAC 가이드) | 문서 | https://developers.openai.com/api/docs/guides/rbac · https://developers.openai.com/cookbook/examples/completions_usage_api |
| 개별 요청 단위 로그 조회 가능 여부 | 콘솔 Logs(https://platform.openai.com/logs?api=responses)에서 저장된 응답을 볼 수 있다. Responses `store`는 기본 true이고 30일 보관된다. 저장된 응답은 `GET /v1/responses/{id}`로 다시 받아 `usage`를 볼 수 있다. 다만 기간·조건으로 요청 목록을 뽑는 API는 없다. 이 문서의 예제는 `store=false`라서 조회되지 않는다 → 요청 단위 기록은 직접 저장해야 한다 | 문서 | https://developers.openai.com/api/docs/guides/migrate-to-responses · https://developers.openai.com/api/reference/resources/responses/methods/create |

### 3.5 비용 확인

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| 호출 응답에 비용 포함 여부 | **포함 안 됨.** 응답에는 토큰 수와 `service_tier`만 있다 | 실행 | https://developers.openai.com/api/reference/resources/responses/methods/create |
| 기간별 비용 조회 API 유무 (Endpoint, 키 권한, 조회 단위, 금액 단위·통화) | 있음. `GET /v1/organization/costs`. **Admin 키 필수**(일반 키로는 Usage API와 같은 403, 2026-10-20 실행). 문서 기준 상세: `bucket_width`는 `1d`만, `limit` 1~180(기본 7). `group_by`는 `project_id`, `user_id`, `line_item`, `api_key_id`, `api_source`이고 **모델별 group_by는 없다**(`line_item` 이름으로 간접 구분). 금액 `amount.value`는 달러 숫자(예 0.06), `amount.currency`는 소문자 `"usd"` | 실행 | https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/costs |
| 단가표 위치 (API로 제공 여부 / 가격 페이지 URL) | API로 제공되지 않는다(모델 목록에도 없음). 기준 출처는 가격 페이지 https://developers.openai.com/api/docs/pricing (Standard / Batch / Flex / Fast / Ultrafast 표)다. 모델 페이지와 처리 모드 가이드에도 같은 값이 있고, URL 끝에 `.md`를 붙이면 Markdown 원문을 받는다 | 문서 | https://developers.openai.com/api/docs/pricing |
| 1회 호출 비용 계산식 | `비용 = (input − cached − cache_write) × 입력단가 + cached × 캐시입력단가 + cache_write × 캐시쓰기단가 + output(reasoning 포함) × 출력단가` (단가 $/1M). 캐시 쓰기 단가는 GPT-5.6 이후 모델에만 있고 입력의 1.25배다. `gpt-5.4` 계열은 캐시 쓰기 단가가 따로 없어 입력 단가를 쓴다 | 문서 | https://developers.openai.com/api/docs/guides/prompt-caching |
| 할인·할증 요소 (캐시, 배치, 긴 입력, 우선 처리, 리전) | **캐시 읽기**: 모델별 cached input 단가를 쓴다. GPT-5.x 이후 입력의 10%(`gpt-6.1-sol` 5%), gpt-4.1 계열 25%, gpt-4o 계열·o1 50%. **Batch**·**Flex**(`service_tier="flex"`): 표준의 50%. **Fast**(구 Priority, `"fast"`/`"priority"`): 모델별 할증. GPT-6·5.6·5.4·5.4-mini는 2배, gpt-5.5는 2.5배, 구형은 1.7~2배. `gpt-5.4-nano`는 Fast 미지원. 혼잡하면 표준으로 강등되고 표준 요금이 붙는다(응답 `service_tier: "default"`). **Ultrafast**(`gpt-6-astra`, `gpt-6.1-sol`만): 6배. **긴 입력**(272K 초과): GPT-6·5.6 계열, gpt-5.5, gpt-5.4에서 입력·캐시 입력·캐시 쓰기 2배, 출력 1.5배. `gpt-5.4-mini`, `nano`는 해당 없음. **리전**(data residency): 2026-03-05 이후 출시 모델에 10% 가산 | 문서 | https://developers.openai.com/api/docs/pricing · https://developers.openai.com/api/docs/guides/priority-processing · https://developers.openai.com/api/docs/guides/flex-processing |
| 호출 전 예상 비용 계산 방법 | 입력은 `POST /v1/responses/input_tokens`로 정확히 센다(실행 45 = 실제 45). 출력은 미리 알 수 없어 `max_output_tokens`를 상한으로 최대 비용을 잡는다(예: 45 × 0.75 + 1,024 × 4.50 → 최대 $0.004642) | 실행 | https://developers.openai.com/api/docs/guides/token-counting |
| 콘솔에서 비용 보는 방법과 반영 시점 | platform.openai.com/usage(쿡북의 "usage and cost dashboards")에서 line item으로 묶어 비용을 본다. 크레딧 충전·잔액은 Settings → Organization → Billing(https://platform.openai.com/settings/organization/billing)이다. 반영 시점은 미확인(문서 없음, 7장) | 문서 | https://developers.openai.com/api/docs/guides/priority-processing · https://developers.openai.com/cookbook/examples/completions_usage_api |

**실행 결과** (3.3과 같은 호출, 단가는 2026-10-20 가격 페이지의 `gpt-5.4-mini` 표준 티어)

| 모델 | 입력 / 출력 토큰 | 계산 비용 (USD) | 적용 단가 (입력 / 출력, $/백만 토큰) |
| --- | --- | --- | --- |
| `gpt-5.4-mini` · Responses ① | 45 / 100 | 0.000484 | 0.75 / 4.50 |
| `gpt-5.4-mini` · 스트리밍 ② | 45 / 101 | 0.000488 | 0.75 / 4.50 |
| `gpt-5.4-mini` · Chat ③ | 45 / 105 | 0.000506 | 0.75 / 4.50 |

세 응답 모두 `cached_tokens: 0`, `service_tier: "default"`(표준)여서 표준 입력 단가만 적용됐다. 콘솔 청구액과의 대조는 반영 시점을 몰라서 아직 하지 않았다(7장).

### 3.6 상태 및 오류 확인

| 확인할 내용 | 조사 결과 | 근거 | 참고 URL |
| --- | --- | --- | --- |
| 연결 성공 확인 방법 (가장 가벼운 호출) | `GET /v1/models` → 200. 토큰을 생성하지 않고 키와 네트워크를 함께 확인한다. 서버 처리 837ms(`openai-processing-ms`, 2026-10-20). 생성 경로까지 확인하려면 `max_output_tokens=16`으로 짧게 호출한다(소액 과금) | 실행 | https://developers.openai.com/api/reference/resources/models/methods/list |
| 오류 응답 구조 (JSON 필드) | `{"error": {"message", "type", "param", "code"}}`. SDK는 `e.status_code`, `e.body`(error 안쪽 dict), `e.request_id`로 꺼낸다. **예외**: Admin 엔드포인트의 403은 `{"error": "<문장>"}`(문자열)이라 `type`과 `code`가 없다. 공식 가이드에는 JSON 전체 예시가 없다(7장) | 실행 | https://developers.openai.com/api/docs/guides/error-codes |
| 인증 오류 (HTTP 코드, 오류 타입) | **401**, `type: "invalid_request_error"`, `code: "invalid_api_key"`, 메시지 `"Incorrect API key provided: INVALID-********TEST. …"`, SDK `AuthenticationError`. 만료된 키는 `code: "expired_secret_key"`(문서. 2026-10-18 콘솔에서 관찰했지만 원본은 보존하지 못했다) | 실행 | https://developers.openai.com/api/docs/guides/error-codes |
| Rate Limit (HTTP 코드, 오류 타입, retry-after 헤더) | **429**, SDK `RateLimitError`. 속도 제한은 두 종류다. ① "Rate limit reached for requests"(가이드에 type/code 표기 없음). ② "Slow down" `type: "rate_limit_error"`, `code: "slow_down"`(요청률 급증). 둘 다 `Retry-After`(초)가 붙을 수 있으니 기다린 뒤 재시도한다. **크레딧·한도 소진도 429**다: `code: "credit_balance_exhausted"`(`type`은 `insufficient_quota`일 수 있음), `organization_spend_limit_exceeded`, `project_spend_limit_exceeded`, `organization_usage_limit_exceeded` → 재시도 금지. HTTP 코드만으로는 구분할 수 없어 `error.code`로 나눈다. 크레딧 소진은 2026-10-18에 겪었지만 원본은 보존하지 못했다 | 문서 | https://developers.openai.com/api/docs/guides/error-codes · https://developers.openai.com/api/docs/guides/rate-limits |
| 남은 한도 확인 방법 (응답 헤더 / 콘솔) | 생성 응답 헤더 `x-ratelimit-limit-requests` / `-tokens`, `x-ratelimit-remaining-requests` / `-tokens`, `x-ratelimit-reset-requests` / `-tokens`. 호출 ② 헤더 기준 실행값: 한도 10,000 요청 / 10,000,000 토큰, 남은 9,999 / 9,999,792, 리셋 6ms / 1ms. 헤더에는 기간 단위가 없다. 가이드는 한도를 RPM·TPM 등으로 정의하고, 프로젝트 단위 `x-ratelimit-*-project-tokens`도 있다(문서). 콘솔은 Settings → Organization → Limits(https://platform.openai.com/settings/organization/limits)이고, 사용량 티어는 Free / Build / Launch / Grow다(문서) | 실행 | https://developers.openai.com/api/docs/guides/rate-limits |
| Timeout (클라이언트 예외 / 서버 오류 코드) | 클라이언트 예외는 `APITimeoutError`이고 `APIConnectionError`의 하위 클래스다. SDK 기본값은 전체 600초, 연결 5초(문서). 읽기 Timeout은 2026-10-19 로컬 무응답 서버로 재현했다(OpenAI 서버 아님): `APITimeoutError("Request timed out.")`, 원인 예외 `httpx2.ReadTimeout`. **실제 OpenAI 호출에 `timeout=0.001`을 주면 `APIConnectionError("Connection error.")`가 났다.** 연결 단계 오류가 ConnectError로 분류되기 때문으로 보인다(같은 설정으로 다른 호스트에 호출했을 때 원인 예외가 ConnectError였다). 그래서 `except APITimeoutError`를 먼저 두고 `e.__cause__` 타입을 같이 기록해야 한다. 서버 쪽 timeout 전용 코드(504)는 문서에 없다 | 실행 / 문서 | https://github.com/openai/openai-python/blob/main/src/openai/_exceptions.py · https://github.com/openai/openai-python/blob/main/src/openai/_constants.py |
| 과부하·서버 오류 (5xx 코드와 타입) | 500 "The server had an error while processing your request"(가이드에 type/code 표기 없음) → 잠시 후 재시도하고 상태 페이지를 확인한다. 503 "Model temporarily overloaded", `type: "service_unavailable_error"`, `code: "server_is_overloaded"`(`Retry-After` 가능). SDK는 5xx를 모두 `InternalServerError`로 던진다. 재현하지 못했다 | 문서 | https://developers.openai.com/api/docs/guides/error-codes |
| SDK 자동 재시도 기본값과 끄는 방법 | 기본 **2회**, 지수 백오프 0.5~8초. 대상은 연결 오류, timeout, 408, 409, 429, 5xx다. 판단 순서: `Retry-After`가 120초를 넘으면 재시도하지 않는다(최우선). 그다음 `x-should-retry` 헤더(true/false)를 따르고, 그 뒤 상태 코드로 판단한다. 끄기: `OpenAI(max_retries=0)` 또는 `client.with_options(max_retries=0)`. 이번 실행은 모두 `max_retries=0`이다 | 문서 | https://github.com/openai/openai-python/blob/main/README.md · https://github.com/openai/openai-python/blob/main/src/openai/_base_client.py |
| 서비스 상태 페이지 URL | https://status.openai.com. 인증 없이 JSON으로도 볼 수 있다: `GET https://status.openai.com/api/v2/status.json` → `{"status": {"indicator": "none", "description": "All Systems Operational"}}`. `/api/v2/components.json`에는 Responses, Chat Completions 등 37개 컴포넌트가 있다(2026-10-19 실행) | 실행 | https://status.openai.com/ |

**오류 코드 정리** (직접 재현한 것은 응답 원본을 7장 아래 첨부)

| HTTP 코드 | 오류 타입 (응답 값) | 의미 | SDK 예외 클래스 | 대응 (재시도 / 중단) | 근거 |
| --- | --- | --- | --- | --- | --- |
| 400 | `invalid_request_error` / `integer_below_min_value`(`max_output_tokens=8`, 2026-10-20), `unsupported_parameter`(Chat `max_tokens`, 2026-10-19), code `null` + param `reasoning_effort`(Chat tools + reasoning, 2026-10-19) | 잘못된 요청 | `BadRequestError` | 중단 (요청 수정) | 실행 |
| 401 | `invalid_request_error` / `invalid_api_key`. 만료 키는 `expired_secret_key`(문서) | 인증 실패 | `AuthenticationError` | 중단 (키 확인) | 실행 |
| 403 | Admin API를 일반 키로 호출: 바디가 문자열(`type`/`code` 없음), "Missing scopes: api.usage.read". 일반 API에서는 지원하지 않는 국가·지역일 때(문서) | 권한 없음 | `PermissionDeniedError` | 중단 | 실행 |
| 404 | `invalid_request_error` / `model_not_found` | 모델·경로 없음 | `NotFoundError` | 중단 (모델 ID 확인) | 실행 |
| 429 | 속도 제한: "Rate limit reached for requests"(type 미기재), `rate_limit_error` / `slow_down`. 할당량: `insufficient_quota` / `credit_balance_exhausted`, `*_spend_limit_exceeded`, `organization_usage_limit_exceeded` | Rate Limit 또는 할당량 초과 | `RateLimitError` | 속도 제한 → `Retry-After` 후 재시도 / 크레딧·한도 → 중단 | 문서 |
| 500 | 가이드에 type/code 표기 없음 (메시지 "The server had an error while processing your request") | 서버 오류 | `InternalServerError` | 재시도 (상태 페이지 확인) | 문서 |
| 503 | `service_unavailable_error` / `server_is_overloaded` | 과부하·일시 중단 | `InternalServerError` | `Retry-After` 후 재시도 | 문서 |
| 504 | 미확인 (오류 가이드에 504 없음, 7장) | 서버 쪽 Timeout | `InternalServerError` (5xx) | 재시도 | 미확인 |

---

## 4. 호출 예제

세 Provider가 같은 출력 형식(6장 공통 결과 스키마)을 찍도록 템플릿 골격의 `TODO`를 OpenAI SDK에 맞게 바꿨다. 파일은 `examples/openai/example.py`이고 아래 코드와 같다.

**공통 호출 조건** (세 Provider 동일)

| 조건 | 값 |
| --- | --- |
| system prompt | 당신은 쇼핑몰 상품 설명을 작성하는 전문가입니다. (Responses `instructions`) |
| user prompt | 무선 블루투스 이어폰의 상품 설명을 3문장으로 작성해 주세요. (Responses `input`) |
| 최대 출력 토큰 | 1024 (`max_output_tokens`) |
| temperature | 모델 기본값 (보내지 않음. 응답에 1.0으로 나옴) |
| 추론·thinking 설정 | 모델 기본값 (보내지 않음. `gpt-5.4-mini`의 기본값은 `none`) |
| 자동 재시도 | 0회 (`max_retries=0`) |
| Timeout | 60초 (`timeout=60.0`) |
| 스트리밍 | 사용 안 함 |
| 추가 | `store=false` (2장 "이 문서에서 달리한 점") |

**실행 방법**

| 항목 | 값 |
| --- | --- |
| 설치 | `pip install openai==3.35.1` |
| 키 설정 | `export OPENAI_API_KEY=...` |
| 실행 | `python example.py` (파일로 저장해 실행한다. `__file__`을 써서 노트북 셀에서는 동작하지 않는다. 실행할 때마다 같은 폴더의 `response_raw.json`을 덮어쓰고, 이 문서의 증거 사본은 `evidence/openai/template_20261020/responses_call.json`에 따로 있다) |
| 실행 환경 | Python 3.12, macOS 26.4 (저장소에서는 `uv run --env-file .env python examples/openai/example.py`) |

```python
"""OpenAI 호출 예제 — LLM Provider API 조사 템플릿 4장 (공통 호출 조건 그대로).

pip install openai==3.35.1
export OPENAI_API_KEY=...
python example.py

실행하면 콘솔에 공통 결과 스키마 JSON 을 출력하고, 같은 폴더에 HTTP 응답 원본(response_raw.json)을 덮어쓴다.
"""
import json
import os
import sys
import time
from pathlib import Path

import openai
from openai import OpenAI

API_KEY = os.environ["OPENAI_API_KEY"]
MODEL = "gpt-5.4-mini"
# USD / 1M tokens, standard tier, https://developers.openai.com/api/docs/pricing (2026-10-20 확인)
# gpt-5.4 계열은 캐시 쓰기 단가가 따로 없어 입력 단가를 쓴다. GPT-5.6 이후 모델은 "cache_write" 를 넣는다.
PRICE_USD_PER_M = {"input": 0.75, "cached_input": 0.075, "output": 4.50}

SYSTEM_PROMPT = "당신은 쇼핑몰 상품 설명을 작성하는 전문가입니다."
USER_PROMPT = "무선 블루투스 이어폰의 상품 설명을 3문장으로 작성해 주세요."
RAW_OUT = Path(__file__).with_name("response_raw.json")

client = OpenAI(api_key=API_KEY, timeout=60.0, max_retries=0)  # Timeout 60초, 자동 재시도 0회

try:
    # 1) 모델 목록 조회 → 연결 확인을 겸함 (토큰 과금 없음)
    models = client.models.list()
    print("models:", [m.id for m in models.data][:5])

    # 2) 모델 호출 (Responses API). temperature·reasoning 은 모델 기본값 그대로 둔다.
    t0 = time.perf_counter()
    raw = client.responses.with_raw_response.create(
        model=MODEL,
        instructions=SYSTEM_PROMPT,
        input=USER_PROMPT,
        max_output_tokens=1024,
        store=False,  # 비교 실험 응답을 OpenAI 에 저장하지 않음 (기본값 true)
    )
    latency_ms = (time.perf_counter() - t0) * 1000
except openai.AuthenticationError as e:  # 401
    print("AUTH", e.status_code, e.body, e.request_id)
    sys.exit(1)
except openai.RateLimitError as e:  # 429: 속도 제한 / 크레딧 소진 / 지출 한도 → body 의 code 로 구분
    print("RATE_LIMIT_OR_QUOTA", e.status_code, e.body, e.request_id)
    sys.exit(1)
except openai.APIStatusError as e:  # 400/403/404/5xx
    print("API_ERROR", e.status_code, e.body, e.request_id)
    sys.exit(1)
except openai.APITimeoutError:  # APIConnectionError 의 하위 클래스라 먼저 잡는다
    print("TIMEOUT")
    sys.exit(1)
except openai.APIConnectionError as e:  # 아주 짧은 timeout 은 여기로 올 수 있어 원인 예외도 남긴다
    print("NETWORK", type(e.__cause__).__name__ if e.__cause__ else None, e)
    sys.exit(1)
resp = raw.parse()

RAW_OUT.write_text(
    json.dumps(
        {
            "status_code": raw.status_code,
            "headers": {
                k: v
                for k, v in raw.headers.items()
                if k.startswith("x-ratelimit-") or k in ("x-request-id", "openai-processing-ms")
            },
            "body": raw.http_response.json(),
        },
        ensure_ascii=False,
        indent=2,
    ),
    encoding="utf-8",
)

# 3) 응답 텍스트와 Token Usage
text = resp.output_text  # = output[type=message].content[type=output_text].text
usage = resp.usage
input_tokens = usage.input_tokens  # 캐시 읽기·쓰기 포함
cached_tokens = usage.input_tokens_details.cached_tokens
cache_write_tokens = usage.input_tokens_details.cache_write_tokens
output_tokens = usage.output_tokens  # reasoning 포함
reasoning_tokens = usage.output_tokens_details.reasoning_tokens
total_tokens = input_tokens + output_tokens
assert total_tokens == usage.total_tokens, (total_tokens, usage.total_tokens)

# 종료 사유: 원시 status 를 그대로 남긴다 (정상/잘림/거절 매핑은 6장)
reason = getattr(resp.incomplete_details, "reason", None)
refused = any(c.type == "refusal" for o in resp.output if o.type == "message" for c in o.content)
finish_reason = "refusal" if refused else (resp.status if reason is None else f"{resp.status}:{reason}")

# 4) 비용 계산 (토큰 × 단가)
cost_usd = (
    (input_tokens - cached_tokens - cache_write_tokens) * PRICE_USD_PER_M["input"]
    + cached_tokens * PRICE_USD_PER_M["cached_input"]
    + cache_write_tokens * PRICE_USD_PER_M.get("cache_write", PRICE_USD_PER_M["input"])
    + output_tokens * PRICE_USD_PER_M["output"]
) / 1_000_000

print(
    json.dumps(
        {
            "provider": "OpenAI",
            "model": resp.model,  # 응답 스냅샷 (요청 모델 ID 는 MODEL)
            "response_text": text[:100],
            "finish_reason": finish_reason,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "reasoning_tokens": reasoning_tokens,
            "total_tokens": total_tokens,
            "cost_usd": round(cost_usd, 6),
            "latency_ms": round(latency_ms),
            "request_id": resp._request_id,  # 응답 헤더 x-request-id
        },
        ensure_ascii=False,
        indent=2,
    )
)
```

- 출력 키 `model`은 6장의 `model_id`에 해당한다. 템플릿 골격은 요청 모델 ID(`MODEL`)를 출력하지만, 이 예제는 실제로 응답한 스냅샷(`resp.model`)을 출력한다.
- 아래 실행 결과는 오류 처리를 보강하기 전 버전으로 돌린 것이다. 보강한 부분은 1단계를 `try` 안으로 옮긴 것, `finish_reason` 안전 처리, 캐시 쓰기 비용, 원인 예외 기록이다. 저장된 응답 원본으로 후처리를 다시 돌려 출력값이 같음을 확인했다(`finish_reason` `completed`, 비용 0.000484). 잘못된 키 분기는 무료 호출로 따로 확인했다(`AUTH 401 … invalid_api_key`).

**실행 결과** (콘솔 출력 그대로, 2026-10-20)

```text
models: ['gpt-4-turbo-2024-04-09', 'gpt-realtime-2.1-mini', 'gpt-realtime-2025-08-28', 'omni-moderation-2024-09-26', 'gpt-live-transcribe']
{
  "provider": "OpenAI",
  "model": "gpt-5.4-mini-2026-03-17",
  "response_text": "편안한 착용감과 깔끔한 음질을 갖춘 무선 블루투스 이어폰으로, 일상과 운동 모두에 잘 어울립니다.  \n빠르고 안정적인 블루투스 연결을 지원해 음악 감상과 통화 시 끊김 없이 편리하",
  "finish_reason": "completed",
  "input_tokens": 45,
  "output_tokens": 100,
  "reasoning_tokens": 0,
  "total_tokens": 145,
  "cost_usd": 0.000484,
  "latency_ms": 2120,
  "request_id": "req_6acd917c9b204d6d84d4898a64845cf4"
}
```

응답시간 참고(2026-10-20, 1회씩): Responses ①은 클라이언트 2,120ms(서버 `openai-processing-ms` 1,805). 스트리밍 ②는 첫 텍스트까지 2,059ms, 완료까지 2,470ms. Chat ③은 1,768ms(서버 1,012). 한 번씩만 잰 값이라 비교 근거로는 부족하다.

**오류 재현 결과** (잘못된 키, 없는 모델 ID, 최소값 미만 파라미터. 모두 `POST /v1/responses`, 2026-10-20, 과금 없음. 원본 `evidence/openai/template_20261020/free_checks.json`)

```json
{
  "err_401_bad_key": {
    "status": 401,
    "headers": { "openai-processing-ms": "47", "openai-version": "2020-10-01", "x-request-id": "req_54e889f4ed0a40fd8e0453250587b834" },
    "body": {
      "error": {
        "message": "Incorrect API key provided: INVALID-********TEST. You can find your API key at https://platform.openai.com/account/api-keys.",
        "type": "invalid_request_error",
        "param": null,
        "code": "invalid_api_key"
      }
    }
  },
  "err_404_bad_model": {
    "status": 404,
    "headers": { "openai-processing-ms": "180", "openai-version": "2020-10-01", "x-request-id": "req_669d34594fd64efe8b74bd0109987555" },
    "body": {
      "error": {
        "message": "The model `model-does-not-exist-123` does not exist or you do not have access to it.",
        "type": "invalid_request_error",
        "param": null,
        "code": "model_not_found"
      }
    }
  },
  "err_400_min_output": {
    "status": 400,
    "headers": { "openai-processing-ms": "23", "openai-version": "2020-10-01", "x-request-id": "req_d5e5268fe2ec41d5902b55cb247ee2c0" },
    "body": {
      "error": {
        "message": "Invalid 'max_output_tokens': integer below minimum value. Expected a value >= 16, but got 8 instead.",
        "type": "invalid_request_error",
        "param": "max_output_tokens",
        "code": "integer_below_min_value"
      }
    }
  }
}
```

---

## 5. Provider 비교표

> 취합 담당자가 세 문서의 3장을 보고 채웁니다. 앞의 두 표는 `제공` / `부분 제공` / `미제공` / `미확인` 중 하나를 적고, 마지막 표에 구체적인 방법의 차이를 적습니다.
> 이 문서에서는 **OpenAI 열만** 채웠다(근거는 3장). Anthropic, Google 열과 차이점 요약은 취합할 때 채운다.

**모델 목록 · 모델 호출 · Token Usage**

| 항목 | 세부 | OpenAI | Anthropic | Google | 차이점 요약 |
| --- | --- | --- | --- | --- | --- |
| 모델 목록 | 목록 조회 API | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 목록 | 컨텍스트 길이·지원 기능 포함 | 미제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 목록 | 단가 포함 | 미제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 호출 | 단일 호출 API | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 호출 | system prompt 별도 파라미터 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 호출 | 구조화 출력 (JSON 스키마 강제) | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 모델 호출 | 이미지 입력 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Token Usage | Input / Output 필드 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Token Usage | Total 필드 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Token Usage | 추론 토큰 필드 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Token Usage | 캐시 토큰 필드 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Token Usage | 호출 전 토큰 세기 API | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |

**Usage 조회 · 비용 · 상태·오류**

| 항목 | 세부 | OpenAI | Anthropic | Google | 차이점 요약 |
| --- | --- | --- | --- | --- | --- |
| Usage 조회 | 기간별 사용량 API | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Usage 조회 | 일반 API 키로 조회 가능 | 미제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Usage 조회 | 콘솔 대시보드 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 비용 | 호출 응답에 비용 포함 | 미제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 비용 | 기간별 비용 API | 부분 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 비용 | 단가 API 제공 | 미제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 상태·오류 | 오류 응답에 타입·요청 ID 포함 | 부분 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 상태·오류 | 남은 한도 응답 헤더 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 상태·오류 | SDK 자동 재시도 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| 상태·오류 | 서비스 상태 페이지 | 제공 | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |

OpenAI 값의 단서: '기간별 비용 API'가 부분 제공인 이유는 Admin 키가 필요하고, 1일 단위이며, 모델별 group_by가 없기 때문이다. '오류 응답에 타입·요청 ID 포함'이 부분 제공인 이유는 Admin 엔드포인트 403에 type/code가 없기 때문이다.

**호출·응답 구조 차이** (값은 응답 원본 기준)

| 비교 항목 | OpenAI | Anthropic | Google |
| --- | --- | --- | --- |
| 호출 Endpoint (HTTP Method·경로) | `POST /v1/responses` | 취합 시 기입 | 취합 시 기입 |
| 인증 헤더 | `Authorization: Bearer <key>` | 취합 시 기입 | 취합 시 기입 |
| 필수 파라미터 | 레퍼런스상 모두 optional. 실무상 `model` + `input` (`max_output_tokens`는 선택, 주면 ≥ 16) | 취합 시 기입 | 취합 시 기입 |
| 응답 텍스트 JSON 경로 | `output[type=message].content[type=output_text].text` | 취합 시 기입 | 취합 시 기입 |
| 종료 사유 필드와 정상 값 | `status` = `completed` | 취합 시 기입 | 취합 시 기입 |
| usage JSON 경로와 필드명 | `usage.input_tokens` / `output_tokens` / `total_tokens` | 취합 시 기입 | 취합 시 기입 |
| 오류 응답 구조 | `{"error": {"message","type","param","code"}}` (Admin 403은 `{"error": "<문장>"}`) | 취합 시 기입 | 취합 시 기입 |
| Usage·비용 API 필요 권한 | Admin API 키 (Org owner가 생성) | 취합 시 기입 | 취합 시 기입 |
| 가격 페이지 URL | https://developers.openai.com/api/docs/pricing | 취합 시 기입 | 취합 시 기입 |

---

## 6. 공통 수집 항목과 Provider별 고유 항목

세 Provider에서 모두 얻을 수 있는 값을 공통 결과 스키마로 정하고, 각 Provider에서 어느 필드를 가져올지 적습니다. 4장 예제의 출력 키와 같습니다.

> 이 문서에서는 OpenAI 출처만 채웠다. 경로는 Responses 응답 원본 기준이고 괄호 안은 Chat Completions 경로다. 템플릿 4장 골격의 출력 키는 `model`, 이 표의 필드는 `model_id`라 서로 다르다(취합 담당에게 공유).

| 공통 필드 | 의미 | OpenAI 출처 (JSON 경로) | Anthropic 출처 (JSON 경로) | Google 출처 (JSON 경로) | 직접 계산 필요 |
| --- | --- | --- | --- | --- | --- |
| `model_id` | 호출에 쓴 모델 ID | 요청 `model`(`gpt-5.4-mini`). 응답 `model`은 스냅샷(`gpt-5.4-mini-2026-03-17`)이다. 예제는 스냅샷을 출력 | 취합 시 기입 | 취합 시 기입 | 아니오 (요청 ID와 스냅샷을 둘 다 저장 권장) |
| `response_text` | 응답 본문 텍스트 | `output[type=message].content[type=output_text].text` (`choices[0].message.content`) | 취합 시 기입 | 취합 시 기입 | 아니오 (항목이 여럿이면 이어 붙임) |
| `finish_reason` | 종료 사유 (정상 / 잘림 / 거절로 통일) | `status` + `incomplete_details.reason`, 거절은 content `type: "refusal"` (`choices[0].finish_reason`) | 취합 시 기입 | 취합 시 기입 | 매핑 필요: `completed`→정상, `incomplete`+`max_output_tokens`→잘림, refusal·`content_filter`→거절 |
| `input_tokens` | 입력 토큰 (캐시 포함 여부 명시) | `usage.input_tokens` (`usage.prompt_tokens`). **캐시 포함** | 취합 시 기입 | 취합 시 기입 | 아니오 |
| `output_tokens` | 출력 토큰 (추론 포함 여부 명시) | `usage.output_tokens` (`usage.completion_tokens`). **추론 포함** | 취합 시 기입 | 취합 시 기입 | 아니오 |
| `reasoning_tokens` | 추론·thinking 토큰, 없으면 0 | `usage.output_tokens_details.reasoning_tokens` (`usage.completion_tokens_details.reasoning_tokens`) | 취합 시 기입 | 취합 시 기입 | 아니오 |
| `cached_tokens` | 캐시에서 읽은 입력 토큰, 없으면 0 | `usage.input_tokens_details.cached_tokens` (`usage.prompt_tokens_details.cached_tokens`) | 취합 시 기입 | 취합 시 기입 | 아니오 |
| `total_tokens` | 입력 + 출력 | `usage.total_tokens` | 취합 시 기입 | 취합 시 기입 | 아니오 (응답값과 계산값이 같은지 확인) |
| `cost_usd` | 토큰 × 단가 | 없음 | 취합 시 기입 | 취합 시 기입 | **예** (3.5 계산식, `service_tier`별 단가) |
| `latency_ms` | 클라이언트 측정 응답시간 | 없음 (서버 처리 시간은 헤더 `openai-processing-ms`) | 취합 시 기입 | 취합 시 기입 | **예** (클라이언트 측정) |
| `request_id` | 문의·추적용 요청 ID | 응답 헤더 `x-request-id` | 취합 시 기입 | 취합 시 기입 | 아니오 |
| `error_status` | 오류 시 HTTP 코드 | HTTP 상태 코드 (SDK `e.status_code`) | 취합 시 기입 | 취합 시 기입 | 아니오 (연결 오류·Timeout은 코드 없음) |
| `error_type` | 오류 시 오류 타입 문자열 | `error.type` + `error.code` (Admin 403은 문자열만) | 취합 시 기입 | 취합 시 기입 | 429는 `error.code`까지 봐야 분류됨 |
| `context_window` | 모델 최대 입력 토큰 (모델 목록 API 또는 문서) | 모델 목록 API에 없음 → 모델 문서의 "Maximum input tokens". 컨텍스트 윈도우와 값이 다르다(5.4-mini 272K vs 400K, gpt-6-* 922K vs 1.05M, gpt-5.4는 미기재) | 취합 시 기입 | 취합 시 기입 | **예** (문서 기반 표 유지) |
| `price_input` / `price_output` | 단가 ($/백만 토큰), 출처와 기준일 | API에 없음 → 가격 페이지 (2026-10-20 확인) | 취합 시 기입 | 취합 시 기입 | **예** (단가표 유지) |

**Provider별 고유 항목** (다른 Provider에 없는 필드·설정·제약)

| Provider | 고유 항목 | 비교에 미치는 영향 | 공통 스키마 반영 방안 (무시 / 별도 필드 / 기본값 0) |
| --- | --- | --- | --- |
| OpenAI | 호출 API가 둘(Responses / Chat)이고 usage 필드 이름이 다르다. Chat은 tools + reasoning 제약이 있다(3.2) | 같은 모델도 API에 따라 필드와 지원 기능이 다르다 | 별도 필드 `api` (`responses` / `chat_completions`), 기본 Responses |
| OpenAI | `service_tier`(`default` / `flex` / `fast`·`priority` / `ultrafast`)에 따라 단가가 0.5~6배 | 같은 토큰이어도 비용이 다르고, Fast는 혼잡하면 표준으로 강등된다 | 별도 필드 `service_tier` (응답값을 기록해 비용 계산에 사용) |
| OpenAI | `cache_write_tokens`와 캐시 쓰기 단가(GPT-5.6 이후 1.25배) | 캐시 쓰기가 있으면 입력 비용이 늘어난다 | 별도 필드 `cache_write_tokens` (없으면 0) |
| OpenAI | 모델마다 reasoning 기본값이 다르다(`gpt-5.4-mini` `none`, `gpt-6-luna` `medium`, `gpt-6.1-sol`·`gpt-6-astra`는 `none` 불가) | "모델 기본값"으로 비교하면 추론량이 달라진다 | 별도 필드 `reasoning_effort` (실제 적용값, 응답 `reasoning.effort`) |
| OpenAI | `store` 기본 true (응답 30일 저장) | 비교 결과에는 영향 없음, 데이터 정책에 영향 | 무시 (요청에서 `store=false` 고정) |
| OpenAI | 서버 처리 시간 헤더 `openai-processing-ms` | 네트워크 시간을 뺀 서버 시간을 따로 볼 수 있다 | 별도 필드 `server_latency_ms` (없으면 null) |
| Anthropic | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |
| Google | 취합 시 기입 | 취합 시 기입 | 취합 시 기입 |

---

## 7. 이슈·특이사항 및 미확인 항목

3장에서 `미확인`으로 남긴 것, 문서와 실행 결과가 다른 것, 공통 비교를 방해하는 제약, 기업에 물어봐야 할 것을 한 표에 모읍니다. 실행하지 못한 항목은 이유(키 권한, 비용, 대량 요청 필요 등)를 같이 적습니다.

구분: `제약사항` / `문서·실행 불일치` / `미확인` / `기업 문의`

| 구분 | 내용 | 영향 (공통 비교·개발 시) | 조치 또는 질문 | Provider |
| --- | --- | --- | --- | --- |
| 제약사항 | Admin 키 없이는 기간별 Usage·Costs API를 쓸 수 없다(일반 키 403, 2026-10-20 실행). Admin 키는 Org owner만 만들 수 있고(RBAC 가이드), Usage 대시보드도 기본 역할 중 Org owner만 본다 | 기능 ③의 기간별 사용량·비용을 API로 받을 수 없다 → 시뮬레이터가 호출마다 usage를 저장해 직접 집계해야 한다 | 기업 PoC 조직의 Owner가 Admin 키나 Usage 조회 권한을 줄 수 있는지 킥오프에서 질문 | OpenAI |
| 제약사항 | `gpt-5.4-mini` Chat에서 function tools + `reasoning_effort≠none`이면 400(2026-10-19 실행). 문서상 `gpt-6-astra`·`gpt-6.1-sol`은 Chat에서 function calling 자체가 안 된다. `max_output_tokens` 최소 16, Chat `max_tokens`는 400 | 도구·추론 비교는 Responses로 통일해야 하고, 출력 상한을 16 미만으로 맞출 수 없다 | 어댑터 기본을 Responses로 하고, 공통 최대 출력은 16 이상 | OpenAI |
| 제약사항 | reasoning 기본값이 모델마다 다르고 `gpt-6.1-sol`·`gpt-6-astra`는 `none`을 지원하지 않는다 | 템플릿 조건 "추론 설정 = 모델 기본값"으로는 모델 간 추론량이 같지 않다 | 비교 결과에 실제 effort 값을 함께 표시하고, 기업과 공통 effort 기준을 협의 | OpenAI |
| 문서·실행 불일치 | SDK README는 "timeout이면 `APITimeoutError`"라고 하지만, 실제 OpenAI 호출에 `timeout=0.001`을 주면 `APIConnectionError`가 났다. 읽기 Timeout(로컬 모의 서버)은 `APITimeoutError`로 문서와 같았다 | Timeout과 네트워크 오류가 섞여 집계될 수 있다 | `APITimeoutError`를 먼저 잡고 `e.__cause__` 타입을 기록(예제 반영). OpenAI 실서버 대상 읽기 Timeout은 미확인(유료 호출 필요) | OpenAI |
| 문서·실행 불일치 | Chat 응답 원본의 `prompt_tokens_details`에는 `cached_tokens`, `audio_tokens`만 있었다. 문서에는 `cache_write_tokens`, `image_tokens`, `text_tokens`도 optional로 정의돼 있다 | 필드가 빠질 수 있어 어댑터가 KeyError를 낼 수 있다 | 없는 키는 0으로 처리 | OpenAI |
| 문서·실행 불일치 | 오류 가이드에는 404 행과 오류 JSON 전체 예시가 없다. Admin 403은 바디가 문자열이라 `type`/`code`가 없다 | 오류 분류 코드가 문자열 바디에서 깨질 수 있다 | `e.body`가 문자열이면 메시지로 분류 | OpenAI |
| 문서·실행 불일치 | 응답 원본의 `top_p: 0.98`은 기본값이 문서에 없다. `prompt_cache_retention`은 deprecated 필드다(`prompt_cache_options.ttl`로 대체) | 기본 샘플링 값이 문서와 다를 수 있다 | 응답에 echo된 값을 결과에 같이 저장 | OpenAI |
| 미확인 | 별칭 `gpt-5-mini`, `gpt-5-nano`의 종료일. 스냅샷 `-2025-08-07`은 API와 문서 모두 2026-12-11이지만, 별칭은 API `shutdown_date`가 `null`이고 문서에도 없다 | `shutdown_date`만 보고 경고하면 별칭 모델의 종료를 놓칠 수 있다 | 별칭 대신 스냅샷 ID로 호출하거나 모델표에 문서 기준 종료일을 따로 관리 | OpenAI |
| 미확인 | Usage·Costs 데이터 반영 지연 시간, Usage API로 조회 가능한 과거 기간 | 호출 직후 대시보드·API 값과 자체 집계를 대조할 때 차이가 날 수 있다 | Admin 키를 받으면 호출 후 몇 분 간격으로 재조회해 측정 | OpenAI |
| 미확인 | `POST /v1/responses/input_tokens`의 과금·rate limit 여부. 문서에 없고, 응답에 rate-limit 헤더가 없었다 | 호출 전 비용 예측에 매번 써도 되는지 판단할 수 없다 | 콘솔 Usage에서 카운트 호출이 잡히는지 확인 | OpenAI |
| 미확인 | 504 발생 여부와 의미(오류 가이드에 없음). 429, 500, 503 실제 재현 | 오류 매핑표 일부가 문서 근거뿐이다 | 대량 요청이나 장애 시점이 필요해 보류 | OpenAI |
| 미확인 | 모델별 `temperature` 허용 여부. `gpt-5.4` 최대 입력 토큰(모델 페이지 미기재) | 공통 파라미터 설계, 입력 길이 제한 설계 | 유료 호출이 필요해 보류. 필요하면 #30-벤치마크에서 승인 후 실행 | OpenAI |
| 미확인 | 401 `expired_secret_key`, 429 `credit_balance_exhausted`의 응답 원본. 2026-10-18에 겪었지만 원본을 보존하지 못했다 | 3.6의 해당 부분이 문서 근거로 남는다 | 다시 발생하면 `evidence/`에 원본 저장 | OpenAI |
| 미확인 | 신규 계정 무료 크레딧, 최소 충전 금액, 크레딧 만료(help.openai.com 본문 접근 실패) | 팀 예산 계획 | 기업 PoC 키를 쓰면 영향 없음 | OpenAI |
| 기업 문의 | 비교 대상 OpenAI 모델 확정(`gpt-5.4-mini` vs `gpt-6-luna` 등). `gpt-4.1-nano`는 10/23, `gpt-5-mini`·`nano` 스냅샷은 12/11 종료(별칭은 미확인) | 시나리오와 비용 기준표 확정 | 킥오프 질문 | OpenAI |
| 기업 문의 | 기업 PoC 키의 사용 한도·티어, `store` 정책(응답 저장 허용 여부) | 한도 초과 대응, 데이터 정책 | 킥오프 질문 | OpenAI |

**오류 재현 응답 원본** (3.6 오류 코드 표에서 `실행`으로 표시한 항목 중 4장에 없는 것)

2026-10-20, 일반 API 키, 과금 없음 (`evidence/openai/template_20261020/free_checks.json`)

```json
{
  "err_403_usage_api": {
    "request": "GET /v1/organization/usage/completions?start_time=<24시간 전>",
    "status": 403,
    "headers": { "openai-version": "2020-10-01", "x-request-id": "ac922af5-1dd6-445b-9f0b-136793db6024", "openai-processing-ms": "9" },
    "body": {
      "error": "You have insufficient permissions for this operation. Missing scopes: api.usage.read. Check that you have the correct role in your organization, and if you're using a restricted API key, that it has the necessary scopes."
    }
  },
  "err_403_costs_api": {
    "request": "GET /v1/organization/costs?start_time=<24시간 전>",
    "status": 403,
    "body": {
      "error": "You have insufficient permissions for this operation. Missing scopes: api.usage.read. Check that you have the correct role in your organization, and if you're using a restricted API key, that it has the necessary scopes."
    }
  },
  "timeout_0.001s": {
    "request": "OpenAI(timeout=0.001, max_retries=0).models.list()",
    "exception": "APIConnectionError",
    "mro": ["APIConnectionError", "APIError", "OpenAIError", "Exception"],
    "msg": "Connection error."
  }
}
```

2026-10-19, `gpt-5.4-mini`, 400이라 과금 없음 (`evidence/openai/template_20261020/errors_20261019.json`)

```json
{
  "F6_chat_tools_plus_reasoning": {
    "request": "POST /v1/chat/completions  tools=[function] + reasoning_effort=\"low\"",
    "status_code": 400,
    "body": {
      "error": {
        "message": "Function tools with reasoning_effort are not supported for gpt-5.4-mini in /v1/chat/completions. To use function tools, use /v1/responses or set reasoning_effort to 'none'.",
        "type": "invalid_request_error",
        "param": "reasoning_effort",
        "code": null
      }
    }
  },
  "F8_chat_max_tokens": {
    "request": "POST /v1/chat/completions  max_tokens=16",
    "status_code": 400,
    "body": {
      "error": {
        "message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
        "type": "invalid_request_error",
        "param": "max_tokens",
        "code": "unsupported_parameter"
      }
    }
  }
}
```

2026-10-19, 로컬 무응답 서버(OpenAI 서버 아님, 더미 키, `evidence/openai/template_20261020/local_timeout_20261019.json` 발췌)

```json
{
  "T1_read0.5_retries0": {
    "label": "httpx.Timeout(10.0, read=0.5), max_retries=0",
    "elapsed_ms": 538.5,
    "exception_class": "openai.APITimeoutError",
    "mro": ["openai.APITimeoutError", "openai.APIConnectionError", "openai.APIError", "openai.OpenAIError", "builtins.Exception", "builtins.BaseException", "builtins.object"],
    "str": "Request timed out.",
    "cause_class": "httpx2.ReadTimeout",
    "has_status_code_attr": false
  }
}
```

---

## 8. 제출 전 체크리스트

작성자가 확인합니다.

- [x] 1장에 조사 기준일, SDK 버전, 사용한 키 종류를 적었다
- [x] 3장 모든 행에 근거(실행 / 문서 / 미확인)를 적었다
- [x] 필드 이름은 HTTP 응답 원본 기준이다
- [x] 가격·한도 숫자에 단위, 기준일, 출처 URL이 있다 (한도 헤더에는 기간 단위가 없어 3.6에 그 사실을 적음)
- [x] 4장 예제는 키를 환경변수로 읽고, 복사해서 그대로 실행된다 (파일로 저장해 실행)
- [x] 4장 공통 호출 조건을 바꾸지 않았다 (바꿨으면 이유를 적었다) — `store=false` 추가, 이유는 2장
- [x] 실행 결과와 오류 응답은 원본 JSON을 붙였다 (원본이 없는 2026-10-18 관찰 2건은 `문서`로 낮추고 7장에 적음)
- [x] 미확인 항목은 이유와 함께 7장에 모았다
- [x] 문서와 첨부 파일에 API 키, 계정 정보가 없다 (`scripts/check_secrets.sh` 통과)

취합 담당자가 확인합니다.

- [ ] 5장 비교표를 세 문서의 3장 기준으로 채웠다
- [ ] 6장 공통 스키마의 모든 필드에 Provider별 출처 또는 "직접 계산"이 적혀 있다
- [ ] 7장 기업 문의 항목을 킥오프 질문 목록으로 따로 뽑았다
