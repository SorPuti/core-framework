"""
Redis connection factory with support for standalone, cluster, and sentinel modes.
"""

from __future__ import annotations

from typing import Any
import logging

from core.config import get_settings


logger = logging.getLogger(__name__)


def parse_redis_hosts(url: str) -> list[tuple[str, int]]:
    """
    Parse Redis URL to extract hosts.
    
    Supports formats:
    - redis://host:port/db
    - redis://host1:port1,host2:port2,host3:port3
    - host:port,host:port (without scheme)
    
    Returns:
        List of (host, port) tuples
    """
    # Remove scheme if present
    if "://" in url:
        url = url.split("://", 1)[1]
    
    # Remove database suffix if present
    if "/" in url:
        url = url.split("/")[0]
    
    # Remove auth if present
    if "@" in url:
        url = url.split("@")[-1]
    
    hosts = []
    for part in url.split(","):
        part = part.strip()
        if ":" in part:
            host, port_str = part.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError:
                port = 6379
        else:
            host = part
            port = 6379
        hosts.append((host, port))
    
    return hosts


async def create_redis_client(
    url: str | None = None,
    mode: str | None = None,
    sentinel_master: str | None = None,
    max_connections: int | None = None,
    socket_timeout: float | None = None,
    **kwargs: Any,
):
    """
    Create a Redis client based on configuration.
    
    Automatically detects mode from settings or uses provided parameters.
    
    Args:
        url: Redis URL (uses settings.redis_url if None)
        mode: Connection mode: standalone, cluster, sentinel (uses settings.redis_mode if None)
        sentinel_master: Sentinel master name (uses settings.redis_sentinel_master if None)
        max_connections: Max pool connections (uses settings.redis_max_connections if None)
        socket_timeout: Socket timeout in seconds (uses settings.redis_socket_timeout if None)
        **kwargs: Additional redis options
    
    Returns:
        Redis client instance (type depends on mode)
    
    Example:
        # Standalone (default)
        client = await create_redis_client()
        
        # Cluster
        client = await create_redis_client(
            url="redis://node1:6379,node2:6379,node3:6379",
            mode="cluster"
        )
        
        # Sentinel
        client = await create_redis_client(
            url="redis://sentinel1:26379,sentinel2:26379",
            mode="sentinel",
            sentinel_master="mymaster"
        )
    """
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "redis is required for Redis support. "
            "Install with: pip install redis"
        )
    
    settings = get_settings()
    
    # Use settings as defaults
    url = url or settings.redis_url
    mode = mode or getattr(settings, "redis_mode", "standalone")
    sentinel_master = sentinel_master or getattr(settings, "redis_sentinel_master", "mymaster")
    max_connections = max_connections or settings.redis_max_connections
    socket_timeout = socket_timeout or getattr(settings, "redis_socket_timeout", 5.0)
    
    if mode == "cluster":
        return await _create_cluster_client(
            url=url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            **kwargs,
        )
    elif mode == "sentinel":
        return await _create_sentinel_client(
            url=url,
            master_name=sentinel_master,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            **kwargs,
        )
    else:
        # Standalone mode
        return aioredis.from_url(
            url,
            max_connections=max_connections,
            socket_timeout=socket_timeout,
            **kwargs,
        )


async def _create_cluster_client(
    url: str,
    max_connections: int,
    socket_timeout: float,
    **kwargs: Any,
):
    """Create Redis Cluster client."""
    try:
        from redis.asyncio.cluster import RedisCluster  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "Redis Cluster support requires redis>=4.1.0. "
            "Install with: pip install 'redis>=4.1.0'"
        )
    
    hosts = parse_redis_hosts(url)
    
    # Build startup nodes
    startup_nodes = [
        {"host": host, "port": port}
        for host, port in hosts
    ]
    
    logger.info(f"Connecting to Redis Cluster: {hosts}")
    
    # RedisCluster handles connection pooling internally
    client = RedisCluster(
        startup_nodes=startup_nodes,
        socket_timeout=socket_timeout,
        **kwargs,
    )
    
    # Test connection
    await client.ping()
    
    return client


async def _create_sentinel_client(
    url: str,
    master_name: str,
    max_connections: int,
    socket_timeout: float,
    **kwargs: Any,
):
    """Create Redis Sentinel client."""
    try:
        from redis.asyncio.sentinel import Sentinel  # type: ignore[import-untyped]
    except ImportError:
        raise ImportError(
            "Redis Sentinel support requires redis>=4.1.0. "
            "Install with: pip install 'redis>=4.1.0'"
        )
    
    hosts = parse_redis_hosts(url)
    
    logger.info(f"Connecting to Redis Sentinel: {hosts}, master={master_name}")
    
    sentinel = Sentinel(
        sentinels=hosts,
        socket_timeout=socket_timeout,
        **kwargs,
    )
    
    # Get master client
    client = sentinel.master_for(
        master_name,
        socket_timeout=socket_timeout,
    )
    
    # Test connection
    await client.ping()
    
    return client


def get_redis_info() -> dict[str, Any]:
    """
    Get Redis configuration info from settings.
    
    Returns:
        Dict with redis configuration details
    """
    settings = get_settings()
    
    return {
        "url": settings.redis_url,
        "mode": getattr(settings, "redis_mode", "standalone"),
        "sentinel_master": getattr(settings, "redis_sentinel_master", "mymaster"),
        "max_connections": settings.redis_max_connections,
        "socket_timeout": getattr(settings, "redis_socket_timeout", 5.0),
        "stream_max_len": getattr(settings, "redis_stream_max_len", 10000),
    }
