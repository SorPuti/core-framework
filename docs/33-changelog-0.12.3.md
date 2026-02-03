# Changelog v0.12.3

**Data de Release:** 03/02/2026

Esta versão corrige 5 bugs críticos encontrados na v0.12.2 que impediam o funcionamento do `AuthenticationMiddleware` e causavam erros em models com UUID.

---

## Bugs Corrigidos

### Bug #1: `AbstractUUIDUser` usa tipo não resolvível
**Arquivo:** `core/auth/models.py`

**Problema:** A classe `AbstractUUIDUser` definia o campo `id` com um tipo `UUIDType` que não era importado corretamente no escopo do módulo, causando erro de resolução de tipo pelo SQLAlchemy.

**Antes:**
```python
class AbstractUUIDUser(AbstractUser):
    # Import dentro da classe (problemático)
    from uuid import UUID as UUIDType
    id: Mapped[UUIDType] = AdvancedField.uuid_pk()
```

**Erro:**
```
MappedAnnotationError: Could not resolve all types within mapped annotation: "Mapped[UUIDType]"
```

**Depois:**
```python
# Imports no topo do módulo
from uuid import UUID
from core.fields import AdvancedField

class AbstractUUIDUser(AbstractUser):
    id: Mapped[UUID] = AdvancedField.uuid_pk()
```

---

### Bug #2: Shortcut `"auth"` não registrado nos middleware shortcuts
**Arquivo:** `core/middleware.py`

**Problema:** O shortcut `"auth"` era definido no início do arquivo, mas podia falhar dependendo da ordem de carregamento dos módulos.

**Correção:** Adicionados os shortcuts de auth também no `_builtin_middlewares.update()` para garantir registro mesmo em casos de edge.

```python
_builtin_middlewares.update({
    # ... outros middlewares ...
    "auth": "core.auth.middleware.AuthenticationMiddleware",
    "authentication": "core.auth.middleware.AuthenticationMiddleware",
    "optional_auth": "core.auth.middleware.OptionalAuthenticationMiddleware",
})
```

---

### Bug #3: `AuthenticationMiddleware` usa `async for` incorretamente
**Arquivo:** `core/auth/middleware.py`

**Problema:** O middleware usava `async for db in get_read_session()` mas `get_read_session()` é uma coroutine que retorna `AsyncSession` diretamente, não um async generator.

**Antes:**
```python
async for db in get_read_session():  # ERRADO!
    # ...
```

**Erro:**
```
RuntimeWarning: coroutine 'get_read_session' was never awaited
```

**Depois:**
```python
db = await self._get_db_session()
try:
    # ... usar db ...
finally:
    await db.close()
```

---

### Bug #4: `get_read_session()` falha fora do contexto FastAPI
**Arquivo:** `core/auth/middleware.py`

**Problema:** O middleware executa antes do lifecycle de dependency injection do FastAPI, então `init_replicas()` pode não ter sido chamado, causando erro de "Database not initialized".

**Erro:**
```
RuntimeError: Database not initialized. Call init_replicas() first.
```

**Correção:** Implementado método `_get_db_session()` no middleware que:
1. Tenta usar o session factory padrão se já inicializado
2. Como fallback, cria uma sessão diretamente a partir das settings

```python
async def _get_db_session(self) -> AsyncSession | None:
    # Try 1: Use standard factory if initialized
    try:
        if _read_session_factory is not None:
            return _read_session_factory()
    except RuntimeError:
        pass
    
    # Try 2: Create from settings (lazy init)
    try:
        settings = get_settings()
        db_url = settings.database_url
        engine = create_async_engine(db_url)
        session_factory = async_sessionmaker(engine)
        return session_factory()
    except Exception:
        pass
    
    return None
```

---

### Bug #5: Ordenação topológica incorreta nas migrations
**Arquivo:** `core/migrations/engine.py`

**Problema:** Tabelas com foreign keys eram criadas antes das tabelas que elas referenciam, causando erro de "relation does not exist".

**Erro:**
```
asyncpg.exceptions.UndefinedTableError: relation "workspaces" does not exist
[SQL: CREATE TABLE "domains" (..., FOREIGN KEY ("workspace_id") REFERENCES "workspaces" ...)]
```

**Correção:** Implementado algoritmo de ordenação topológica (Kahn's algorithm) no método `_topological_sort_tables()` que:
1. Constrói grafo de dependências baseado em FKs
2. Ordena tabelas garantindo que referenciadas sejam criadas primeiro
3. Detecta e alerta sobre dependências circulares

```python
def _topological_sort_tables(self, tables: list[TableState]) -> list[TableState]:
    # Constrói grafo de dependências
    dependencies = {t.name: set() for t in tables}
    for table in tables:
        for fk in table.foreign_keys:
            if fk.references_table in table_map:
                dependencies[table.name].add(fk.references_table)
    
    # Kahn's algorithm para ordenação topológica
    # ... ordena tabelas por dependências ...
    return sorted_tables
```

---

## Resumo das Mudanças

| Bug | Arquivo | Correção |
|-----|---------|----------|
| #1 | `core/auth/models.py` | Import de `UUID` movido para nível do módulo |
| #2 | `core/middleware.py` | Shortcuts de auth adicionados no `.update()` |
| #3 | `core/auth/middleware.py` | Removido `async for`, usa `await` corretamente |
| #4 | `core/auth/middleware.py` | Novo método `_get_db_session()` com lazy init |
| #5 | `core/migrations/engine.py` | Implementada ordenação topológica de tabelas |

---

## Como Atualizar

```bash
pip install --upgrade core-framework==0.12.3
```

## Impacto

Com estas correções:
- `AbstractUUIDUser` funciona corretamente para modelos com UUID PK
- `AuthenticationMiddleware` funciona out-of-the-box
- `request.state.user` é populado corretamente
- Endpoint `/auth/me` funciona sem workarounds
- Migrations criam tabelas na ordem correta de dependências
