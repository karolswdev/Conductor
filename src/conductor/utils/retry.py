"""
Retry logic with exponential backoff and jitter.
"""

import random
import asyncio
import logging
from typing import TypeVar, Callable, Any, Optional


logger = logging.getLogger(__name__)

T = TypeVar("T")


def calculate_jitter(delay: float, jitter: float = 0.2) -> float:
    """
    Add jitter to a delay value.

    Args:
        delay: Base delay in seconds
        jitter: Jitter percentage (0.0 to 1.0)

    Returns:
        Delay with jitter applied
    """
    jitter_amount = delay * random.uniform(-jitter, jitter)
    return max(0.0, delay + jitter_amount)


def exponential_backoff(
    attempt: int,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    max_delay: float = 300.0,
    jitter: float = 0.2,
) -> float:
    """
    Calculate delay for exponential backoff with jitter.

    Args:
        attempt: Attempt number (0-indexed)
        initial_delay: Initial delay in seconds
        backoff_factor: Exponential backoff factor
        max_delay: Maximum delay cap
        jitter: Jitter percentage (0.0 to 1.0)

    Returns:
        Delay in seconds with jitter applied
    """
    # Calculate base delay: initial_delay * (backoff_factor ^ attempt)
    delay = min(initial_delay * (backoff_factor**attempt), max_delay)

    # Add jitter
    jittered_delay = calculate_jitter(delay, jitter)

    return jittered_delay


async def retry_async(
    func: Callable[..., Any],
    max_attempts: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    max_delay: float = 300.0,
    jitter: float = 0.2,
    exceptions: tuple = (Exception,),
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Exponential backoff factor
        max_delay: Maximum delay cap
        jitter: Jitter percentage
        exceptions: Tuple of exceptions to catch

    Returns:
        Function result

    Raises:
        Last exception if all retries fail
    """
    last_exception: Optional[Exception] = None

    for attempt in range(max_attempts):
        try:
            return await func()

        except exceptions as e:
            last_exception = e
            logger.warning(f"Attempt {attempt + 1}/{max_attempts} failed: {e}")

            if attempt < max_attempts - 1:
                delay = exponential_backoff(
                    attempt=attempt,
                    initial_delay=initial_delay,
                    backoff_factor=backoff_factor,
                    max_delay=max_delay,
                    jitter=jitter,
                )

                logger.info(f"Retrying in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
            else:
                logger.error(f"All {max_attempts} attempts failed")

    if last_exception:
        raise last_exception

    raise RuntimeError("Retry logic error: no exception but no success")
