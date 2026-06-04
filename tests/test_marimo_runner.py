"""Tests for the Marimo subprocess manager (issue #88).

Two tiers:

* Unit tests monkey-patch ``subprocess.Popen`` and the URL probe to
  exercise the lifecycle without paying the cost of a real Marimo boot.
  These cover concurrency cap, orphan sweep, error mapping, and
  cleanup semantics.

* Integration tests (``@pytest.mark.integration``) spawn a real
  ``python -m marimo edit`` subprocess on Windows/POSIX. Each uses a
  fixture that registers ``runner.kill_all()`` as a finalizer so a
  failing test never leaks subprocesses across the suite. Skipped
  automatically when marimo isn't importable.
"""

from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import psutil
import pytest

from copyclip.intelligence.marimo_runner import (
    MAX_CONCURRENT_PLAYGROUNDS,
    MarimoRunner,
    _RunningInstance,
    _StderrCollector,
    create_runner,
)
from copyclip.intelligence.playground import (
    MarimoNotInstalledError,
    MarimoSpawnError,
    NoFreePortError,
)


_MINIMAL_NOTEBOOK = (
    "import marimo\n"
    "app = marimo.App()\n\n"
    "@app.cell\n"
    "def __():\n"
    "    return\n\n"
    "if __name__ == '__main__':\n"
    "    app.run()\n"
)


def _has_marimo() -> bool:
    try:
        import marimo  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# FakeProcess for unit tests (no real subprocess)
# ---------------------------------------------------------------------------


class _FakeProcess:
    """Mimics the slice of ``subprocess.Popen`` that ``MarimoRunner`` uses."""

    def __init__(
        self,
        stderr_data: bytes = b"",
        poll_initial: int | None = None,
    ) -> None:
        self._poll_value = poll_initial
        self.returncode = poll_initial if poll_initial is not None else 0
        self.stderr = io.BytesIO(stderr_data)
        self.stdout = None
        self.pid = 0
        self.terminated = False
        self.killed = False

    def poll(self) -> int | None:
        return self._poll_value

    def terminate(self) -> None:
        self.terminated = True
        if self._poll_value is None:
            self._poll_value = -15
            self.returncode = -15

    def kill(self) -> None:
        self.killed = True
        if self._poll_value is None:
            self._poll_value = -9
            self.returncode = -9

    def wait(self, timeout: float | None = None) -> int:
        if self._poll_value is None:
            self._poll_value = 0
            self.returncode = 0
        return self._poll_value


def _make_notebook(tmp_path: Path, name: str) -> str:
    nb_dir = tmp_path / f"copyclip-playground-{name}"
    nb_dir.mkdir()
    nb = nb_dir / "playground.py"
    nb.write_text(_MINIMAL_NOTEBOOK, encoding="utf-8")
    return str(nb)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def runner(request):
    """A MarimoRunner with kill_all registered as a finalizer.

    Guarantees no orphan subprocesses leak even if a test asserts and
    aborts before its own cleanup.
    """
    r = MarimoRunner()
    request.addfinalizer(r.kill_all)
    return r


@pytest.fixture
def minimal_notebook(tmp_path):
    return _make_notebook(tmp_path, "integration")


# ---------------------------------------------------------------------------
# Unit tests: API basics
# ---------------------------------------------------------------------------


def test_status_returns_missing_for_unknown_id():
    assert MarimoRunner().status("nonexistent-id") == "missing"


def test_kill_returns_false_for_unknown_id():
    assert MarimoRunner().kill("nonexistent-id") is False


def test_create_runner_returns_marimo_runner():
    assert isinstance(create_runner(), MarimoRunner)


def test_allocate_port_returns_valid_port():
    port = MarimoRunner()._allocate_port()
    assert 1024 <= port < 65536


# ---------------------------------------------------------------------------
# Unit tests: launch / kill happy path (mocked subprocess)
# ---------------------------------------------------------------------------


def _patch_healthy_spawn(monkeypatch, fake_proc=None):
    """Wire Popen and _probe_url so launch() succeeds without real marimo."""
    proc = fake_proc or _FakeProcess()
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen",
        lambda *a, **k: proc,
    )
    return proc


def test_launch_returns_id_and_iframe_url(monkeypatch, tmp_path):
    _patch_healthy_spawn(monkeypatch)
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "launch")

    pid, url = r.launch(nb)

    assert pid and len(pid) >= 16
    assert url.startswith("http://127.0.0.1:")
    assert url.endswith("/")
    assert r.status(pid) == "running"
    r.kill_all()


def test_launch_picks_a_port_via_bind_zero(monkeypatch, tmp_path):
    _patch_healthy_spawn(monkeypatch)
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "port")
    _, url = r.launch(nb)

    # The URL has a non-zero port that we can parse back.
    port_str = url.rstrip("/").rsplit(":", 1)[-1]
    port = int(port_str)
    assert 1024 <= port < 65536
    r.kill_all()


def test_kill_removes_instance_and_temp_dir(monkeypatch, tmp_path):
    fake_proc = _FakeProcess()
    _patch_healthy_spawn(monkeypatch, fake_proc)
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "kill")
    nb_dir = os.path.dirname(nb)

    pid, _ = r.launch(nb)
    assert os.path.isdir(nb_dir)

    assert r.kill(pid) is True
    assert fake_proc.terminated
    assert r.status(pid) == "missing"
    assert not os.path.exists(nb_dir)


def test_kill_all_clears_every_instance(monkeypatch, tmp_path):
    procs: list[_FakeProcess] = []

    def fake_popen(*args, **kwargs):
        p = _FakeProcess()
        procs.append(p)
        return p

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", fake_popen
    )
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)

    nb_dirs = []
    for i in range(3):
        nb = _make_notebook(tmp_path, f"all{i}")
        r.launch(nb)
        nb_dirs.append(os.path.dirname(nb))

    assert len(r._instances) == 3
    r.kill_all()
    assert r._instances == {}
    for p in procs:
        assert p.terminated or p.killed
    for d in nb_dirs:
        assert not os.path.exists(d)


# ---------------------------------------------------------------------------
# Unit tests: error mapping
# ---------------------------------------------------------------------------


def test_launch_raises_marimo_not_installed_when_stderr_says_so(
    monkeypatch, tmp_path
):
    dead = _FakeProcess(
        stderr_data=b"/usr/bin/python3: No module named marimo\n",
        poll_initial=1,
    )
    _patch_healthy_spawn(monkeypatch, dead)
    r = MarimoRunner()
    nb = _make_notebook(tmp_path, "missing")

    with pytest.raises(MarimoNotInstalledError):
        r.launch(nb)


def test_launch_raises_marimo_spawn_failed_on_early_exit(monkeypatch, tmp_path):
    dead = _FakeProcess(
        stderr_data=b"unrelated traceback: ValueError: boom\n", poll_initial=2
    )
    _patch_healthy_spawn(monkeypatch, dead)
    r = MarimoRunner()
    nb = _make_notebook(tmp_path, "early-exit")

    with pytest.raises(MarimoSpawnError) as exc_info:
        r.launch(nb)
    # stderr tail should appear in the error for diagnostics
    assert "boom" in str(exc_info.value) or "rc=2" in str(exc_info.value)


def test_launch_raises_marimo_spawn_failed_on_timeout(monkeypatch, tmp_path):
    """Subprocess stays alive but never serves HTTP — must raise after timeout."""
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.HEALTHCHECK_TIMEOUT_S", 0.3
    )
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.HEALTHCHECK_POLL_S", 0.05
    )
    proc = _FakeProcess()  # poll() returns None — alive forever
    _patch_healthy_spawn(monkeypatch, proc)
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: False)
    nb = _make_notebook(tmp_path, "timeout")

    with pytest.raises(MarimoSpawnError) as exc_info:
        r.launch(nb)
    assert "respond" in str(exc_info.value).lower()
    assert proc.terminated  # launch must kill the hung subprocess before raising


def test_launch_raises_marimo_not_installed_when_interpreter_missing(
    monkeypatch, tmp_path
):
    def boom(*args, **kwargs):
        raise FileNotFoundError("no such interpreter")

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", boom
    )
    r = MarimoRunner()
    nb = _make_notebook(tmp_path, "no-py")

    with pytest.raises(MarimoNotInstalledError):
        r.launch(nb)


# ---------------------------------------------------------------------------
# Unit tests: concurrency cap
# ---------------------------------------------------------------------------


def test_concurrency_cap_enforced(monkeypatch, tmp_path):
    procs: list[_FakeProcess] = []

    def fake_popen(*args, **kwargs):
        p = _FakeProcess()
        procs.append(p)
        return p

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", fake_popen
    )
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)

    for i in range(MAX_CONCURRENT_PLAYGROUNDS):
        r.launch(_make_notebook(tmp_path, f"cap{i}"))

    extra_nb = _make_notebook(tmp_path, "overflow")
    with pytest.raises(NoFreePortError):
        r.launch(extra_nb)
    # cap rejection should not register a new instance or spawn anything new
    assert len(r._instances) == MAX_CONCURRENT_PLAYGROUNDS
    assert len(procs) == MAX_CONCURRENT_PLAYGROUNDS
    r.kill_all()


def test_concurrency_cap_enforced_under_parallel_launches(monkeypatch, tmp_path):
    """The reservation-slot pattern must hold the cap when launches race.

    Without it, ``launch()`` released the lock between the cap check and
    instance registration, so N concurrent launches could all pass the
    guard while none had registered yet. This test gates ``Popen`` on a
    barrier so every thread reaches it under the slot reservation, then
    releases them simultaneously.
    """
    import threading as _t

    spawn_gate = _t.Event()
    procs: list[_FakeProcess] = []
    procs_lock = _t.Lock()

    def gated_popen(*args, **kwargs):
        spawn_gate.wait(timeout=5.0)
        p = _FakeProcess()
        with procs_lock:
            procs.append(p)
        return p

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", gated_popen
    )
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)

    n_threads = MAX_CONCURRENT_PLAYGROUNDS + 2
    results: list[str] = []
    results_lock = _t.Lock()

    def attempt(idx: int) -> None:
        nb = _make_notebook(tmp_path, f"race{idx}")
        try:
            r.launch(nb)
            with results_lock:
                results.append("ok")
        except NoFreePortError:
            with results_lock:
                results.append("rejected")

    threads = [
        _t.Thread(target=attempt, args=(i,)) for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    # Give every thread time to acquire its slot reservation before any
    # spawn proceeds. Without this beat, the first thread might complete
    # before later threads run their cap check.
    time.sleep(0.1)
    spawn_gate.set()
    for t in threads:
        t.join(timeout=10.0)
        assert not t.is_alive(), "race-test thread did not finish"

    assert results.count("ok") == MAX_CONCURRENT_PLAYGROUNDS, (
        f"got {results.count('ok')} successful launches; "
        f"expected exactly {MAX_CONCURRENT_PLAYGROUNDS}"
    )
    assert results.count("rejected") == n_threads - MAX_CONCURRENT_PLAYGROUNDS
    assert len(r._instances) == MAX_CONCURRENT_PLAYGROUNDS
    # Reservations must drain after the launches settle, so a follow-up
    # kill+launch can still admit a new slot.
    assert r._reservations == set()
    r.kill_all()


# ---------------------------------------------------------------------------
# Unit tests: orphan sweep on startup
# ---------------------------------------------------------------------------


def test_orphan_temp_dir_cleaned_on_startup(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    orphan = tmp_path / "copyclip-playground-orphan"
    orphan.mkdir()
    (orphan / "playground.py").write_text("# leftover", encoding="utf-8")
    assert orphan.exists()

    MarimoRunner()

    assert not orphan.exists()


def test_orphan_sweep_ignores_unrelated_temp_dirs(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    keep = tmp_path / "some-other-prefix-keepme"
    keep.mkdir()

    MarimoRunner()

    assert keep.exists()


def test_orphan_sweep_preserves_dirs_with_live_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.tempfile.gettempdir",
        lambda: str(tmp_path),
    )
    live_dir = tmp_path / "copyclip-playground-live"
    live_dir.mkdir()
    marker_path = str(live_dir / "playground.py")
    # Spawn a long-running python process whose cmdline contains
    # the live_dir path verbatim (no shell escaping involved — argv
    # is passed via CreateProcess/execve, so psutil sees it raw).
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(15)", marker_path]
    )
    try:
        # Wait for the process to be visible in psutil's listing.
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            if any(
                marker_path in (arg or "")
                for p in psutil.process_iter(["cmdline"])
                for arg in (p.info.get("cmdline") or [])
            ):
                break
            time.sleep(0.05)

        MarimoRunner()
        assert live_dir.exists(), (
            "live_dir should not be swept — its path is in a live process's cmdline"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)


# ---------------------------------------------------------------------------
# Unit tests: stderr collector
# ---------------------------------------------------------------------------


def test_stderr_collector_captures_data_and_tails():
    data = b"warning A\n" + b"warning B\n" * 50 + b"final line\n"
    collector = _StderrCollector(io.BytesIO(data))
    collector.join(timeout=1.0)
    tail = collector.tail(40)
    assert "final line" in tail
    assert len(tail.encode("utf-8")) <= 40 or tail.endswith("final line\n")


def test_stderr_collector_handles_empty_stream():
    collector = _StderrCollector(io.BytesIO(b""))
    collector.join(timeout=0.5)
    assert collector.tail() == ""


# ---------------------------------------------------------------------------
# Integration tests: real marimo subprocess
# ---------------------------------------------------------------------------

pytestmark_integration = pytest.mark.skipif(
    not _has_marimo(), reason="marimo not installed; pip install copyclip[playground]"
)


@pytest.mark.integration
@pytestmark_integration
def test_integration_launch_starts_real_marimo(runner, minimal_notebook):
    pid, url = runner.launch(minimal_notebook)
    assert pid
    assert url.startswith("http://127.0.0.1:")
    assert runner.status(pid) == "running"

    port = int(url.rstrip("/").rsplit(":", 1)[-1])
    with socket.create_connection(("127.0.0.1", port), timeout=2.0):
        pass  # something is listening


@pytest.mark.integration
@pytestmark_integration
def test_integration_kill_terminates_within_2s(runner, minimal_notebook):
    pid, _ = runner.launch(minimal_notebook)
    with runner._lock:
        sub_pid = runner._instances[pid].process.pid
    assert psutil.pid_exists(sub_pid)

    start = time.monotonic()
    assert runner.kill(pid) is True
    elapsed = time.monotonic() - start
    # Spec budget is 2s grace + 0.5s slack for wait/cleanup
    assert elapsed < 3.0, f"kill took {elapsed:.2f}s"

    # Either gone outright, or a transient zombie on POSIX — never alive.
    for _ in range(20):
        if not psutil.pid_exists(sub_pid):
            return
        try:
            status = psutil.Process(sub_pid).status()
        except psutil.NoSuchProcess:
            return
        if status == psutil.STATUS_ZOMBIE:
            return
        time.sleep(0.05)
    pytest.fail(f"subprocess pid {sub_pid} still alive after kill")


@pytest.mark.integration
@pytestmark_integration
def test_integration_kill_removes_temp_dir(runner, minimal_notebook):
    pid, _ = runner.launch(minimal_notebook)
    with runner._lock:
        temp_dir = runner._instances[pid].temp_dir
    assert os.path.isdir(temp_dir)

    runner.kill(pid)

    assert not os.path.exists(temp_dir)


@pytest.mark.integration
@pytestmark_integration
def test_integration_status_reports_running_then_exited(runner, minimal_notebook):
    pid, _ = runner.launch(minimal_notebook)
    assert runner.status(pid) == "running"

    # Terminate the subprocess without going through runner.kill (which would
    # remove the instance from the registry). After it dies, status flips
    # from "running" to "exited" — the instance is still tracked.
    with runner._lock:
        proc = runner._instances[pid].process
    proc.terminate()
    try:
        proc.wait(timeout=3.0)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=3.0)

    assert runner.status(pid) == "exited"


@pytest.mark.integration
@pytestmark_integration
def test_integration_kill_all_cleans_everything(runner, tmp_path):
    nb1 = _make_notebook(tmp_path, "all1")
    nb2 = _make_notebook(tmp_path, "all2")
    pid1, _ = runner.launch(nb1)
    pid2, _ = runner.launch(nb2)
    assert runner.status(pid1) == "running"
    assert runner.status(pid2) == "running"

    runner.kill_all()

    assert runner.status(pid1) == "missing"
    assert runner.status(pid2) == "missing"
    assert not os.path.exists(os.path.dirname(nb1))
    assert not os.path.exists(os.path.dirname(nb2))


# ---------------------------------------------------------------------------
# Unit tests: mode parameter + list()
# ---------------------------------------------------------------------------


def test_launch_default_mode_is_edit(monkeypatch, tmp_path):
    """launch() with no mode kwarg must spawn 'marimo edit ...'."""
    captured_argv: list[list[str]] = []

    def fake_popen(args, **kwargs):
        captured_argv.append(list(args))
        return _FakeProcess()

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", fake_popen
    )
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "default-mode")

    r.launch(nb)

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    assert argv[2] == "marimo"
    assert argv[3] == "edit"
    r.kill_all()


def test_launch_run_mode_spawn_args(monkeypatch, tmp_path):
    """launch(mode='run') must pass 'run' as the marimo sub-command, not 'edit'."""
    captured_argv: list[list[str]] = []

    def fake_popen(args, **kwargs):
        captured_argv.append(list(args))
        return _FakeProcess()

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", fake_popen
    )
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "run-mode")

    r.launch(nb, mode="run")

    assert len(captured_argv) == 1
    argv = captured_argv[0]
    # argv: [sys.executable, "-m", "marimo", "run", notebook_path, ...]
    assert argv[2] == "marimo"
    assert argv[3] == "run"
    r.kill_all()


def test_launch_unknown_mode_raises(monkeypatch, tmp_path):
    """launch(mode='bogus') must raise MarimoSpawnError before spawning."""
    popen_calls: list = []

    def capturing_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return _FakeProcess()

    monkeypatch.setattr(
        "copyclip.intelligence.marimo_runner.subprocess.Popen", capturing_popen
    )
    r = MarimoRunner()
    nb = _make_notebook(tmp_path, "bad-mode")

    with pytest.raises(MarimoSpawnError, match="unknown marimo mode"):
        r.launch(nb, mode="bogus")

    assert popen_calls == [], "Popen must not be called when mode is invalid"


def test_list_empty_when_no_instances():
    r = MarimoRunner()
    assert r.list() == []


def test_list_returns_instances(monkeypatch, tmp_path):
    """After a successful launch, list() must include the instance id + status."""
    _patch_healthy_spawn(monkeypatch)
    r = MarimoRunner()
    monkeypatch.setattr(r, "_probe_url", lambda url: True)
    nb = _make_notebook(tmp_path, "list-test")

    pid, _ = r.launch(nb)

    items = r.list()
    assert len(items) == 1
    assert items[0]["id"] == pid
    assert items[0]["status"] == "running"
    r.kill_all()
