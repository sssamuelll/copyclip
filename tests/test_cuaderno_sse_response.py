import io
import json

from copyclip.intelligence.server_helpers import sse_response


class FakeHandler:
    def __init__(self, fail_after=None):
        self.wfile = io.BytesIO()
        self.headers_sent = []
        self.status = None
        self._writes = 0
        self._fail_after = fail_after

    def send_response(self, code):
        self.status = code

    def send_header(self, k, v):
        self.headers_sent.append((k, v))

    def end_headers(self):
        self.headers_sent.append(("__end__", ""))


def _records(handler):
    text = handler.wfile.getvalue().decode("utf-8")
    return [r for r in text.split("\n\n") if r.strip()]


def test_sse_response_writes_headers_and_data_records():
    h = FakeHandler()
    ok = sse_response(h, iter([{"type": "meta", "session_id": "s1"},
                               {"type": "block", "block": {"kind": "lead"}}]))
    assert ok is True
    assert h.status == 200
    assert ("Content-Type", "text/event-stream") in h.headers_sent
    recs = _records(h)
    assert recs[0] == 'data: {"type": "meta", "session_id": "s1"}'
    assert json.loads(recs[1][len("data: "):])["type"] == "block"


def test_sse_response_returns_false_on_broken_pipe():
    class Boom(io.BytesIO):
        def write(self, b):
            raise BrokenPipeError("client gone")

    closed = {"v": False}

    def events():
        try:
            yield {"type": "meta", "session_id": "s1"}
            yield {"type": "block", "block": {}}
        finally:
            closed["v"] = True

    h = FakeHandler()
    h.wfile = Boom()
    ok = sse_response(h, events())
    assert ok is False
    assert closed["v"] is True  # generator was closed so its finally ran
