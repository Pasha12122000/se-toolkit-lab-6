"""Regression tests for agent.py (Task 3)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run_agent_with_mock(question: str, scenario: str) -> dict[str, object]:
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    env = os.environ.copy()
    env["LLM_API_KEY"] = "test-llm-key"
    env["LLM_API_BASE"] = "http://test-llm/v1"
    env["LLM_MODEL"] = "test-model"
    env["LMS_API_KEY"] = "test-lms-key"
    env["MOCK_SCENARIO"] = scenario

    with tempfile.TemporaryDirectory() as temp_dir:
        mock_httpx = Path(temp_dir) / "httpx.py"
        mock_httpx.write_text(
            """
import json as json_lib
import os


class HTTPError(Exception):
    pass


class Response:
    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        return None

    def json(self):
        if self._payload is None:
            raise ValueError("No JSON payload")
        return self._payload


LLM_CALL_COUNT = 0


def _tool_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json_lib.dumps(arguments),
        },
    }


def post(url, headers, json, timeout):
    global LLM_CALL_COUNT
    LLM_CALL_COUNT += 1

    assert url == "http://test-llm/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-llm-key"
    scenario = os.environ["MOCK_SCENARIO"]
    user_question = json["messages"][1]["content"]

    if scenario == "framework":
        assert user_question == "What framework does the backend use?"
        if LLM_CALL_COUNT == 1:
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    _tool_call(
                                        "call-1",
                                        "read_file",
                                        {"path": "backend/app/main.py"},
                                    )
                                ],
                            }
                        }
                    ]
                }
            )
        return Response(
            {
                "choices": [
                    {
                        "message": {
                                "content": json_lib.dumps(
                                    {
                                        "answer": "The backend uses FastAPI.",
                                        "source": "backend/app/main.py",
                                }
                            )
                        }
                    }
                ]
            }
        )

    if scenario == "items_count":
        assert user_question == "How many items are in the database?"
        if LLM_CALL_COUNT == 1:
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    _tool_call(
                                        "call-1",
                                        "query_api",
                                        {"method": "GET", "path": "/items/"},
                                    )
                                ],
                            }
                        }
                    ]
                }
            )
        return Response(
            {
                "choices": [
                    {
                        "message": {
                                "content": json_lib.dumps(
                                    {
                                        "answer": "There are 3 items in the database.",
                                        "source": "",
                                }
                            )
                        }
                    }
                ]
            }
        )

    raise AssertionError(f"Unexpected scenario: {scenario}")


def request(method, url, headers=None, timeout=None, json=None, content=None):
    scenario = os.environ["MOCK_SCENARIO"]
    assert headers["Authorization"] == "Bearer test-lms-key"

    if scenario == "items_count":
        assert method == "GET"
        assert url == "http://localhost:42002/items/"
        return Response(payload=[{"id": 1}, {"id": 2}, {"id": 3}], status_code=200)

    raise AssertionError(f"Unexpected API request for scenario: {scenario}")
""".strip()
        )
        env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

        result = subprocess.run(
            [sys.executable, str(agent_path), question],
            capture_output=True,
            text=True,
            cwd=project_root,
            env=env,
        )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"
    return json.loads(result.stdout)


def test_agent_uses_read_file_for_framework_question():
    data = _run_agent_with_mock(
        "What framework does the backend use?",
        "framework",
    )

    assert data["source"] == "backend/app/main.py"
    assert [call["tool"] for call in data["tool_calls"]] == ["read_file"]
    assert data["tool_calls"][0]["args"] == {"path": "backend/app/main.py"}


def test_agent_uses_query_api_for_live_item_count():
    data = _run_agent_with_mock(
        "How many items are in the database?",
        "items_count",
    )

    assert data["source"] == ""
    assert [call["tool"] for call in data["tool_calls"]] == ["query_api"]
    assert data["tool_calls"][0]["args"] == {"method": "GET", "path": "/items/"}
    result_payload = json.loads(data["tool_calls"][0]["result"])
    assert result_payload["status_code"] == 200
