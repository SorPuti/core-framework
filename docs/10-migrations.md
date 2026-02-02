# Migrations

Sistema de migracoes automaticas para banco de dados.

## Estrutura de Arquivos

```
/my-project
  /migrations              # Criado automaticamente
    /main                  # App label
      0001_initial.py
      0002_add_avatar.py
  /src
    /apps
      /users
        models.py
```

## Comandos

### Criar Migracao

```bash
# Detecta mudancas e gera arquivo
core makemigrations --name add_avatar

# Apenas mostra o que seria gerado (sem criar arquivo)
core makemigrations --name add_avatar --dry-run

# Cria migracao vazia (para SQL customizado)
core makemigrations --name custom_index --empty
```

### Aplicar Migracoes

```bash
# Aplica todas as migracoes pendentes
core migrate

# Aplica ate uma migracao especifica
core migrate --target 0002_add_avatar

# Mostra o que seria executado (sem aplicar)
core migrate --dry-run

# Marca como aplicada sem executar (cuidado!)
core migrate --fake
```

### Ver Status

```bash
# Lista migracoes e status
core showmigrations
```

Saida:

```
[X] 0001_initial
[X] 0002_add_avatar
[ ] 0003_add_phone
```

## Fluxo de Trabalho

### 1. Criar/Modificar Model

```python
# src/apps/users/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column

class User(Model):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    # Novo campo adicionado
    avatar_url: Mapped[str | None] = mapped_column(default=None)
```

### 2. Gerar Migracao

```bash
core makemigrations --name add_avatar
```

Saida:

```
Migrations for 'main':
  migrations/main/0002_add_avatar.py
    - Add column 'avatar_url' to 'users'
```

### 3. Aplicar Migracao

```bash
core migrate
```

Saida:

```
Applying migrations...
  Applying 0002_add_avatar... OK
```

## Arquivo de Migracao

```python
# migrations/main/0002_add_avatar.py
"""
Add avatar_url to users.

Revision ID: 0002_add_avatar
Revises: 0001_initial
Create Date: 2026-02-01 12:00:00
"""

from core.migrations import Migration, operations

revision = "0002_add_avatar"
down_revision = "0001_initial"

def upgrade():
    operations.add_column(
        "users",
        operations.Column("avatar_url", operations.String(255), nullable=True),
    )

def downgrade():
    operations.drop_column("users", "avatar_url")
```

## Operacoes Disponiveis

| Operacao | Descricao |
|----------|-----------|
| `create_table` | Cria tabela |
| `drop_table` | Remove tabela |
| `add_column` | Adiciona coluna |
| `drop_column` | Remove coluna |
| `alter_column` | Modifica coluna |
| `create_index` | Cria indice |
| `drop_index` | Remove indice |
| `create_foreign_key` | Cria FK |
| `drop_foreign_key` | Remove FK |
| `execute` | SQL customizado |

## Migracao com SQL Customizado

```bash
core makemigrations --name custom_index --empty
```

```python
# migrations/main/0003_custom_index.py
from core.migrations import Migration, operations

revision = "0003_custom_index"
down_revision = "0002_add_avatar"

def upgrade():
    # SQL customizado
    operations.execute("""
        CREATE INDEX CONCURRENTLY idx_users_email_lower 
        ON users (LOWER(email))
    """)

def downgrade():
    operations.execute("DROP INDEX IF EXISTS idx_users_email_lower")
```

## Migracao de Dados

```python
# migrations/main/0004_populate_slugs.py
from core.migrations import Migration, operations

revision = "0004_populate_slugs"
down_revision = "0003_custom_index"

async def upgrade():
    # Migracao de dados
    operations.execute("""
        UPDATE posts 
        SET slug = LOWER(REPLACE(title, ' ', '-'))
        WHERE slug IS NULL
    """)

def downgrade():
    pass  # Dados nao podem ser revertidos
```

## Producao

### Docker Compose

```yaml
services:
  api:
    command: sh -c "core migrate && core run"
```

### Entrypoint Script

```bash
#!/bin/sh
# entrypoint.sh
set -e

echo "Applying migrations..."
core migrate

echo "Starting server..."
exec core run
```

## Dicas

1. Sempre faca backup antes de migrar em producao
2. Use `--dry-run` para verificar antes de aplicar
3. Teste migracoes em staging primeiro
4. Migracoes de dados devem ser idempontentes
5. Nunca edite migracoes ja aplicadas em producao

Next: [Permissions](11-permissions.md)
