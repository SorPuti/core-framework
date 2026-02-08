# Migrations

Sistema de migracoes para versionamento de schema de banco de dados. Detecta mudancas nos models e gera scripts de migracao automaticamente.

## Estrutura de Arquivos

```
/my-project
  /migrations              # Criado automaticamente pelo primeiro makemigrations
    /main                  # App label - agrupa migracoes por contexto
      0001_initial.py      # Primeira migracao
      0002_add_avatar.py   # Migracoes subsequentes
  /src
    /apps
      /users
        models.py          # Models SQLAlchemy
```

## Comandos

### Criar Migracao

```bash
# Detecta diferencas entre models e banco, gera arquivo de migracao
# --name e obrigatorio e deve descrever a mudanca
core makemigrations --name add_avatar

# Mostra o que seria gerado sem criar arquivo
# Use para verificar antes de commitar
core makemigrations --name add_avatar --dry-run

# Cria migracao vazia para SQL customizado
# Util para indices especiais, triggers, etc
core makemigrations --name custom_index --empty
```

### Aplicar Migracoes

```bash
# Aplica todas as migracoes pendentes em ordem
core migrate

# Aplica ate uma migracao especifica (inclusive)
# Util para rollback parcial ou debug
core migrate --target 0002_add_avatar

# Mostra SQL que seria executado sem aplicar
core migrate --dry-run

# Marca migracao como aplicada sem executar SQL
# CUIDADO: Use apenas se o schema ja foi alterado manualmente
core migrate --fake
```

### Ver Status

```bash
# Lista todas as migracoes e status de aplicacao
core showmigrations
```

Saida:

```
[X] 0001_initial          # Aplicada
[X] 0002_add_avatar       # Aplicada
[ ] 0003_add_phone        # Pendente
```

## Fluxo de Trabalho

### 1. Modificar Model

```python
# src/apps/users/models.py
from core import Model
from sqlalchemy.orm import Mapped, mapped_column

class User(Model):
    __tablename__ = "users"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(unique=True)
    name: Mapped[str]
    
    # Campo adicionado - requer migracao
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

Migracoes sao arquivos Python com funcoes `upgrade()` e `downgrade()`.

```python
# migrations/main/0002_add_avatar.py
"""
Add avatar_url to users.

Revision ID: 0002_add_avatar
Revises: 0001_initial
Create Date: 2026-02-01 12:00:00
"""

from core.migrations import Migration, operations

# Identificador unico desta migracao
revision = "0002_add_avatar"

# Migracao anterior - define ordem de execucao
down_revision = "0001_initial"

def upgrade():
    """
    Aplica mudancas ao banco.
    Executado por 'core migrate'.
    """
    operations.add_column(
        "users",  # Nome da tabela
        operations.Column(
            "avatar_url",           # Nome da coluna
            operations.String(255), # Tipo SQL
            nullable=True,          # Permite NULL
        ),
    )

def downgrade():
    """
    Reverte mudancas.
    Executado por 'core migrate --target <anterior>'.
    """
    operations.drop_column("users", "avatar_url")
```

**Importante sobre downgrade**: Nem todas as operacoes sao reversiveis. Remocao de coluna com dados, por exemplo, perde informacao permanentemente.

## Operacoes Disponiveis

| Operacao | Descricao | Reversivel |
|----------|-----------|------------|
| `create_table` | Cria tabela | Sim |
| `drop_table` | Remove tabela | Nao (dados perdidos) |
| `add_column` | Adiciona coluna | Sim |
| `drop_column` | Remove coluna | Nao (dados perdidos) |
| `alter_column` | Modifica tipo/constraints | Depende |
| `create_index` | Cria indice | Sim |
| `drop_index` | Remove indice | Sim |
| `create_foreign_key` | Cria FK | Sim |
| `drop_foreign_key` | Remove FK | Sim |
| `execute` | SQL customizado | Depende |

## Migracao com SQL Customizado

Para operacoes nao suportadas pelas operacoes padrao.

```bash
# Cria migracao vazia
core makemigrations --name custom_index --empty
```

```python
# migrations/main/0003_custom_index.py
from core.migrations import Migration, operations

revision = "0003_custom_index"
down_revision = "0002_add_avatar"

def upgrade():
    # SQL executado diretamente no banco
    # CONCURRENTLY evita lock em tabelas grandes (PostgreSQL)
    operations.execute("""
        CREATE INDEX CONCURRENTLY idx_users_email_lower 
        ON users (LOWER(email))
    """)

def downgrade():
    operations.execute("DROP INDEX IF EXISTS idx_users_email_lower")
```

**Nota sobre CONCURRENTLY**: Nao funciona dentro de transacao. O framework executa este tipo de migracao fora de transacao automaticamente.

## Migracao de Dados

Para transformar dados existentes alem de schema.

```python
# migrations/main/0004_populate_slugs.py
from core.migrations import Migration, operations

revision = "0004_populate_slugs"
down_revision = "0003_custom_index"

def upgrade():
    """
    Migracoes de dados devem ser idempotentes.
    WHERE slug IS NULL garante que re-execucao nao causa problemas.
    """
    operations.execute("""
        UPDATE posts 
        SET slug = LOWER(REPLACE(title, ' ', '-'))
        WHERE slug IS NULL
    """)

def downgrade():
    # Dados transformados nao podem ser revertidos
    # Deixe vazio ou documente que rollback nao e possivel
    pass
```

## Producao

### Docker Compose

Execute migracoes antes de iniciar a aplicacao:

```yaml
services:
  api:
    # sh -c permite executar multiplos comandos
    command: sh -c "core migrate && core run"
```

### Entrypoint Script (Recomendado)

Mais controle sobre o processo de startup:

```bash
#!/bin/sh
# entrypoint.sh

# set -e: Falha imediatamente se qualquer comando falhar
# Evita iniciar aplicacao com banco desatualizado
set -e

echo "Applying migrations..."
core migrate

echo "Starting server..."
exec core run
```

## Boas Praticas

1. **Backup antes de migrar em producao**: Migracoes podem falhar no meio, deixando banco em estado inconsistente.

2. **Use --dry-run primeiro**: Verifique o SQL gerado antes de aplicar.

3. **Teste em staging**: Aplique migracoes em ambiente identico a producao antes.

4. **Migracoes de dados idempotentes**: Use WHERE clauses para permitir re-execucao segura.

5. **Nunca edite migracoes aplicadas**: Se ja foi aplicada em algum ambiente, crie nova migracao para corrigir.

6. **Commits atomicos**: Commite model e migracao juntos para manter consistencia.

---

Proximo: [Permissions](11-permissions.md) - Sistema de controle de acesso.
