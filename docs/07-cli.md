# CLI Reference

Todos os comandos disponíveis via CLI `core`.

## Projeto

```bash
# Criar novo projeto
core init my-api
core init my-api --python 3.13
core init my-api --minimal  # Projeto mínimo

# Criar nova app
core createapp posts
```

## Servidor

```bash
# Servidor de desenvolvimento (hot reload)
core run

# Produção
core run --no-reload --workers 4 --host 0.0.0.0 --port 8000
```

## Banco de Dados

```bash
# Criar migration
core makemigrations --name add_posts

# Aplicar migrations
core migrate

# Mostrar status das migrations
core showmigrations

# Rollback última migration
core rollback

# Rollback para migration específica
core rollback 0002

# Info do banco
core dbinfo

# Reset do banco (DESTRUTIVO)
core reset_db --yes
```

## Auth

```bash
# Criar superusuário
core createsuperuser

# Coletar permissões dos models
core collectpermissions
```

## Debug

```bash
# Listar todas as rotas
core routes

# Verificar configuração
core check

# Shell interativo
core shell
```

## Deployment

```bash
# Gerar Dockerfile
core docker generate

# Gerar docker-compose.yml
core docker compose

# Gerar manifests Kubernetes
core deploy kubernetes

# Gerar config PM2
core deploy pm2
```

## Kafka / Messaging

```bash
# Listar topics
core kafka topics

# Criar topic
core kafka create-topic my-topic --partitions 3

# Deletar topic
core kafka delete-topic my-topic

# Consumir mensagens
core kafka consume my-topic --group my-service

# Executar worker específico
core kafka worker MyWorker

# Executar todos os workers
core kafka worker --all

# Executar worker com opções
core kafka worker MyWorker --concurrency 8
```

## Workers / Tasks

```bash
# Iniciar worker de background
core runworker

# Listar workers
core workers_list

# Scheduler
core scheduler start
core scheduler stop
```

## Testing

```bash
# Executar testes
core test

# Com coverage
core test --cov

# Arquivo específico
core test tests/test_posts.py
```

## Versão

```bash
core version
core --version
```

## Ajuda

```bash
core --help
core <command> --help
```

## Opções Comuns

A maioria dos comandos suporta:

| Opção | Descrição |
|-------|-----------|
| `--help` | Mostrar ajuda |
| `--dry-run` | Preview sem executar |
| `--yes` | Pular confirmações |

## Configuração via Settings

O CLI usa configurações do Settings:

```python
class AppSettings(Settings):
    # CLI / Discovery
    migrations_dir: str = "./migrations"
    app_label: str = "main"
    models_module: str = "app.models"
    workers_module: str | None = None  # Auto-discovery
    tasks_module: str | None = None    # Auto-discovery
    app_module: str = "src.main"
```

| Setting | Descrição |
|---------|-----------|
| `migrations_dir` | Diretório de migrations |
| `app_label` | Label da aplicação |
| `models_module` | Módulo dos models |
| `workers_module` | Módulo dos workers (auto-discovery se None) |
| `tasks_module` | Módulo das tasks (auto-discovery se None) |
| `app_module` | Módulo da aplicação principal |

## Próximos Passos

- [Migrations](41-migrations.md) — Detalhes de migrations
- [Permissions](08-permissions.md) — Controle de acesso
- [Settings](02-settings.md) — Todas as configurações
