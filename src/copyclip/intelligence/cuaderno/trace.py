"""Interaction trace: one append-only JSONL timeline per cuaderno ask / playground launch.

Spec: docs/superpowers/specs/2026-06-10-cuaderno-interaction-trace-design.md

This is an artifact writer, not a logger: the file IS the debugging record of one
interaction, written incrementally (append + flush per event) so a crash leaves a
readable prefix. Golden rule: tracing can NEVER break the ask path — every public
method swallows its own failures, and the tracer self-disables after the first one.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Union

MAX_TRACE_FILES = 200
WIRE_ENV_VAR = "COPYCLIP_TRACE_WIRE"  # wire traces can reach several MB per ask (full messages per round); see spec §5.3


def trace_logs_dir(project_root: str) -> Path:
    return Path(project_root) / ".copyclip" / "logs" / "cuaderno"


class NullTrace:
    """No-op stand-in exposing the full InteractionTrace surface."""

    wire = False
    enabled = False
    path: Optional[Path] = None

    def event(self, name: str, /, **payload: Any) -> None:  # fix 1: positional-only
        return None

    def close(self, **payload: Any) -> None:
        return None


NULL_TRACE = NullTrace()


class InteractionTrace:
    """Append-only JSONL trace for one interaction. Construct via `start()`."""

    def __init__(self) -> None:
        self.wire = False
        self.enabled = False
        self.path: Optional[Path] = None
        self._fh = None
        self._seq = 0
        self._t0 = time.perf_counter()
        self._kind = "ask"

    @classmethod
    def start(
        cls,
        kind: str,
        logs_dir: Union[str, Path],
        header: Optional[dict] = None,
        tag: Optional[str] = None,
    ) -> "InteractionTrace":
        """Open `<kind>_<UTCstamp>_<tag>.jsonl` and write the `<kind>.start` header
        event. On ANY failure returns a disabled instance (one stderr WARN, no raise)."""
        t = cls()
        t._kind = kind
        t.wire = os.environ.get(WIRE_ENV_VAR, "") not in ("", "0")
        try:
            d = Path(logs_dir)
            d.mkdir(parents=True, exist_ok=True)
            _prune(d)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            safe_tag = tag or uuid.uuid4().hex[:8]
            base = f"{kind}_{stamp}_{safe_tag}"
            # fix 4: retry on FileExistsError instead of disabling (TOCTOU)
            path = d / f"{base}.jsonl"
            i = 2
            fh = None
            while True:
                try:
                    fh = path.open("x", encoding="utf-8", newline="\n")  # fix 6: LF-only
                    break
                except FileExistsError:
                    path = d / f"{base}-{i}.jsonl"
                    i += 1
                    # any other exception falls through to the outer except -> disable
            t._fh = fh
            t.path = path
            t.enabled = True
            t.event(f"{kind}.start", **{**(header or {}), "wire": t.wire})
        except Exception as exc:  # noqa: BLE001 — golden rule: never break the pipeline
            t._disable(f"trace start failed: {exc!r}")
        return t

    def event(self, name: str, /, **payload: Any) -> None:  # fix 1: positional-only
        if not self.enabled or self._fh is None:
            return
        try:
            # fix 5: fixed fields always win over payload keys
            line = json.dumps(
                {**payload,
                 "seq": self._seq,
                 "t_ms": int((time.perf_counter() - self._t0) * 1000),
                 "event": name},
                ensure_ascii=False, default=str,
            )
            self._fh.write(line + "\n")
            self._fh.flush()
            self._seq += 1
        except Exception as exc:  # noqa: BLE001 — golden rule
            self._disable(f"trace write failed: {exc!r}")

    def close(self, **payload: Any) -> None:
        if self._fh is None:
            return
        self.event(f"{self._kind}.end", **payload)
        try:
            self._fh.close()
        except Exception:
            pass
        self._fh = None
        self.enabled = False

    def _disable(self, why: str) -> None:
        self.enabled = False
        fh, self._fh = self._fh, None
        if fh is not None:
            try:
                fh.close()
            except Exception:
                pass
        # fix 2: guard the print in case stderr is broken
        try:
            print(f"WARN trace disabled: {why}", file=sys.stderr)
        except Exception:
            pass


def _prune(d: Path) -> None:
    """Keep the directory under MAX_TRACE_FILES, oldest-first by name. Files are
    named `<kind>_<UTCstamp>_<tag>.jsonl`; sorting by the part after the first
    underscore (timestamp + tag) is kind-agnostic and stays chronological even
    when ask_ and launch_ files coexist. Called before each new file is created,
    so we prune to MAX-1 and the new file lands at MAX."""
    # fix 3: sort by timestamp portion (after kind prefix) so pruning is kind-agnostic
    files = sorted(
        (p for p in d.glob("*.jsonl") if p.is_file()),
        key=lambda p: p.name.split("_", 1)[-1],
    )
    excess = len(files) - (MAX_TRACE_FILES - 1)
    for p in files[: max(0, excess)]:
        try:
            p.unlink()
        except OSError:
            pass
