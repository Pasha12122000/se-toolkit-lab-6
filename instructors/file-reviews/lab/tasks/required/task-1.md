# Review: `lab/tasks/required/task-1.md`

- **Date:** 2026-03-10
- **Convention files used:**
  - `contributing/conventions/writing/tasks.md` — task structure, design principles, conceptual review dimensions (D1–D12)
  - `contributing/conventions/writing/common.md` — writing conventions (4.1–4.26)

---

## Conceptual findings

### D1. Learning objective clarity

No issues found.

### D2. Step-by-step completeness

No issues found.

### D3. Student navigation

No issues found.

### D4. Checkpoints and feedback loops

No issues found.

### D5. Acceptance criteria alignment

No issues found.

### D6. Difficulty and progression

No issues found.

### D7. Practical usability

No issues found.

### D8. LLM-independence

No issues found.

### D9. Git workflow coherence

No issues found.

### D10. Conceptual gaps and misconceptions

No issues found.

### D11. Controlled AI steps

1. **[Low]** Lines 252–253: The prompt includes subjective phrasing ("explain each function step by step as if teaching a junior engineer") that may produce variable outputs across AI tools. The review checklist (lines 257–265) partially constrains the result but is a post-hoc review, not a concrete verifiable checkpoint.
   **Suggested fix:** Add a concrete checkpoint at the end of step 1.4.2 (e.g., "The implementation must pass `POST /pipeline/sync` — proceed to step 1.4.3 to verify"), which the task already provides implicitly but could state explicitly to close the feedback loop.

### D12. Autochecker verifiability

No issues found.

---

## Convention findings

### 4.1. Instructions wording

1. **[Low]** Line 291: Three actions chained in one instruction: "expand `POST /pipeline/sync`, click `Try it out`, then `Execute`." Convention 4.1 requires splitting compound instructions into separate numbered steps. Borderline case since these actions form a single Swagger UI interaction flow.
   **Suggested fix:** Split into sub-steps, or keep as-is if considered a single logical action.

### 4.2. Terminal commands

No issues found.

### 4.3. Command Palette commands

Not applicable.

### 4.4. Options vs steps

No issues found.

### 4.5. Ordered lists

No issues found.

### 4.6. Mini-ToC

No issues found.

### 4.7. Table of contents

No issues found.

### 4.8. Links and cross-references

No issues found.

### 4.9. Notes, tips, warnings

No issues found.

### 4.10. Images

Not applicable.

### 4.11. Collapsible hints and solutions

No issues found.

### 4.12. Commit message format

No issues found.

### 4.13. Diagrams

No issues found.

### 4.14. `<!-- TODO -->` comments

Not applicable.

### 4.15. `<!-- no toc -->` comments

No issues found.

### 4.16. Code snippets in explanations

Not applicable.

### 4.17. Heading levels in section titles

Not applicable.

### 4.18. Inline formatting of technical terms

No issues found.

### 4.19. Steps with sub-steps

No issues found.

### 4.20. Placeholders in docs

No issues found.

### 4.21. `docker compose up` commands

No issues found.

### 4.22. Environment variable references

No issues found.

### 4.23. Horizontal rules

No issues found.

### 4.24. Inline paths

No issues found.

### 4.25. Branch-on-remote references

Not applicable.

### 4.26. Example IP address

Not applicable.

### Section 1. Task document template (tasks.md)

1. ~~**[Low]** Lines 94–107: [Section 1.2 "Create a `Lab Task` issue"](lab/tasks/required/task-1.md#12-create-a-lab-task-issue) includes branch creation instructions and a naming explanation. The template (tasks.md lines 89–91) specifies that step 1.2 should contain only the issue title. Branch creation belongs in a dedicated step or is covered by the git workflow reference in step 1.1.
   **Suggested fix:** Move branch creation to a separate step (e.g., 1.3) or to the git workflow wiki.~~

### Recovery guidance (tasks.md 4.19)

No issues found.

---

## TODOs

No TODOs found.

---

## Empty sections

No empty sections found.

---

## Summary

| Category | Count |
| --- | --- |
| Conceptual [High] | 0 |
| Conceptual [Medium] | 0 |
| Conceptual [Low] | 1 |
| Convention [High] | 0 |
| Convention [Medium] | 0 |
| Convention [Low] | 1 |
| TODOs | 0 |
| Empty sections | 0 |
| **Total** | **2** |

**Overall:** The remaining issues are one conceptual (author decision required) plus one low-severity convention finding. One borderline compound instruction in step 1.4.3 could optionally be split (4.1 finding). All high and medium violations have been fixed.
