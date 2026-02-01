"""
Docker deployment generator.

Generates docker-compose.yml and Dockerfile for containerized deployment.
"""

from __future__ import annotations

from pathlib import Path


def generate_docker(output_dir: Path) -> None:
    """
    Generate Docker deployment files.
    
    Creates:
        - docker-compose.yml
        - Dockerfile
        - .dockerignore
    
    Args:
        output_dir: Directory to write files to
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # docker-compose.yml
    docker_compose = '''version: "3.8"

services:
  # ==========================================================================
  # Application Services
  # ==========================================================================
  
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
      - ENVIRONMENT=production
      - DEBUG=false
    depends_on:
      db:
        condition: service_healthy
      kafka:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s

  worker:
    build:
      context: .
      dockerfile: Dockerfile
    command: core worker --queue default --concurrency 4
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
    depends_on:
      - kafka
      - db
      - redis
    restart: unless-stopped
    deploy:
      replicas: 2

  scheduler:
    build:
      context: .
      dockerfile: Dockerfile
    command: core scheduler
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY:-change-me-in-production}
    depends_on:
      - kafka
    restart: unless-stopped

  # ==========================================================================
  # Infrastructure Services
  # ==========================================================================
  
  db:
    image: postgres:15-alpine
    environment:
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=postgres
      - POSTGRES_DB=app
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  # ==========================================================================
  # Kafka (Message Broker)
  # ==========================================================================
  
  zookeeper:
    image: confluentinc/cp-zookeeper:7.5.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
      ZOOKEEPER_TICK_TIME: 2000
    volumes:
      - zookeeper_data:/var/lib/zookeeper/data
      - zookeeper_log:/var/lib/zookeeper/log
    restart: unless-stopped

  kafka:
    image: confluentinc/cp-kafka:7.5.0
    depends_on:
      - zookeeper
    ports:
      - "9092:9092"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: PLAINTEXT:PLAINTEXT
      KAFKA_INTER_BROKER_LISTENER_NAME: PLAINTEXT
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
      KAFKA_TRANSACTION_STATE_LOG_MIN_ISR: 1
      KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR: 1
      KAFKA_AUTO_CREATE_TOPICS_ENABLE: "true"
    volumes:
      - kafka_data:/var/lib/kafka/data
    healthcheck:
      test: ["CMD", "kafka-broker-api-versions", "--bootstrap-server", "localhost:9092"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 30s
    restart: unless-stopped

  # ==========================================================================
  # Optional: Kafka UI
  # ==========================================================================
  
  kafka-ui:
    image: provectuslabs/kafka-ui:latest
    ports:
      - "8080:8080"
    environment:
      KAFKA_CLUSTERS_0_NAME: local
      KAFKA_CLUSTERS_0_BOOTSTRAPSERVERS: kafka:9092
      KAFKA_CLUSTERS_0_ZOOKEEPER: zookeeper:2181
    depends_on:
      - kafka
    profiles:
      - tools
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
  kafka_data:
  zookeeper_data:
  zookeeper_log:

networks:
  default:
    name: core-network
'''
    
    # Dockerfile
    dockerfile = '''# Build stage
FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    build-essential \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
RUN pip install uv

# Copy dependency files
COPY pyproject.toml .
COPY uv.lock* .

# Install dependencies
RUN uv pip install --system -e .

# Production stage
FROM python:3.12-slim

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY . .

# Create non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

# Default command
CMD ["core", "run", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
'''
    
    # .dockerignore
    dockerignore = '''# Git
.git
.gitignore

# Python
__pycache__
*.py[cod]
*$py.class
*.so
.Python
.venv
venv
ENV
env

# IDE
.idea
.vscode
*.swp
*.swo

# Testing
.pytest_cache
.coverage
htmlcov
.tox

# Build
dist
build
*.egg-info

# Local
.env.local
*.db
*.sqlite3

# Docker
Dockerfile*
docker-compose*
.docker

# Documentation
docs
*.md
!README.md

# Misc
.DS_Store
Thumbs.db
'''
    
    # Write files
    (output_dir / "docker-compose.yml").write_text(docker_compose)
    (output_dir / "Dockerfile").write_text(dockerfile)
    (output_dir / ".dockerignore").write_text(dockerignore)
