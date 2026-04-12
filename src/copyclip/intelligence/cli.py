import argparse
import json
import os
import subprocess
import sys
import socket

from .analyzer import analyze
from .db import connect, init_schema
from .server import run_server


COMMANDS = {"analyze", "serve", "start", "decision", "report", "issue", "audit", "mcp", "update"}


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
                # Selection made!
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
    try:
        return _maybe_handle_internal(argv)
    except KeyboardInterrupt:
        print("\n" + _info("Operation cancelled by user. Exiting..."))
        sys.exit(0)
    except Exception as e:
        print(_err(f"Fatal error: {e}"))
        sys.exit(1)

def _maybe_handle_internal(argv) -> bool:
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
        except Exception as e:
            llm_ok = False
            print(_warn(f"LLM configuration issue: {str(e)}"))
            if sys.stdin.isatty():
                choice = input(_c("? ", "35") + "Do you want to configure an LLM provider now? (y/N): ").strip().lower()
                if choice == 'y':
                    opts = ["deepseek", "openai", "anthropic", "gemini", "local"]
                    cols = ["36", "32", "33", "35", "34"] # Cyan, Green, Yellow, Magenta, Blue
                    
                    print(_info("Select provider (Arrows to navigate, Space/Enter to select):"))
                    provider = _interactive_select(opts, cols)
                    print(f"  Selected: \033[1m{provider}\033[0m")
                    
                    api_key = input(_c("  Enter API Key: ", "37")).strip()
                    if provider and api_key:
                        from dotenv import load_dotenv
                        env_path = os.path.join(root, ".env")
                        meta = PROVIDERS.get(provider, PROVIDERS["deepseek"])
                        key_var = meta.api_key_env
                        
                        with open(env_path, "a" if os.path.exists(env_path) else "w") as f:
                            f.write(f"\n# CopyClip Configuration\n")
                            f.write(f"COPYCLIP_LLM_PROVIDER={provider}\n")
                            f.write(f"{key_var}={api_key}\n")
                        
                        # Load immediately into current process
                        load_dotenv(env_path, override=True)
                        print(_ok(f"Settings saved to {env_path}. Semantic intelligence enabled."))
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

    # Other commands (simplified for this fix)
    if cmd == "analyze":
        import asyncio
        res = asyncio.run(analyze("."))
        print(_ok(f"Indexed {res['files']} files."))
        return True

    if cmd == "mcp":
        import asyncio
        from ..mcp_server import main as run_mcp_server
        print(_info("Starting MCP Oracle..."))
        asyncio.run(run_mcp_server())
        return True

    if cmd == "update":
        import shutil
        REPO_URL = "git+https://github.com/sssamuelll/copyclip.git"
        print(_info("Updating copyclip..."))

        # Try pipx first
        if shutil.which("pipx"):
            pipx_list = subprocess.run(["pipx", "list"], capture_output=True, text=True)
            if "copyclip" in (pipx_list.stdout or ""):
                print(_info("Upgrading via pipx..."))
                result = subprocess.run(["pipx", "upgrade", "copyclip"])
                if result.returncode != 0:
                    print(_warn("pipx upgrade failed, reinstalling..."))
                    subprocess.run(["pipx", "install", f"copyclip @ {REPO_URL}", "--force"])
                print(_ok("copyclip updated successfully."))
                return True

        # Fall back to pip
        pip_cmd = [sys.executable, "-m", "pip", "install", "--upgrade", f"copyclip @ {REPO_URL}"]
        print(_info("Upgrading via pip..."))
        result = subprocess.run(pip_cmd)
        if result.returncode == 0:
            print(_ok("copyclip updated successfully."))
        else:
            print(_err("Update failed. Try manually: pip install --upgrade copyclip"))
        return True

    return False
