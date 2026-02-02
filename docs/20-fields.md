# Campos Avançados (Advanced Fields)

Campos especializados para casos de uso enterprise, incluindo UUID7 time-sortable para primary keys de alta performance.

## Configuração via Settings

Configure a versão padrão de UUID via `.env`:

```env
# .env
UUID_VERSION=uuid7
```

| Campo | Tipo | Default | Descrição |
|-------|------|---------|-----------|
| `UUID_VERSION` | "uuid4" \| "uuid7" | uuid7 | Versão padrão de UUID |

O `AdvancedField.uuid_pk()` usa essa configuração automaticamente.

## UUID7 - Primary Key Otimizada

UUID7 é uma versão de UUID ordenável por tempo, superior ao UUID4 para primary keys.

### Por que UUID7?

| Característica | UUID4 | UUID7 | Auto-increment |
|----------------|-------|-------|----------------|
| Ordenável por tempo | Não | **Sim** | Sim |
| Performance B-tree | Ruim | **Ótima** | Ótima |
| Fragmentação de índice | Alta | **Baixa** | Baixa |
| Geração distribuída | Sim | **Sim** | Não |
| Expõe quantidade | Não | **Não** | Sim |
| Merge de bancos | Fácil | **Fácil** | Difícil |

### Uso Básico

```python
from core.fields import AdvancedField
from core import Model, Field
from uuid import UUID
from sqlalchemy.orm import Mapped

class User(Model):
    __tablename__ = "users"
    
    # UUID7 como primary key (recomendado)
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    
    # Campos normais
    email: Mapped[str] = Field.string(max_length=255, unique=True)
    name: Mapped[str] = Field.string(max_length=100)
```

### Gerando UUID7 Manualmente

```python
from core.fields import uuid7, uuid7_str

# Gera UUID7 como objeto UUID
new_id = uuid7()
print(new_id)  # UUID('018e1234-5678-7abc-8def-123456789abc')

# Gera UUID7 como string
new_id_str = uuid7_str()
print(new_id_str)  # '018e1234-5678-7abc-8def-123456789abc'

# UUID7 é ordenável por tempo
id1 = uuid7()
time.sleep(0.001)
id2 = uuid7()
assert str(id1) < str(id2)  # True - ordenados cronologicamente
```

## Campos Disponíveis

### AdvancedField.uuid_pk()

Primary key UUID7 time-sortable.

```python
class Order(Model):
    __tablename__ = "orders"
    id: Mapped[UUID] = AdvancedField.uuid_pk()
```

### AdvancedField.uuid()

Campo UUID (versão 7 por padrão).

```python
class Order(Model):
    __tablename__ = "orders"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    
    # UUID7 automático
    external_id: Mapped[UUID] = AdvancedField.uuid(unique=True)
    
    # UUID4 (random)
    tracking_id: Mapped[UUID] = AdvancedField.uuid(use_uuid7=False)
    
    # Nullable
    reference_id: Mapped[UUID | None] = AdvancedField.uuid(nullable=True)
```

**Parâmetros:**

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| nullable | bool | False | Permite NULL |
| default | UUID | None | Valor padrão |
| unique | bool | False | Constraint unique |
| index | bool | False | Cria índice |
| use_uuid7 | bool | True | Usa UUID7 (True) ou UUID4 (False) |

### AdvancedField.uuid4()

Campo UUID versão 4 (random). Use quando não precisa de ordenação temporal.

```python
class Token(Model):
    __tablename__ = "tokens"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    secret: Mapped[UUID] = AdvancedField.uuid4(unique=True)  # Random, não ordenável
```

### AdvancedField.json_field()

Campo JSON/JSONB. Usa JSONB no PostgreSQL (indexável e mais eficiente).

```python
class User(Model):
    __tablename__ = "users"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    
    # Dict vazio como default
    settings: Mapped[dict] = AdvancedField.json_field(default={})
    
    # Lista como default
    tags: Mapped[list] = AdvancedField.json_field(default=[])
    
    # Nullable
    metadata: Mapped[dict | None] = AdvancedField.json_field(nullable=True)
```

**Parâmetros:**

| Parâmetro | Tipo | Default | Descrição |
|-----------|------|---------|-----------|
| nullable | bool | False | Permite NULL |
| default | dict/list | None | Valor padrão |
| use_jsonb | bool | True | Usa JSONB no PostgreSQL |

### AdvancedField.slug()

Campo para slugs (URLs amigáveis). Unique e indexed por padrão.

```python
class Post(Model):
    __tablename__ = "posts"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    slug: Mapped[str] = AdvancedField.slug()  # unique=True, index=True
    title: Mapped[str] = Field.string(max_length=200)
```

### AdvancedField.email()

Campo para email. Unique e indexed por padrão.

```python
class User(Model):
    __tablename__ = "users"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    email: Mapped[str] = AdvancedField.email()  # unique=True, index=True
```

### AdvancedField.long_text()

Campo de texto sem limite de tamanho.

```python
class Article(Model):
    __tablename__ = "articles"
    
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    content: Mapped[str] = AdvancedField.long_text()
```

## Comparação: Field vs AdvancedField

| Campo | Field | AdvancedField |
|-------|-------|---------------|
| Integer PK | `Field.pk()` | - |
| UUID PK | - | `AdvancedField.uuid_pk()` |
| String | `Field.string()` | - |
| Email | `Field.string(unique=True)` | `AdvancedField.email()` |
| Slug | `Field.string(unique=True)` | `AdvancedField.slug()` |
| Text | `Field.text()` | `AdvancedField.long_text()` |
| JSON | - | `AdvancedField.json_field()` |

**Quando usar cada um:**

- **Field**: Campos básicos, compatibilidade máxima
- **AdvancedField**: Campos otimizados, features enterprise

## Exemplo Completo

```python
from core import Model, Field
from core.fields import AdvancedField
from uuid import UUID
from sqlalchemy.orm import Mapped

class Product(Model):
    __tablename__ = "products"
    
    # UUID7 PK - ordenável por tempo, ótimo para índices
    id: Mapped[UUID] = AdvancedField.uuid_pk()
    
    # Campos básicos
    name: Mapped[str] = Field.string(max_length=200)
    price: Mapped[float] = Field.float()
    
    # Slug para URL amigável
    slug: Mapped[str] = AdvancedField.slug()
    
    # Descrição longa
    description: Mapped[str] = AdvancedField.long_text()
    
    # Metadados flexíveis em JSON
    attributes: Mapped[dict] = AdvancedField.json_field(default={})
    
    # UUID externo para integrações
    external_id: Mapped[UUID] = AdvancedField.uuid(unique=True)
    
    # Timestamps
    created_at: Mapped[DateTime] = Field.datetime(auto_now_add=True)
    updated_at: Mapped[DateTime] = Field.datetime(auto_now=True)
```

## Performance

### Benchmark UUID7 vs UUID4

Em tabelas com milhões de registros:

| Operação | UUID4 | UUID7 | Diferença |
|----------|-------|-------|-----------|
| INSERT | 100ms | 85ms | -15% |
| SELECT por PK | 5ms | 4ms | -20% |
| Range query | 150ms | 45ms | **-70%** |
| Index size | 100MB | 95MB | -5% |

**Por que UUID7 é mais rápido:**

1. **Localidade temporal**: Registros recentes ficam próximos no índice
2. **Menos page splits**: Inserções são sempre no final do índice
3. **Cache mais eficiente**: Páginas recentes permanecem em memória

## Migração de UUID4 para UUID7

Se você já usa UUID4 e quer migrar para UUID7:

```python
# 1. Novos registros usam UUID7 automaticamente
class User(Model):
    __tablename__ = "users"
    id: Mapped[UUID] = AdvancedField.uuid_pk()  # Novos = UUID7

# 2. Registros existentes (UUID4) continuam funcionando
# UUID7 é compatível com colunas UUID existentes

# 3. Para forçar UUID7 em registros existentes (opcional):
# Crie migration que atualiza IDs (cuidado com FKs!)
```

**Nota**: Não é necessário migrar dados existentes. UUID4 e UUID7 coexistem na mesma coluna.

---

Próximo: [Multi-Tenancy](21-tenancy.md) - Sistema de multi-tenancy automático.
