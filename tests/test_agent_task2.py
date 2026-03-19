"""Regression tests for agent.py (Task 2)."""

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
    env["LLM_API_KEY"] = "test-key"
    env["LLM_API_BASE"] = "http://test-server/v1"
    env["LLM_MODEL"] = "test-model"
    env["MOCK_SCENARIO"] = scenario

    with tempfile.TemporaryDirectory() as temp_dir:
        mock_httpx = Path(temp_dir) / "httpx.py"
        mock_httpx.write_text(
            """
import json
import os


class HTTPError(Exception):
    pass


class Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


CALL_COUNT = 0


def _tool_call(call_id, name, arguments):
    return {
        "id": call_id,
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        },
    }


def post(url, headers, json, timeout):
    global CALL_COUNT
    CALL_COUNT += 1

    assert url == "http://test-server/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert json["model"] == "test-model"
    assert "tools" in json

    scenario = os.environ["MOCK_SCENARIO"]
    user_question = json["messages"][1]["content"]

    if scenario == "merge_conflict":
        assert user_question == "How do you resolve a merge conflict?"
        if CALL_COUNT == 1:
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    _tool_call("call-1", "list_files", {"path": "wiki"})
                                ],
                            }
                        }
                    ]
                }
            )
        if CALL_COUNT == 2:
            assert json["messages"][-1]["role"] == "tool"
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    _tool_call(
                                        "call-2",
                                        "read_file",
                                        {"path": "wiki/git-workflow.md"},
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
                            "content": json_dumps(
                                {
                                    "answer": "Edit the conflicting file, choose the changes to keep, then stage and commit.",
                                    "source": "wiki/git-workflow.md#edit-files",
                                }
                            )
                        }
                    }
                ]
            }
        )

    if scenario == "wiki_listing":
        assert user_question == "What files are in the wiki?"
        if CALL_COUNT == 1:
            return Response(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    _tool_call("call-1", "list_files", {"path": "wiki"})
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
                            "content": json_dumps(
                                {
                                    "answer": "The wiki contains documentation files such as api.md and git-workflow.md.",
                                    "source": "wiki",
                                }
                            )
                        }
                    }
                ]
            }
        )

    raise AssertionError(f"Unexpected scenario: {scenario}")


def json_dumps(payload):
    return json.dumps(payload)
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


def test_agent_uses_read_file_for_documentation_answer():
    data = _run_agent_with_mock(
        "How do you resolve a merge conflict?",
        "merge_conflict",
    )

    assert "answer" in data
    assert "source" in data
    assert "tool_calls" in data
    assert data["source"] == "wiki/git-workflow.md#edit-files"
    assert [call["tool"] for call in data["tool_calls"]] == ["list_files", "read_file"]
    assert data["tool_calls"][1]["args"] == {"path": "wiki/git-workflow.md"}


def test_agent_uses_list_files_for_wiki_listing():
    data = _run_agent_with_mock(
        "What files are in the wiki?",
        "wiki_listing",
    )

    assert "answer" in data
    assert "source" in data
    assert "tool_calls" in data
    assert data["source"] == "wiki"
    assert [call["tool"] for call in data["tool_calls"]] == ["list_files"]
    assert data["tool_calls"][0]["args"] == {"path": "wiki"}
