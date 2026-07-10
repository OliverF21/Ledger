"""
Shared error handling for API routes.

Route handlers should log the real exception server-side and return a
generic message to the client, rather than echoing str(e) -- which can
leak internal details (stack traces, Plaid API error bodies, DB errors).
"""

import logging

from fastapi import HTTPException

logger = logging.getLogger("ledger")


def log_and_raise(e: Exception, status_code: int = 500, message: str = "An internal error occurred") -> None:
    """Log the full exception server-side, then raise a generic HTTPException for the client."""
    logger.exception(message)
    raise HTTPException(status_code=status_code, detail=message) from e
