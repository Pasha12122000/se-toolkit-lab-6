# Agent Architecture

## Overview

This is a simple CLI agent that connects to an LLM and returns structured JSON responses.

## LLM Provider

- **Provider:** OpenRouter
- **Model:** `meta-llama/llama-3.3-70b-instruct:free`
- **Base URL:** `https://openrouter.ai/api/v1`
- **API:** OpenAI-compatible chat completions endpoint

## How It Works

1. User runs `uv run agent.py "question"`
2. Agent loads configuration from `.env.agent.secret`
3. Agent sends `POST /chat/completions` with a minimal system prompt and the user question
4. Agent extracts `choices[0].message.content` from the provider response
5. Agent outputs JSON to stdout

## Configuration

Environment variables (from `.env.agent.secret`):

- `LLM_API_KEY` — API key for OpenRouter
- `LLM_API_BASE` — base API URL, for example `https://openrouter.ai/api/v1`
- `LLM_MODEL` — model name, for example `meta-llama/llama-3.3-70b-instruct:free`

The agent appends `/chat/completions` to `LLM_API_BASE`, so the environment variable should contain the API base, not the full endpoint path.

## Output Format

```json
{"answer": "...", "tool_calls": []}
```

- `answer` — LLM response text
- `tool_calls` — empty array (Task 1)

## Usage

```bash
uv run agent.py "What does REST stand for?"
```

## Notes

- Only valid JSON is printed to stdout.
- Debug and error messages go to stderr.
- `tool_calls` is always an empty array in Task 1 because tool use is added in later tasks.
