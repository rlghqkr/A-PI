# 취합 절차 (MERGE_PROCESS)

조사 결과는 **셀 단위**(Provider 3 × 항목 7 = 21셀)로 모은다. 사람이 손으로 합치지 않고 `scripts/build_comparison.py` 가 `docs/COMPARISON.md` 를 생성한다. 마감: **10/20(화) 10:00** 까지 각자 입력 → 10:00~11:30 머지 → 14:00 킥오프에서 사용.

## 1. 참여 경로

### A. git 을 쓰는 팀원 — matrix YAML

```bash
cp matrix/_template.yaml matrix/<handle>.yaml     # 파일 1개 = 작성자 1명. <handle> 은 Slack 핸들
# 21셀을 채운다. 모르는 셀은 unknown 으로 두고 넘어간다. 필드 설명: matrix/SCHEMA.md
uv run python scripts/validate_matrix.py matrix/<handle>.yaml   # FAIL 이 없어야 PR 가능 (WARN 은 참고)
bash scripts/check_secrets.sh                                    # 키 모양 문자열 검사
git checkout -b matrix/<handle> && git add matrix/<handle>.yaml && git commit -m "matrix: <handle> 1차" && git push
```

PR 제목 `matrix: <handle>`, 라벨 `research`. 리뷰는 머지 리드 1명이 validate 통과만 확인하고 바로 머지한다(내용 토론은 §3 에서).

실측(`live`)을 했으면 `evidence/<provider>/<항목>.json` 도 같은 PR 에 넣는다(노트북/demo 가 만든 마스킹 JSON. `raw_*` 는 gitignore).

### B. git 을 쓰지 않는 팀원 — Notion 셀 카드

Notion "참여 방법 & 템플릿" 페이지의 토글 21개(Provider × 항목)에 `docs/templates/CELL_CARD.md` 양식으로 적는다. 필드명이 YAML 키와 같다. 머지 리드가 10/20 10:00 에 `matrix/<handle>.yaml` 로 옮겨 PR 을 올린다(author 는 카드 작성자 핸들).

둘 다 **키·응답 원문·스크린샷 금지**. 숫자와 URL 만.

## 2. 머지 절차 (10/20 10:00~11:30, 머지 리드 1명 + 작성자 전원 온라인)

| 시각 | 할 일 | 명령 |
|---|---|---|
| 10:00 | B 경로 카드 → YAML 변환, 모든 PR 머지 | — |
| 10:15 | 전체 검증. FAIL 파일은 작성자가 10분 안에 고침 | `uv run python scripts/validate_matrix.py matrix/*.yaml` (또는 `make validate`) |
| 10:25 | 비교표 생성. `_merged.yaml` 과 `COMPARISON.md` §5 충돌 표 확인 | `uv run python scripts/build_comparison.py` (또는 `make build`) |
| 10:30~11:00 | **충돌 해결**(§3). 결정 즉시 각자 YAML 수정 → 재생성 | 반복 |
| 11:00 | 최종 생성 + 시크릿 검사 → `main` 커밋 | `make build && make secrets` |
| 11:15 | Notion 2차 반영: COMPARISON.md §1·§2·§6 을 Notion 조사 페이지에 붙이고 PR 링크 첨부 | — |
| 11:30 | #00-공지 에 한 줄: "비교표 v1 확정, BLOCKED n셀, 킥오프 질문 docs/KICKOFF_QUESTIONS.md" | — |

생성물 규칙: `docs/COMPARISON.md` 와 `matrix/_merged.yaml` 은 **손으로 고치지 않는다**. 고칠 것이 있으면 자기 YAML 을 고치고 다시 생성한다.

## 3. 충돌 해결 규칙

스크립트가 자동으로 하는 것:

1. **evidence 등급**이 높은 쪽이 대표: `live > observed > docs > blocked`. `evidence/<provider>/<항목>.json` 의 source 도 같은 순위로 비교해 더 높은 쪽이 배지가 된다.
2. 같은 등급이면 `confidence` 높은 쪽.
3. `availability` 가 다르면 **보수적인 값**(`api → partial → dashboard_only → none` 에서 뒤쪽) 채택. 반대 의견은 지우지 않고 caveats 에 `(@핸들: 값 — 첫 출처 URL)` 로 남는다. `unknown` 은 의견 없음.
4. `endpoint` 가 다르면 둘 다 나열. `response_fields`/`common_fields`/`sources` 는 합집합.

사람이 결정하는 것(§5 충돌 표 한 줄씩, 10:30~11:00):

- **출처 우선**: 공식 문서 URL 을 가진 의견 > 블로그/커뮤니티 > 기억. 공식 문서끼리 다르면 더 최근 페이지(`as_of` 기록).
- **실측 우선**: `live` 가 하나라도 있으면 그 결과가 사실. 단 실측 조건(모델·SDK 버전·날짜)을 caveats 에 적는다.
- **모르면 보수적으로**: 5분 안에 결론이 안 나면 스크립트가 고른 보수적 값을 그대로 두고 `docs/KICKOFF_QUESTIONS.md` 또는 `docs/providers/<p>.md` "## 9. 미해결 질문" 에 넘긴다.
- 결정은 **당사자가 자기 YAML 을 수정**해서 반영한다(머지 리드가 대신 고치지 않는다). 재생성 후 §5 에서 사라졌는지 확인.

## 4. 셀 단위 Definition of Done

한 셀이 "끝났다" 는 아래를 모두 만족할 때다.

- [ ] `availability`, `endpoint`, `auth`, `evidence` 가 `unknown`/빈 값이 아니다 (정말 모르면 `unknown` + caveats 에 이유)
- [ ] `sources` 에 **공식 문서 URL 1개 이상**
- [ ] `evidence=live` 면 `evidence/<provider>/<항목>.json` 이 있고 `python -m apicompare.demo` 또는 노트북으로 재현 가능
- [ ] `evidence=blocked` 면 `blocked_reason` 에 사유(`no key`, `admin key`, `org + admin key`, `paid tier` …)
- [ ] `caveats` 에 Simulator 설계에 영향 주는 함정 1개 이상(예: "Anthropic usage 에 total 없음", "Gemini SDK 재시도 기본 0회")
- [ ] `common_fields` 에 3사 공통으로 뽑을 수 있다고 보는 필드명(§2 교집합 계산에 쓰임)
- [ ] `validate_matrix.py` FAIL 0, `check_secrets.sh` OK
- [ ] 검증된 조사 매트릭스와 어긋나지 않는다 — 특히: Anthropic 과부하 529(503 아님) · Anthropic usage 에 total 없음 · 현행 Claude 는 temperature 400(SDK 1.x 는 파라미터 제거) · Gemini SDK 재시도 기본 0회 · Gemini 기간별 Usage/Cost API 없음 · OpenAI Usage/Costs 는 Admin 키 · Chat Completions 는 GPT-5.4+ 에서 tools + reasoning_effort≠none 불가 · 단가는 3사 모두 API 미제공

## 5. 커뮤니케이션 규칙

- 조사 관련 대화는 **#10-조사 의 스레드 하나**("사전조사 취합 10/20")에서만. 채널 본문에는 결정 한 줄만.
- 스레드에 **키·응답 원문·스크린샷을 올리지 않는다.** 숫자, 필드명, URL, 오류 코드 문자열만.
- 의견이 다르면 지우지 말고 자기 YAML caveats 에 `(@핸들: 이렇게 봄 — URL)` 로 남긴다(스크립트도 같은 형식으로 보존).
- 유료 호출은 #30-벤치마크 에서 "모델·횟수·예상 비용" 을 먼저 적고 실행. 개인 키 사용분은 개인 부담.
- 생성물(`COMPARISON.md`, `_merged.yaml`)에 대한 피드백은 "어느 YAML 의 어느 셀을 고치면 되는지" 로 말한다.
- 기업 키가 오면: §6 BLOCKED 목록의 "기업 키가 오면 할 일" 대로 `notebooks/<n>_<provider>.ipynb` 해당 섹션을 재실행 → evidence 갱신 → `make build` → PR.

## 6. 파일 책임

| 파일 | 누가 | 비고 |
|---|---|---|
| `matrix/<handle>.yaml` | 작성자 본인 | 유일한 입력. 다른 사람 파일은 고치지 않는다 |
| `matrix/_parts/*.yaml` | 자동화/에이전트 | 작성자 파일이 0개일 때만 대신 사용됨 |
| `matrix/_merged.yaml`, `docs/COMPARISON.md` | 스크립트 | 손편집 금지 |
| `docs/providers/<p>.md` | Provider 담당 1명 | 템플릿 `docs/templates/PROVIDER_TEMPLATE.md`. "## 8." 과 "## 9." 가 COMPARISON §3·§7 로 인용된다 |
| `evidence/<p>/*.json` | 노트북/demo | 마스킹된 JSON 만. `raw_*` 커밋 금지 |
| `docs/KICKOFF_QUESTIONS.md` | 머지 리드 | BLOCKED 셀과 미해결 질문이 근거 |
