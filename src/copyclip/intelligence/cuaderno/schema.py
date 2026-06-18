from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class Citation:
    path: Optional[str] = None
    line_start: Optional[int] = None
    line_end: Optional[int] = None
    commit: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        if self.commit:
            return {"kind": "commit", "commit": self.commit}
        d: dict[str, Any] = {"kind": "path", "path": self.path}
        if self.line_start is not None:
            d["line_start"] = self.line_start
        if self.line_end is not None:
            d["line_end"] = self.line_end
        return d

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Citation":
        if d.get("kind") == "commit":
            return Citation(commit=d["commit"])
        return Citation(
            path=d.get("path"),
            line_start=d.get("line_start"),
            line_end=d.get("line_end"),
        )


@dataclass(frozen=True)
class Widget:
    """A display-only widget glimpse inside a frame block."""
    kind: str  # 'graph_subset' | 'sequence_diagram' | 'callers_tree' | 'graph_view' | 'playground'
    data: dict[str, Any]

    @staticmethod
    def graph_subset(nodes: list[dict], edges: list[dict]) -> "Widget":
        return Widget(kind="graph_subset", data={"nodes": nodes, "edges": edges})

    @staticmethod
    def sequence_diagram(actors: list[str], steps: list[dict]) -> "Widget":
        return Widget(kind="sequence_diagram", data={"actors": actors, "steps": steps})

    @staticmethod
    def callers_tree(root: str, callers: list[dict]) -> "Widget":
        return Widget(kind="callers_tree", data={"root": root, "callers": callers})

    @staticmethod
    def graph_view(nodes: list[dict], edges: list[dict],
                   focus: Optional[str] = None, truncated: bool = False) -> "Widget":
        d: dict[str, Any] = {"nodes": nodes, "edges": edges, "truncated": truncated}
        if focus is not None:
            d["focus"] = focus
        return Widget(kind="graph_view", data=d)

    @staticmethod
    def playground(function_ref: dict, breadcrumb: str,
                   suggested_inputs: Optional[list] = None,
                   call: Optional[dict] = None,
                   needs_args: Optional[bool] = None) -> "Widget":
        citation: dict[str, Any] = {"kind": "path", "path": function_ref.get("file")}
        if function_ref.get("line") is not None:
            citation["line_start"] = function_ref["line"]
        d: dict[str, Any] = {"function_ref": function_ref, "breadcrumb": breadcrumb,
                             "citation": citation}
        if suggested_inputs is not None:
            d["suggested_inputs"] = suggested_inputs
        if call is not None:
            d["call"] = call
        if needs_args:
            d["needs_args"] = True
        return Widget(kind="playground", data=d)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Widget":
        kind = d["kind"]
        data = {k: v for k, v in d.items() if k != "kind"}
        return Widget(kind=kind, data=data)


@dataclass(frozen=True)
class Block:
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def lead(text: str) -> "Block":
        return Block(kind="lead", data={"text": text})

    @staticmethod
    def paragraph(text: str) -> "Block":
        return Block(kind="paragraph", data={"text": text})

    @staticmethod
    def ordered_list(items: list[dict]) -> "Block":
        return Block(kind="ordered_list", data={"items": items})

    @staticmethod
    def code_block(code: str, language: str, citation: Optional[dict] = None) -> "Block":
        d: dict[str, Any] = {"code": code, "language": language}
        if citation is not None:
            d["citation"] = citation
        return Block(kind="code_block", data=d)

    @staticmethod
    def ascii_block(text: str) -> "Block":
        return Block(kind="ascii_block", data={"text": text})

    @staticmethod
    def citation(citation: dict) -> "Block":
        return Block(kind="citation", data={"citation": citation})

    @staticmethod
    def citation_stack(items: list[dict]) -> "Block":
        return Block(kind="citation_stack", data={"items": items})

    @staticmethod
    def callout(kicker: str, text: str, citations: Optional[list[dict]] = None) -> "Block":
        d: dict[str, Any] = {"kicker": kicker, "text": text}
        if citations is not None:
            d["citations"] = citations
        return Block(kind="callout", data=d)

    @staticmethod
    def widget(widget: dict) -> "Block":
        return Block(kind="widget", data={"widget": widget})

    @staticmethod
    def followups(items: list[dict]) -> "Block":
        return Block(kind="followups", data={"items": items})

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, **self.data}

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Block":
        kind = d["kind"]
        data = {k: v for k, v in d.items() if k != "kind"}
        return Block(kind=kind, data=data)


# Frame-level verdict about answer quality (see the answer-quality spec).
FRAME_STATUS_ANSWER = "answer"                       # a normal, grounded answer
FRAME_STATUS_INSUFFICIENT_EVIDENCE = "insufficient_evidence"  # World A: consulted, genuinely empty
FRAME_STATUS_UNGROUNDED = "ungrounded"               # World B: never consulted the code
FRAME_STATUS_PARTIAL = "partial"                     # interrupted mid-composition
FRAME_STATUS_FALLBACK = "fallback"                   # no blocks / budget exhausted
FRAME_STATUS_LEGACY = "legacy"                       # pre-existing frame with no recorded status
FRAME_STATUS_OFF_TARGET = "off_target"               # grounded, but answers a different question

KNOWN_FRAME_STATUSES: frozenset[str] = frozenset({
    FRAME_STATUS_ANSWER, FRAME_STATUS_INSUFFICIENT_EVIDENCE, FRAME_STATUS_UNGROUNDED,
    FRAME_STATUS_PARTIAL, FRAME_STATUS_FALLBACK, FRAME_STATUS_LEGACY,
    FRAME_STATUS_OFF_TARGET,
})


@dataclass
class Frame:
    question: str
    blocks: list[Block]
    status: str = FRAME_STATUS_ANSWER
    verdict: Optional[dict[str, Any]] = None
    question_language: Optional[str] = None


def frame_to_dict(f: Frame) -> dict[str, Any]:
    return {
        "question": f.question,
        "blocks": [b.to_dict() for b in f.blocks],
        "status": f.status,
        "verdict": f.verdict,
        "question_language": f.question_language,
    }


def frame_from_dict(d: dict[str, Any]) -> Frame:
    return Frame(
        question=d["question"],
        blocks=[Block.from_dict(b) for b in d["blocks"]],
        status=d.get("status", FRAME_STATUS_LEGACY),
        verdict=d.get("verdict"),
        question_language=d.get("question_language"),
    )


KNOWN_BLOCK_KINDS: frozenset[str] = frozenset({
    "lead", "paragraph", "ordered_list", "code_block", "ascii_block",
    "citation", "citation_stack", "callout", "widget", "followups",
})


def validate_block_dict(d: Any) -> Optional[str]:
    """Return None if d is a renderable Block dict, else a short reason string.

    Light validation: the block must be an object with a known `kind`. Per-kind
    field validation is intentionally deferred — Block.from_dict tolerates extra
    or missing fields, and the kind check is what guards the renderer against an
    unknown block type falling through to a null render.
    """
    if not isinstance(d, dict):
        return "block is not an object"
    kind = d.get("kind")
    if kind not in KNOWN_BLOCK_KINDS:
        return f"unknown or missing block kind: {kind!r}"
    return None
