# CLI Reference

All commands available via `core` CLI.

## Project

```bash
# Create new project
core init my-api
core init my-api --python 3.13

# Create new app
core createapp posts
```

## Server

```bash
# Development server (hot reload)
core run

# Production
core run --no-reload --workers 4 --host 0.0.0.0 --port 8000
```

## Database

```bash
# Create migration
core makemigrations --name add_posts

# Apply migrations
core migrate

# Show migration status
core showmigrations

# Rollback last migration
core rollback

# Rollback to specific migration
core rollback 0002

# Database info
core dbinfo

# Reset database (DESTRUCTIVE)
core reset_db --yes
```

## Auth

```bash
# Create superuser
core createsuperuser

# Collect permissions from models
core collectpermissions
```

## Debug

```bash
# List all routes
core routes

# Check configuration
core check

# Interactive shell
core shell
```

## Deployment

```bash
# Generate Dockerfile
core docker generate

# Generate docker-compose.yml
core docker compose

# Generate Kubernetes manifests
core deploy kubernetes

# Generate PM2 config
core deploy pm2
```

## Workers (Enterprise)

```bash
# Start background worker
core runworker

# List workers
core workers_list

# Scheduler
core scheduler start
core scheduler stop
```

## Kafka (Enterprise)

```bash
# List topics
core topics_list

# Create topic
core topics_create my-topic --partitions 3

# Delete topic
core topics_delete my-topic

# Start consumer
core consumer start
```

## Testing

```bash
# Run tests
core test

# With coverage
core test --cov

# Specific file
core test tests/test_posts.py
```

## Version

```bash
core version
core --version
```

## Help

```bash
core --help
core <command> --help
```

## Common Options

Most commands support:

| Option | Description |
|--------|-------------|
| `--help` | Show help |
| `--dry-run` | Preview without executing |
| `--yes` | Skip confirmations |

## Next

- [Migrations](41-migrations.md) — Migration details
- [Permissions](08-permissions.md) — Access control
