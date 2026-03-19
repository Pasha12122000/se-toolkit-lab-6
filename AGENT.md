# Agent Architecture

## Overview

This CLI agent answers repository documentation questions by combining an LLM with local file tools. It can inspect the `wiki/` directory, read relevant files, and then return a structured JSON response.

## LLM Provider

- **Provider:** OpenRouter
- **Model:** `meta-llama/llama-3.3-70b-instruct:free`
- **Base URL:** `https://openrouter.ai/api/v1`
- **API:** OpenAI-compatible chat completions endpoint

## Tools

### `list_files`

- Input: relative directory path
- Output: newline-separated directory listing
- Purpose: help the LLM discover which wiki file to inspect

### `read_file`

- Input: relative file path
- Output: file contents
- Purpose: give the LLM the exact documentation text it needs

Both tools use path validation based on `Path.resolve()` and reject paths that escape the project root.

## Agentic Loop

1. User runs `uv run agent.py "question"`.
2. The agent loads LLM settings from `.env.agent.secret`.
3. The agent sends the user question, system prompt, and tool schemas to the LLM.
4. If the LLM requests tools, the agent executes them locally and appends the results as `tool` messages.
5. The loop continues until the LLM returns a final answer or the agent reaches the 10-tool-call limit.
6. The agent prints one JSON object to stdout with `answer`, `source`, and `tool_calls`.

## System Prompt Strategy

- Tell the model to use `list_files` first to discover relevant wiki files.
- Tell the model to use `read_file` to inspect the most relevant article.
- Tell the model to prefer wiki content over general knowledge.
- Tell the model to return final output as a JSON object with:
  - `answer`
  - `source`

## Configuration

Environment variables (from `.env.agent.secret`):

- `LLM_API_KEY` — API key for OpenRouter
- `LLM_API_BASE` — base API URL, for example `https://openrouter.ai/api/v1`
- `LLM_MODEL` — model name, for example `meta-llama/llama-3.3-70b-instruct:free`

The agent appends `/chat/completions` to `LLM_API_BASE`, so the environment variable should contain the API base, not the full endpoint path.

## Output Format

```json
{
  "answer": "...",
  "source": "wiki/file.md#section-anchor",
  "tool_calls": [
    {"tool": "list_files", "args": {"path": "wiki"}, "result": "..."}
  ]
}
```

- `answer` — LLM response text
- `source` — wiki file and section anchor used for the answer
- `tool_calls` — all tool calls executed during the run

## Usage

```bash
uv run agent.py "How do you resolve a merge conflict?"
```

## Notes

- Only valid JSON is printed to stdout.
- Debug and error messages go to stderr.
- The agent stops after at most 10 tool calls.
