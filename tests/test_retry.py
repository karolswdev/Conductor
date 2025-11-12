"""
Tests for retry logic with exponential backoff and jitter.
"""

import pytest
from conductor.utils.retry import exponential_backoff, calculate_jitter


def test_exponential_backoff_first_attempt():
    """Test that first attempt uses initial delay."""
    delay = exponential_backoff(
        attempt=0,
        initial_delay=5.0,
        backoff_factor=2.0,
        max_delay=300.0,
        jitter=0.0,  # No jitter for predictable test
    )

    assert delay == 5.0


def test_exponential_backoff_second_attempt():
    """Test that second attempt doubles the delay."""
    delay = exponential_backoff(
        attempt=1,
        initial_delay=5.0,
        backoff_factor=2.0,
        max_delay=300.0,
        jitter=0.0,
    )

    assert delay == 10.0


def test_exponential_backoff_third_attempt():
    """Test that third attempt quadruples the delay."""
    delay = exponential_backoff(
        attempt=2,
        initial_delay=5.0,
        backoff_factor=2.0,
        max_delay=300.0,
        jitter=0.0,
    )

    assert delay == 20.0


def test_exponential_backoff_max_delay():
    """Test that delay never exceeds max_delay."""
    delay = exponential_backoff(
        attempt=10,  # Would be 5 * 2^10 = 5120 without cap
        initial_delay=5.0,
        backoff_factor=2.0,
        max_delay=300.0,
        jitter=0.0,
    )

    assert delay == 300.0


def test_exponential_backoff_with_jitter():
    """Test that jitter adds randomization."""
    delays = []

    for _ in range(10):
        delay = exponential_backoff(
            attempt=2,
            initial_delay=5.0,
            backoff_factor=2.0,
            max_delay=300.0,
            jitter=0.2,  # ±20%
        )
        delays.append(delay)

    # With jitter, delays should vary
    assert len(set(delays)) > 1

    # All delays should be within ±20% of 20.0
    for delay in delays:
        assert 16.0 <= delay <= 24.0


def test_calculate_jitter():
    """Test jitter calculation."""
    jitters = []

    for _ in range(100):
        jittered = calculate_jitter(delay=100.0, jitter=0.2)
        jitters.append(jittered)

    # All jittered values should be within ±20% of 100
    for value in jitters:
        assert 80.0 <= value <= 120.0

    # Should have variety
    assert len(set(jitters)) > 10


def test_jitter_never_negative():
    """Test that jitter never produces negative delays."""
    for _ in range(100):
        jittered = calculate_jitter(delay=1.0, jitter=0.5)
        assert jittered >= 0.0


@pytest.mark.asyncio
async def test_retry_async_success():
    """Test that retry_async succeeds on first try."""
    from conductor.utils.retry import retry_async

    call_count = 0

    async def succeeding_func():
        nonlocal call_count
        call_count += 1
        return "success"

    result = await retry_async(succeeding_func, max_attempts=3)

    assert result == "success"
    assert call_count == 1


@pytest.mark.asyncio
async def test_retry_async_eventual_success():
    """Test that retry_async retries until success."""
    from conductor.utils.retry import retry_async

    call_count = 0

    async def eventually_succeeding_func():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("Not yet")
        return "success"

    result = await retry_async(
        eventually_succeeding_func,
        max_attempts=5,
        initial_delay=0.01,  # Fast retry for test
    )

    assert result == "success"
    assert call_count == 3


@pytest.mark.asyncio
async def test_retry_async_all_failures():
    """Test that retry_async raises after all attempts fail."""
    from conductor.utils.retry import retry_async

    call_count = 0

    async def failing_func():
        nonlocal call_count
        call_count += 1
        raise ValueError("Always fails")

    with pytest.raises(ValueError, match="Always fails"):
        await retry_async(
            failing_func,
            max_attempts=3,
            initial_delay=0.01,
        )

    assert call_count == 3
