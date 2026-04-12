# Language Support

## Tree-sitter Deep Extraction (v0.4.0+)

The following languages receive full symbol-level extraction via Tree-sitter:

| Language | Extensions | Definitions | Imports | Calls | Inheritance |
|----------|-----------|-------------|---------|-------|-------------|
| Python | .py | functions, classes, methods | import, from...import | function calls, method calls | class inheritance |
| JavaScript | .js, .jsx | functions, classes, methods | import...from | function calls, method calls | extends |
| TypeScript | .ts, .tsx | functions, classes, methods | import...from | function calls, method calls | extends |
| CSS | .css | — | @import | — | — |
| C++ | .cpp, .cc, .cxx, .h, .hpp | functions, classes, structs | #include | function calls | base classes |
| Rust | .rs | functions, structs, enums, traits | use | function calls, macro invocations | impl...for (trait implementations) |

## Regex Fallback

Files in unsupported languages receive basic import extraction via regex patterns. This provides module-level dependency edges but no function/class-level symbols.

## Adding a New Language

To add Tree-sitter support for a new language:

1. Install the tree-sitter grammar package (e.g., `tree-sitter-go`)
2. Add the language to `_LANG_MODULES` in `src/copyclip/intelligence/tree_sitter_parser.py`
3. Implement an `_extract_<language>` function using AST node traversal
4. Register it in `_EXTRACTORS`
5. Add the extension mapping in `analyzer.py:_lang_from_ext`
6. Add tests in `tests/test_tree_sitter_parser.py`
