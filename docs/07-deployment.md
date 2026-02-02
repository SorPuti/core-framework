# Deployment

## Generate Docker Files

```bash
core docker generate
```

Creates:
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`

## Docker Compose Structure

```yaml
services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      kafka:
        condition: service_healthy

  worker:
    build: .
    command: core worker --queue default --concurrency 4
    deploy:
      replicas: 2
    depends_on:
      kafka:
        condition: service_healthy

  scheduler:
    build: .
    command: core scheduler
    depends_on:
      kafka:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: app
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  kafka:
    image: bitnami/kafka:latest
    environment:
      KAFKA_CFG_NODE_ID: 0
      KAFKA_CFG_PROCESS_ROLES: controller,broker
      KAFKA_CFG_LISTENERS: PLAINTEXT://:9092,CONTROLLER://:9093
      KAFKA_CFG_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_CFG_CONTROLLER_QUORUM_VOTERS: 0@kafka:9093
      KAFKA_CFG_CONTROLLER_LISTENER_NAMES: CONTROLLER
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 10s
      retries: 5

  redis:
    image: redis:7-alpine
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

  dozzle:
    image: amir20/dozzle:latest
    ports:
      - "9999:8080"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro

volumes:
  postgres_data:
```

## Build and Run

```bash
# Build
docker compose build

# Run
docker compose up -d

# View logs
docker compose logs -f api

# Scale workers
docker compose up -d --scale worker=4
```

## Environment Variables

```env
# .env.production
APP_NAME=My API
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=your-production-secret-key

DATABASE_URL=postgresql+asyncpg://user:pass@db-host:5432/myapp
KAFKA_BOOTSTRAP_SERVERS=kafka-host:9092
REDIS_URL=redis://redis-host:6379/0

AUTH_ACCESS_TOKEN_EXPIRE_MINUTES=15
AUTH_REFRESH_TOKEN_EXPIRE_DAYS=7
```

## Migrations in Production

```bash
# Run migrations before starting
docker compose run --rm api core migrate

# Or in entrypoint
# entrypoint.sh
#!/bin/sh
core migrate
exec "$@"
```

## Health Checks

Built-in `/health` endpoint:

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production"
}
```

## Kubernetes

```bash
core k8s generate
```

Creates:
- `k8s/deployment.yaml`
- `k8s/service.yaml`
- `k8s/configmap.yaml`
- `k8s/secrets.yaml`

## PM2 (Node-style)

```bash
core pm2 generate
```

Creates `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [
    {
      name: "api",
      script: "core",
      args: "run --host 0.0.0.0 --port 8000",
      instances: "max",
      exec_mode: "cluster",
    },
    {
      name: "worker",
      script: "core",
      args: "worker --queue default",
      instances: 2,
    },
    {
      name: "scheduler",
      script: "core",
      args: "scheduler",
      instances: 1,
    },
  ],
};
```

## Log Viewer

Dozzle is included by default at `http://localhost:9999`.

Features:
- Real-time logs
- Filter by container
- Merged view
- Search

## Production Checklist

- [ ] Set `DEBUG=false`
- [ ] Use strong `SECRET_KEY`
- [ ] Configure proper database credentials
- [ ] Set up SSL/TLS
- [ ] Configure CORS properly
- [ ] Set up monitoring (Prometheus, Grafana)
- [ ] Configure log aggregation
- [ ] Set up backups
- [ ] Configure rate limiting
- [ ] Review permissions

Next: [Complete Example](08-complete-example.md)
