# 셀 카드 (git 을 쓰지 않는 팀원용 입력 양식)

Notion "참여 방법 & 템플릿" 페이지의 토글 21개(Provider 3 × 항목 7)에 아래 양식으로 채운다.
필드명이 `matrix/_template.yaml` 의 키와 같아서 머지 리드가 그대로 옮긴다. 모르는 항목은 `unknown` 으로 두고 넘어가도 된다.

```
Provider:        openai | anthropic | gemini
항목(item):      models_list | generate | token_usage | usage_report | cost | status_errors | example
가능 여부:       api | partial | dashboard_only | none | unknown
엔드포인트:      예) GET /v1/models
인증(auth):      standard_key | admin_key | oauth_cloud | login_only | none | unknown
SDK 호출:        예) client.models.list()
응답 필드:       예) id, owned_by, created
주의점:
증거(evidence):  live | docs | observed | blocked
BLOCKED 사유:    (evidence=blocked 일 때만)
출처 URL:
확신도(0~1):
```

규칙
- 키·응답 원문·스크린샷은 올리지 않는다. 숫자와 URL 만.
- 실측했으면 `live`, 공식 문서만 봤으면 `docs`. 정직하게.
- 의견이 다른 셀은 지우지 말고 주의점에 `(@핸들: 이렇게 봄 — 근거 URL)` 로 남긴다.
