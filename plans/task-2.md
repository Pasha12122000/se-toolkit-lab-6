# Task 2 Plan: The Documentation Agent

## Goal

Turn the Task 1 CLI into a documentation agent that can inspect the repository wiki through tool calls and answer with both `answer` and `source`.

## Tools

### `list_files`

- Input: relative directory path from the project root
- Output: newline-separated list of files and directories
- Use: help the LLM discover relevant wiki files before reading them

### `read_file`

- Input: relative file path from the project root
- Output: file contents as text
- Use: let the LLM read the relevant wiki article before answering

## Path Security

- Resolve every requested path relative to the project root with `Path.resolve()`.
- Reject any path that escapes the repository root.
- Return an error string instead of raising if the path is invalid, missing, or of the wrong type.

## Agentic Loop

1. Start with system prompt + user question.
2. Send the message history and tool schemas to the LLM.
3. If the LLM returns tool calls:
   - execute each tool
   - append the assistant tool-call message
   - append one `tool` message per result
   - store each call in the output `tool_calls` array
4. If the LLM returns normal text:
   - parse it as JSON with `answer` and `source`
   - return the final result
5. Stop after at most 10 tool calls.

## Prompt Strategy

- Tell the LLM to use `list_files("wiki")` first when it needs to find documentation.
- Tell it to prefer wiki content over general knowledge.
- Tell it to finish with a JSON object containing:
  - `answer`
  - `source`

## Tests

- Add one regression test where the LLM uses `list_files` and `read_file` to answer a wiki question.
- Add one regression test where the LLM uses `list_files` to answer a file-discovery question.
- Mock the OpenAI-compatible API with a fake `httpx` module so tests do not depend on network access.
