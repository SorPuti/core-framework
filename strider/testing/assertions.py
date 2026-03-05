"""
Custom assertions for API testing.

Provides helper functions for common test assertions.

Usage:
    response = await client.get("/users/1")
    
    assert_status(response, 200)
    assert_json_contains(response, {"email": "test@example.com"})
    assert_error_code(response, "not_found")
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from httpx import Response


def assert_status(response: "Response", expected: int, msg: str = "") -> None:
    """
    Assert response has expected status code.
    
    Args:
        response: HTTP response
        expected: Expected status code
        msg: Optional message
        
    Raises:
        AssertionError: If status doesn't match
        
    Example:
        assert_status(response, 200)
        assert_status(response, 201, "User should be created")
    """
    actual = response.status_code
    if actual != expected:
        body = _safe_json(response)
        error_msg = f"Expected status {expected}, got {actual}. Response: {body}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_status_ok(response: "Response", msg: str = "") -> None:
    """Assert response is 2xx."""
    if not 200 <= response.status_code < 300:
        body = _safe_json(response)
        error_msg = f"Expected 2xx status, got {response.status_code}. Response: {body}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_status_error(response: "Response", msg: str = "") -> None:
    """Assert response is 4xx or 5xx."""
    if response.status_code < 400:
        body = _safe_json(response)
        error_msg = f"Expected error status, got {response.status_code}. Response: {body}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_json_contains(
    response: "Response",
    expected: dict[str, Any],
    msg: str = "",
) -> None:
    """
    Assert response JSON contains expected fields.
    
    Args:
        response: HTTP response
        expected: Dict of expected fields and values
        msg: Optional message
        
    Raises:
        AssertionError: If fields don't match
        
    Example:
        assert_json_contains(response, {"email": "test@example.com"})
        assert_json_contains(response, {"status": "active", "role": "admin"})
    """
    actual = _safe_json(response)
    
    if not isinstance(actual, dict):
        raise AssertionError(
            f"Expected JSON object, got {type(actual).__name__}: {actual}"
        )
    
    for key, value in expected.items():
        if key not in actual:
            error_msg = f"Missing key '{key}' in response. Response: {actual}"
            if msg:
                error_msg = f"{msg}. {error_msg}"
            raise AssertionError(error_msg)
        
        if actual[key] != value:
            error_msg = (
                f"Value mismatch for '{key}': expected {value!r}, "
                f"got {actual[key]!r}. Response: {actual}"
            )
            if msg:
                error_msg = f"{msg}. {error_msg}"
            raise AssertionError(error_msg)


def assert_json_equals(
    response: "Response",
    expected: dict[str, Any] | list[Any],
    msg: str = "",
) -> None:
    """
    Assert response JSON equals expected exactly.
    
    Args:
        response: HTTP response
        expected: Expected JSON value
        msg: Optional message
    """
    actual = _safe_json(response)
    
    if actual != expected:
        error_msg = f"JSON mismatch. Expected: {expected}. Got: {actual}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_json_list(
    response: "Response",
    min_length: int = 0,
    max_length: int | None = None,
    msg: str = "",
) -> list[Any]:
    """
    Assert response is a JSON list and return it.
    
    Args:
        response: HTTP response
        min_length: Minimum list length
        max_length: Maximum list length (None = no limit)
        msg: Optional message
        
    Returns:
        The response JSON list
    """
    actual = _safe_json(response)
    
    if not isinstance(actual, list):
        raise AssertionError(
            f"Expected JSON list, got {type(actual).__name__}: {actual}"
        )
    
    if len(actual) < min_length:
        error_msg = f"List too short: expected at least {min_length}, got {len(actual)}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)
    
    if max_length is not None and len(actual) > max_length:
        error_msg = f"List too long: expected at most {max_length}, got {len(actual)}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)
    
    return actual


def assert_error_code(
    response: "Response",
    code: str,
    msg: str = "",
) -> None:
    """
    Assert response contains specific error code.
    
    Looks for code in: detail.code, code, error.code
    
    Args:
        response: HTTP response
        code: Expected error code
        msg: Optional message
        
    Example:
        assert_error_code(response, "not_found")
        assert_error_code(response, "validation_error")
    """
    actual = _safe_json(response)
    
    if not isinstance(actual, dict):
        raise AssertionError(f"Expected JSON object, got: {actual}")
    
    # Try different locations for error code
    actual_code = (
        actual.get("code") or
        (actual.get("detail", {}).get("code") if isinstance(actual.get("detail"), dict) else None) or
        actual.get("error", {}).get("code") if isinstance(actual.get("error"), dict) else None
    )
    
    if actual_code != code:
        error_msg = f"Expected error code '{code}', got '{actual_code}'. Response: {actual}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_validation_error(
    response: "Response",
    field: str | None = None,
    msg: str = "",
) -> None:
    """
    Assert response is a validation error.
    
    Args:
        response: HTTP response
        field: Optional field that should have error
        msg: Optional message
        
    Example:
        assert_validation_error(response)
        assert_validation_error(response, field="email")
    """
    if response.status_code != 422:
        raise AssertionError(
            f"Expected 422 validation error, got {response.status_code}. "
            f"Response: {_safe_json(response)}"
        )
    
    if field is not None:
        actual = _safe_json(response)
        
        # Look for field in various error formats
        found = False
        
        # FastAPI format: detail[].loc
        detail = actual.get("detail", [])
        if isinstance(detail, list):
            for error in detail:
                loc = error.get("loc", [])
                if field in loc or (len(loc) > 1 and loc[-1] == field):
                    found = True
                    break
        
        # Our format: errors[].field
        errors = actual.get("errors", [])
        if isinstance(errors, list):
            for error in errors:
                if error.get("field") == field:
                    found = True
                    break
        
        if not found:
            error_msg = f"Expected validation error for field '{field}'. Response: {actual}"
            if msg:
                error_msg = f"{msg}. {error_msg}"
            raise AssertionError(error_msg)


def assert_header(
    response: "Response",
    header: str,
    expected: str | None = None,
    msg: str = "",
) -> str | None:
    """
    Assert response has header, optionally with specific value.
    
    Args:
        response: HTTP response
        header: Header name
        expected: Expected value (None = just check exists)
        msg: Optional message
        
    Returns:
        Header value
    """
    actual = response.headers.get(header)
    
    if actual is None:
        error_msg = f"Missing header '{header}'. Headers: {dict(response.headers)}"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)
    
    if expected is not None and actual != expected:
        error_msg = f"Header '{header}' mismatch: expected '{expected}', got '{actual}'"
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)
    
    return actual


def assert_no_error(response: "Response", msg: str = "") -> None:
    """
    Assert response is not an error (2xx status).
    
    Provides detailed error message on failure.
    """
    if response.status_code >= 400:
        body = _safe_json(response)
        error_msg = (
            f"Request failed with {response.status_code}. "
            f"Response: {body}"
        )
        if msg:
            error_msg = f"{msg}. {error_msg}"
        raise AssertionError(error_msg)


def assert_created(response: "Response", msg: str = "") -> dict[str, Any]:
    """
    Assert response is 201 Created and return JSON body.
    
    Returns:
        Response JSON
    """
    assert_status(response, 201, msg)
    return _safe_json(response)


def assert_not_found(response: "Response", msg: str = "") -> None:
    """Assert response is 404 Not Found."""
    assert_status(response, 404, msg)


def assert_unauthorized(response: "Response", msg: str = "") -> None:
    """Assert response is 401 Unauthorized."""
    assert_status(response, 401, msg)


def assert_forbidden(response: "Response", msg: str = "") -> None:
    """Assert response is 403 Forbidden."""
    assert_status(response, 403, msg)


def _safe_json(response: "Response") -> Any:
    """Safely get JSON from response."""
    try:
        return response.json()
    except Exception:
        return response.text
