"""
Messaging configuration settings.

All messaging-related settings are defined here and can be
configured via environment variables or .env file.
"""

from __future__ import annotations

from typing import Literal
from pydantic import Field as PydanticField
from pydantic_settings import BaseSettings


class MessagingSettings(BaseSettings):
    """
    Messaging system configuration.
    
    All settings can be overridden via environment variables:
        MESSAGE_BROKER=kafka
        KAFKA_BOOTSTRAP_SERVERS=localhost:9092
        REDIS_URL=redis://localhost:6379/0
    """
    
    # ==========================================================================
    # BROKER SELECTION
    # ==========================================================================
    
    message_broker: Literal["kafka", "redis", "rabbitmq", "memory"] = PydanticField(
        default="kafka",
        description="Message broker to use: kafka, redis, rabbitmq, memory (for testing)",
    )
    
    # ==========================================================================
    # KAFKA SETTINGS
    # ==========================================================================
    
    kafka_bootstrap_servers: str = PydanticField(
        default="localhost:9092",
        description="Kafka bootstrap servers (comma-separated)",
    )
    kafka_security_protocol: Literal["PLAINTEXT", "SSL", "SASL_PLAINTEXT", "SASL_SSL"] = PydanticField(
        default="PLAINTEXT",
        description="Kafka security protocol",
    )
    kafka_sasl_mechanism: str | None = PydanticField(
        default=None,
        description="SASL mechanism (PLAIN, SCRAM-SHA-256, SCRAM-SHA-512)",
    )
    kafka_sasl_username: str | None = PydanticField(
        default=None,
        description="SASL username",
    )
    kafka_sasl_password: str | None = PydanticField(
        default=None,
        description="SASL password",
    )
    kafka_ssl_cafile: str | None = PydanticField(
        default=None,
        description="Path to CA certificate file",
    )
    kafka_ssl_certfile: str | None = PydanticField(
        default=None,
        description="Path to client certificate file",
    )
    kafka_ssl_keyfile: str | None = PydanticField(
        default=None,
        description="Path to client key file",
    )
    kafka_client_id: str = PydanticField(
        default="core-framework",
        description="Kafka client ID",
    )
    kafka_request_timeout_ms: int = PydanticField(
        default=30000,
        description="Kafka request timeout in milliseconds",
    )
    kafka_retry_backoff_ms: int = PydanticField(
        default=100,
        description="Kafka retry backoff in milliseconds",
    )
    kafka_max_batch_size: int = PydanticField(
        default=16384,
        description="Maximum batch size in bytes",
    )
    kafka_linger_ms: int = PydanticField(
        default=0,
        description="Time to wait for batch to fill (0 = send immediately)",
    )
    kafka_compression_type: Literal["none", "gzip", "snappy", "lz4", "zstd"] = PydanticField(
        default="none",
        description="Compression type for messages",
    )
    
    # Consumer settings
    kafka_auto_offset_reset: Literal["earliest", "latest", "none"] = PydanticField(
        default="earliest",
        description="Where to start consuming when no offset exists",
    )
    kafka_enable_auto_commit: bool = PydanticField(
        default=True,
        description="Enable auto-commit of offsets",
    )
    kafka_auto_commit_interval_ms: int = PydanticField(
        default=5000,
        description="Auto-commit interval in milliseconds",
    )
    kafka_max_poll_records: int = PydanticField(
        default=500,
        description="Maximum records to poll at once",
    )
    kafka_session_timeout_ms: int = PydanticField(
        default=10000,
        description="Consumer session timeout in milliseconds",
    )
    kafka_heartbeat_interval_ms: int = PydanticField(
        default=3000,
        description="Consumer heartbeat interval in milliseconds",
    )
    
    # ==========================================================================
    # REDIS SETTINGS
    # ==========================================================================
    
    redis_url: str = PydanticField(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    redis_max_connections: int = PydanticField(
        default=10,
        description="Maximum Redis connections in pool",
    )
    redis_stream_max_len: int = PydanticField(
        default=10000,
        description="Maximum length of Redis streams (older messages trimmed)",
    )
    redis_consumer_block_ms: int = PydanticField(
        default=5000,
        description="How long to block waiting for messages",
    )
    redis_consumer_count: int = PydanticField(
        default=10,
        description="Number of messages to read at once",
    )
    
    # ==========================================================================
    # RABBITMQ SETTINGS
    # ==========================================================================
    
    rabbitmq_url: str = PydanticField(
        default="amqp://guest:guest@localhost:5672/",
        description="RabbitMQ connection URL",
    )
    rabbitmq_exchange: str = PydanticField(
        default="core_events",
        description="Default exchange name",
    )
    rabbitmq_exchange_type: Literal["direct", "fanout", "topic", "headers"] = PydanticField(
        default="topic",
        description="Exchange type",
    )
    rabbitmq_prefetch_count: int = PydanticField(
        default=10,
        description="Number of messages to prefetch",
    )
    rabbitmq_durable: bool = PydanticField(
        default=True,
        description="Whether queues and exchanges are durable",
    )
    
    # ==========================================================================
    # GENERAL SETTINGS
    # ==========================================================================
    
    messaging_enabled: bool = PydanticField(
        default=True,
        description="Enable/disable messaging system",
    )
    messaging_default_topic: str = PydanticField(
        default="events",
        description="Default topic for events without explicit topic",
    )
    messaging_event_source: str = PydanticField(
        default="",
        description="Source identifier for events (e.g., service name)",
    )
    messaging_serializer: Literal["json", "msgpack"] = PydanticField(
        default="json",
        description="Message serialization format",
    )
    messaging_retry_attempts: int = PydanticField(
        default=3,
        description="Number of retry attempts for failed messages",
    )
    messaging_retry_delay_seconds: int = PydanticField(
        default=5,
        description="Delay between retry attempts in seconds",
    )
    messaging_dead_letter_topic: str = PydanticField(
        default="dead-letter",
        description="Topic for failed messages after all retries",
    )
    
    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Global settings instance
_messaging_settings: MessagingSettings | None = None


def get_messaging_settings() -> MessagingSettings:
    """
    Get the global messaging settings instance.
    
    Returns:
        MessagingSettings instance
    """
    global _messaging_settings
    if _messaging_settings is None:
        _messaging_settings = MessagingSettings()
    return _messaging_settings


def configure_messaging(**kwargs) -> MessagingSettings:
    """
    Configure messaging settings programmatically.
    
    Args:
        **kwargs: Settings to override
    
    Returns:
        Updated MessagingSettings instance
    
    Example:
        configure_messaging(
            message_broker="kafka",
            kafka_bootstrap_servers="kafka1:9092,kafka2:9092",
        )
    """
    global _messaging_settings
    _messaging_settings = MessagingSettings(**kwargs)
    return _messaging_settings
