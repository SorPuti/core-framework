"""
Helper functions for authentication.

Provides consistent user access across the framework, supporting both:
- request.user (Starlette AuthenticationMiddleware pattern - preferred)
- request.state.user (legacy pattern - backward compatibility)
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.requests import Request

logger = logging.getLogger("core.auth")


def get_request_user(request: "Request") -> Any | None:
    """
    Get authenticated user from request.
    
    Checks both patterns for compatibility:
    1. request.user (Starlette AuthenticationMiddleware - preferred)
    2. request.state.user (legacy pattern)
    
    Args:
        request: The Starlette/FastAPI request object
        
    Returns:
        The authenticated user model or None if not authenticated
        
    Example:
        from core.auth.helpers import get_request_user
        
        async def my_view(request: Request):
            user = get_request_user(request)
            if user is None:
                raise HTTPException(401, "Not authenticated")
    """
    # Pattern 1: request.user (Starlette AuthenticationMiddleware)
    user = getattr(request, "user", None)
    if user is not None:
        # Check if it's an authenticated user (has is_authenticated = True)
        if getattr(user, "is_authenticated", False):
            # If it's our AuthenticatedUser wrapper, return the underlying model
            if hasattr(user, "_user"):
                return user._user
            return user
    
    # Pattern 2: request.state.user (legacy)
    user = getattr(request.state, "user", None) if hasattr(request, "state") else None
    
    return user


def is_authenticated(request: "Request") -> bool:
    """
    Check if request has an authenticated user.
    
    Args:
        request: The Starlette/FastAPI request object
        
    Returns:
        True if authenticated, False otherwise
    """
    # Pattern 1: request.user with is_authenticated
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return True
    
    # Pattern 2: request.state.user
    if hasattr(request, "state"):
        user = getattr(request.state, "user", None)
        if user is not None:
            return True
    
    return False


def set_request_user(request: "Request", user: Any | None) -> None:
    """
    Set the authenticated user on the request.
    
    Sets both patterns for maximum compatibility:
    - request.state.user (for dependencies and legacy code)
    
    Note: request.user is set by Starlette's AuthenticationMiddleware
    via scope["user"] and cannot be set directly.
    
    Args:
        request: The Starlette/FastAPI request object
        user: The user model or None
    """
    if hasattr(request, "state"):
        request.state.user = user


__all__ = [
    "get_request_user",
    "is_authenticated", 
    "set_request_user",
]
