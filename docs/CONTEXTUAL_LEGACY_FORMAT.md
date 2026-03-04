# Contextual Legacy Output Format (Contract)

This document freezes the expected shape of legacy contextual fallback output used in tests/mocks.

## Python

- Starts with module header comment:
  - `# Module: Contextual minimization of source code`
- Function/class blocks are declarative skeletons (not full bodies)
- Placeholder body indentation is **4 spaces**
- Example:

```py
# desc1
def foo():
    pass
```

## JavaScript / TypeScript

- Starts with module header comment:
  - `// Module: Contextual minimization of source code`
- Function/class signatures are preserved in compact skeleton style

## Legacy extra descriptions behavior

When mocked descriptions are more than discovered symbols:
- extra descriptions are inserted as additional module-level comments
- current frozen ordering contract in tests is:
  - `desc4`, `desc3`, then paired entries (`desc1`, `desc2`)

This is intentionally locked by regression tests to avoid accidental drift.
