# Task 1 Plan: Call an LLM from Code

## LLM Provider

- **Provider:** OpenRouter
- **Model:** `meta-llama/llama-3.3-70b-instruct:free`
- **Base URL:** `https://openrouter.ai/api/v1`
- **Endpoint used by the agent:** `POST /chat/completions`

## Architecture

1. **Input**
   - Read the user question from the first CLI argument.
2. **Configuration**
   - Load `LLM_API_KEY`, `LLM_API_BASE`, and `LLM_MODEL` from `.env.agent.secret`.
3. **LLM request**
   - Send an OpenAI-compatible chat completions request with a minimal system prompt and one user message.
   - Apply a timeout below the 60-second task limit.
4. **Response handling**
   - Parse the JSON response from the LLM provider.
   - Extract `choices[0].message.content` as the final answer.
5. **Output**
   - Print exactly one JSON object to stdout with `answer` and `tool_calls`.
   - Print any diagnostics only to stderr.

## Error Handling

- If the question is missing, print usage to stderr and exit with non-zero status.
- If environment variables are missing or invalid, print the error to stderr.
- If the HTTP request fails or the response is malformed, print the error to stderr.

## Data Flow

1. User runs `uv run agent.py "question"`.
2. `agent.py` loads settings from `.env.agent.secret`.
3. `agent.py` sends a POST request to `LLM_API_BASE + /chat/completions`.
4. OpenRouter returns a chat completion response.
5. `agent.py` prints `{"answer": "...", "tool_calls": []}` to stdout.

## Testing

- Run `agent.py` as a subprocess.
- Parse stdout as JSON.
- Check that `answer` exists and is a string.
- Check that `tool_calls` exists and equals an empty array.
