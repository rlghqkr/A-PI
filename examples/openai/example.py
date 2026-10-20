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
