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
    load_dotenv(override=True)
    parser = argparse.ArgumentParser(
        description=(
            "Copies the content of all files in a folder to the clipboard, "
            "respecting .copyclipignore and supporting presets and token minimization."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("folder", nargs="?", default=".", help="Path to the base folder (default: current directory).")
    parser.add_argument("--extension", help="File extension to include, e.g., .go (optional).", default=None)
    parser.add_argument("--preset", help="Use predefined filters (code, docs, styles, configs)", default=None)
    parser.add_argument("--include", help="Glob patterns to include (comma-separated)", default=None)
    parser.add_argument("--exclude", help="Glob patterns to exclude (comma-separated)", default=None)
    parser.add_argument("--only", help="Restrict to specific subpaths (comma-separated)", default=None)
    parser.add_argument("--max-file-size", type=int, default=DEFAULT_MAX_FILE_SIZE, help=f"Skip files larger than this (bytes, default: {DEFAULT_MAX_FILE_SIZE})")
    parser.add_argument("--concurrency", type=int, default=None, help="Max concurrent file reads (auto-detected if not set)")
    parser.add_argument("--no-progress", action="store_true", help="Disable progress bars")
    
    # --- START: Nuevos argumentos para LLM ---
    parser.add_argument("--provider", default=os.environ.get("COPYCLIP_LLM_PROVIDER"), help="Specify the LLM provider to use (e.g., openai, anthropic)")
    # --- END: Nuevos argumentos para LLM ---
    # Removed: --ignore-file (now always uses .copyclipignore if found)
    parser.add_argument("--output", help="Write output to file in addition to clipboard", default=None)
    parser.add_argument("--minimize", choices=["basic", "aggressive", "structural", "contextual"], help="Reduce token count")
    parser.add_argument("--model", default=os.environ.get("COPYCLIP_MODEL"), help="AI Model for precise token counting")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow symlinks during scan")
    parser.add_argument("--flow-diagram", action="store_true", help="Deprecated, use --view=flow or --view=both")
    parser.add_argument("--view", choices=["text", "flow", "both"], help="Output view mode: text, flow, or both", default=None)
    # Opt-in flag to print final assembled output to stdout (keeps default CLI quiet)
    parser.add_argument("--print", dest="print_output", action="store_true", help="Print final output to stdout (opt-in)")

    parser.add_argument("--docstrings", choices=["off", "generate", "overwrite"], default=os.environ.get("COPYCLIP_DOCSTRINGS", "off"))
    parser.add_argument("--doc-lang", choices=["en","es"], default=os.environ.get("COPYCLIP_DOC_LANG","en"))
    parser.add_argument("--with-dependencies", action="store_true",
                        help="When used with --minimize contextual, prepend a Mermaid module dependency graph.")

    # Removed: --discover-ignore and --no-discover-ignore arguments

    args = parser.parse_args()

    from copyclip.llm.provider_config import resolve_provider, ProviderConfigError
    
    try:
        # Pasa 'None' como configuración para forzar a resolve_provider
        # a usar únicamente las variables de entorno que acabamos de cargar.
        _ = resolve_provider(args.provider, config={}) 
    except ProviderConfigError as e:
        # Este error ahora te dirá exactamente qué variable falta en TU .env
        print(f"[ERROR] Provider config error: {e}", file=sys.stderr)
        sys.exit(2)
    
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
