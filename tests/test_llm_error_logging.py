# tests/test_llm_error_logging.py
import unittest
import logging
import json
import asyncio
from unittest.mock import patch, MagicMock

# Add src to path
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from copyclip.minimizer import minimize_content

# Mock aiohttp exceptions
class MockAiohttpResponseError(Exception):
    def __init__(self, status, headers=None):
        self.status = status
        self.headers = headers if headers is not None else {}

class TestLLMErrorLogging(unittest.TestCase):

    @patch('copyclip.minimizer._run_coro_sync')
    @patch('logging.getLogger')
    def test_logs_error_on_final_failure(self, mock_get_logger, mock_run_coro):
        # Arrange
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        error = MockAiohttpResponseError(401) # The constructor now handles headers
        settings = {'provider': 'openai'}
        mock_run_coro.return_value = (None, error, settings)

        code = "def hello(): pass"
        file_path = "src/app.py"

        # Act
        result = minimize_content(code, "py", "contextual", file_path=file_path)

        # Assert
        self.assertIn("def hello():", result) # Check for fallback

        mock_get_logger.assert_called_with('copyclip.minimizer')
        mock_logger.error.assert_called_once()
        
        log_call_arg = mock_logger.error.call_args[0][0]
        log_data = json.loads(log_call_arg)

        self.assertEqual(log_data['event'], 'minimization_failed')
        self.assertEqual(log_data['cause'], 'unauthorized')
        self.assertEqual(log_data['provider'], 'openai')
        self.assertEqual(log_data['file'], file_path)
        self.assertEqual(log_data['status_code'], 401)

if __name__ == '__main__':
    unittest.main()