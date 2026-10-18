#!/usr/bin/env bash
# 저장소 안의 텍스트 파일에서 API 키 모양 문자열을 찾는다. 발견 시 파일:행 을 출력하고 exit 1.
#   bash scripts/check_secrets.sh
# 대상: git 추적 파일 + 추적되지 않은 작업 트리 파일(.gitignore 적용). .env*, .venv/ 는 제외. git 이 없으면 find 로 대체.
# 패턴(OpenAI / Google / Anthropic / OpenAI Admin / Notion / Slack 토큰):
set -u
cd "$(dirname "$0")/.." || exit 2

PATTERN='sk-[A-Za-z0-9_-]{16,}|AIza[0-9A-Za-z_-]{20,}|sk-ant-|sk-admin-|ntn_[A-Za-z0-9]{20,}|xox[abp]-'
SELF="scripts/check_secrets.sh"   # 이 파일은 패턴 문자열 자체를 담고 있어 제외

list_files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    { git ls-files -z; git ls-files -z --others --exclude-standard; } | tr '\0' '\n'
  else
    find . -type f -not -path './.git/*' -not -path './.venv/*' | sed 's|^\./||'
  fi
}

found=0
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    .env|.env.*|.venv/*|*/.venv/*|"$SELF") continue ;;
  esac
  [ -f "$f" ] || continue
  # 바이너리는 건너뛴다(grep -I)
  if hits=$(grep -nIE "$PATTERN" -- "$f" 2>/dev/null) && [ -n "$hits" ]; then
    while IFS= read -r line; do
      # 매치된 줄 전체를 출력하면 키가 터미널에 남으므로 파일:행 번호만 출력한다
      lineno="${line%%:*}"
      echo "SECRET? $f:$lineno"
    done <<< "$hits"
    found=1
  fi
done < <(list_files)

if [ "$found" -ne 0 ]; then
  echo "키 모양 문자열이 발견됐습니다. 해당 줄을 지우고(키는 .env 에만) 노출된 키는 즉시 폐기하세요." >&2
  exit 1
fi
echo "OK: 키 모양 문자열 없음"
exit 0
