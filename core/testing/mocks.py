"""
Mock implementations for external services.

Provides mock objects for Kafka, Redis, HTTP clients, and other external
services to enable isolated unit testing.

Usage:
    # Kafka mock
    kafka = MockKafka()
    await kafka.send("events", {"type": "user.created"})
    kafka.assert_sent("events", count=1)
    
    # Redis mock
    redis = MockRedis()
    await redis.set("key", "value")
    assert await redis.get("key") == "value"
    
    # HTTP mock
    http = MockHTTP()
    http.when("GET", "https://api.example.com/users/1").respond(
        status=200,
        json={"id": 1, "name": "John"}
    )
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable
from datetime import datetime, timedelta

logger = logging.getLogger("core.testing")


# =============================================================================
# Kafka Mocks
# =============================================================================

@dataclass
class MockMessage:
    """
    Mock Kafka message.
    
    Attributes:
        topic: Topic the message was sent to
        value: Message payload
        key: Optional message key
        headers: Optional message headers
        timestamp: When the message was sent
    """
    topic: str
    value: dict[str, Any]
    key: str | None = None
    headers: dict[str, str] | None = None
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MockKafka:
    """
    Mock Kafka producer/consumer.
    
    Records all sent messages for assertions in tests.
    
    Example:
        kafka = MockKafka()
        
        # Send messages
        await kafka.send("events", {"type": "user.created", "user_id": 1})
        await kafka.send("events", {"type": "user.updated", "user_id": 1})
        await kafka.send("notifications", {"message": "Hello"})
        
        # Assert
        kafka.assert_sent("events", count=2)
        kafka.assert_sent("notifications", count=1)
        
        # Check specific message
        assert kafka.messages[0].value["type"] == "user.created"
        
        # Get messages by topic
        event_messages = kafka.get_messages("events")
        assert len(event_messages) == 2
    """
    
    messages: list[MockMessage] = field(default_factory=list)
    _consumers: dict[str, list[Callable]] = field(default_factory=dict)
    
    async def send(
        self,
        topic: str,
        value: dict[str, Any],
        key: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """
        Record a sent message.
        
        Args:
            topic: Topic to send to
            value: Message payload
            key: Optional message key
            headers: Optional headers
        """
        message = MockMessage(
            topic=topic,
            value=value,
            key=key,
            headers=headers,
        )
        self.messages.append(message)
        logger.debug(f"MockKafka: sent to {topic}: {value}")
        
        # Notify consumers
        for consumer in self._consumers.get(topic, []):
            await consumer(message)
    
    async def send_batch(
        self,
        topic: str,
        messages: list[dict[str, Any]],
    ) -> None:
        """Send multiple messages to a topic."""
        for msg in messages:
            await self.send(topic, msg)
    
    def subscribe(self, topic: str, callback: Callable) -> None:
        """Subscribe to a topic."""
        if topic not in self._consumers:
            self._consumers[topic] = []
        self._consumers[topic].append(callback)
    
    def get_messages(self, topic: str) -> list[MockMessage]:
        """Get all messages sent to a topic."""
        return [m for m in self.messages if m.topic == topic]
    
    def assert_sent(self, topic: str, count: int = 1) -> None:
        """
        Assert that messages were sent to a topic.
        
        Args:
            topic: Topic to check
            count: Expected number of messages
            
        Raises:
            AssertionError: If count doesn't match
        """
        sent = self.get_messages(topic)
        assert len(sent) == count, (
            f"Expected {count} messages to '{topic}', got {len(sent)}. "
            f"Messages: {[m.value for m in sent]}"
        )
    
    def assert_sent_with(
        self,
        topic: str,
        **expected_fields,
    ) -> None:
        """
        Assert that a message with specific fields was sent.
        
        Args:
            topic: Topic to check
            **expected_fields: Fields that must be in at least one message
            
        Raises:
            AssertionError: If no matching message found
        """
        sent = self.get_messages(topic)
        for msg in sent:
            if all(msg.value.get(k) == v for k, v in expected_fields.items()):
                return
        
        raise AssertionError(
            f"No message to '{topic}' with fields {expected_fields}. "
            f"Messages: {[m.value for m in sent]}"
        )
    
    def assert_not_sent(self, topic: str) -> None:
        """Assert that no messages were sent to a topic."""
        sent = self.get_messages(topic)
        assert len(sent) == 0, (
            f"Expected no messages to '{topic}', got {len(sent)}. "
            f"Messages: {[m.value for m in sent]}"
        )
    
    def clear(self) -> None:
        """Clear all recorded messages."""
        self.messages.clear()
        logger.debug("MockKafka: cleared messages")


# =============================================================================
# Redis Mocks
# =============================================================================

@dataclass
class MockRedis:
    """
    Mock Redis client.
    
    Simulates Redis operations in memory for testing.
    
    Example:
        redis = MockRedis()
        
        # Basic operations
        await redis.set("user:1:name", "John")
        name = await redis.get("user:1:name")
        assert name == "John"
        
        # With expiration
        await redis.set("session:abc", "data", ex=3600)
        
        # Delete
        await redis.delete("user:1:name")
        assert await redis.get("user:1:name") is None
        
        # Hash operations
        await redis.hset("user:1", "name", "John")
        await redis.hset("user:1", "email", "john@example.com")
        user = await redis.hgetall("user:1")
        assert user == {"name": "John", "email": "john@example.com"}
    """
    
    data: dict[str, Any] = field(default_factory=dict)
    _expiry: dict[str, datetime] = field(default_factory=dict)
    _hash_data: dict[str, dict[str, Any]] = field(default_factory=dict)
    _list_data: dict[str, list[Any]] = field(default_factory=dict)
    _set_data: dict[str, set[Any]] = field(default_factory=dict)
    
    async def get(self, key: str) -> Any | None:
        """Get value by key."""
        self._check_expiry(key)
        return self.data.get(key)
    
    async def set(
        self,
        key: str,
        value: Any,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set value.
        
        Args:
            key: Key to set
            value: Value to store
            ex: Expiration in seconds
            px: Expiration in milliseconds
            nx: Only set if key doesn't exist
            xx: Only set if key exists
        """
        if nx and key in self.data:
            return False
        if xx and key not in self.data:
            return False
        
        self.data[key] = value
        
        if ex:
            self._expiry[key] = datetime.now() + timedelta(seconds=ex)
        elif px:
            self._expiry[key] = datetime.now() + timedelta(milliseconds=px)
        
        return True
    
    async def setex(self, key: str, seconds: int, value: Any) -> bool:
        """Set value with expiration in seconds."""
        return await self.set(key, value, ex=seconds)
    
    async def delete(self, *keys: str) -> int:
        """Delete keys. Returns number of deleted keys."""
        count = 0
        for key in keys:
            if key in self.data:
                del self.data[key]
                count += 1
            self._expiry.pop(key, None)
        return count
    
    async def exists(self, *keys: str) -> int:
        """Check if keys exist. Returns count of existing keys."""
        count = 0
        for key in keys:
            self._check_expiry(key)
            if key in self.data:
                count += 1
        return count
    
    async def incr(self, key: str) -> int:
        """Increment value by 1."""
        self._check_expiry(key)
        value = int(self.data.get(key, 0)) + 1
        self.data[key] = value
        return value
    
    async def decr(self, key: str) -> int:
        """Decrement value by 1."""
        self._check_expiry(key)
        value = int(self.data.get(key, 0)) - 1
        self.data[key] = value
        return value
    
    async def expire(self, key: str, seconds: int) -> bool:
        """Set expiration on key."""
        if key in self.data:
            self._expiry[key] = datetime.now() + timedelta(seconds=seconds)
            return True
        return False
    
    async def ttl(self, key: str) -> int:
        """Get TTL in seconds. Returns -1 if no expiry, -2 if key doesn't exist."""
        if key not in self.data:
            return -2
        if key not in self._expiry:
            return -1
        remaining = (self._expiry[key] - datetime.now()).total_seconds()
        return max(0, int(remaining))
    
    # Hash operations
    async def hset(self, name: str, key: str, value: Any) -> int:
        """Set hash field."""
        if name not in self._hash_data:
            self._hash_data[name] = {}
        is_new = key not in self._hash_data[name]
        self._hash_data[name][key] = value
        return 1 if is_new else 0
    
    async def hget(self, name: str, key: str) -> Any | None:
        """Get hash field."""
        return self._hash_data.get(name, {}).get(key)
    
    async def hgetall(self, name: str) -> dict[str, Any]:
        """Get all hash fields."""
        return self._hash_data.get(name, {}).copy()
    
    async def hdel(self, name: str, *keys: str) -> int:
        """Delete hash fields."""
        if name not in self._hash_data:
            return 0
        count = 0
        for key in keys:
            if key in self._hash_data[name]:
                del self._hash_data[name][key]
                count += 1
        return count
    
    # List operations
    async def lpush(self, name: str, *values: Any) -> int:
        """Push values to list head."""
        if name not in self._list_data:
            self._list_data[name] = []
        for value in values:
            self._list_data[name].insert(0, value)
        return len(self._list_data[name])
    
    async def rpush(self, name: str, *values: Any) -> int:
        """Push values to list tail."""
        if name not in self._list_data:
            self._list_data[name] = []
        self._list_data[name].extend(values)
        return len(self._list_data[name])
    
    async def lrange(self, name: str, start: int, end: int) -> list[Any]:
        """Get list range."""
        lst = self._list_data.get(name, [])
        if end == -1:
            return lst[start:]
        return lst[start:end + 1]
    
    async def llen(self, name: str) -> int:
        """Get list length."""
        return len(self._list_data.get(name, []))
    
    # Set operations
    async def sadd(self, name: str, *values: Any) -> int:
        """Add values to set."""
        if name not in self._set_data:
            self._set_data[name] = set()
        before = len(self._set_data[name])
        self._set_data[name].update(values)
        return len(self._set_data[name]) - before
    
    async def smembers(self, name: str) -> set[Any]:
        """Get all set members."""
        return self._set_data.get(name, set()).copy()
    
    async def sismember(self, name: str, value: Any) -> bool:
        """Check if value is in set."""
        return value in self._set_data.get(name, set())
    
    def _check_expiry(self, key: str) -> None:
        """Check and remove expired key."""
        if key in self._expiry and datetime.now() > self._expiry[key]:
            self.data.pop(key, None)
            del self._expiry[key]
    
    def clear(self) -> None:
        """Clear all data."""
        self.data.clear()
        self._expiry.clear()
        self._hash_data.clear()
        self._list_data.clear()
        self._set_data.clear()
        logger.debug("MockRedis: cleared all data")


# =============================================================================
# HTTP Mocks
# =============================================================================

class MockHTTPResponse:
    """
    Builder for mock HTTP responses.
    
    Example:
        http.when("GET", "/users/1").respond(
            status=200,
            json={"id": 1, "name": "John"}
        )
    """
    
    def __init__(self, mock: "MockHTTP", method: str, url: str) -> None:
        self.mock = mock
        self.method = method
        self.url = url
        self.key = f"{method}:{url}"
    
    def respond(
        self,
        status: int = 200,
        json: dict[str, Any] | None = None,
        text: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> "MockHTTP":
        """
        Set the response for this mock.
        
        Args:
            status: HTTP status code
            json: JSON response body
            text: Text response body
            headers: Response headers
            
        Returns:
            The MockHTTP instance for chaining
        """
        self.mock._responses[self.key] = {
            "status": status,
            "json": json,
            "text": text,
            "headers": headers or {},
        }
        return self.mock
    
    def respond_with_error(
        self,
        status: int = 500,
        message: str = "Internal Server Error",
    ) -> "MockHTTP":
        """Set an error response."""
        return self.respond(
            status=status,
            json={"error": message, "status": status},
        )
    
    def respond_with_timeout(self) -> "MockHTTP":
        """Set a timeout response."""
        self.mock._responses[self.key] = {"timeout": True}
        return self.mock


@dataclass
class MockHTTPRequest:
    """Recorded HTTP request."""
    method: str
    url: str
    json: dict[str, Any] | None = None
    data: Any = None
    headers: dict[str, str] | None = None
    timestamp: datetime = field(default_factory=datetime.now)


class MockHTTP:
    """
    Mock HTTP client for external API calls.
    
    Example:
        http = MockHTTP()
        
        # Configure mock responses
        http.when("GET", "https://api.example.com/users/1").respond(
            status=200,
            json={"id": 1, "name": "John"}
        )
        
        http.when("POST", "https://api.example.com/users").respond(
            status=201,
            json={"id": 2, "name": "Jane"}
        )
        
        # Use in tests
        response = await http.request("GET", "https://api.example.com/users/1")
        assert response["status"] == 200
        assert response["json"]["name"] == "John"
        
        # Assert requests were made
        http.assert_called("GET", "https://api.example.com/users/1")
    """
    
    def __init__(self) -> None:
        self._responses: dict[str, dict[str, Any]] = {}
        self._requests: list[MockHTTPRequest] = []
    
    def when(self, method: str, url: str) -> MockHTTPResponse:
        """
        Configure a mock response for a request.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: URL to mock
            
        Returns:
            MockHTTPResponse builder
        """
        return MockHTTPResponse(self, method.upper(), url)
    
    async def request(
        self,
        method: str,
        url: str,
        json: dict[str, Any] | None = None,
        data: Any = None,
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Execute a mocked HTTP request.
        
        Args:
            method: HTTP method
            url: URL to request
            json: JSON body
            data: Form data
            headers: Request headers
            
        Returns:
            Mock response dict with status, json, text, headers
        """
        method = method.upper()
        
        # Record request
        self._requests.append(MockHTTPRequest(
            method=method,
            url=url,
            json=json,
            data=data,
            headers=headers,
        ))
        
        # Find mock response
        key = f"{method}:{url}"
        response = self._responses.get(key)
        
        if response is None:
            logger.warning(f"MockHTTP: No mock for {method} {url}")
            return {"status": 404, "json": {"error": "Not found"}}
        
        if response.get("timeout"):
            raise TimeoutError(f"Mock timeout for {method} {url}")
        
        return response
    
    # Convenience methods
    async def get(self, url: str, **kwargs) -> dict[str, Any]:
        """GET request."""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> dict[str, Any]:
        """POST request."""
        return await self.request("POST", url, **kwargs)
    
    async def put(self, url: str, **kwargs) -> dict[str, Any]:
        """PUT request."""
        return await self.request("PUT", url, **kwargs)
    
    async def delete(self, url: str, **kwargs) -> dict[str, Any]:
        """DELETE request."""
        return await self.request("DELETE", url, **kwargs)
    
    def get_requests(
        self,
        method: str | None = None,
        url: str | None = None,
    ) -> list[MockHTTPRequest]:
        """Get recorded requests, optionally filtered."""
        requests = self._requests
        if method:
            requests = [r for r in requests if r.method == method.upper()]
        if url:
            requests = [r for r in requests if r.url == url]
        return requests
    
    def assert_called(
        self,
        method: str,
        url: str,
        times: int = 1,
    ) -> None:
        """
        Assert a request was made.
        
        Args:
            method: Expected HTTP method
            url: Expected URL
            times: Expected number of calls
            
        Raises:
            AssertionError: If assertion fails
        """
        requests = self.get_requests(method, url)
        assert len(requests) == times, (
            f"Expected {times} calls to {method} {url}, got {len(requests)}. "
            f"All requests: {[(r.method, r.url) for r in self._requests]}"
        )
    
    def assert_called_with_json(
        self,
        method: str,
        url: str,
        json: dict[str, Any],
    ) -> None:
        """Assert a request was made with specific JSON body."""
        requests = self.get_requests(method, url)
        for req in requests:
            if req.json == json:
                return
        raise AssertionError(
            f"No {method} {url} call with json={json}. "
            f"Requests: {[(r.method, r.url, r.json) for r in requests]}"
        )
    
    def assert_not_called(self, method: str, url: str) -> None:
        """Assert a request was NOT made."""
        requests = self.get_requests(method, url)
        assert len(requests) == 0, (
            f"Expected no calls to {method} {url}, got {len(requests)}"
        )
    
    def clear(self) -> None:
        """Clear all mocks and recorded requests."""
        self._responses.clear()
        self._requests.clear()
        logger.debug("MockHTTP: cleared mocks and requests")
