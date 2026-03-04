import unittest
import asyncio
import tempfile
import os
import sys
import subprocess
from unittest.mock import patch, AsyncMock

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from copyclip.minimizer import extract_functions, inject_comments, minimize_content

class TestExtractFunctions(unittest.TestCase):
    def test_extract_python_functions_and_classes(self):
        code = """
def foo(x):
    return x + 1

class Bar:
    def baz(self):
        pass
"""
        funcs = extract_functions(code, "python")
        names = {f["name"] for f in funcs}
        self.assertIn("foo", names)
        self.assertIn("Bar", names)
        self.assertIn("baz", names)

    def test_extract_javascript_functions_and_classes(self):
        code = """
function foo(x) {
    return x + 1;
}

class Bar {
    baz() {}
}
"""
        funcs = extract_functions(code, "javascript")
        names = {f["name"] for f in funcs}
        self.assertIn("foo", names)
        self.assertIn("Bar", names)
        self.assertIn("baz", names)

class TestInjectComments(unittest.TestCase):
    def test_inject_comments_python(self):
        code = """
def foo():
    pass
"""
        funcs = extract_functions(code, "python")
        descs = ["Test description"]
        result = inject_comments(code, funcs, descs)
        self.assertIn("# Test description", result)

    def test_inject_comments_javascript(self):
        code = """
function foo() {
    return 1;
}
"""
        funcs = extract_functions(code, "javascript")
        descs = ["JS description"]
        result = inject_comments(code, funcs, descs)
        self.assertIn("// JS description", result)

class TestMinimizeContentContextualIntegration(unittest.TestCase):
    @patch("copyclip.minimizer._run_coro_sync")
    def test_minimize_content_contextual_python(self, mock_run_coro):
        mock_run_coro.return_value = ["desc1", "desc2", "desc3"]
        code = """
def foo():
    pass

class Bar:
    def baz(self):
        pass
"""
        result = minimize_content(code, "py", "contextual")
        self.assertIn("# desc1", result)
        self.assertIn("# desc2", result)
        self.assertIn("# desc3", result)

    @patch("copyclip.minimizer._run_coro_sync")
    def test_minimize_content_contextual_javascript(self, mock_run_coro):
        mock_run_coro.return_value = ["desc1", "desc2", "desc3"]
        code = """
function foo() {
    return 1;
}

class Bar {
    baz() {}
}
"""
        result = minimize_content(code, "js", "contextual")
        self.assertIn("// desc1", result)
        self.assertIn("// desc2", result)
        self.assertIn("// desc3", result)


class TestJSFallbackRendering(unittest.TestCase):
    @patch("copyclip.minimizer._run_coro_sync")
    def test_contextual_fallback_keeps_export_arrow_signal(self, mock_run_coro):
        mock_run_coro.side_effect = RuntimeError("LLM unavailable")
        code = "export const sum=(a:number,b:number)=>a+b"
        result = minimize_content(code, "ts", "contextual")
        self.assertIn("export const sum", result)
        self.assertIn("=> { /* ... logic omitted ... */ }", result)


class TestCLIEndToEnd(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.py_file = os.path.join(self.temp_dir.name, "test.py")
        self.js_file = os.path.join(self.temp_dir.name, "test.js")
        with open(self.py_file, "w", encoding="utf-8") as f:
            f.write("def foo(): return 42\nclass Bar: pass")
        with open(self.js_file, "w", encoding="utf-8") as f:
            f.write("function foo(){ return 42; }\nclass Bar {}")

    def tearDown(self):
        self.temp_dir.cleanup()

    @patch("copyclip.minimizer._run_coro_sync")
    def test_cli_minimize_contextual(self, mock_run_coro):
        mock_run_coro.return_value = ["desc1", "desc2", "desc3", "desc4"]

        # Run CLI in-process so patched _run_coro_sync is used and output can be captured
        from io import StringIO
        import contextlib
        from copyclip import __main__ as main_module

        old_argv = sys.argv[:]
        try:
            sys.argv = [old_argv[0], self.temp_dir.name, "--minimize", "contextual", "--preset", "code", "--print"]
            buf = StringIO()
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
                main_module.main()
            out = buf.getvalue()
        finally:
            sys.argv = old_argv

        self.assertIn("# desc1", out or "")
        self.assertIn("// desc3", out or "")

        # Python fallback skeleton must remain syntactically valid/declarative
        self.assertNotIn("return 42:", out or "")
        self.assertNotIn("pass:", out or "")
        self.assertIn("def foo():", out or "")
        self.assertIn("class Bar:", out or "")

        # Exact indentation contract: 4 spaces for Python placeholder bodies.
        self.assertIn("def foo():\n    pass", out or "")
        self.assertIn("class Bar:\n    pass", out or "")

        # Legacy description ordering contract for extra descriptions.
        i_desc4 = (out or "").find("# desc4")
        i_desc3 = (out or "").find("# desc3")
        i_desc1 = (out or "").find("# desc1")
        i_desc2 = (out or "").find("# desc2")
        self.assertTrue(0 <= i_desc4 < i_desc3 < i_desc1 < i_desc2)