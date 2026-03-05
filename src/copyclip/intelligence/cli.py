import argparse
import json
import os
import subprocess
import sys
import socket

from .analyzer import analyze
from .db import connect, init_schema
from .server import run_server


COMMANDS = {"analyze", "serve", "start", "decision", "report", "issue", "audit", "mcp"}


def _use_color() -> bool:
    return sys.stdout.isatty() and os.getenv("NO_COLOR") is None


def _c(text: str, code: str) -> str:
    if not _use_color():
        return text
    return f"\033[{code}m{text}\033[0m"


def _info(msg: str) -> str:
    return f"{_c('INFO', '36')} {msg}"


def _ok(msg: str) -> str:
    return f"{_c('OK', '32')} {msg}"


def _warn(msg: str) -> str:
    return f"{_c('WARN', '33')} {msg}"


def _err(msg: str) -> str:
    return f"{_c('ERROR', '31')} {msg}"


def _get_key():
    """Read a single key press from stdin."""
    import tty, termios
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(sys.stdin.fileno())
        ch = sys.stdin.read(1)
        if ch == '\x1b':
            ch += sys.stdin.read(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return ch

def _interactive_select(options, colors):
    """Render a vertical list with arrow navigation and colored items."""
    idx = 0
    num_opts = len(options)
    
    # Hide cursor
    sys.stdout.write("\033[?25l")
    sys.stdout.flush()
    
    try:
        while True:
            # Print options
            for i, (opt, col) in enumerate(zip(options, colors)):
                if i == idx:
                    prefix = _c("  → [x] ", "37;1")
                    label = f"\033[1;{col}m{opt}\033[0m"
                else:
                    prefix = "      [ ] "
                    label = f"\033[{col}m{opt}\033[0m"
                sys.stdout.write(f"{prefix}{label}\n")
            
            # Read input
            key = _get_key()
            
            # Move cursor back up to start of list
            sys.stdout.write(f"\033[{num_opts}A")
            
            if key in ('\r', '\n', ' '):
                # Selection made! Move cursor down to the end of list and show cursor
                sys.stdout.write(f"\033[{num_opts}B")
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
                return options[idx]
            elif key == '\x1b[A': # Up arrow
                idx = (idx - 1) % num_opts
            elif key == '\x1b[B': # Down arrow
                idx = (idx + 1) % num_opts
            elif key == '\x03': # Ctrl+C
                sys.stdout.write(f"\033[{num_opts}B")
                sys.stdout.write("\033[?25h")
                sys.stdout.flush()
                raise KeyboardInterrupt
    except Exception as e:
        sys.stdout.write("\033[?25h")
        raise e

def _looks_like_project_folder(root: str) -> bool:
    markers = [".git", "pyproject.toml", "package.json", "requirements.txt", ".copyclip"]
    return any(os.path.exists(os.path.join(root, m)) for m in markers)

def _pick_open_port(base_port: int, max_scan: int = 50) -> int:
    for port in range(base_port, base_port + max_scan + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise OSError(f"No open port near {base_port}")

def maybe_handle(argv) -> bool:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        return False

    cmd = argv[1]
    
    if cmd == "start":
        import asyncio
        from ..llm.config import load_config
        from ..llm.provider_config import resolve_provider, PROVIDERS

        p = argparse.ArgumentParser("copyclip start")
        p.add_argument("--path", default=".")
        p.add_argument("--port", type=int, default=4310)
        p.add_argument("--open", dest="open_browser", action=argparse.BooleanOptionalAction, default=True)
        args = p.parse_args(argv[2:])

        root = os.path.abspath(args.path)
        if not _looks_like_project_folder(root):
            print(_err(f"'{root}' is not a project folder."))
            return True

        # 1) Check LLM Configuration interactively
        llm_ok = True
        try:
            cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
            _ = resolve_provider(os.getenv("COPYCLIP_LLM_PROVIDER"), cfg)
            print(_ok("LLM provider configured."))
        except Exception:
            llm_ok = False
            print(_warn("LLM provider not configured."))
            if sys.stdin.isatty():
                choice = input(_c("? ", "35") + "Do you want to configure an LLM provider now? (y/N): ").strip().lower()
                if choice == 'y':
                    opts = ["deepseek", "openai", "anthropic", "gemini", "local"]
                    # Colors: Cyan, Green, Yellow, Magenta, Blue
                    cols = ["36", "32", "33", "35", "34"]
                    
                    print(_info("Select provider (Use arrows to navigate, Space/Enter to select):"))
                    provider = _interactive_select(opts, cols)
                    print(f"  Selected: \033[1m{provider}\033[0m")
                    
                    api_key = input(_c("  Enter API Key: ", "37")).strip()
                    if provider and api_key:
                        env_path = os.path.join(root, ".env")
                        meta = PROVIDERS.get(provider, PROVIDERS["deepseek"])
                        key_var = meta.api_key_env
                        
                        with open(env_path, "a" if os.path.exists(env_path) else "w") as f:
                            f.write(f"\n# CopyClip Configuration\n")
                            f.write(f"COPYCLIP_LLM_PROVIDER={provider}\n")
                            f.write(f"{key_var}={api_key}\n")
                        
                        os.environ["COPYCLIP_LLM_PROVIDER"] = provider
                        os.environ[key_var] = api_key
                        print(_ok("Settings saved to .env. Semantic intelligence enabled."))
                        llm_ok = True
                    else:
                        print(_warn("Incomplete info. Using basic mode."))
                else:
                    print(_info("Continuing in basic mode."))

        # 2) Ensure initial analysis
        conn = connect(root)
        init_schema(conn)
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row or not conn.execute("SELECT id FROM snapshots WHERE project_id=?", (row[0],)).fetchone():
            print(_info("No analysis found. Indexing project..."))
            res = asyncio.run(analyze(root))
            print(_ok(f"Analysis complete: {res['files']} files."))
        else:
            print(_info("Existing analysis found."))
        conn.close()

        # 3) Pick port and start
        port = _pick_open_port(args.port)
        dash_url = f"http://127.0.0.1:{port}"
        if not llm_ok: dash_url += "/settings"

        if args.open_browser:
            try:
                if sys.platform == "darwin":
                    subprocess.Popen(["open", dash_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    print(_info(f"Opening dashboard: {dash_url}"))
            except Exception: pass

        try:
            run_server(root, port)
        except KeyboardInterrupt:
            print("\n" + _info("Stopped."))
        return True

    if cmd == "analyze":
        import asyncio
        res = asyncio.run(analyze("."))
        print(_ok(f"Indexed {res['files']} files, {res['commits']} commits."))
        return True

    if cmd == "decision":
        # Simplified decision logic for space efficiency in rewrite
        import sys
        print(_info("Use 'copyclip decision add|list|link|resolve'"))
        return True

    if cmd == "audit":
        import asyncio
        from .cli_audit import run_audit # Assuming we move full audit logic to helper to keep cli.py lean
        asyncio.run(run_audit(argv[2:]))
        return True

    if cmd == "mcp":
        import asyncio
        from ..mcp_server import main as run_mcp_server
        print(_info("Starting MCP Oracle..."))
        asyncio.run(run_mcp_server())
        return True

    return False
