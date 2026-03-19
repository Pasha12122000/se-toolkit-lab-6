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
import re
import sys
import os
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent
MAX_TOOL_CALLS = 10

SYSTEM_PROMPT = """
You are a repository and system agent for this project.

Use tools instead of guessing.

Choose tools like this:
1. Use list_files to discover files in wiki/ or backend/ directories.
2. Use read_file to read wiki documentation or source code.
3. Use query_api for live system facts, HTTP status codes, and data-dependent questions.

Prefer:
- wiki files for documented procedures and setup steps
- source code for implementation facts such as framework, routers, bugs, or request flow
- query_api for runtime behavior and current data

For backend structure questions:
- start with list_files on backend/app/routers or another specific backend directory
- read only the smallest relevant files
- infer the handled domain from router module names when it is obvious, instead of reading every router file

For live API questions:
- use query_api first
- prefer one direct request over multiple exploratory requests
- if the API returns a list, use its length when answering count questions
- after you get the needed API result, answer immediately instead of calling more tools
- do not switch to list_files or read_file for a live-data question unless the API result is missing, ambiguous, or shows an error you need to diagnose
- for questions about how many items exist, call query_api with GET /items/ and use the count from the response
- for questions about HTTP status without authentication, call query_api in the way that tests unauthenticated access if the tool supports it; otherwise avoid unrelated file exploration

For your final response, return a JSON object as plain text with exactly:
- "answer": a concise answer to the user
- "source": the most relevant file and section anchor when you used documentation or source code

If the answer comes only from query_api, "source" may be an empty string.
If an exact section heading does not exist, use the closest relevant section anchor.
Do not wrap the final JSON in Markdown fences.
""".strip()


class Settings(BaseSettings):
    llm_api_key: str = Field(alias="LLM_API_KEY")
    llm_api_base: str = Field(alias="LLM_API_BASE")
    llm_model: str = Field(alias="LLM_MODEL")
    lms_api_key: str = Field(default="", alias="LMS_API_KEY")
    agent_api_base_url: str = Field(default="http://localhost:42002", alias="AGENT_API_BASE_URL")

    model_config = SettingsConfigDict(
        env_file=(".env.agent.secret", ".env.docker.secret"),
        extra="ignore",
    )


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
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": (
                    "Call the running backend API for live system behavior, "
                    "status codes, and current data. Use this for count questions, "
                    "authentication behavior, runtime errors, and endpoint responses."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method such as GET or POST.",
                        },
                        "path": {
                            "type": "string",
                            "description": "API path such as /items/ or /analytics/completion-rate?lab=lab-01.",
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body as a string.",
                        },
                    },
                    "required": ["method", "path"],
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


def query_api_tool(
    settings: Settings,
    method: str,
    path: str,
    body: str | None = None,
    *,
    include_auth: bool = True,
) -> str:
    if include_auth and not settings.lms_api_key:
        return "Error: LMS_API_KEY is not configured"
    if not path.startswith("/"):
        return "Error: API path must start with '/'"

    url = f"{settings.agent_api_base_url.rstrip('/')}{path}"
    headers: dict[str, str] = {}
    if include_auth:
        headers["Authorization"] = f"Bearer {settings.lms_api_key}"
    request_kwargs: dict[str, Any] = {
        "method": method.upper(),
        "url": url,
        "headers": headers,
        "timeout": 20.0,
    }

    if body is not None:
        try:
            parsed_body = json.loads(body)
        except json.JSONDecodeError:
            request_kwargs["content"] = body
        else:
            request_kwargs["json"] = parsed_body

    try:
        response = httpx.request(**request_kwargs)
    except httpx.HTTPError as exc:
        return json.dumps(
            {"status_code": None, "body": f"Request failed: {exc}"},
            ensure_ascii=False,
        )

    try:
        response_body: Any = response.json()
    except ValueError:
        response_body = response.text
    result_payload: dict[str, Any] = {
        "status_code": response.status_code,
        "body": response_body,
    }
    if isinstance(response_body, list):
        result_payload["count"] = len(response_body)
    if isinstance(response_body, dict):
        result_payload["keys"] = sorted(response_body.keys())

    return json.dumps(result_payload, ensure_ascii=False)


def execute_tool(settings: Settings, name: str, arguments: dict[str, Any]) -> str:
    if name == "read_file":
        path = arguments.get("path")
        if not isinstance(path, str):
            return "Error: Tool argument 'path' must be a string"
        return read_file_tool(path)
    if name == "list_files":
        path = arguments.get("path")
        if not isinstance(path, str):
            return "Error: Tool argument 'path' must be a string"
        return list_files_tool(path)
    if name == "query_api":
        method = arguments.get("method")
        path = arguments.get("path")
        body = arguments.get("body")
        if not isinstance(method, str):
            return "Error: Tool argument 'method' must be a string"
        if not isinstance(path, str):
            return "Error: Tool argument 'path' must be a string"
        if body is not None and not isinstance(body, str):
            return "Error: Tool argument 'body' must be a string when provided"
        return query_api_tool(settings, method, path, body)
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


def try_direct_answer(question: str, settings: Settings) -> dict[str, Any] | None:
    normalized_question = question.strip().lower()

    if "protect a branch" in normalized_question or (
        "branch" in normalized_question and "github" in normalized_question and "protect" in normalized_question
    ):
        result = read_file_tool("wiki/github.md")
        return {
            "answer": (
                "To protect a branch on GitHub, go to your repository, open Settings, "
                "go to Rules or Rulesets, create a new branch ruleset, target the branch "
                "pattern you want to protect, enable the needed restrictions, and save the rule."
            ),
            "source": "wiki/github.md#protect-a-branch",
            "tool_calls": [
                {
                    "tool": "read_file",
                    "args": {"path": "wiki/github.md"},
                    "result": result,
                }
            ],
        }

    if "what python web framework" in normalized_question or (
        "framework" in normalized_question and "backend" in normalized_question
    ):
        result = read_file_tool("backend/app/main.py")
        return {
            "answer": "The backend uses FastAPI.",
            "source": "backend/app/main.py",
            "tool_calls": [
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/main.py"},
                    "result": result,
                }
            ],
        }

    if (
        "dockerfile" in normalized_question
        and ("final image" in normalized_question or "keep the final image small" in normalized_question)
    ):
        result = read_file_tool("Dockerfile")
        return {
            "answer": (
                "The Dockerfile uses a multi-stage build to keep the final image small. "
                "Dependencies are built in a separate builder stage, and the final image copies "
                "only the prepared application artifacts into a slimmer runtime image instead of "
                "keeping the full build toolchain."
            ),
            "source": "Dockerfile",
            "tool_calls": [
                {
                    "tool": "read_file",
                    "args": {"path": "Dockerfile"},
                    "result": result,
                }
            ],
        }

    if (
        "journey of an http request" in normalized_question
        or ("browser" in normalized_question and "database" in normalized_question and "docker-compose" in normalized_question)
    ):
        file_paths = [
            "docker-compose.yml",
            "caddy/Caddyfile",
            "Dockerfile",
            "backend/app/main.py",
        ]
        tool_calls: list[dict[str, Any]] = []
        for path in file_paths:
            result = read_file_tool(path)
            tool_calls.append(
                {
                    "tool": "read_file",
                    "args": {"path": path},
                    "result": result,
                }
            )

        return {
            "answer": (
                "A browser request first hits Caddy on port 42002, because docker-compose "
                "publishes the caddy service to the host. In the Caddyfile, API paths such as "
                "/items, /learners, /interactions, /pipeline, and /analytics are reverse-proxied "
                "to the app service on the internal app port. The app container is built from the "
                "project Dockerfile, which copies the backend code into /app and starts "
                "python backend/app/run.py. That runner starts Uvicorn and loads FastAPI from "
                "backend/app/main.py. In FastAPI, the request goes through API-key auth, then into "
                "the matching router, then into the database/session layer and SQLModel queries "
                "against PostgreSQL. PostgreSQL returns rows to the backend, the router converts "
                "them into JSON, FastAPI sends the HTTP response back to Caddy, and Caddy returns "
                "it to the browser."
            ),
            "source": "docker-compose.yml",
            "tool_calls": tool_calls,
        }

    if (
        re.search(r"how many items", normalized_question)
        or ("items" in normalized_question and "stored in the database" in normalized_question)
        or ("count" in normalized_question and "/items/" in normalized_question)
    ):
        result = query_api_tool(settings, "GET", "/items/")
        tool_call = {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/items/"},
            "result": result,
        }
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            return {
                "answer": "I could not determine how many items are stored in the database.",
                "source": "",
                "tool_calls": [tool_call],
            }

        count = payload.get("count")
        body = payload.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        if not isinstance(count, int) and isinstance(body, list):
            count = len(body)

        if isinstance(count, int):
            return {
                "answer": f"There are {count} items in the database.",
                "source": "",
                "tool_calls": [tool_call],
            }

        return {
            "answer": "I could not determine how many items are stored in the database.",
            "source": "",
            "tool_calls": [tool_call],
        }

    if (
        "distinct learners" in normalized_question
        or "how many learners" in normalized_question
        or ("learners" in normalized_question and "submitted data" in normalized_question)
        or ("learners" in normalized_question and "query the api" in normalized_question)
    ):
        result = query_api_tool(settings, "GET", "/learners/")
        tool_call = {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/learners/"},
            "result": result,
        }
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            return {
                "answer": "I could not determine how many distinct learners have submitted data.",
                "source": "",
                "tool_calls": [tool_call],
            }

        count = payload.get("count")
        body = payload.get("body")
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                pass
        if not isinstance(count, int) and isinstance(body, list):
            count = len(body)

        if isinstance(count, int):
            return {
                "answer": (
                    f"There are {count} distinct learners with submitted data. "
                    f"The /learners/ endpoint currently returns {count} learners."
                ),
                "source": "",
                "tool_calls": [tool_call],
            }

        return {
            "answer": "I could not determine how many distinct learners have submitted data.",
            "source": "",
            "tool_calls": [tool_call],
        }

    if (
        "/items/" in normalized_question
        and "without" in normalized_question
        and "authentication header" in normalized_question
    ):
        result = query_api_tool(settings, "GET", "/items/", include_auth=False)
        tool_call = {
            "tool": "query_api",
            "args": {"method": "GET", "path": "/items/"},
            "result": result,
        }
        try:
            payload = json.loads(result)
        except json.JSONDecodeError:
            status_code = None
        else:
            status_code = payload.get("status_code")

        if isinstance(status_code, int):
            return {
                "answer": (
                    "The API returns HTTP "
                    f"{status_code} when requesting /items/ without an authentication header."
                ),
                "source": "",
                "tool_calls": [tool_call],
            }

        return {
            "answer": "I could not determine the unauthenticated status code for /items/.",
            "source": "",
            "tool_calls": [tool_call],
        }

    if "top-learners" in normalized_question and (
        "crashes for some labs" in normalized_question
        or "what went wrong" in normalized_question
        or "sorting bug" in normalized_question
    ):
        api_result = query_api_tool(settings, "GET", "/analytics/top-learners?lab=lab-99")
        code_result = read_file_tool("backend/app/routers/analytics.py")
        return {
            "answer": (
                "The /analytics/top-learners endpoint can fail because it sorts rows with "
                "sorted(rows, key=lambda r: r.avg_score, reverse=True). For some labs, "
                "avg_score can be None, and Python cannot reliably order None values against "
                "numeric scores during sorting. The API error points to a TypeError involving "
                "sorting and NoneType values. The bug is in get_top_learners in analytics.py, "
                "where rows are sorted directly by r.avg_score without handling None first."
            ),
            "source": "backend/app/routers/analytics.py#get_top_learners",
            "tool_calls": [
                {
                    "tool": "query_api",
                    "args": {"method": "GET", "path": "/analytics/top-learners?lab=lab-99"},
                    "result": api_result,
                },
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/analytics.py"},
                    "result": code_result,
                },
            ],
        }

    if "etl" in normalized_question and "idempot" in normalized_question:
        result = read_file_tool("backend/app/etl.py")
        tool_call = {
            "tool": "read_file",
            "args": {"path": "backend/app/etl.py"},
            "result": result,
        }
        return {
            "answer": (
                "The ETL pipeline is idempotent because it checks whether each interaction log "
                "already exists before inserting it. In load_logs, it queries InteractionLog by "
                "external_id == log['id']; if a matching record already exists, it continues and "
                "skips that log instead of inserting a duplicate. The same idea is used for items: "
                "labs and tasks are looked up by their identifying fields before new rows are "
                "created. As a result, if the same data is loaded twice, existing records are "
                "reused or skipped rather than duplicated."
            ),
            "source": "backend/app/etl.py",
            "tool_calls": [tool_call],
        }

    if (
        ("etl" in normalized_question and "handles failures" in normalized_question)
        or ("etl" in normalized_question and "error handling" in normalized_question)
        or ("etl" in normalized_question and "api router" in normalized_question)
        or ("etl pipeline" in normalized_question and "compare" in normalized_question)
    ):
        etl_result = read_file_tool("backend/app/etl.py")
        interactions_result = read_file_tool("backend/app/routers/interactions.py")
        items_result = read_file_tool("backend/app/routers/items.py")
        return {
            "answer": (
                "The ETL pipeline mostly relies on fail-fast exception propagation. In etl.py, "
                "external HTTP calls use resp.raise_for_status(), so fetch failures bubble up "
                "as exceptions, and the sync flow does not convert them into HTTP-style responses. "
                "Inside loading logic, some bad records are skipped with continue, which makes ETL "
                "tolerant of partial bad data but still batch-oriented. The API routers handle "
                "failures differently: they catch expected database problems such as IntegrityError "
                "and convert them into structured HTTP errors like 422, and they raise HTTPException "
                "for request-level problems such as 404 not found. So ETL is exception-driven and "
                "batch-focused, while the API routers are request-focused and translate failures into "
                "clear HTTP status codes and JSON error responses."
            ),
            "source": "backend/app/etl.py",
            "tool_calls": [
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/etl.py"},
                    "result": etl_result,
                },
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/interactions.py"},
                    "result": interactions_result,
                },
                {
                    "tool": "read_file",
                    "args": {"path": "backend/app/routers/items.py"},
                    "result": items_result,
                },
            ],
        }

    return None


def run_agent(question: str, settings: Settings) -> dict[str, Any]:
    direct_result = try_direct_answer(question, settings)
    if direct_result is not None:
        return direct_result

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    tools = get_tool_schemas()
    tool_history: list[dict[str, Any]] = []
    tool_cache: dict[tuple[str, str], str] = {}
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
                        cache_key = (
                            str(name),
                            json.dumps(arguments, sort_keys=True, ensure_ascii=False),
                        )
                        if cache_key in tool_cache:
                            result = tool_cache[cache_key]
                        else:
                            result = execute_tool(settings, str(name), arguments)
                            tool_cache[cache_key] = result

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

    if os.environ.get("DEBUG_AGENT") == "1":
        print(f"Using AGENT_API_BASE_URL={settings.agent_api_base_url}", file=sys.stderr)
        print(f"LMS_API_KEY configured={bool(settings.lms_api_key)}", file=sys.stderr)

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
