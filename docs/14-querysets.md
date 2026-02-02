# QuerySets

API fluente para queries de banco de dados estilo Django.

## Uso Basico

```python
from src.apps.users.models import User

# Buscar todos
users = await User.objects.using(db).all()

# Buscar um
user = await User.objects.using(db).get(id=1)

# Filtrar
active_users = await User.objects.using(db).filter(is_active=True).all()

# Primeiro resultado
user = await User.objects.using(db).filter(email="test@example.com").first()
```

## Metodos Disponiveis

### Filtragem

| Metodo | Descricao |
|--------|-----------|
| `filter(**kwargs)` | Filtra registros |
| `exclude(**kwargs)` | Exclui registros |
| `get(**kwargs)` | Busca um registro (erro se 0 ou >1) |
| `first()` | Primeiro resultado ou None |
| `last()` | Ultimo resultado ou None |

### Ordenacao

| Metodo | Descricao |
|--------|-----------|
| `order_by(*fields)` | Ordena resultados |

### Paginacao

| Metodo | Descricao |
|--------|-----------|
| `limit(n)` | Limita quantidade |
| `offset(n)` | Pula registros |

### Agregacao

| Metodo | Descricao |
|--------|-----------|
| `count()` | Conta registros |
| `exists()` | Verifica se existe |

### Execucao

| Metodo | Descricao |
|--------|-----------|
| `all()` | Retorna lista |
| `values(*fields)` | Retorna dicts |
| `values_list(*fields)` | Retorna tuplas |

## Lookups (Operadores)

```python
# Igualdade (padrao)
User.objects.filter(name="John")
User.objects.filter(name__exact="John")

# Case insensitive
User.objects.filter(name__iexact="john")

# Contem
User.objects.filter(name__contains="oh")
User.objects.filter(name__icontains="oh")  # case insensitive

# Comeca/termina com
User.objects.filter(email__startswith="admin")
User.objects.filter(email__endswith="@gmail.com")

# Comparacao
User.objects.filter(age__gt=18)   # maior que
User.objects.filter(age__gte=18)  # maior ou igual
User.objects.filter(age__lt=65)   # menor que
User.objects.filter(age__lte=65)  # menor ou igual

# In
User.objects.filter(role__in=["admin", "moderator"])

# Null
User.objects.filter(deleted_at__isnull=True)

# Range
User.objects.filter(age__range=(18, 65))
```

## Encadeamento

```python
# Queries sao lazy - so executam quando necessario
users = await User.objects.using(db)\
    .filter(is_active=True)\
    .exclude(role="admin")\
    .order_by("-created_at")\
    .limit(10)\
    .all()
```

## Ordenacao

```python
# Ascendente
users = await User.objects.using(db).order_by("name").all()

# Descendente (prefixo -)
users = await User.objects.using(db).order_by("-created_at").all()

# Multiplos campos
users = await User.objects.using(db).order_by("role", "-created_at").all()
```

## Paginacao

```python
# Pagina 1 (primeiros 10)
page1 = await User.objects.using(db).limit(10).offset(0).all()

# Pagina 2
page2 = await User.objects.using(db).limit(10).offset(10).all()

# Pagina N
page_size = 10
page_number = 3
users = await User.objects.using(db)\
    .limit(page_size)\
    .offset((page_number - 1) * page_size)\
    .all()
```

## Agregacao

```python
# Contar
total = await User.objects.using(db).filter(is_active=True).count()

# Verificar existencia
exists = await User.objects.using(db).filter(email="test@example.com").exists()

if exists:
    print("Usuario existe")
```

## Get vs First

```python
# get() - levanta erro se nao encontrar ou encontrar mais de um
try:
    user = await User.objects.using(db).get(id=1)
except DoesNotExist:
    print("Usuario nao encontrado")
except MultipleObjectsReturned:
    print("Multiplos usuarios encontrados")

# first() - retorna None se nao encontrar
user = await User.objects.using(db).filter(email="test@example.com").first()
if user is None:
    print("Usuario nao encontrado")
```

## Values e Values List

```python
# Retorna lista de dicts
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values("id", "email")
# [{"id": 1, "email": "a@b.com"}, {"id": 2, "email": "c@d.com"}]

# Retorna lista de tuplas
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("id", "email")
# [(1, "a@b.com"), (2, "c@d.com")]

# Flat (apenas um campo)
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("email", flat=True)
# ["a@b.com", "c@d.com"]
```

## No ViewSet

```python
class UserViewSet(ModelViewSet):
    model = User
    
    def get_queryset(self, db):
        """Customiza queryset base."""
        qs = super().get_queryset(db)
        user = self.request.state.user
        
        # Admin ve todos, usuario comum ve apenas ativos
        if not user or not user.is_admin:
            return qs.filter(is_active=True)
        
        return qs
```

## Queries Complexas

```python
from sqlalchemy import or_, and_

# OR
users = await User.objects.using(db).filter(
    or_(
        User.role == "admin",
        User.role == "moderator",
    )
).all()

# AND explicito
users = await User.objects.using(db).filter(
    and_(
        User.is_active == True,
        User.role == "admin",
    )
).all()
```

## Resumo

1. Use `Model.objects.using(db)` para iniciar query
2. Encadeie metodos: `filter()`, `exclude()`, `order_by()`, `limit()`
3. Execute com `all()`, `first()`, `get()`, `count()`, `exists()`
4. Use lookups para operadores: `field__gt`, `field__contains`, etc
5. Queries sao lazy - so executam quando voce chama metodo de execucao

Next: [Routing](15-routing.md)
