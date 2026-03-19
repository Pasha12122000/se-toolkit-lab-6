"""Regression tests for agent.py (Task 1)."""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


def test_agent_returns_valid_json():
    """Test that agent.py returns valid JSON with required fields."""
    project_root = Path(__file__).parent.parent
    agent_path = project_root / "agent.py"

    env = os.environ.copy()
    env["LLM_API_KEY"] = "test-key"
    env["LLM_API_BASE"] = "http://test-server/v1"
    env["LLM_MODEL"] = "test-model"

    with tempfile.TemporaryDirectory() as temp_dir:
        mock_httpx = Path(temp_dir) / "httpx.py"
        mock_httpx.write_text(
            """
class HTTPError(Exception):
    pass


class Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def post(url, headers, json, timeout):
    assert url == "http://test-server/v1/chat/completions"
    assert headers["Authorization"] == "Bearer test-key"
    assert json["model"] == "test-model"
    assert json["messages"][-1]["content"] == "What is 2+2?"
    return Response(
        {
            "choices": [
                {
                    "message": {
                        "content": "2 + 2 = 4."
                    }
                }
            ]
        }
    )
""".strip()
        )
        env["PYTHONPATH"] = f"{temp_dir}{os.pathsep}{env.get('PYTHONPATH', '')}".rstrip(os.pathsep)

        result = subprocess.run(
            [sys.executable, str(agent_path), "What is 2+2?"],
            capture_output=True,
            text=True,
            cwd=project_root,
            env=env,
        )

    assert result.returncode == 0, f"Agent failed: {result.stderr}"

    stdout = result.stdout.strip()
    assert stdout, "stdout is empty"

    data = json.loads(stdout)

    assert "answer" in data, "Missing 'answer' field"
    assert isinstance(data["answer"], str), "'answer' must be a string"
    assert "tool_calls" in data, "Missing 'tool_calls' field"
    assert isinstance(data["tool_calls"], list), "'tool_calls' must be an array"
    assert data["tool_calls"] == [], "'tool_calls' must be empty in Task 1"
