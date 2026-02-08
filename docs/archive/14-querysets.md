# QuerySets

API fluente para queries de banco de dados. Inspirada no Django ORM, mas assincrona e com tipagem forte.

## Conceito

QuerySets sao objetos que representam queries ao banco de dados. Sao **lazy** - a query so e executada quando voce chama um metodo terminal (`all()`, `first()`, `get()`, etc).

Existem duas formas de acessar:

```python
# Via Manager (Model.objects) - acesso direto
users = await User.objects.using(db).all()

# Via QuerySet (retornado por filter/exclude/order_by)
users = await User.objects.using(db).filter(is_active=True).all()
```

**Importante**: `using(db)` e obrigatorio. Passa a sessao de banco para o Manager/QuerySet.

## Referencia Completa de Metodos

### Manager (Model.objects.using(db))

Todos estes metodos estao disponiveis diretamente no Manager:

| Metodo | Tipo | Retorno | Descricao |
|--------|------|---------|-----------|
| `using(session)` | encadeavel | Manager | Define a sessao do banco |
| `filter(**kwargs)` | encadeavel | QuerySet | Filtra registros (WHERE AND) |
| `exclude(**kwargs)` | encadeavel | QuerySet | Exclui registros (WHERE NOT) |
| `order_by(*fields)` | encadeavel | QuerySet | Ordena resultados |
| `limit(n)` | encadeavel | QuerySet | Limita quantidade |
| `offset(n)` | encadeavel | QuerySet | Pula N registros |
| `select_related(*fields)` | encadeavel | QuerySet | Eager load (JOIN) |
| `prefetch_related(*fields)` | encadeavel | QuerySet | Pre-carrega em queries separadas |
| `all()` | terminal | `Sequence[T]` | Todos os registros |
| `first()` | terminal | `T \| None` | Primeiro ou None |
| `last()` | terminal | `T \| None` | Ultimo ou None |
| `get(**kwargs)` | terminal | `T` | Exatamente 1 (raise se 0 ou >1) |
| `get_or_none(**kwargs)` | terminal | `T \| None` | 1 ou None |
| `count()` | terminal | `int` | Conta registros |
| `exists(**kwargs)` | terminal | `bool` | Verifica existencia |
| `values(*fields)` | terminal | `list[dict]` | Retorna dicts |
| `values_list(*fields, flat)` | terminal | `list` | Retorna tuplas/lista |
| `aggregate(**kwargs)` | terminal | `dict` | Funcoes de agregacao |
| `create(**kwargs)` | terminal | `T` | Cria registro |
| `bulk_create(objects)` | terminal | `list[T]` | Cria multiplos |
| `update(filters, **values)` | terminal | `int` | Atualiza em massa |
| `delete(**filters)` | terminal | `int` | Deleta em massa |

### QuerySet (retornado por filter/exclude/order_by)

Alem de todos os metodos encadeaveis e terminais acima, o QuerySet tambem suporta:

| Metodo | Tipo | Retorno | Descricao |
|--------|------|---------|-----------|
| `update(**kwargs)` | terminal | `int` | Atualiza registros filtrados |
| `delete()` | terminal | `int` | Deleta registros filtrados |
| `async for` | terminal | `T` | Iteracao assincrona |

> **Nota**: `update()` e `delete()` no QuerySet tem assinatura diferente do Manager.
> No QuerySet usam os filtros ja encadeados; no Manager recebem filtros como parametro.

## Uso Basico

```python
# Buscar todos
users = await User.objects.using(db).all()

# Buscar por ID
user = await User.objects.using(db).get(id=1)

# Filtrar
active = await User.objects.using(db).filter(is_active=True).all()

# Primeiro ou None
user = await User.objects.using(db).first()

# Ultimo ou None
user = await User.objects.using(db).last()

# Verificar existencia
has_admin = await User.objects.using(db).exists(role="admin")

# Contar
total = await User.objects.using(db).count()
```

## Lookups (Operadores de Comparacao)

Lookups sao sufixos adicionados ao nome do campo com `__` para especificar o tipo de comparacao. Funcionam em `filter()` e `exclude()`.

### Tabela de Lookups

| Operador | SQL Gerado | Exemplo |
|----------|-----------|---------|
| *(nenhum)* / `__exact` | `= valor` | `filter(name="João")` |
| `__iexact` | `ILIKE valor` | `filter(name__iexact="joão")` |
| `__contains` | `LIKE '%valor%'` | `filter(name__contains="Silva")` |
| `__icontains` | `ILIKE '%valor%'` | `filter(email__icontains="@gmail")` |
| `__startswith` | `LIKE 'valor%'` | `filter(name__startswith="Jo")` |
| `__istartswith` | `ILIKE 'valor%'` | `filter(name__istartswith="jo")` |
| `__endswith` | `LIKE '%valor'` | `filter(email__endswith=".com")` |
| `__iendswith` | `ILIKE '%valor'` | `filter(email__iendswith=".COM")` |
| `__gt` | `> valor` | `filter(price__gt=100)` |
| `__gte` | `>= valor` | `filter(price__gte=100)` |
| `__lt` | `< valor` | `filter(price__lt=50)` |
| `__lte` | `<= valor` | `filter(stock__lte=0)` |
| `__in` | `IN (valores)` | `filter(role__in=["admin", "mod"])` |
| `__isnull` | `IS NULL / IS NOT NULL` | `filter(deleted_at__isnull=True)` |
| `__range` | `BETWEEN a AND b` | `filter(price__range=(10, 100))` |

### Exemplos Detalhados

```python
# Igualdade (padrao)
await User.objects.using(db).filter(name="John").all()
await User.objects.using(db).filter(name__exact="John").all()  # Equivalente

# Case insensitive
await User.objects.using(db).filter(name__iexact="john").all()
# Encontra "John", "JOHN", "john"

# Contem substring
await User.objects.using(db).filter(name__contains="oh").all()       # Case sensitive
await User.objects.using(db).filter(name__icontains="oh").all()      # Case insensitive

# Comeca/termina com
await User.objects.using(db).filter(email__startswith="admin").all()
await User.objects.using(db).filter(email__endswith="@gmail.com").all()
# Versoes case-insensitive:
await User.objects.using(db).filter(email__istartswith="ADMIN").all()
await User.objects.using(db).filter(email__iendswith="@GMAIL.COM").all()

# Comparacao numerica
await Product.objects.using(db).filter(price__gt=100).all()    # price > 100
await Product.objects.using(db).filter(price__gte=100).all()   # price >= 100
await Product.objects.using(db).filter(price__lt=50).all()     # price < 50
await Product.objects.using(db).filter(stock__lte=0).all()     # stock <= 0

# Lista de valores (IN)
await User.objects.using(db).filter(role__in=["admin", "moderator"]).all()

# Null check
await User.objects.using(db).filter(deleted_at__isnull=True).all()    # IS NULL
await User.objects.using(db).filter(phone__isnull=False).all()        # IS NOT NULL

# Range (BETWEEN)
await Product.objects.using(db).filter(price__range=(10, 100)).all()
await Event.objects.using(db).filter(date__range=(start_date, end_date)).all()
```

## Encadeamento

Metodos encadeaveis retornam novo QuerySet. A query so e executada no metodo terminal.

```python
# Cada metodo retorna novo QuerySet
# A query SQL e construida incrementalmente
# Execucao acontece apenas em all()
users = await User.objects.using(db)\
    .filter(is_active=True)\
    .exclude(role="admin")\
    .order_by("-created_at")\
    .limit(10)\
    .all()

# SQL gerado:
# SELECT * FROM users
# WHERE is_active = true AND NOT (role = 'admin')
# ORDER BY created_at DESC
# LIMIT 10
```

## Ordenacao

```python
# Ascendente (padrao)
users = await User.objects.using(db).order_by("name").all()

# Descendente (prefixo -)
users = await User.objects.using(db).order_by("-created_at").all()

# Multiplos campos
users = await User.objects.using(db).order_by("role", "-created_at").all()
```

## Paginacao

```python
page_size = 10
page = 3  # Paginas comecam em 1

users = await User.objects.using(db)\
    .order_by("id")\
    .offset((page - 1) * page_size)\
    .limit(page_size)\
    .all()
```

> **Nota**: Sem `order_by()`, a ordem dos resultados nao e garantida, tornando paginacao inconsistente.

## get() vs first() vs get_or_none() vs last()

```python
from core.querysets import DoesNotExist, MultipleObjectsReturned

# get() - EXATAMENTE 1 resultado, raise se 0 ou >1
try:
    user = await User.objects.using(db).get(id=1)
except DoesNotExist:
    print("Nao encontrado")
except MultipleObjectsReturned:
    print("Multiplos encontrados")

# get_or_none() - 1 resultado ou None (nunca raise)
user = await User.objects.using(db).get_or_none(email="test@example.com")
if user is None:
    print("Nao encontrado")

# first() - primeiro registro ou None
user = await User.objects.using(db).filter(role="admin").first()

# last() - ultimo registro ou None
latest = await User.objects.using(db).order_by("created_at").last()
```

**Quando usar cada um**:
- `get()`: Busca por primary key ou campo unique (quando DEVE existir)
- `get_or_none()`: Busca por campo unique (quando pode nao existir)
- `first()`: Busca que pode ter 0 ou mais resultados
- `last()`: Ultimo registro (combine com `order_by()`)

## values() e values_list()

Para quando voce nao precisa de instancias completas do model.

```python
# values() retorna lista de dicts
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values("id", "email")
# [{"id": 1, "email": "a@b.com"}, {"id": 2, "email": "c@d.com"}]

# values() sem campos = todos os campos (usa to_dict())
all_data = await User.objects.using(db).values()
# [{"id": 1, "email": "a@b.com", "name": "Ana", ...}, ...]

# values_list() retorna lista de tuplas
pairs = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("id", "email")
# [(1, "a@b.com"), (2, "c@d.com")]

# flat=True para lista simples (apenas 1 campo)
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("email", flat=True)
# ["a@b.com", "c@d.com"]
```

## Agregacoes

Funcoes de agregacao para calculos no banco de dados. Todas resolvem a coluna real do modelo automaticamente.

```python
from core.querysets import Count, Sum, Avg, Max, Min
```

### Funcoes Disponiveis

| Funcao | SQL | Exemplo |
|--------|-----|---------|
| `Count("*")` | `COUNT(*)` | Total de registros |
| `Count("field")` | `COUNT(model.field)` | Total de valores nao-null |
| `Sum("field")` | `SUM(model.field)` | Soma |
| `Avg("field")` | `AVG(model.field)` | Media |
| `Max("field")` | `MAX(model.field)` | Valor maximo |
| `Min("field")` | `MIN(model.field)` | Valor minimo |

### Exemplos

```python
# Conta total de usuarios
result = await User.objects.using(db).aggregate(
    total=Count("*"),
)
# {"total": 42}

# Multiplas agregacoes de uma vez
result = await Order.objects.using(db).aggregate(
    total_orders=Count("*"),
    revenue=Sum("total"),
    avg_ticket=Avg("total"),
    biggest_order=Max("total"),
    smallest_order=Min("total"),
)
# {"total_orders": 150, "revenue": 45000.0, "avg_ticket": 300.0, ...}

# Com filtro
result = await Order.objects.using(db)\
    .filter(status="completed")\
    .aggregate(
        total=Count("*"),
        revenue=Sum("total"),
    )
# {"total": 120, "revenue": 38000.0}

# Contar campo especifico (ignora NULL)
result = await User.objects.using(db).aggregate(
    with_phone=Count("phone"),
)
```

## Relacionamentos

### select_related (Eager Loading via JOIN)

Carrega relacionamentos na mesma query (JOIN SQL).

```python
# Carrega autor junto com posts
posts = await Post.objects.using(db)\
    .select_related("author")\
    .filter(is_published=True)\
    .all()

# Acessa sem query extra
for post in posts:
    print(f"{post.title} por {post.author.name}")
```

### prefetch_related (Queries Separadas)

Pre-carrega relacionamentos em queries adicionais.

```python
# Carrega posts de cada usuario em query separada
users = await User.objects.using(db)\
    .prefetch_related("posts")\
    .filter(is_active=True)\
    .all()
```

## Iteracao Assincrona

```python
# async for itera sem carregar tudo na memoria
async for user in User.objects.using(db).filter(is_active=True):
    await send_notification(user.email)
```

## Update e Delete em Massa

### Via Manager

```python
# update recebe filtros como primeiro arg + valores como kwargs
updated = await User.objects.using(db).update(
    {"role": "guest"},     # filtros (WHERE)
    role="member",         # novos valores (SET)
)
print(f"{updated} usuarios atualizados")

# delete recebe filtros como kwargs
deleted = await User.objects.using(db).delete(is_active=False)
print(f"{deleted} usuarios removidos")
```

### Via QuerySet (encadeado)

```python
# update com filtros encadeados
updated = await User.objects.using(db)\
    .filter(role="guest")\
    .update(role="member")

# delete com filtros encadeados
deleted = await User.objects.using(db)\
    .filter(is_active=False, last_login__lt=cutoff_date)\
    .delete()
```

## Create

```python
# Criar um registro
user = await User.objects.using(db).create(
    name="Ana",
    email="ana@example.com",
    is_active=True,
)
print(user.id)  # ID gerado automaticamente

# Criar multiplos de uma vez
users = await User.objects.using(db).bulk_create([
    {"name": "Bob", "email": "bob@example.com"},
    {"name": "Carol", "email": "carol@example.com"},
])
print(f"{len(users)} usuarios criados")
```

## Queries Complexas com SQLAlchemy

Para queries que os lookups nao suportam, use operadores SQLAlchemy diretamente.

```python
from sqlalchemy import or_, and_

# OR - qualquer condicao
users = await User.objects.using(db).filter(
    or_(
        User.role == "admin",
        User.role == "moderator",
    )
).all()

# AND explicito (filter() ja faz AND implicito)
users = await User.objects.using(db).filter(
    and_(
        User.is_active == True,
        User.role == "admin",
    )
).all()
```

## Customizar QuerySet no ViewSet

Override `get_queryset()` para aplicar filtros globais.

```python
class UserViewSet(ModelViewSet):
    model = User

    def get_queryset(self, db):
        qs = super().get_queryset(db)
        user = self.request.state.user

        # Usuarios nao-admin so veem registros ativos
        if not user or not user.is_admin:
            return qs.filter(is_active=True)

        return qs
```

## SoftDeleteQuerySet

Para models com soft delete (campo `deleted_at`). Filtra deletados automaticamente.

```python
# Por padrao, registros deletados sao EXCLUIDOS
users = await User.objects.using(db).all()              # Apenas ativos

# Incluir deletados
all_users = await User.objects.using(db).with_deleted().all()

# Apenas deletados (lixeira)
trash = await User.objects.using(db).only_deleted().all()

# Apenas ativos (explicito, mesmo comportamento padrao)
active = await User.objects.using(db).active().all()
```

Veja [23 Soft Delete](23-soft-delete.md) para mais detalhes.

## TenantQuerySet

Para models multi-tenant. Filtra pelo tenant do contexto automaticamente.

```python
# Filtra pelo tenant do contexto atual (request)
items = await Item.objects.using(db).for_tenant().all()

# Filtra por tenant especifico
items = await Item.objects.using(db).for_tenant(tenant_id=workspace_id).all()

# Combina com soft delete
items = await Item.objects.using(db)\
    .for_tenant()\
    .with_deleted()\
    .all()
```

Veja [21 Multi-Tenancy](21-tenancy.md) para mais detalhes.

## Excecoes

```python
from core.querysets import DoesNotExist, MultipleObjectsReturned

# DoesNotExist - get() nao encontrou nenhum registro
try:
    user = await User.objects.using(db).get(id=999)
except DoesNotExist:
    raise HTTPException(404, "Usuario nao encontrado")

# MultipleObjectsReturned - get() encontrou mais de um
try:
    user = await User.objects.using(db).filter(role="admin").get()
except MultipleObjectsReturned:
    # Use first() em vez de get() para queries que podem retornar multiplos
    pass
```

---

Proximo: [Routing](15-routing.md) - Sistema de rotas automaticas.
