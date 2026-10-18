# matrix YAML 스키마 (한 화면 요약)

정식 정의: `matrix/matrix_entry.schema.json` · 빈 양식: `matrix/_template.yaml` · 검증: `uv run python scripts/validate_matrix.py matrix/<handle>.yaml`

**파일 1개 = 작성자 1명.** `entries` 에 Provider 3 × 항목 7 = 21셀을 넣는다(모르는 셀은 `unknown` 으로 두고 넘어가도 됨). 스키마에 없는 키를 추가하면 실패한다(`additionalProperties: false`).

## 최상위

| 키 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `author` | string | ✔ | Slack 핸들 또는 이름. `_merged.yaml` 과 COMPARISON.md 충돌 표에 `@author` 로 표시된다 |
| `as_of` | `YYYY-MM-DD` | ✔ | 조사 기준일(문서를 본 날) |
| `entries` | list | ✔ | 아래 엔트리 1개 이상 |

## 엔트리(셀)

| 키 | 타입 / enum | 필수 | 설명 |
|---|---|---|---|
| `provider` | `openai` \| `anthropic` \| `gemini` | ✔ | |
| `item` | `models_list` 모델 목록 조회 · `generate` 모델 호출 · `token_usage` Token Usage · `usage_report` Usage 조회 · `cost` 비용 확인 · `status_errors` 상태 및 오류 확인 · `example` 호출 예제 | ✔ | `apicompare.ITEMS` 와 1:1 |
| `availability` | `api` API 로 가능 · `partial` 일부만(예: 로컬 계산 + Admin 전용) · `dashboard_only` 대시보드만 · `none` 없음 · `unknown` | ✔ | 머지 시 의견이 갈리면 **더 보수적인 값**(api → partial → dashboard_only → none 순서에서 뒤쪽) 채택 |
| `endpoint` | string | ✔ | 예: `GET /v1/models`. 없으면 `없음(대시보드)`. 작성자마다 다르면 둘 다 나열됨 |
| `auth` | `standard_key` · `admin_key` · `oauth_cloud` · `login_only` · `none` · `unknown` | ✔ | 필요한 키 종류 |
| `sdk_call` | string | | 예: `client.models.list()` |
| `response_fields` | list[string] | | 응답 필드명(합집합으로 머지) |
| `common_fields` | list[string] | | 3사 공통으로 뽑을 수 있다고 보는 필드. §2 "공통 수집 가능 항목" 에 **교집합**이 실린다 |
| `caveats` | string | | 주의점. 반대 의견은 `(@핸들: 값 — URL)` 형태로 자동 보존된다 |
| `evidence` | `live` 직접 호출 · `observed` 관찰만 · `docs` 공식 문서 · `blocked` 키/권한 없음 | ✔ | 배지 우선순위 live > observed > docs > blocked. `evidence/<provider>/<항목>.json` 의 source 와 비교해 높은 쪽이 배지 |
| `blocked_reason` | string | blocked 일 때 | 예: `admin key`, `no key`. 비어 있으면 검증기가 경고 |
| `sources` | list[string] | ✔ | 공식 문서 URL. 빈 리스트 허용(검증 통과)이지만 머지 충돌 시 첫 URL 이 근거로 인용된다 |
| `confidence` | number 0~1 | | 같은 evidence 등급이면 높은 쪽이 대표 엔트리 |

## 예시 엔트리 1개

```yaml
author: hong
as_of: "2026-10-19"
entries:
  - provider: anthropic
    item: usage_report                 # Usage 조회
    availability: partial              # API 는 있지만 Admin 키 + 조직 계정 필수
    endpoint: "GET /v1/organizations/usage_report/messages"
    auth: admin_key
    sdk_call: "requests.get(...)  # SDK 미지원 → raw HTTP"
    response_fields: [uncached_input_tokens, cache_read_input_tokens, output_tokens, model, bucket_width]
    common_fields: [input_tokens, output_tokens, model, start, end]
    caveats: "개인 계정 불가(조직 생성 필요). 입력 필드명이 Messages 응답(input_tokens)과 다름(uncached_input_tokens). 데이터 지연 약 5분."
    evidence: blocked
    blocked_reason: "no admin key"
    sources:
      - https://platform.claude.com/docs/en/manage-claude/usage-cost-api
    confidence: 0.9
```

규칙: 키·응답 원문·스크린샷은 넣지 않는다(숫자와 URL 만). 실측했으면 `live`, 문서만 봤으면 `docs` — 정직하게.
