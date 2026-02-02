# Core Framework Documentation

## Guides

| Guide | Description |
|-------|-------------|
| [Quickstart](01-quickstart.md) | First API in 5 minutes |
| [ViewSets](02-viewsets.md) | CRUD, actions, hooks |
| [Authentication](03-authentication.md) | JWT, permissions, backends |
| [Messaging](04-messaging.md) | Producers, consumers, Kafka |
| [Multi-Service](05-multi-service.md) | Two APIs with messaging |
| [Tasks](06-tasks.md) | Background jobs, scheduling |
| [Deployment](07-deployment.md) | Docker, Kubernetes, PM2 |
| [Complete Example](08-complete-example.md) | E-commerce API |

## Reference

| Document | Description |
|----------|-------------|
| [GUIDE.md](GUIDE.md) | Full API reference |

## Quick Links

```bash
# Install
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"

# Create project
core init my-api

# Run
core run

# Deploy
core docker generate
docker compose up -d
```
