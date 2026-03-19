#!/usr/bin/env uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "httpx",
#     "pydantic",
#     "pydantic-settings",
# ]
# ///

import json
import sys
from typing import Any

import httpx
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    llm_api_key: str
    llm_api_base: str
    llm_model: str

    model_config = SettingsConfigDict(env_file=".env.agent.secret", extra="ignore")


def build_chat_completions_url(api_base: str) -> str:
    return f"{api_base.rstrip('/')}/chat/completions"


def extract_answer(response_json: dict[str, Any]) -> str:
    try:
        answer = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response does not contain choices[0].message.content") from exc

    if not isinstance(answer, str):
        raise ValueError("LLM answer must be a string")

    return answer


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]

    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"Error loading settings: {exc}", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": settings.llm_model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant. Answer the user's question clearly "
                    "and concisely."
                ),
            },
            {"role": "user", "content": question},
        ],
    }

    request_url = build_chat_completions_url(settings.llm_api_base)
    print(f"Calling model {settings.llm_model} at {request_url}", file=sys.stderr)

    try:
        response = httpx.post(request_url, headers=headers, json=payload, timeout=45.0)
        response.raise_for_status()
        answer = extract_answer(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Error calling LLM: {exc}", file=sys.stderr)
        return 1

    result = {
        "answer": answer,
        "tool_calls": [],
    }

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
