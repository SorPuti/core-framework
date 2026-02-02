# QuerySets

API fluente para queries de banco de dados. Inspirada no Django ORM, mas assincrona e com tipagem forte.

## Conceito

QuerySets sao objetos que representam queries ao banco de dados. Sao **lazy** - a query so e executada quando voce chama um metodo de execucao (`all()`, `first()`, `get()`, etc).

## Uso Basico

```python
from src.apps.users.models import User

# Buscar todos os registros
# all() executa SELECT * FROM users
users = await User.objects.using(db).all()

# Buscar por ID
# get() levanta excecao se nao encontrar ou encontrar mais de um
user = await User.objects.using(db).get(id=1)

# Filtrar registros
# filter() adiciona WHERE a query
active_users = await User.objects.using(db).filter(is_active=True).all()

# Primeiro resultado ou None
# first() retorna None se nao encontrar (diferente de get())
user = await User.objects.using(db).filter(email="test@example.com").first()
```

**Importante**: `using(db)` e obrigatorio. Passa a sessao de banco para o QuerySet. Sem isso, a query nao pode ser executada.

## Metodos de Filtragem

| Metodo | Comportamento |
|--------|---------------|
| `filter(**kwargs)` | Adiciona condicoes WHERE (AND) |
| `exclude(**kwargs)` | Adiciona condicoes WHERE NOT |
| `get(**kwargs)` | Retorna exatamente 1 registro ou levanta excecao |
| `first()` | Retorna primeiro registro ou None |
| `last()` | Retorna ultimo registro ou None |

## Metodos de Ordenacao e Paginacao

| Metodo | Comportamento |
|--------|---------------|
| `order_by(*fields)` | Adiciona ORDER BY |
| `limit(n)` | Adiciona LIMIT |
| `offset(n)` | Adiciona OFFSET |

## Metodos de Agregacao

| Metodo | Comportamento |
|--------|---------------|
| `count()` | Retorna COUNT(*) |
| `exists()` | Retorna True se existe pelo menos 1 registro |

## Metodos de Execucao

| Metodo | Retorno |
|--------|---------|
| `all()` | Lista de instancias do model |
| `values(*fields)` | Lista de dicts com campos especificados |
| `values_list(*fields)` | Lista de tuplas |

## Lookups (Operadores de Comparacao)

Lookups sao sufixos adicionados ao nome do campo para especificar o tipo de comparacao.

```python
# Igualdade (padrao quando nao especifica lookup)
User.objects.filter(name="John")
User.objects.filter(name__exact="John")  # Equivalente

# Case insensitive
User.objects.filter(name__iexact="john")  # Encontra "John", "JOHN", "john"

# Contem substring
User.objects.filter(name__contains="oh")      # Case sensitive
User.objects.filter(name__icontains="oh")     # Case insensitive

# Comeca/termina com
User.objects.filter(email__startswith="admin")
User.objects.filter(email__endswith="@gmail.com")

# Comparacao numerica
User.objects.filter(age__gt=18)   # age > 18
User.objects.filter(age__gte=18)  # age >= 18
User.objects.filter(age__lt=65)   # age < 65
User.objects.filter(age__lte=65)  # age <= 65

# Lista de valores (IN)
User.objects.filter(role__in=["admin", "moderator"])

# Null check
User.objects.filter(deleted_at__isnull=True)   # IS NULL
User.objects.filter(deleted_at__isnull=False)  # IS NOT NULL

# Range (BETWEEN)
User.objects.filter(age__range=(18, 65))  # age BETWEEN 18 AND 65
```

## Encadeamento

Metodos retornam novo QuerySet, permitindo encadeamento. A query so e executada no final.

```python
# Cada metodo retorna novo QuerySet
# A query SQL e construida incrementalmente
# Execucao acontece apenas em all()
users = await User.objects.using(db)\
    .filter(is_active=True)\       # WHERE is_active = true
    .exclude(role="admin")\        # AND NOT role = 'admin'
    .order_by("-created_at")\      # ORDER BY created_at DESC
    .limit(10)\                    # LIMIT 10
    .all()                         # Executa!
```

**Lazy evaluation**: Ate chamar `all()`, `first()`, `get()`, `count()` ou `exists()`, nenhuma query e enviada ao banco.

## Ordenacao

```python
# Ascendente (padrao)
users = await User.objects.using(db).order_by("name").all()

# Descendente (prefixo -)
users = await User.objects.using(db).order_by("-created_at").all()

# Multiplos campos - ordena pelo primeiro, desempata pelo segundo
users = await User.objects.using(db).order_by("role", "-created_at").all()
```

## Paginacao

```python
page_size = 10
page_number = 3  # Paginas comecam em 1

users = await User.objects.using(db)\
    .order_by("id")\  # Ordenacao e importante para paginacao consistente
    .limit(page_size)\
    .offset((page_number - 1) * page_size)\
    .all()
```

**Nota**: Sem `order_by()`, a ordem dos resultados nao e garantida, tornando paginacao inconsistente.

## get() vs first()

```python
# get() - para quando voce ESPERA exatamente 1 resultado
# Levanta DoesNotExist se 0 resultados
# Levanta MultipleObjectsReturned se >1 resultados
try:
    user = await User.objects.using(db).get(id=1)
except DoesNotExist:
    # ID nao existe
    print("Usuario nao encontrado")
except MultipleObjectsReturned:
    # Nao deveria acontecer com primary key
    print("Multiplos usuarios encontrados")

# first() - para quando 0 resultados e aceitavel
# Retorna None se nao encontrar
# Nunca levanta excecao por quantidade
user = await User.objects.using(db).filter(email="test@example.com").first()
if user is None:
    print("Usuario nao encontrado")
```

**Quando usar cada um**:
- `get()`: Busca por primary key ou campo unique
- `first()`: Busca por campos que podem ter 0 ou mais resultados

## values() e values_list()

Para quando voce nao precisa de instancias completas do model.

```python
# values() retorna lista de dicts
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values("id", "email")
# [{"id": 1, "email": "a@b.com"}, {"id": 2, "email": "c@d.com"}]

# values_list() retorna lista de tuplas
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("id", "email")
# [(1, "a@b.com"), (2, "c@d.com")]

# flat=True para lista simples (apenas 1 campo)
emails = await User.objects.using(db)\
    .filter(is_active=True)\
    .values_list("email", flat=True)
# ["a@b.com", "c@d.com"]
```

**Performance**: `values()` e `values_list()` sao mais eficientes que `all()` quando voce nao precisa de todos os campos.

## Customizar QuerySet no ViewSet

Override `get_queryset()` para aplicar filtros globais.

```python
class UserViewSet(ModelViewSet):
    model = User
    
    def get_queryset(self, db):
        """
        Retorna QuerySet base para todas as operacoes.
        
        Chamado em list(), retrieve(), update(), destroy().
        Filtros aqui afetam TODAS as operacoes do ViewSet.
        """
        qs = super().get_queryset(db)
        user = self.request.state.user
        
        # Usuarios nao-admin so veem registros ativos
        # Admins veem todos
        if not user or not user.is_admin:
            return qs.filter(is_active=True)
        
        return qs
```

**Cuidado**: Filtros em `get_queryset()` afetam `retrieve()` tambem. Um usuario nao conseguira acessar um registro mesmo conhecendo o ID se o filtro excluir.

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

**Trade-off**: Usar SQLAlchemy diretamente e mais poderoso, mas perde a sintaxe simplificada dos lookups.

---

Proximo: [Routing](15-routing.md) - Sistema de rotas automaticas.
