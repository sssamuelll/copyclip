import unittest
import sys
import os
from unittest.mock import patch

# Add the 'src' directory to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from copyclip.minimizer import minimize_content

class TestContextualMinimization(unittest.TestCase):
    @patch("copyclip.minimizer._run_coro_sync")
    def test_python_functions_have_comments(self, mock_run_coro):
        # Simulate the AI returning descriptions
        mock_run_coro.return_value = ["returns x plus one", "a class named Bar", "a method named baz"]
        code = '''
def foo(x):
    return x + 1

class Bar:
    def baz(self):
        pass
'''
        minimized = minimize_content(code, "py", "contextual")
        lines = minimized.splitlines()
        
        comment_count = sum(1 for line in lines if line.strip().startswith("#"))
        self.assertGreaterEqual(comment_count, 2)
        
        for i, line in enumerate(lines):
            if line.strip().startswith("def ") or line.strip().startswith("class "):
                self.assertTrue(i > 0)
                comment_line = lines[i-1].strip()
                self.assertTrue(comment_line.startswith("# "))

    @patch("copyclip.minimizer._run_coro_sync")
    def test_javascript_functions_have_comments(self, mock_run_coro):
        # Simulate the AI returning descriptions
        mock_run_coro.return_value = ["returns x plus one", "a class named Bar", "a method named baz"]
        code = '''
function foo(x) {
    return x + 1;
}

class Bar {
    baz() {}
}
'''
        minimized = minimize_content(code, "js", "contextual")
        lines = minimized.splitlines()
        
        comment_count = sum(1 for line in lines if line.strip().startswith("//"))
        self.assertGreaterEqual(comment_count, 2)
        
        for i, line in enumerate(lines):
            if line.strip().startswith("function ") or line.strip().startswith("class "):
                self.assertTrue(i > 0)
                comment_line = lines[i-1].strip()
                self.assertTrue(comment_line.startswith("// "))


if __name__ == "__main__":
    unittest.main()