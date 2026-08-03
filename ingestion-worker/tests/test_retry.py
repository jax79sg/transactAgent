from unittest.mock import patch

import pytest

from ingestion_worker.clients.retry import TransientError, retry_with_backoff


class TestRetryWithBackoff:
    def test_succeeds_on_first_attempt_without_sleeping(self):
        calls = []

        @retry_with_backoff(max_attempts=3, base_seconds=0.01)
        def flaky():
            calls.append(1)
            return "ok"

        with patch("ingestion_worker.clients.retry.time.sleep") as mock_sleep:
            result = flaky()

        assert result == "ok"
        assert len(calls) == 1
        mock_sleep.assert_not_called()

    def test_succeeds_after_transient_failures(self):
        calls = []

        @retry_with_backoff(max_attempts=3, base_seconds=0.01)
        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise TransientError("temporary")
            return "ok"

        with patch("ingestion_worker.clients.retry.time.sleep") as mock_sleep:
            result = flaky()

        assert result == "ok"
        assert len(calls) == 3
        assert mock_sleep.call_count == 2

    def test_exhausts_attempts_and_raises(self):
        calls = []

        @retry_with_backoff(max_attempts=3, base_seconds=0.01)
        def always_fails():
            calls.append(1)
            raise TransientError("still failing")

        with patch("ingestion_worker.clients.retry.time.sleep"):
            with pytest.raises(TransientError):
                always_fails()

        assert len(calls) == 3

    def test_non_transient_error_is_not_retried(self):
        calls = []

        @retry_with_backoff(max_attempts=3, base_seconds=0.01)
        def raises_value_error():
            calls.append(1)
            raise ValueError("not transient")

        with patch("ingestion_worker.clients.retry.time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                raises_value_error()

        assert len(calls) == 1
        mock_sleep.assert_not_called()

    def test_backoff_is_exponential(self):
        @retry_with_backoff(max_attempts=3, base_seconds=2.0)
        def always_fails():
            raise TransientError("fail")

        with patch("ingestion_worker.clients.retry.time.sleep") as mock_sleep:
            with pytest.raises(TransientError):
                always_fails()

        mock_sleep.assert_any_call(2.0)  # 2 * 2^0
        mock_sleep.assert_any_call(4.0)  # 2 * 2^1
