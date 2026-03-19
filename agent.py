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
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent
MAX_TOOL_CALLS = 10

SYSTEM_PROMPT = """
You are a documentation agent for this repository.

Use tools to answer questions about the project documentation.
When you need information from the wiki:
1. Start with list_files on the most relevant directory, usually "wiki".
2. Then use read_file on the most relevant file.
3. Prefer wiki sources over general knowledge.

For your final response, return a JSON object as plain text with exactly:
- "answer": a concise answer to the user
- "source": the most relevant wiki file and section anchor, like "wiki/file.md#section-name"

If an exact section heading does not exist, use the closest relevant section anchor.
Do not wrap the final JSON in Markdown fences.
""".strip()


class Settings(BaseSettings):
    llm_api_key: str
    llm_api_base: str
    llm_model: str

    model_config = SettingsConfigDict(env_file=".env.agent.secret", extra="ignore")


def build_chat_completions_url(api_base: str) -> str:
    return f"{api_base.rstrip('/')}/chat/completions"


def get_tool_schemas() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a text file from the repository.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from the project root.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories under a repository path.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from the project root.",
                        }
                    },
                    "required": ["path"],
                    "additionalProperties": False,
                },
            },
        },
    ]


def resolve_project_path(path_str: str) -> Path:
    candidate = (PROJECT_ROOT / path_str).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError("Path must stay inside the project directory") from exc
    return candidate


def read_file_tool(path_str: str) -> str:
    try:
        path = resolve_project_path(path_str)
    except ValueError as exc:
        return f"Error: {exc}"

    if not path.exists():
        return f"Error: File does not exist: {path_str}"
    if not path.is_file():
        return f"Error: Path is not a file: {path_str}"

    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        return f"Error reading file: {exc}"


def list_files_tool(path_str: str) -> str:
    try:
        path = resolve_project_path(path_str)
    except ValueError as exc:
        return f"Error: {exc}"

    if not path.exists():
        return f"Error: Directory does not exist: {path_str}"
    if not path.is_dir():
        return f"Error: Path is not a directory: {path_str}"

    try:
        entries = sorted(path.iterdir(), key=lambda entry: entry.name)
    except OSError as exc:
        return f"Error listing directory: {exc}"

    lines = [entry.name + ("/" if entry.is_dir() else "") for entry in entries]
    return "\n".join(lines)


def execute_tool(name: str, arguments: dict[str, Any]) -> str:
    path = arguments.get("path")
    if not isinstance(path, str):
        return "Error: Tool argument 'path' must be a string"

    if name == "read_file":
        return read_file_tool(path)
    if name == "list_files":
        return list_files_tool(path)
    return f"Error: Unknown tool: {name}"


def parse_content(message: dict[str, Any]) -> str:
    content = message.get("content")
    if isinstance(content, str):
        return content
    if content is None:
        return ""
    if isinstance(content, list):
        text_parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    text_parts.append(text)
        return "".join(text_parts)
    return str(content)


def extract_message(response_json: dict[str, Any]) -> dict[str, Any]:
    try:
        message = response_json["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("LLM response does not contain choices[0].message") from exc

    if not isinstance(message, dict):
        raise ValueError("LLM message must be an object")
    return message


def parse_final_content(content: str) -> tuple[str, str]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return content.strip(), ""

    if not isinstance(payload, dict):
        raise ValueError("Final LLM response must be a JSON object")

    answer = payload.get("answer", "")
    source = payload.get("source", "")
    if not isinstance(answer, str):
        raise ValueError("Final answer must be a string")
    if not isinstance(source, str):
        raise ValueError("Final source must be a string")
    return answer, source


def call_llm(
    settings: Settings,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.llm_model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
    }

    request_url = build_chat_completions_url(settings.llm_api_base)
    response = httpx.post(request_url, headers=headers, json=payload, timeout=45.0)
    response.raise_for_status()
    return response.json()


def run_agent(question: str, settings: Settings) -> dict[str, Any]:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools = get_tool_schemas()
    tool_history: list[dict[str, Any]] = []
    final_answer = ""
    final_source = ""

    while len(tool_history) < MAX_TOOL_CALLS:
        response_json = call_llm(settings, messages, tools)
        message = extract_message(response_json)
        content = parse_content(message)
        response_tool_calls = message.get("tool_calls")

        if isinstance(response_tool_calls, list) and response_tool_calls:
            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": content,
                "tool_calls": response_tool_calls,
            }
            messages.append(assistant_message)

            remaining_calls = MAX_TOOL_CALLS - len(tool_history)
            for tool_call in response_tool_calls[:remaining_calls]:
                if not isinstance(tool_call, dict):
                    continue

                function_data = tool_call.get("function", {})
                name = function_data.get("name", "")
                raw_arguments = function_data.get("arguments", "{}")

                try:
                    arguments = json.loads(raw_arguments)
                except json.JSONDecodeError:
                    arguments = {}
                    result = "Error: Tool arguments must be valid JSON"
                else:
                    if not isinstance(arguments, dict):
                        arguments = {}
                        result = "Error: Tool arguments must decode to an object"
                    else:
                        result = execute_tool(str(name), arguments)

                tool_history.append(
                    {
                        "tool": str(name),
                        "args": arguments,
                        "result": result,
                    }
                )

                tool_call_id = tool_call.get("id")
                tool_message: dict[str, Any] = {
                    "role": "tool",
                    "content": result,
                }
                if isinstance(tool_call_id, str):
                    tool_message["tool_call_id"] = tool_call_id
                messages.append(tool_message)

            continue

        final_answer, final_source = parse_final_content(content)
        break

    if not final_answer:
        final_answer = "I could not complete the request within the tool-call limit."

    return {
        "answer": final_answer,
        "source": final_source,
        "tool_calls": tool_history,
    }


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: agent.py <question>", file=sys.stderr)
        return 1

    question = sys.argv[1]

    try:
        settings = Settings()
        result = run_agent(question, settings)
    except ValidationError as exc:
        print(f"Error loading settings: {exc}", file=sys.stderr)
        return 1
    except (httpx.HTTPError, ValueError) as exc:
        print(f"Error running agent: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
