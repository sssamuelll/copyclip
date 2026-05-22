"""Marimo subprocess manager for the Anchored Playground (issue #88).

Implements the ``MarimoRunner`` Protocol defined in ``playground.py``:

* Spawn a fresh ``python -m marimo edit`` subprocess per launch on a
  127.0.0.1-only port picked via the bind-to-0 trick.
* Healthcheck the editor URL until it responds (or the subprocess dies),
  surfacing ``MarimoNotInstalledError`` / ``MarimoSpawnError`` with a
  stderr tail.
* Terminate cross-platform with ``Popen.terminate()`` then ``kill()`` —
  ``os.kill(SIGTERM)`` is POSIX-only and silently breaks on Windows.
* Sweep orphaned ``copyclip-playground-*`` directories from previous
  CopyClip crashes on startup (psutil ``cmdline`` scan — open_files
  needs admin on Windows).

Trust-by-design per the spec: the editor uses ``--no-token`` because
the iframe is loaded by the same CopyClip dashboard that spawned the
subprocess, both on 127.0.0.1. No sandboxing — the subprocess inherits
``sys.executable``'s venv.
"""

from __future__ import annotations

import collections
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import Literal

import psutil

from .playground import (
    MarimoNotInstalledError,
    MarimoSpawnError,
    NoFreePortError,
)

MAX_CONCURRENT_PLAYGROUNDS = 5
HEALTHCHECK_TIMEOUT_S = 10.0
HEALTHCHECK_POLL_S = 0.1
TERMINATE_GRACE_S = 2.0
TEMP_DIR_PREFIX = "copyclip-playground-"
_STDERR_TAIL_BYTES = 500
_STDERR_BUFFER_BYTES = 8192

# Marker substrings that prove the subprocess died because marimo itself
# wasn't importable — distinct from a generic spawn failure.
_MARIMO_NOT_INSTALLED_MARKERS = (
    "No module named 'marimo'",
    "No module named marimo",
)


class _StderrCollector:
    """Background drain for the subprocess stderr pipe.

    Without this, marimo's startup chatter (typically 1–4 KB) eventually
    fills the OS pipe buffer (~64 KB POSIX, ~4 KB Windows) and blocks the
    child on its next stderr write. The thread reads with ``read1`` so it
    never waits for the buffer to fill before flushing — short reads land
    in our deque immediately. The deque caps at ``_STDERR_BUFFER_BYTES``;
    older bytes are evicted, which is what ``tail(n)`` wants anyway.
    """

    def __init__(self, stream) -> None:
        self._buf: collections.deque = collections.deque(maxlen=_STDERR_BUFFER_BYTES)
        self._lock = threading.Lock()
        self._stream = stream
        self._thread = threading.Thread(
            target=self._drain, name="copyclip-marimo-stderr", daemon=True
        )
        self._thread.start()

    def _drain(self) -> None:
        try:
            while True:
                chunk = self._stream.read1(4096)
                if not chunk:
                    return  # EOF: subprocess closed stderr
                with self._lock:
                    self._buf.extend(chunk)
        except Exception:
            return

    def tail(self, n: int = _STDERR_TAIL_BYTES) -> str:
        with self._lock:
            data = bytes(self._buf)
        return data[-n:].decode("utf-8", errors="replace")

    def join(self, timeout: float = 0.5) -> None:
        self._thread.join(timeout=timeout)


@dataclass
class _RunningInstance:
    playground_id: str
    port: int
    process: subprocess.Popen
    temp_dir: str
    stderr_collector: _StderrCollector = field(repr=False)


class MarimoRunner:
    """Spawn-on-demand Marimo subprocess manager. Thread-safe."""

    def __init__(self) -> None:
        self._instances: dict[str, _RunningInstance] = {}
        self._lock = threading.Lock()
        self._sweep_orphans_on_startup()

    # ------------------------------------------------------------------
    # Public API (MarimoRunner Protocol + kill_all)
    # ------------------------------------------------------------------

    def launch(self, notebook_path: str) -> tuple[str, str]:
        with self._lock:
            if len(self._instances) >= MAX_CONCURRENT_PLAYGROUNDS:
                raise NoFreePortError(
                    f"max {MAX_CONCURRENT_PLAYGROUNDS} playgrounds already running; "
                    "close one before opening another"
                )

        port = self._allocate_port()
        cmd = [
            sys.executable,
            "-m",
            "marimo",
            "edit",
            notebook_path,
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--headless",
            "--no-token",
        ]
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError as exc:
            # sys.executable went away; treat as marimo-unavailable.
            raise MarimoNotInstalledError(
                f"python interpreter not found at {sys.executable!r}: {exc}"
            ) from exc

        collector = _StderrCollector(process.stderr)
        try:
            self._wait_for_healthy(process, port, collector)
        except BaseException:
            self._best_effort_kill(process)
            raise

        playground_id = uuid.uuid4().hex
        temp_dir = os.path.dirname(os.path.abspath(notebook_path))
        instance = _RunningInstance(
            playground_id=playground_id,
            port=port,
            process=process,
            temp_dir=temp_dir,
            stderr_collector=collector,
        )
        with self._lock:
            self._instances[playground_id] = instance
        return playground_id, f"http://127.0.0.1:{port}/"

    def kill(self, playground_id: str) -> bool:
        with self._lock:
            instance = self._instances.pop(playground_id, None)
        if instance is None:
            return False
        self._best_effort_kill(instance.process)
        shutil.rmtree(instance.temp_dir, ignore_errors=True)
        return True

    def status(
        self, playground_id: str
    ) -> Literal["running", "exited", "missing"]:
        with self._lock:
            instance = self._instances.get(playground_id)
        if instance is None:
            return "missing"
        return "running" if instance.process.poll() is None else "exited"

    def kill_all(self) -> None:
        with self._lock:
            instances = list(self._instances.values())
            self._instances.clear()
        for inst in instances:
            try:
                self._best_effort_kill(inst.process)
            except Exception:
                pass
            shutil.rmtree(inst.temp_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _allocate_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    def _probe_url(self, url: str) -> bool:
        """Return True iff the URL responds with any HTTP status.

        Even 4xx counts as healthy — what we care about is that the
        subprocess bound the port and the HTTP layer is up.
        """
        try:
            with urllib.request.urlopen(url, timeout=0.5) as r:
                return 200 <= r.status < 500
        except urllib.error.HTTPError as e:
            return 200 <= e.code < 500
        except Exception:
            return False

    def _wait_for_healthy(
        self,
        process: subprocess.Popen,
        port: int,
        collector: _StderrCollector,
    ) -> None:
        url = f"http://127.0.0.1:{port}/"
        start = time.monotonic()
        while time.monotonic() - start < HEALTHCHECK_TIMEOUT_S:
            rc = process.poll()
            if rc is not None:
                # subprocess died before the editor came up
                collector.join(timeout=0.5)
                stderr_tail = collector.tail()
                if any(m in stderr_tail for m in _MARIMO_NOT_INSTALLED_MARKERS):
                    raise MarimoNotInstalledError(
                        "marimo is not installed in the active python "
                        f"({sys.executable}); install with: "
                        "pip install 'copyclip[playground]'"
                    )
                raise MarimoSpawnError(
                    f"marimo exited before becoming healthy (rc={rc}); "
                    f"stderr_tail: {stderr_tail!r}"
                )
            if self._probe_url(url):
                return
            time.sleep(HEALTHCHECK_POLL_S)
        # timeout: kill, then drain stderr for diagnostics
        self._best_effort_kill(process)
        collector.join(timeout=0.5)
        raise MarimoSpawnError(
            f"marimo failed to respond within {HEALTHCHECK_TIMEOUT_S}s on port {port}; "
            f"stderr_tail: {collector.tail()!r}"
        )

    def _best_effort_kill(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            pass
        try:
            process.wait(timeout=TERMINATE_GRACE_S)
            return
        except subprocess.TimeoutExpired:
            pass
        try:
            process.kill()
        except Exception:
            pass
        try:
            process.wait(timeout=TERMINATE_GRACE_S)
        except Exception:
            pass

    def _sweep_orphans_on_startup(self) -> None:
        tmp = tempfile.gettempdir()
        try:
            entries = os.listdir(tmp)
        except OSError:
            return
        for name in entries:
            if not name.startswith(TEMP_DIR_PREFIX):
                continue
            path = os.path.join(tmp, name)
            if not os.path.isdir(path):
                continue
            if self._dir_has_live_owner(path):
                continue
            shutil.rmtree(path, ignore_errors=True)

    def _dir_has_live_owner(self, path: str) -> bool:
        """Detect whether any live process holds ``path``.

        Implementation note: we scan ``cmdline`` rather than ``open_files``
        because ``open_files`` requires elevated privileges on Windows and
        is slow on Linux. The marimo subprocess is always spawned with the
        notebook path (which lives inside ``path``) in its argv, so a
        substring match is sufficient and cheap.
        """
        target = os.path.normcase(path)
        for proc in psutil.process_iter(["pid", "cmdline"]):
            try:
                cmdline = proc.info.get("cmdline") or []
                for arg in cmdline:
                    if arg and target in os.path.normcase(arg):
                        return True
            except (psutil.AccessDenied, psutil.NoSuchProcess, OSError):
                continue
        return False


def create_runner() -> MarimoRunner:
    """Factory consumed by ``server.py``'s fallback wiring."""
    return MarimoRunner()
