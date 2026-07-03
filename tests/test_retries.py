"""Tests for retry logic."""

from unittest.mock import Mock, patch

import pytest
import requests

from trans_epub.engines.base import call_with_retry


def _make_success_resp(text="Xin chào"):
    resp = Mock()
    resp.status_code = 200
    resp.json.return_value = {
        "choices": [{"message": {"content": f'{{"translations": ["{text}"]}}'}}]
    }
    resp.raise_for_status.return_value = None
    return resp


def _parse_fn(resp):
    """Minimal parse_fn: extract translations list from response."""
    import json

    content = resp.json()["choices"][0]["message"]["content"]
    return json.loads(content)["translations"]


def test_call_with_retry_success_first_attempt():
    """Test that call_with_retry works on first attempt."""
    mock_request_fn = Mock(return_value=_make_success_resp())

    result = call_with_retry("TestEngine", mock_request_fn, _parse_fn, max_attempts=3)

    assert result == ["Xin chào"]
    mock_request_fn.assert_called_once()


def test_call_with_retry_on_network_error():
    """Test that call_with_retry retries on network errors."""
    success = _make_success_resp()
    mock_request_fn = Mock(
        side_effect=[
            requests.exceptions.ConnectionError("Network error"),
            requests.exceptions.Timeout("Timeout"),
            success,
        ]
    )

    with patch("time.sleep"):
        result = call_with_retry(
            "TestEngine", mock_request_fn, _parse_fn, max_attempts=5
        )

    assert result == ["Xin chào"]
    assert mock_request_fn.call_count == 3


def test_call_with_retry_on_429():
    """Test that call_with_retry handles 429 rate limiting."""
    rate_limited_resp = Mock()
    rate_limited_resp.status_code = 429
    rate_limited_resp.headers = {"Retry-After": "1"}

    success_resp = _make_success_resp()

    mock_request_fn = Mock(side_effect=[rate_limited_resp, success_resp])

    with patch("time.sleep") as mock_sleep:
        result = call_with_retry(
            "TestEngine", mock_request_fn, _parse_fn, max_attempts=3
        )

    assert result == ["Xin chào"]
    assert mock_request_fn.call_count == 2
    mock_sleep.assert_called_once_with(1)


def test_call_with_retry_on_json_error():
    """Test that call_with_retry retries on JSON parse errors."""
    success = _make_success_resp()
    mock_request_fn = Mock(return_value=success)

    call_count = 0

    def flaky_parse(resp):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("JSON parse error")
        return _parse_fn(resp)

    result = call_with_retry("TestEngine", mock_request_fn, flaky_parse, max_attempts=3)

    assert result == ["Xin chào"]
    assert call_count == 2


def test_call_with_retry_exhausts_attempts():
    """Test that call_with_retry raises after max attempts."""
    mock_request_fn = Mock(
        side_effect=requests.exceptions.ConnectionError("Network error")
    )

    with patch("time.sleep"):
        with pytest.raises(requests.exceptions.ConnectionError):
            call_with_retry("TestEngine", mock_request_fn, _parse_fn, max_attempts=2)

    assert mock_request_fn.call_count == 2


def test_call_with_retry_exhausts_attempts_with_429():
    """Test that call_with_retry succeeds after a 429 then success."""
    rate_limited_resp = Mock()
    rate_limited_resp.status_code = 429
    rate_limited_resp.headers = {"Retry-After": "1"}

    success_resp = _make_success_resp()
    mock_request_fn = Mock(side_effect=[rate_limited_resp, success_resp])

    with patch("time.sleep"):
        result = call_with_retry(
            "TestEngine", mock_request_fn, _parse_fn, max_attempts=2
        )

    assert result == ["Xin chào"]
    assert mock_request_fn.call_count == 2


def test_call_with_retry_does_not_retry_4xx():
    """400-level errors (except 429) should raise immediately, no retry."""
    bad_resp = Mock()
    bad_resp.status_code = 400
    bad_resp.raise_for_status.side_effect = requests.exceptions.HTTPError("Bad request")

    mock_request_fn = Mock(return_value=bad_resp)

    with pytest.raises(requests.exceptions.HTTPError):
        call_with_retry("TestEngine", mock_request_fn, _parse_fn, max_attempts=3)

    assert mock_request_fn.call_count == 1  # only one attempt
