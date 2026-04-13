import argparse
import asyncio
import os
import sys
import logging
from typing import Optional
from tqdm import tqdm 
from dotenv import load_dotenv

# Agrega 'src' al path si se ejecuta directamente desde el repo
if __package__ is None and not hasattr(sys, "frozen"):
    # Permite ejecutar el script directamente para desarrollo
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from copyclip.scanner import scan_files, is_python_shebang
from copyclip.reader import read_files_concurrently
from copyclip.clipboard import ClipboardManager
from copyclip.presets import get_preset
from copyclip.minimizer import minimize_content
from copyclip.tokens import count_raw_tokens
from copyclip.flow_diagram import extract_flow_diagram
from copyclip.ast_extractor import build_dependency_mermaid
from copyclip.intelligence.cli import maybe_handle as maybe_handle_intelligence
from copyclip.intelligence.db import get_active_decisions
from copyclip.llm.selector_service import select_relevant_files

DEFAULT_MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

# Brief: _get_copyclip_ignore_file
def _get_copyclip_ignore_file() -> Optional[str]:
    """
    Locate the .copyclipignore that ships with the CopyClip installation by
    walking upward from this module's directory. If not found, fall back to a
    .copyclipignore in the current working directory. Returns an absolute path
    or None if no ignore file is found.
    """
    try:
        module_dir = os.path.abspath(os.path.dirname(__file__))
        path = module_dir
        while True:
            candidate = os.path.join(path, ".copyclipignore")
            if os.path.exists(candidate):
                return os.path.abspath(candidate)
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
    except Exception:
        # best-effort; fall through to CWD check
        ...

    # Fallback: a project-local .copyclipignore in the CWD
    cwd_candidate = os.path.join(os.getcwd(), ".copyclipignore")
    if os.path.exists(cwd_candidate):
        return os.path.abspath(cwd_candidate)
    return None


# Brief: main
def main():
    try:
        _main_inner()
    except KeyboardInterrupt:
        print("\n\n  Exiting copyclip. (Ctrl+C)", file=sys.stderr)
        print("  Run 'copyclip start' to launch the dashboard.", file=sys.stderr)
        print("  Run 'copyclip --help' for all commands.\n", file=sys.stderr)
        sys.exit(0)


def _main_inner():
    # Explicitly load .env from CWD to ensure it's found on all platforms
    _cwd_env = os.path.join(os.getcwd(), ".env")
    if os.path.exists(_cwd_env):
        load_dotenv(_cwd_env, override=True)
    else:
        load_dotenv(override=True)
    # Intelligence commands are handled first and remain additive.
    if maybe_handle_intelligence(sys.argv):
        return
    parser = argparse.ArgumentParser(
        prog="copyclip",
        description="CopyClip v0.4.0 — Project Intelligence & Intent Authority\n\n"
                    "Scan, analyze, and maintain cognitive ownership of your codebase.\n"
                    "Provides semantic analysis, architectural decision tracking,\n"
                    "risk detection, and AI-agent governance via MCP.",
        epilog="commands:\n"
               "  start             Launch the intelligence dashboard\n"
               "  analyze            Index project files, build dependency graph\n"
               "  update             Update copyclip to the latest version\n"
               "  decision           Manage architectural decisions\n"
               "  mcp                Start the MCP Intent Authority server\n"
               "\n"
               "examples:\n"
               "  copyclip start                Start dashboard for current project\n"
               "  copyclip start --path ./myapp  Start dashboard for a specific project\n"
               "  copyclip analyze               Re-index the current project\n"
               "  copyclip update                Update to latest version\n"
               "  copyclip .                     Copy project context to clipboard\n"
               "  copyclip . --minimize basic    Copy with token reduction\n"
               "  copyclip . --prompt \"fix auth\" Copy files relevant to a task\n",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", nargs="?", default=".", help="Path to scan (default: current directory)")
    parser.add_argument("--extension", help="File extension filter, e.g., .py", default=None)
    parser.add_argument("--preset", help="Predefined filters: code, docs, styles, configs", default=None)
    parser.add_argument("--include", help="Glob patterns to include (comma-separated)", default=None)
    parser.add_argument("--exclude", help="Glob patterns to exclude (comma-separated)", default=None)
    parser.add_argument("--only", help="Restrict to specific subpaths (comma-separated)", default=None)
    parser.add_argument("--max-file-size", type=int, default=DEFAULT_MAX_FILE_SIZE, help=f"Skip files larger than N bytes (default: {DEFAULT_MAX_FILE_SIZE})")
    parser.add_argument("--concurrency", type=int, default=None, help="Max concurrent file reads (auto-detected)")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")
    parser.add_argument("--provider", default=os.environ.get("COPYCLIP_LLM_PROVIDER"), help="LLM provider: openai, deepseek, anthropic")
    parser.add_argument("--output", help="Write output to file in addition to clipboard", default=None)
    parser.add_argument("--minimize", choices=["basic", "aggressive", "structural", "contextual"], help="Token reduction level")
    parser.add_argument("--model", default=os.environ.get("COPYCLIP_MODEL"), help="LLM model for token counting")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow symlinks during scan")
    parser.add_argument("--view", choices=["text", "flow", "both"], help="Output view: text, flow diagram, or both", default=None)
    parser.add_argument("--flow-diagram", action="store_true", help=argparse.SUPPRESS)  # deprecated
    parser.add_argument("--print", dest="print_output", action="store_true", help="Print output to stdout")
    parser.add_argument("--docstrings", choices=["off", "generate", "overwrite"], default=os.environ.get("COPYCLIP_DOCSTRINGS", "off"), help="Docstring handling mode")
    parser.add_argument("--doc-lang", choices=["en","es"], default=os.environ.get("COPYCLIP_DOC_LANG","en"), help="Docstring language")
    parser.add_argument("--with-dependencies", action="store_true", help="Prepend Mermaid dependency graph (with --minimize contextual)")
    parser.add_argument("--no-decisions", action="store_true", help="Exclude architectural decisions from context")
    parser.add_argument("--prompt", help="Select files relevant to this task/intent via LLM")

    args = parser.parse_args()

    from copyclip.llm.provider_config import resolve_provider, ProviderConfigError, PROVIDERS

    try:
        _ = resolve_provider(args.provider, config={})
    except ProviderConfigError:
        if sys.stdin.isatty():
            from copyclip.intelligence.cli import _run_onboarding
            configured = _run_onboarding(os.path.abspath(args.folder), PROVIDERS)
            if not configured:
                print("[INFO] No LLM configured. Some features will be unavailable.", file=sys.stderr)
        else:
            print("[WARN] No LLM configured. Set COPYCLIP_LLM_PROVIDER and API key in .env", file=sys.stderr)
    
    # Always search for .copyclipignore upward from the provided folder
    base_path = os.path.abspath(args.folder)
    ignore_file = _get_copyclip_ignore_file()

    # Configure module logger to write INFO logs to stderr without interfering with stdout output
    logger = logging.getLogger("copyclip")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    if args.view:
        view_mode = args.view
    elif args.flow_diagram:
        view_mode = "both"
    else:
        # Si es TTY y no se especifica --view, preguntar (los tests esperan esto)
        if sys.stdin.isatty():
            print("Select output view: [1] text  [2] flow  [3] both", file=sys.stderr)
            choice = (input("> ").strip() or "1")
            view_mode = {"1": "text", "2": "flow", "3": "both"}.get(choice, "text")
        else:
            view_mode = "text"

    exclude_patterns = args.exclude
    extensions = None
    if args.preset:
        preset_exts, preset_exclude = get_preset(args.preset)
        if preset_exts:
            extensions = preset_exts
        if preset_exclude:
            exclude_patterns = preset_exclude

    if not os.path.exists(base_path):
        print(f"[ERROR] The folder {base_path} does not exist.", file=sys.stderr)
        sys.exit(1)

    try:
        all_files = scan_files(
            base_path,
            ignore_file_path=ignore_file,
            extension=args.extension,
            extensions=extensions,
            include=args.include,
            exclude=exclude_patterns,
            only=args.only,
            max_file_size=args.max_file_size,
            follow_symlinks=args.follow_symlinks,
        )

        if not all_files:
            print("[WARN] No files found to process based on the current filters.", file=sys.stderr)
            return

        # --- AI-based file selection ---
        if args.prompt:
            print(f"[INFO] Using AI to select relevant files for intent: '{args.prompt}'...", file=sys.stderr)
            all_files = asyncio.run(select_relevant_files(all_files, args.prompt, provider_hint=args.provider))
            print(f"[INFO] AI selected {len(all_files)} files.", file=sys.stderr)

        files_with_content = asyncio.run(read_files_concurrently(
            all_files,
            base_path,
            concurrency=args.concurrency,
            max_file_size=args.max_file_size,
            no_progress=args.no_progress
        ))

        # Keep an immutable snapshot for optional dependency graph generation.
        original_files = dict(files_with_content)

        if args.minimize:
            print(f"[INFO] Applying {args.minimize} token minimization...", file=sys.stderr)

            # =============== NUEVO: barra de progreso para contextual ===============
            if args.minimize == "contextual":
                total_size = sum(len(content) for content in files_with_content.values())

                with tqdm(total=total_size, desc="Minimizing", unit="chars",
                          disable=args.no_progress) as pbar:

                    for rel_path in sorted(files_with_content.keys()):
                        content = files_with_content[rel_path]
                        original_size = len(content)

                        # Actualizar descripción con archivo actual
                        pbar.set_description(f"Processing {os.path.basename(rel_path)}")

                        # Detectar extensión (o shebang para .py)
                        _, ext = os.path.splitext(rel_path)
                        file_ext = ext.lstrip('.').lower() if ext else ""
                        if not file_ext:
                            full_path = os.path.join(base_path, rel_path)
                            if is_python_shebang(full_path):
                                file_ext = "py"

                        # Minimizar (modo contextual)
                        minimized = minimize_content(
                            content,
                            file_ext,
                            args.minimize,
                            docstrings_mode=args.docstrings,
                            doc_lang=args.doc_lang,
                            provider=getattr(args, 'provider', None),
                            file_path=rel_path
                        )
                        files_with_content[rel_path] = minimized

                        # Actualizar progreso por tamaño original
                        pbar.update(original_size)

                        # Mostrar ahorro
                        saved = original_size - len(minimized)
                        if saved > 0:
                            pbar.set_postfix(saved=f"{saved/1000:.1f}KB")

            # =============== Ramas originales para otros modos ===============
            else:
                # Orden determinista: primero .py, luego alfabético
                for rel_path in sorted(files_with_content, key=lambda p: (not p.endswith(".py"), p)):
                    content = files_with_content[rel_path]
                    _, ext = os.path.splitext(rel_path)
                    file_ext = ext.lstrip('.').lower() if ext else ""

                    # Si no hay extensión, revisa si es un script de Python por el shebang
                    if not file_ext:
                        full_path = os.path.join(base_path, rel_path)
                        if is_python_shebang(full_path):
                            file_ext = "py"

                    # Log start of per-file minimization and estimate tokens
                    logger.info("Minimizing file %s (mode=%s) — estimating tokens...", rel_path, args.minimize)
                    try:
                        tokenizer_pref = os.environ.get("COPYCLIP_TOKENIZER")
                        orig_tokens, _, _ = count_raw_tokens(content, tokenizer_pref, args.model)
                        logger.info("Original tokens: %d", int(orig_tokens))
                    except Exception as e:
                        logger.warning("Token estimation failed for %s: %s", rel_path, e)
                        orig_tokens = None

                    minimized = minimize_content(
                        content,
                        file_ext,
                        args.minimize,
                        docstrings_mode=args.docstrings,
                        doc_lang=args.doc_lang,
                    )
                    files_with_content[rel_path] = minimized

                    # Token estimate after minimization
                    try:
                        tokenizer_pref = os.environ.get("COPYCLIP_TOKENIZER")
                        min_tokens, _, _ = count_raw_tokens(minimized, tokenizer_pref, args.model)
                        if orig_tokens is not None:
                            delta = int(orig_tokens) - int(min_tokens)
                            logger.info("Minimized tokens: %d (saved %d)", int(min_tokens), int(delta))
                        else:
                            logger.info("Minimized tokens: %d", int(min_tokens))
                    except Exception as e:
                        logger.warning("Token re-estimation failed for %s: %s", rel_path, e)

        output_parts = []

        if args.minimize == "contextual" and args.with_dependencies:
            try:
                graph = build_dependency_mermaid(original_files)
                if graph.strip():
                    output_parts.append(f"```mermaid\n{graph}\n```")
            except Exception as e:
                print(f"[WARN] Dependency graph generation failed: {e}", file=sys.stderr)

        if view_mode in ("text", "both"):
            for rel_path in sorted(files_with_content):
                output_parts.append(f"{rel_path}:\n{files_with_content[rel_path]}")

        if view_mode in ("flow", "both"):
            print("[INFO] Generating flow diagrams for Python files...", file=sys.stderr)
            flow_diagrams = []
            for rel_path, content in sorted(files_with_content.items()):
                if rel_path.endswith(".py"):
                    try:
                        diagram = extract_flow_diagram(content)
                        flow_diagrams.append(f"Flow Diagram for {rel_path}:\n```mermaid\n{diagram}```")
                    except Exception as e:
                        print(f"[WARN] Could not generate flow diagram for {rel_path}: {e}", file=sys.stderr)
            if flow_diagrams:
                output_parts.append("\n\n".join(flow_diagrams))

        # --- Inject Project Decisions / Intent Manifesto ---
        if not args.no_decisions:
            decisions = get_active_decisions(base_path)
            if decisions:
                d_parts = [
                    "## 🎯 ACTIVE ARCHITECTURAL INTENT & DECISIONS",
                    "> Human-defined constraints for this project.",
                    "",
                ]
                for d in decisions:
                    did = d.get('id', '?')
                    title = d.get('title', 'Untitled decision')
                    summary = (d.get('summary') or '').strip()
                    line = f"- [{did}] {title}: {summary or '(no summary)'}"
                    d_parts.append(line)
                    links = d.get('links') or []
                    for l in links[:6]:
                        d_parts.append(f"  - link: {l.get('link_type')} => {l.get('target_pattern')}")
                output_parts.insert(0, "\n".join(d_parts).strip())

        final_output = "\n\n".join(output_parts)

        clipboard = ClipboardManager()
        if clipboard.copy(final_output):
            print("[INFO] Content has been copied to the clipboard.", file=sys.stderr)
            tokenizer_pref = os.environ.get("COPYCLIP_TOKENIZER")
            raw_tokens, raw_src, raw_exact = count_raw_tokens(final_output, tokenizer_pref, args.model)
            # ... (el resto del código de conteo de tokens)
        else:
            print("[ERROR] Failed to copy content to clipboard.", file=sys.stderr)
            sys.exit(1)

        # Opt-in: print the final assembled output to stdout when requested with --print
        # This keeps default behavior clipboard-only while allowing tests and users to opt-in.
        if getattr(args, "print_output", False):
            print(final_output)

        # Also support the existing '--output -' behavior (explicit opt-in)
        if args.output:
            if args.output == '-':
                # Opt-in: prints to stdout when the user asks for '--output -'
                print(final_output)
            else:
                try:
                    with open(args.output, 'w', encoding='utf-8') as f:
                        f.write(final_output)
                    print(f"[INFO] Output also written to: {args.output}", file=sys.stderr)
                except Exception as e:
                    print(f"[WARN] Failed to write output file: {e}", file=sys.stderr)

    except Exception as e:
        print(f"[ERROR] An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
