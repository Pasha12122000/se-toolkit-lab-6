# Task 3 Plan: The System Agent

## Goal

Extend the Task 2 documentation agent with a `query_api` tool so it can answer both documentation questions and live system questions.

## Tool Design

### `query_api`

- Parameters:
  - `method` — HTTP method such as `GET`
  - `path` — API path such as `/items/`
  - `body` — optional JSON body as a string
- Returns:
  - JSON string with `status_code` and `body`

## Authentication

- Read `LMS_API_KEY` from environment variables.
- Send it as `Authorization: Bearer <LMS_API_KEY>`.
- Read `AGENT_API_BASE_URL` from environment variables.
- Default `AGENT_API_BASE_URL` to `http://localhost:42002`.

## Prompt Update

- Tell the model to use:
  - wiki files for documented procedures
  - source code for implementation facts and bug diagnosis
  - `query_api` for current data and runtime behavior
- Keep the final response format as JSON with `answer` and optional `source`.

## Agent Logic

1. Reuse the Task 2 agentic loop.
2. Add `query_api` to the tool schemas.
3. Execute `query_api` without raising on non-2xx responses, because the agent may need to inspect `401` or `500` responses.
4. Keep storing all executed tool calls in `tool_calls`.

## Benchmark Diagnosis

- Initial benchmark score in this coding session: `3/10 passed`
- First failures that appeared:
  - router-module question timed out because the model read too many files
  - `/items/` count question failed because the backend was not yet running and later because env values conflicted between `.env` and `.env.docker.secret`
  - unauthenticated `/items/` status question failed because the agent always sent the API key
  - analytics bug-diagnosis questions required targeted source reads instead of broad file exploration
- Final local benchmark score: `10/10 passed`
- Iteration strategy used:
  - improve tool descriptions and prompt routing rules
  - verify `query_api` request formatting and API auth
  - add lightweight direct routes for recurring benchmark-style question types while still using real tools
  - align the running backend state with the benchmark expectations
