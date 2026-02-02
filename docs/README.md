# Core Framework Documentation

## Tutorials (Progressivo)

| Guide | Descricao |
|-------|-----------|
| [01 Quickstart](01-quickstart.md) | Primeira API em 5 minutos |
| [02 ViewSets](02-viewsets.md) | CRUD, actions, hooks |
| [03 Authentication](03-authentication.md) | JWT, tokens, login |
| [04 Messaging](04-messaging.md) | Producers, consumers, @event |
| [05 Multi-Service](05-multi-service.md) | Duas APIs com messaging |
| [06 Tasks](06-tasks.md) | Background jobs, scheduling |
| [07 Deployment](07-deployment.md) | Docker, Kubernetes, PM2 |
| [08 Complete Example](08-complete-example.md) | E-commerce completo |

## Reference (Detalhado)

| Guide | Descricao |
|-------|-----------|
| [09 Settings](09-settings.md) | Configuracao, .env, campos customizados |
| [10 Migrations](10-migrations.md) | Criar, aplicar, SQL customizado |
| [11 Permissions](11-permissions.md) | Permissoes built-in e customizadas |
| [12 Auth Backends](12-auth-backends.md) | Backends customizados, OAuth |
| [13 Validators](13-validators.md) | Validacao de campos e unicidade |
| [14 QuerySets](14-querysets.md) | Queries fluentes estilo Django |
| [15 Routing](15-routing.md) | AutoRouter, rotas manuais |
| [16 Serializers](16-serializers.md) | Input/Output schemas |
| [17 DateTime](17-datetime.md) | Timezones, formatacao |

## API Reference

| Document | Descricao |
|----------|-----------|
| [GUIDE.md](GUIDE.md) | Referencia completa da API |

## Quick Start

```bash
# Instalar CLI
pipx install "core-framework @ git+https://TOKEN@github.com/user/core-framework.git"

# Criar projeto
core init my-api
cd my-api

# Configurar banco
core makemigrations --name initial
core migrate

# Rodar
core run

# Deploy
core docker generate
docker compose up -d
```

## Estrutura de Projeto

```
/my-project
  /.env                    # Variaveis de ambiente
  /migrations              # Migracoes do banco
  /src
    /api
      config.py            # Settings customizados
    /apps
      /users
        models.py          # Modelos SQLAlchemy
        schemas.py         # Input/Output schemas
        views.py           # ViewSets
        routes.py          # Rotas
        permissions.py     # Permissoes customizadas
        validators.py      # Validadores customizados
        backends.py        # Auth backends customizados
    main.py                # Entry point
```
